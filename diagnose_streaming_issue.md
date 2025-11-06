# LangGraph 流式输出问题诊断

## 基线测试结果 ✅

✅ **OpenAI API 本身支持流式输出**
- 测试脚本：`test_openai_stream_baseline.py`
- 结果：模型端确实在逐 token 推送（流式输出正常）
- 结论：问题在 LangGraph/服务端实现

## 问题定位

### 当前实现的问题

在 `src/graph/nodes.py` 中，`reporter_node` 和 `simple_researcher_node` 的实现是：

```python
response_content = ""
for chunk in llm.stream(invoke_messages):
    if getattr(chunk, "content", None):
        response_content += chunk.content  # ❌ 先收集所有内容

return {
    "final_report": response_content,
    "messages": [AIMessage(content=response_content, name="reporter")],  # ❌ 一次性返回完整的 AIMessage
}
```

**问题**：节点内部先收集所有 chunk，然后一次性返回完整的 `AIMessage`，这样 LangGraph 的 `stream_mode="messages"` 就无法流式传递了。

### LangGraph 流式工作原理

1. LangGraph 使用 `astream(..., stream_mode=["messages", "updates"])` 来流式传输
2. 当节点返回 `AIMessageChunk` 时，会被自动流式传递
3. 当节点返回完整的 `AIMessage` 时，只会在节点执行完成后一次性传递

### 正确的做法

节点应该直接返回 `AIMessageChunk`，而不是先收集再返回完整的 `AIMessage`。

但是，LangGraph 的节点函数是同步或异步函数，不能直接 yield。所以需要：

1. **方案1（推荐）**：在节点中直接添加 `AIMessageChunk` 到 messages，而不是收集后返回完整消息
2. **方案2**：使用 LangGraph 的 `Runnable` 直接返回流式结果

## 修复方案

需要修改 `reporter_node` 和 `simple_researcher_node`，让每个 chunk 实时传递。

关键点：
- 不要在节点内部收集所有内容
- 应该让 `llm.stream()` 的每个 chunk 实时通过 LangGraph 的状态更新传递出去
- LangGraph 的 `stream_mode="messages"` 会自动捕获 `AIMessageChunk`

## 解决方案

### 方案 1：使用 RunnablePassthrough 让 LLM 直接流式输出（推荐）

在节点中，不要收集 chunk，而是直接返回 LLM 的流式结果。LangGraph 的 `stream_mode="messages"` 会自动捕获 `AIMessageChunk`。

修改 `reporter_node` 和 `simple_researcher_node`：

```python
def reporter_node(state: State, config: RunnableConfig):
    # ... 前面的代码不变 ...
    
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"])
    
    # ❌ 错误方式：收集所有 chunk
    # response_content = ""
    # for chunk in llm.stream(invoke_messages):
    #     response_content += chunk.content
    # return {"messages": [AIMessage(content=response_content, name="reporter")]}
    
    # ✅ 正确方式：让 LLM 的流式输出直接传递
    # 使用 Runnable 包装，让 LangGraph 自动流式传递
    from langchain_core.runnables import RunnableLambda
    
    def stream_llm(inputs):
        full_content = ""
        for chunk in llm.stream(invoke_messages):
            if hasattr(chunk, "content") and chunk.content:
                full_content += chunk.content
                yield chunk  # 实时 yield 每个 chunk
        # 最后返回完整内容用于状态更新
        return AIMessage(content=full_content, name="reporter")
    
    # 但节点函数不能 yield，所以需要另一种方式...
```

### 方案 2：修改节点返回 AIMessageChunk（需要实验）

让每个 chunk 都作为状态更新返回：

```python
# 注意：这个方案需要修改 LangGraph 的执行方式
# 可能需要在节点中使用异步生成器或其他机制
```

### 方案 3：在服务端处理流式（当前可行的方案）

保持节点实现不变，但在服务端的 `_stream_graph_events` 中，当检测到节点返回完整 `AIMessage` 时，尝试将其拆分为多个 `AIMessageChunk` 流式传递。

**但实际上，最根本的解决方案是：让节点直接返回 LLM 的流式结果，而不是收集后返回。**

## 推荐实现方式

根据 LangGraph 文档，正确的做法是：

1. **使用 `Runnable` 作为节点**：将 LLM 的 `stream()` 方法包装成 Runnable，让 LangGraph 自动处理流式输出
2. **或者修改节点逻辑**：不在节点内部收集所有内容，而是让每个 chunk 实时更新状态

由于 LangGraph 节点函数的设计限制，最实用的方案是：

**在服务端的 `_stream_graph_events` 中添加逻辑，检测到完整 `AIMessage` 时，模拟流式传递**

或者更根本的：

**修改节点，使用 LangChain 的 `Runnable` 机制，让 LLM 的流式输出直接传递给 LangGraph**

