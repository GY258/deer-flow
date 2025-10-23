#!/usr/bin/env python3
"""
测试脚本：测试 simple_researcher_node 功能
用于验证餐饮智能助手节点的功能是否正常
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from langchain_core.runnables import RunnableConfig
from src.graph.nodes import simple_researcher_node
from src.graph.types import State
from src.config.configuration import Configuration

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def test_simple_researcher_node():
    """测试 simple_researcher_node 函数"""
    
    # 测试用例列表
    test_cases = [
        {
            "name": "测试1：查询菜品制作方法",
            "query": "汤包怎么做？",
            "locale": "zh-CN",
        },
        {
            "name": "测试2：查询食材用量",
            "query": "南京汤包需要多少盐？",
            "locale": "zh-CN",
        },
        {
            "name": "测试3：查询出品标准",
            "query": "汤包的出品标准是什么？",
            "locale": "zh-CN",
        },
        {
            "name": "测试4：查询不存在的内容",
            "query": "披萨怎么做？",
            "locale": "zh-CN",
        },
    ]
    
    print("=" * 80)
    print("开始测试 simple_researcher_node 功能")
    print("=" * 80)
    print()
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'=' * 80}")
        print(f"测试用例 {i}/{len(test_cases)}: {test_case['name']}")
        print(f"{'=' * 80}")
        print(f"查询: {test_case['query']}")
        print(f"语言: {test_case['locale']}")
        print("-" * 80)
        
        # 构造 State
        state: State = {
            "research_topic": test_case["query"],
            "locale": test_case["locale"],
            "messages": [],
        }
        
        # 构造 RunnableConfig
        config = RunnableConfig(
            configurable={
                "thread_id": f"test_{i}",
                "max_search_results": 5,
            }
        )
        
        try:
            # 调用 simple_researcher_node
            logger.info(f"开始执行测试用例 {i}...")
            result = await simple_researcher_node(state, config)
            
            # 打印结果
            print("\n✅ 测试执行成功")
            print(f"\n返回结果类型: {type(result)}")
            print(f"返回结果: {result}")
            
            # 如果返回的是 Command 对象，提取更新的状态
            if hasattr(result, 'update'):
                updates = result.update
                print(f"\n状态更新:")
                for key, value in updates.items():
                    if key == "messages":
                        print(f"  - {key}: {len(value)} 条消息")
                        for msg in value:
                            print(f"    * {msg.name if hasattr(msg, 'name') else 'unknown'}: {msg.content[:200]}...")
                    else:
                        print(f"  - {key}: {value}")
            
        except Exception as e:
            print(f"\n❌ 测试执行失败")
            print(f"错误类型: {type(e).__name__}")
            print(f"错误信息: {str(e)}")
            logger.error(f"测试用例 {i} 失败", exc_info=True)
        
        print()
    
    print("=" * 80)
    print("所有测试用例执行完毕")
    print("=" * 80)


async def test_simple_graph():
    """测试完整的 simple_graph 流程"""
    from src.graph.builder import build_simple_graph_with_memory
    
    print("\n" + "=" * 80)
    print("测试完整的 simple_graph 流程")
    print("=" * 80)
    
    # 构建图
    graph = build_simple_graph_with_memory()
    
    # 测试查询
    query = "汤包怎么做？"
    thread_id = "test_graph_001"
    
    print(f"\n查询: {query}")
    print(f"Thread ID: {thread_id}")
    print("-" * 80)
    
    # 构造初始状态
    initial_state: State = {
        "research_topic": query,
        "locale": "zh-CN",
        "messages": [],
    }
    
    # 配置
    config = RunnableConfig(
        configurable={
            "thread_id": thread_id,
            "max_search_results": 5,
        }
    )
    
    try:
        print("\n开始执行图流程...")
        
        # 流式执行图
        async for event in graph.astream(initial_state, config, stream_mode="values"):
            print(f"\n📦 收到事件:")
            if "messages" in event:
                messages = event["messages"]
                if messages:
                    last_msg = messages[-1]
                    print(f"  消息类型: {type(last_msg).__name__}")
                    if hasattr(last_msg, 'name'):
                        print(f"  消息来源: {last_msg.name}")
                    print(f"  消息内容: {last_msg.content[:200]}...")
        
        print("\n✅ 图流程执行成功")
        
    except Exception as e:
        print(f"\n❌ 图流程执行失败")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        logger.error("图流程执行失败", exc_info=True)


async def test_api_endpoint():
    """测试后端 API 端点"""
    import httpx
    
    print("\n" + "=" * 80)
    print("测试后端 API 端点")
    print("=" * 80)
    
    # API 地址
    api_url = "http://localhost:8000/api/chat/stream"
    
    # 测试请求
    request_data = {
        "messages": [
            {
                "role": "user",
                "content": "汤包怎么做？"
            }
        ],
        "thread_id": "test_api_001",
        "enable_simple_research": True,
        "locale": "zh-CN",
    }
    
    print(f"\nAPI URL: {api_url}")
    print(f"请求数据: {request_data}")
    print("-" * 80)
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            print("\n发送请求...")
            
            async with client.stream("POST", api_url, json=request_data) as response:
                print(f"响应状态码: {response.status_code}")
                
                if response.status_code == 200:
                    print("\n✅ API 请求成功")
                    print("\n流式响应内容:")
                    print("-" * 80)
                    
                    async for line in response.aiter_lines():
                        if line.strip():
                            # 解析 SSE 格式
                            if line.startswith("data: "):
                                data = line[6:]  # 移除 "data: " 前缀
                                if data != "[DONE]":
                                    try:
                                        import json
                                        event_data = json.loads(data)
                                        print(f"📦 事件: {event_data.get('event', 'unknown')}")
                                        if 'data' in event_data:
                                            print(f"   数据: {str(event_data['data'])[:200]}...")
                                    except json.JSONDecodeError:
                                        print(f"   原始数据: {data[:200]}...")
                else:
                    print(f"\n❌ API 请求失败")
                    print(f"响应内容: {await response.aread()}")
                    
    except httpx.ConnectError:
        print("\n❌ 无法连接到后端服务")
        print("请确保后端服务正在运行: docker ps | grep deer-flow-backend")
    except Exception as e:
        print(f"\n❌ API 测试失败")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        logger.error("API 测试失败", exc_info=True)


async def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("DeerFlow Simple Researcher Node 测试脚本")
    print("=" * 80)
    
    # 选择测试模式
    print("\n请选择测试模式:")
    print("1. 测试 simple_researcher_node 函数 (单元测试)")
    print("2. 测试 simple_graph 流程 (集成测试)")
    print("3. 测试后端 API 端点 (端到端测试)")
    print("4. 运行所有测试")
    
    choice = input("\n请输入选项 (1-4, 默认为 1): ").strip() or "1"
    
    if choice == "1":
        await test_simple_researcher_node()
    elif choice == "2":
        await test_simple_graph()
    elif choice == "3":
        await test_api_endpoint()
    elif choice == "4":
        await test_simple_researcher_node()
        await test_simple_graph()
        await test_api_endpoint()
    else:
        print(f"无效的选项: {choice}")
        return
    
    print("\n测试完成！")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        logger.error("测试脚本执行失败", exc_info=True)
        sys.exit(1)

