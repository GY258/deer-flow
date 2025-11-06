# LangGraph 流式输出问题 - 完整排查报告

## ✅ 排查总结

### 第 0 步：基线对照 ✅

**测试脚本**：`test_openai_stream_baseline.py`

**结果**：
```
✅ 模型端确实在逐 token 推送（流式输出正常）
   总 token 数: 29
   首 token 延迟 (TTFB): 0.01s
   流式传输耗时: 0.31s
   → 如果 LangGraph 中不是流式的，问题在 LangGraph/服务端
```

**结论**：OpenAI API 和 SDK 工作正常，问题在 LangGraph/服务端实现。

---

### 第 1 步：LangGraph 层排查 ✅

**检查位置**：`src/server/app.py`

#### 检查项 1：服务端是否先收集再返回？

```python
# src/server/app.py 第 401-418 行
async for event in _stream_graph_events(...):
    if request_logger:
        _log_event_data(...)
    yield event  # ✅ 逐个 yield，正确！
```

**结论**：✅ 服务端没有先收集再返回的问题。

#### 检查项 2：使用了正确的流式方法？

```python
# src/server/app.py 第 276-280 行
async for agent, _, event_data in graph_instance.astream(  # ✅ 使用 astream
    workflow_input,
    config=workflow_config,
    stream_mode=["messages", "updates"],  # ✅ 正确的 stream_mode
    subgraphs=True,
):
```

**结论**：✅ 使用了正确的 `astream` 和 `stream_mode`。

---

### 第 2 步：节点层排查 ❌

**检查位置**：`src/graph/nodes.py`

#### 问题代码 1：`reporter_node`（第 336-359 行）

```python
def reporter_node(state: State, config: RunnableConfig):
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"])
    
    response_content = ""
    for chunk in llm.stream(invoke_messages):  # ❌ 节点消费了流
        if getattr(chunk, "content", None):
            response_content += chunk.content
    
    return {
        "final_report": response_content,
        "messages": [AIMessage(content=response_content, name="reporter")],  # ❌ 一次性返回
    }
```

#### 问题代码 2：`simple_researcher_node`（第 870-908 行）

```python
async def simple_researcher_node(state: State, config: RunnableConfig):
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"])
    
    response_content = ""
    try:
        for chunk in llm.stream(invoke_messages):  # ❌ 节点消费了流
            if getattr(chunk, "content", None):
                response_content += chunk.content
    except Exception as e:
        # ...
    
    return Command(
        update={
            "final_report": response_content,  # ❌ 一次性返回
        }
    )
```

**问题分析**：
1. 节点内部调用 `llm.stream()` 并用 for 循环消费了所有 chunk
2. LangGraph 的 `stream_mode="messages"` 无法捕获已被消费的 chunk
3. 节点最后一次性返回完整的 `AIMessage`
4. 结果：前端只能收到一次性返回的完整内容

**这就是问题的根本原因！**

---

## 💡 修复方案

### 方案 A：改用 invoke + 配置 streaming=True（推荐）

#### 步骤 1：修改 LLM 配置

```python
# 文件：src/llms/llm.py 第 101 行
def _create_llm_use_conf(llm_type: LLMType, conf: Dict[str, Any]) -> BaseChatModel:
    # ... 前面代码不变 ...
    
    if llm_type == "reasoning":
        merged_conf["api_base"] = merged_conf.pop("base_url", None)
        return ChatDeepSeek(**merged_conf)
    else:
        # ✅ 添加 streaming=True
        return ChatOpenAI(**merged_conf, streaming=True)
```

#### 步骤 2：修改 reporter_node

```python
# 文件：src/graph/nodes.py 第 336-359 行
def reporter_node(state: State, config: RunnableConfig):
    """Reporter node that write a final report."""
    logger.info("Reporter write final report")
    configurable = Configuration.from_runnable_config(config)
    # ... 前面的准备工作不变 ...
    
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"])
    
    try:
        logger.info("Reporter开始生成报告...")
        # ✅ 改用 invoke，不消费流
        response = llm.invoke(invoke_messages)
        response_content = response.content if hasattr(response, 'content') else str(response)
        
        if not response_content:
            logger.warning("Reporter内容为空")
            response_content = "抱歉，生成报告失败。"
            
    except Exception as e:
        logger.error(f"Reporter LLM调用异常: {e}", exc_info=True)
        response_content = f"抱歉，生成报告时出现错误: {str(e)}"
    
    logger.info(f"reporter response length: {len(response_content)}")
    
    return {
        "final_report": response_content,
        "messages": [AIMessage(content=response_content, name="reporter")],
    }
```

#### 步骤 3：修改 simple_researcher_node

```python
# 文件：src/graph/nodes.py 第 870-908 行
async def simple_researcher_node(state: State, config: RunnableConfig) -> Command[Literal["__end__"]]:
    """餐饮智能助手节点"""
    logger.info("餐饮智能助手节点运行中")
    configurable = Configuration.from_runnable_config(config)
    
    # ... 前面的 BM25 搜索等准备工作不变 ...
    
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"])
    logger.info(f"开始生成专业解答，LLM: {AGENT_LLM_MAP['reporter']}")
    
    response_content = ""
    try:
        # ✅ 改用 invoke，不消费流
        response = llm.invoke(invoke_messages)
        response_content = response.content if hasattr(response, 'content') else str(response)
        
        if not response_content:
            logger.warning("流式内容为空")
            response_content = "抱歉，本次回答为空。"
            
    except Exception as e:
        logger.error(f"LLM 调用异常: {e}", exc_info=True)
        response_content = f"抱歉，生成解答时出现错误: {e}"
    
    logger.info(f"simple_researcher 响应长度: {len(response_content)}")
    
    return Command(
        update={
            "final_report": response_content,
        }
    )
```

---

## 🧪 测试验证

### 1. 基线测试（应该仍然通过）

```bash
python3 test_openai_stream_baseline.py
```

### 2. API 流式测试

```bash
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "count to 10 slowly"}],
    "enable_simple_research": true
  }' \
  --no-buffer
```

观察输出是否逐 token 返回（应该看到 `data: {...}` 一条条出现）。

### 3. 前端测试

在 Web UI 中提问，观察是否有"打字机"效果。

---

## 📊 预期效果

修复后：
- ✅ 首 token 延迟（TTFB）< 1 秒
- ✅ 逐个 token 显示内容
- ✅ 前端看到流畅的"打字机"效果
- ✅ 用户体验提升

---

## 📁 相关文件

- ✅ **基线测试脚本**：`test_openai_stream_baseline.py`
- 📋 **诊断文档**：`diagnose_streaming_issue.md`
- 📋 **修复指南**：`STREAMING_FIX_GUIDE.md`
- 📋 **对比测试**：`test_streaming_fix_comparison.md`
- 📋 **本报告**：`STREAMING_DIAGNOSIS_FINAL.md`

---

## 🎯 下一步行动

1. **立即实施修复**：按照上述步骤修改 3 个文件
2. **测试验证**：运行基线测试和 API 测试
3. **前端验证**：在 Web UI 中测试用户体验

需要我帮你实施修复吗？


