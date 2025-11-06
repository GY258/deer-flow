# 流式输出问题对比测试

## 问题重现

### 当前实现（有问题）

```python
def reporter_node(state: State, config: RunnableConfig):
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"])
    
    # ❌ 问题：在节点中消费流
    response_content = ""
    for chunk in llm.stream(invoke_messages):
        if getattr(chunk, "content", None):
            response_content += chunk.content  # 节点消费了所有 chunk
    
    # 节点一次性返回完整消息
    return {
        "messages": [AIMessage(content=response_content, name="reporter")]
    }
```

**结果**：
- LangGraph 的 `stream_mode="messages"` 无法捕获 chunk（已被节点消费）
- 只能捕获到节点返回的完整 `AIMessage`
- 前端看到的是一次性返回

### 修复方案 1：使用 invoke

```python
def reporter_node(state: State, config: RunnableConfig):
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"])
    
    # ✅ 修复：直接 invoke，不消费流
    response = llm.invoke(invoke_messages)
    
    return {
        "messages": [response]  # 返回完整消息用于状态更新
    }
```

**预期**：
- LangGraph 可以在调用 `llm.invoke()` 时捕获底层的流式输出
- 前端应该能看到流式输出

**但是**：这个方案需要验证！因为 `invoke` 本身不是流式方法。

### 修复方案 2：在 LLM 配置中启用流式

```python
# 在 src/llms/llm.py 中
return ChatOpenAI(
    **merged_conf,
    streaming=True  # ✅ 显式启用流式
)
```

然后在节点中使用 `invoke`：

```python
def reporter_node(state: State, config: RunnableConfig):
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"])
    response = llm.invoke(invoke_messages)  # invoke 会自动流式输出
    return {"messages": [response]}
```

### 修复方案 3：让节点返回 Runnable（需要修改图结构）

不使用函数节点，而是直接使用 LLM 作为节点：

```python
# 在构建图时
from langchain_core.runnables import RunnableLambda

def create_graph():
    graph = StateGraph(State)
    
    # 使用 RunnableLambda 包装
    llm = get_llm_by_type("reporter")
    
    def prepare_messages(state):
        # 准备消息
        return invoke_messages
    
    reporter_chain = RunnableLambda(prepare_messages) | llm
    
    graph.add_node("reporter", reporter_chain)
    # ...
```

这样 LangGraph 可以直接捕获 LLM 的流式输出。

## 推荐方案

**方案 2** 最简单实用：
1. 在 `src/llms/llm.py` 中为 ChatOpenAI 添加 `streaming=True`
2. 在节点中改用 `llm.invoke()` 而不是 `llm.stream()`
3. LangGraph 会自动捕获流式输出

## 实施步骤

1. 修改 `src/llms/llm.py`：添加 `streaming=True`
2. 修改 `src/graph/nodes.py`：
   - `reporter_node`：改用 `invoke`
   - `simple_researcher_node`：改用 `invoke`
3. 测试验证

## 测试方法

```bash
# 1. 基线测试（应该仍然通过）
python3 test_openai_stream_baseline.py

# 2. API 测试
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"count to 10"}]}'

# 观察输出是否逐 token 返回
```


