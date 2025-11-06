#!/usr/bin/env python3
"""
测试 LangGraph 中的流式输出

对比：
1. 直接使用 llm.stream() 的输出
2. 通过 LangGraph 节点后的输出
"""

import asyncio
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from langchain_core.messages import HumanMessage, AIMessageChunk
from langgraph.graph import StateGraph, END
from langgraph.types import State
from src.llms.llm import get_llm_by_type

# 测试状态类型
class TestState(State):
    messages: list = []

def test_direct_llm_stream():
    """测试直接使用 llm.stream()"""
    print("=" * 60)
    print("测试 1：直接使用 llm.stream()")
    print("=" * 60)
    
    llm = get_llm_by_type("basic")
    messages = [HumanMessage(content="count to 10 slowly")]
    
    print("开始流式输出...")
    start_time = time.time()
    chunk_count = 0
    
    for chunk in llm.stream(messages):
        if hasattr(chunk, 'content') and chunk.content:
            print(chunk.content, end="", flush=True)
            chunk_count += 1
            time.sleep(0.01)  # 模拟观察延迟
    
    print()
    print(f"\n完成: {chunk_count} chunks, 耗时 {time.time() - start_time:.2f}s")
    print()


def test_node_with_stream_collection():
    """测试节点内部收集所有 chunk 然后返回（当前实现）"""
    print("=" * 60)
    print("测试 2：节点内部收集所有 chunk（当前实现方式）")
    print("=" * 60)
    
    def stream_collection_node(state: TestState):
        """模拟当前 reporter_node 的实现"""
        llm = get_llm_by_type("basic")
        messages = [HumanMessage(content="count to 10 slowly")]
        
        print("节点开始执行...")
        start_time = time.time()
        
        response_content = ""
        chunk_count = 0
        
        for chunk in llm.stream(messages):
            if hasattr(chunk, 'content') and chunk.content:
                response_content += chunk.content  # ❌ 先收集
                chunk_count += 1
        
        print(f"节点完成: 收集了 {chunk_count} chunks，耗时 {time.time() - start_time:.2f}s")
        print("节点返回完整消息...")
        
        return {
            "messages": [AIMessageChunk(content=response_content)]
        }
    
    # 构建图
    graph = StateGraph(TestState)
    graph.add_node("stream_collection", stream_collection_node)
    graph.set_entry_point("stream_collection")
    graph.add_edge("stream_collection", END)
    
    app = graph.compile()
    
    print("开始流式执行图...")
    start_time = time.time()
    
    async def run_test():
        chunk_count = 0
        async for chunk in app.astream(
            {"messages": []},
            stream_mode=["messages"]
        ):
            # 检查是否是消息 chunk
            for node_name, messages in chunk.items():
                for msg in messages:
                    if isinstance(msg, AIMessageChunk) and hasattr(msg, 'content'):
                        print(msg.content, end="", flush=True)
                        chunk_count += 1
        
        print()
        print(f"\n完成: 收到 {chunk_count} 个消息事件，耗时 {time.time() - start_time:.2f}s")
    
    asyncio.run(run_test())
    print()


def test_node_with_chunk_passthrough():
    """测试节点直接传递每个 chunk（理想实现）"""
    print("=" * 60)
    print("测试 3：节点直接传递每个 chunk（理想实现）")
    print("=" * 60)
    print("⚠️  注意：这个测试展示理想情况，但 LangGraph 节点函数不能 yield")
    print()
    
    def chunk_passthrough_node(state: TestState):
        """理想情况：每个 chunk 都实时传递"""
        llm = get_llm_by_type("basic")
        messages = [HumanMessage(content="count to 10 slowly")]
        
        print("节点开始执行（理想情况：应该每个 chunk 都实时传递）...")
        print("⚠️  但节点函数只能返回一次，所以这个测试会失败")
        print()
        
        # 实际实现中，我们需要其他方式来传递 chunk
        response_content = ""
        for chunk in llm.stream(messages):
            if hasattr(chunk, 'content') and chunk.content:
                response_content += chunk.content
        
        return {
            "messages": [AIMessageChunk(content=response_content)]
        }
    
    # 构建图
    graph = StateGraph(TestState)
    graph.add_node("chunk_passthrough", chunk_passthrough_node)
    graph.set_entry_point("chunk_passthrough")
    graph.add_edge("chunk_passthrough", END)
    
    app = graph.compile()
    
    print("开始流式执行图...")
    start_time = time.time()
    
    async def run_test():
        chunk_count = 0
        async for chunk in app.astream(
            {"messages": []},
            stream_mode=["messages"]
        ):
            for node_name, messages in chunk.items():
                for msg in messages:
                    if isinstance(msg, AIMessageChunk) and hasattr(msg, 'content'):
                        print(msg.content, end="", flush=True)
                        chunk_count += 1
        
        print()
        print(f"\n完成: 收到 {chunk_count} 个消息事件，耗时 {time.time() - start_time:.2f}s")
    
    asyncio.run(run_test())
    print()


if __name__ == "__main__":
    print("\n🔍 LangGraph 流式输出诊断测试\n")
    
    # 测试1：直接 LLM 流式
    test_direct_llm_stream()
    
    # 测试2：节点收集后返回
    test_node_with_stream_collection()
    
    # 测试3：理想情况
    test_node_with_chunk_passthrough()
    
    print("=" * 60)
    print("诊断总结：")
    print("1. 如果测试1是流式的，但测试2不是，说明问题在节点实现")
    print("2. LangGraph 节点函数不能 yield，所以需要特殊处理才能实现真正的流式")
    print("=" * 60)


