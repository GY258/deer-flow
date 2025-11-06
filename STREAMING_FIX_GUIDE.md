# LangGraph 流式输出问题修复指南

## 🔍 问题确认

### ✅ 已验证正常的部分

1. **OpenAI API 层**：`test_openai_stream_baseline.py` 测试通过，模型端支持流式输出
2. **服务端代码**：`src/server/app.py` 中的 `_astream_workflow_generator` 正确使用 `yield event`，没有先收集

```python
# ✅ 服务端代码正确
async for event in _stream_graph_events(...):
    yield event  # 逐个 yield，不收集
```

3. **LangGraph 配置**：使用了正确的 `stream_mode=["messages", "updates"]`

```python
# ✅ LangGraph 配置正确
async for agent, _, event_data in graph_instance.astream(
    workflow_input,
    config=workflow_config,
    stream_mode=["messages", "updates"],  # ✅ 正确
    subgraphs=True,
):
```

### ❌ 问题所在：节点实现

在 `src/graph/nodes.py` 中：

```python
# ❌ 问题代码（第 336-359 行，reporter_node）
def reporter_node(state: State, config: RunnableConfig):
    # ...
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"])
    
    response_content = ""
    for chunk in llm.stream(invoke_messages):  # ❌ 节点内部消费了流
        if getattr(chunk, "content", None):
            response_content += chunk.content
    
    return {
        "final_report": response_content,
        "messages": [AIMessage(content=response_content, name="reporter")],  # ❌ 一次性返回
    }
```

**核心问题**：
- 节点内部的 `for chunk in llm.stream()` **消费掉了流**
- LangGraph 的 `stream_mode="messages"` 无法捕获已被消费的 chunk
- 节点最后一次性返回完整的 `AIMessage`，所以前端看到的是一次性返回

## 💡 解决方案

### 方案 1：使用 LangChain 的 Runnable 让节点支持流式（推荐）

关键：不在节点函数中手动调用 `llm.stream()`，而是让 LLM 作为 Runnable 直接绑定到节点。

但 LangGraph 的节点必须是函数，不能直接用 Runnable。解决方法是在节点中**不消费流**：

```python
def reporter_node(state: State, config: RunnableConfig):
    """修改后的 reporter_node"""
    # ... 前面的准备工作不变 ...
    
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"])
    
    # ✅ 方案：直接 invoke，让 LangGraph 在底层处理流式
    # LangGraph 会自动捕获 LLM 的流式输出
    response = llm.invoke(invoke_messages)
    
    return {
        "final_report": response.content,
        "messages": [response],  # 返回完整消息用于状态更新
    }
```

**注意**：虽然这里用的是 `invoke`，但如果 LLM 在内部配置了 `streaming=True`，LangGraph 仍然可以捕获流式输出。

### 方案 2：让 LLM 配置流式回调（需要验证）

在创建 LLM 时配置流式回调：

```python
# 在 src/llms/llm.py 中
llm = ChatOpenAI(
    model=model,
    streaming=True,  # ✅ 启用流式
    callbacks=[...]  # 配置回调
)
```

但这需要确认 LangGraph 能否捕获这些回调。

### 方案 3：修改节点使用异步生成器（复杂）

LangGraph 支持异步生成器节点，但需要修改节点签名和图的构建方式。

## 🎯 推荐修复步骤

### 步骤 1：修改 `simple_researcher_node`

```python
# 在 src/graph/nodes.py 第 870-908 行
async def simple_researcher_node(state: State, config: RunnableConfig) -> Command[Literal["__end__"]]:
    """餐饮智能助手节点（修复流式输出）"""
    logger.info("餐饮智能助手节点运行中")
    configurable = Configuration.from_runnable_config(config)
    
    # ... 前面的 BM25 搜索等准备工作不变 ...
    
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"])
    logger.info(f"开始流式生成专业解答，LLM: {AGENT_LLM_MAP['reporter']}")
    
    # ✅ 修复：直接 invoke，让 LangGraph 处理流式
    response = llm.invoke(invoke_messages)
    response_content = response.content if hasattr(response, 'content') else str(response)
    
    logger.info(f"simple_researcher 响应长度: {len(response_content)}")
    
    return Command(
        update={
            "final_report": response_content,
        }
    )
```

### 步骤 2：修改 `reporter_node`

```python
# 在 src/graph/nodes.py 第 336-359 行
def reporter_node(state: State, config: RunnableConfig):
    """Reporter node that write a final report."""
    logger.info("Reporter write final report")
    configurable = Configuration.from_runnable_config(config)
    
    # ... 前面的准备工作不变 ...
    
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"]) 
    
    # ✅ 修复：直接 invoke，让 LangGraph 处理流式
    try:
        logger.info("Reporter开始生成报告...")
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

### 步骤 3：确认 LLM 配置了流式

检查 `src/llms/llm.py`，确保 LLM 创建时启用了流式：

```python
# 在创建 ChatOpenAI 时添加
return ChatOpenAI(
    **merged_conf,
    streaming=True,  # ✅ 确保启用流式
)
```

## 🧪 测试验证

修改后，运行以下测试：

1. **基线测试**：`python3 test_openai_stream_baseline.py`（应该仍然通过）
2. **API 测试**：调用 `/api/chat/stream` 端点，观察是否逐 token 返回
3. **前端测试**：在 Web UI 中观察是否逐字显示

## 📊 预期效果

修改后，流式输出应该：
- 首 token 延迟（TTFB）< 1 秒
- 逐个 token 显示，而不是一次性显示全部内容
- 用户体验流畅，看到"打字机"效果

## ⚠️  注意事项

1. **不要在节点中使用 `llm.stream()`**：这会消费掉流，LangGraph 无法捕获
2. **使用 `llm.invoke()` 配合 `streaming=True`**：让 LangGraph 在底层处理流式
3. **测试验证**：修改后务必测试确认流式输出正常

## 🔗 参考资料

- [LangGraph 流式输出文档](https://github.langchain.ac.cn/langgraph/how-tos/streaming/)
- [LangChain 流式输出](https://python.langchain.com/docs/how_to/streaming/)


