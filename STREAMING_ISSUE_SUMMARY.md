# LangGraph 流式输出问题排查总结

## ✅ 基线测试结果

已创建并运行 `test_openai_stream_baseline.py`，测试结果：

- ✅ **OpenAI API 本身支持流式输出**
- 首 token 延迟 (TTFB): 0.01s
- 流式传输正常，逐 token 推送

**结论**：模型端和 SDK 正常，问题在 LangGraph/服务端实现。

## 🔍 问题定位

### 问题代码位置

在 `src/graph/nodes.py` 中的以下节点存在问题：

1. **`reporter_node`** (第 336-359 行)
2. **`simple_researcher_node`** (第 870-908 行)

### 问题代码模式

```python
# ❌ 当前实现（错误）
response_content = ""
for chunk in llm.stream(invoke_messages):  # LLM 本身是流式的
    if getattr(chunk, "content", None):
        response_content += chunk.content  # 先收集所有内容

return {
    "final_report": response_content,
    "messages": [AIMessage(content=response_content, name="reporter")],  # 一次性返回完整消息
}
```

**问题**：
- 节点内部先收集所有 chunk
- 然后一次性返回完整的 `AIMessage`
- LangGraph 的 `stream_mode="messages"` 只能捕获到完整的 `AIMessage`，无法流式传递

## 💡 解决方案

### 方案 1：使用 Runnable 包装 LLM（推荐）

将 LLM 的流式调用直接作为节点，让 LangGraph 自动处理流式输出：

```python
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import AIMessageChunk

def reporter_node(state: State, config: RunnableConfig):
    # ... 前面的代码不变 ...
    
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"])
    
    # 创建一个 Runnable，让 LangGraph 自动流式传递
    def stream_llm_wrapper(inputs):
        """包装 LLM stream，实时 yield 每个 chunk"""
        full_content = ""
        for chunk in llm.stream(invoke_messages):
            if hasattr(chunk, "content") and chunk.content:
                full_content += chunk.content
                # 实时 yield chunk，让 LangGraph 捕获
                yield chunk
        
        # 返回完整内容用于状态更新（可选）
        return full_content
    
    # 使用 Runnable 作为节点
    stream_runnable = RunnableLambda(stream_llm_wrapper)
    
    # 执行并收集结果
    full_content = ""
    for chunk in stream_runnable.stream({}):
        full_content += chunk if isinstance(chunk, str) else getattr(chunk, "content", "")
    
    return {
        "final_report": full_content,
        "messages": [AIMessage(content=full_content, name="reporter")],
    }
```

**注意**：这个方案仍需要节点收集内容用于状态更新，但可以让 LangGraph 捕获到流式的 chunk。

### 方案 2：在服务端拆分完整消息（临时方案）

在 `src/server/app.py` 的 `_process_message_chunk` 函数中，检测到完整 `AIMessage` 时，尝试拆分并流式传递：

```python
async def _process_message_chunk(message_chunk, message_metadata, thread_id, agent):
    """Process a single message chunk and yield appropriate events."""
    # ... 现有代码 ...
    
    elif isinstance(message_chunk, AIMessage):
        # 如果收到完整的 AIMessage，尝试拆分并流式传递
        content = message_chunk.content if hasattr(message_chunk, 'content') else ""
        if content and len(content) > 10:  # 只在内容较长时拆分
            # 按字符或词拆分，模拟流式输出
            chunk_size = 5  # 每次传递的字符数
            for i in range(0, len(content), chunk_size):
                chunk_content = content[i:i+chunk_size]
                chunk_msg = AIMessageChunk(
                    content=chunk_content,
                    name=message_chunk.name if hasattr(message_chunk, 'name') else None
                )
                event_stream_message = _create_event_stream_message(
                    chunk_msg, message_metadata, thread_id, agent_name
                )
                yield _make_event("message_chunk", event_stream_message)
                await asyncio.sleep(0.01)  # 模拟流式延迟
            
            # 最后发送完成事件
            event_stream_message = _create_event_stream_message(
                message_chunk, message_metadata, thread_id, agent_name
            )
            event_stream_message["finish_reason"] = "stop"
            yield _make_event("message_chunk", event_stream_message)
        else:
            # 内容较短，直接传递
            event_stream_message["finish_reason"] = "stop"
            yield _make_event("message_chunk", event_stream_message)
```

### 方案 3：修改节点逻辑，实时更新状态（复杂但最正确）

修改节点，让每个 chunk 都实时更新到状态中。但这需要修改 LangGraph 的执行机制，比较复杂。

## 📝 下一步行动

1. **立即行动**：修改 `reporter_node` 和 `simple_researcher_node`，使用方案 1 或方案 2
2. **测试验证**：运行测试确保流式输出正常工作
3. **性能优化**：根据需要调整流式输出的粒度

## 🧪 测试工具

已创建的测试脚本：

1. **`test_openai_stream_baseline.py`** - 基线测试，验证 OpenAI API 流式输出
2. **`test_langgraph_stream.py`** - 测试 LangGraph 中的流式输出（需要安装依赖后运行）

## 参考资料

- [LangGraph 流式输出文档](https://github.langchain.ac.cn/langgraph/how-tos/streaming/)
- [LangChain Runnable 文档](https://python.langchain.com/docs/expression_language/)


