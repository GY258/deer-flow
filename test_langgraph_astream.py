#!/usr/bin/env python3
"""
测试 LangGraph 层的流式输出

目标：确认 graph.astream_events/graph.stream 是否逐步产出
"""

import asyncio
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from typing import TypedDict
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk
from langgraph.graph import StateGraph, END
from src.llms.llm import get_llm_by_type


class MessagesState(TypedDict):
    messages: list


def create_test_graph_with_collection():
    """创建一个测试图：节点内部收集所有 chunk（当前实现方式）"""
    
    def llm_node_with_collection(state: MessagesState):
        """模拟当前 reporter_node/simple_researcher_node 的实现"""
        print("  → [节点] 开始执行...")
        llm = get_llm_by_type("basic")
        messages = [HumanMessage(content="count to 5 quickly")]
        
        response_content = ""
        chunk_count = 0
        start = time.time()
        
        # ❌ 当前实现：先收集所有内容
        for chunk in llm.stream(messages):
            if hasattr(chunk, "content") and chunk.content:
                response_content += chunk.content
                chunk_count += 1
        
        elapsed = time.time() - start
        print(f"  → [节点] 收集完成：{chunk_count} chunks，耗时 {elapsed:.2f}s")
        print(f"  → [节点] 返回完整消息...")
        
        return {"messages": [AIMessage(content=response_content)]}
    
    graph = StateGraph(MessagesState)
    graph.add_node("llm_node", llm_node_with_collection)
    graph.set_entry_point("llm_node")
    graph.add_edge("llm_node", END)
    
    return graph.compile()


def create_test_graph_with_direct_llm():
    """创建一个测试图：节点直接返回 LLM（理想实现）"""
    
    def llm_node_direct(state: MessagesState):
        """直接使用 LLM，不收集"""
        print("  → [节点] 开始执行（直接使用 LLM）...")
        llm = get_llm_by_type("basic")
        messages = [HumanMessage(content="count to 5 quickly")]
        
        # 尝试直接调用 LLM（但节点函数只能返回一次）
        response = llm.invoke(messages)
        
        print(f"  → [节点] 返回消息...")
        return {"messages": [response]}
    
    graph = StateGraph(MessagesState)
    graph.add_node("llm_node", llm_node_direct)
    graph.set_entry_point("llm_node")
    graph.add_edge("llm_node", END)
    
    return graph.compile()


async def test_astream_events_v2(graph, test_name):
    """测试 astream_events (v2)"""
    print("=" * 70)
    print(f"测试：{test_name} - 使用 astream_events(version='v2')")
    print("=" * 70)
    
    start_time = time.time()
    event_count = 0
    message_chunk_count = 0
    
    async for ev in graph.astream_events(
        {"messages": []},
        version="v2"
    ):
        event_count += 1
        event_type = ev.get("event", "")
        
        # 只打印关键事件
        if event_type in ["on_chat_model_stream", "on_chat_model_end"]:
            elapsed = time.time() - start_time
            data = ev.get("data", {})
            
            if event_type == "on_chat_model_stream":
                chunk = data.get("chunk", {})
                content = getattr(chunk, "content", "") if hasattr(chunk, "content") else chunk.get("content", "")
                if content:
                    message_chunk_count += 1
                    print(f"  [{elapsed:.2f}s] on_chat_model_stream: {repr(content)}")
            elif event_type == "on_chat_model_end":
                print(f"  [{elapsed:.2f}s] on_chat_model_end")
    
    total_time = time.time() - start_time
    print()
    print(f"✅ 完成：总事件 {event_count} 个，消息 chunk {message_chunk_count} 个，耗时 {total_time:.2f}s")
    
    if message_chunk_count > 1:
        print(f"   → 流式输出正常（收到 {message_chunk_count} 个 chunk）")
    else:
        print(f"   → ⚠️  可能不是流式（只收到 {message_chunk_count} 个 chunk）")
    
    print()


async def test_astream_messages(graph, test_name):
    """测试 astream with stream_mode='messages'"""
    print("=" * 70)
    print(f"测试：{test_name} - 使用 astream(stream_mode='messages')")
    print("=" * 70)
    
    start_time = time.time()
    event_count = 0
    
    async for event in graph.astream(
        {"messages": []},
        stream_mode="messages"
    ):
        event_count += 1
        elapsed = time.time() - start_time
        
        # 打印收到的消息
        if isinstance(event, tuple) and len(event) == 2:
            msg, metadata = event
            msg_type = type(msg).__name__
            content = getattr(msg, "content", "") if hasattr(msg, "content") else ""
            if content:
                print(f"  [{elapsed:.2f}s] {msg_type}: {repr(content[:50])}")
    
    total_time = time.time() - start_time
    print()
    print(f"✅ 完成：总事件 {event_count} 个，耗时 {total_time:.2f}s")
    
    if event_count > 1:
        print(f"   → 流式输出可能正常（收到 {event_count} 个事件）")
    else:
        print(f"   → ⚠️  可能不是流式（只收到 {event_count} 个事件）")
    
    print()


async def test_astream_values(graph, test_name):
    """测试 astream with stream_mode='values'"""
    print("=" * 70)
    print(f"测试：{test_name} - 使用 astream(stream_mode='values')")
    print("=" * 70)
    
    start_time = time.time()
    event_count = 0
    
    async for state in graph.astream(
        {"messages": []},
        stream_mode="values"
    ):
        event_count += 1
        elapsed = time.time() - start_time
        
        messages = state.get("messages", [])
        print(f"  [{elapsed:.2f}s] State update: {len(messages)} messages")
    
    total_time = time.time() - start_time
    print()
    print(f"✅ 完成：总状态更新 {event_count} 次，耗时 {total_time:.2f}s")
    print(f"   → stream_mode='values' 通常不会流式传递 LLM chunks")
    print()


async def main():
    print("\n" + "=" * 70)
    print("LangGraph 层流式输出测试")
    print("=" * 70)
    print()
    
    # 测试1：当前实现方式（节点内部收集）
    graph1 = create_test_graph_with_collection()
    await test_astream_events_v2(graph1, "节点内部收集 chunk")
    await test_astream_messages(graph1, "节点内部收集 chunk")
    
    # 测试2：直接调用 LLM
    graph2 = create_test_graph_with_direct_llm()
    await test_astream_events_v2(graph2, "直接调用 LLM invoke")
    
    print("=" * 70)
    print("测试总结：")
    print("=" * 70)
    print("1. 如果 astream_events 能看到 on_chat_model_stream 事件，")
    print("   说明 LangGraph 层能捕获到流式 chunk")
    print()
    print("2. 如果看不到，说明节点内部的 llm.stream() 循环")
    print("   阻止了 LangGraph 捕获流式输出")
    print()
    print("3. 常见坑：在节点中 for chunk in llm.stream() 会消费掉流，")
    print("   导致 LangGraph 无法捕获 chunk")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())


