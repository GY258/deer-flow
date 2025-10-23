#!/usr/bin/env python3
"""
快速测试脚本：测试后端 simple_researcher API
直接测试 HTTP API 端点，无需依赖项目代码
"""

import asyncio
import json
import sys


async def test_api():
    """测试 API 端点"""
    try:
        import httpx
    except ImportError:
        print("❌ 需要安装 httpx: pip install httpx")
        sys.exit(1)
    
    print("=" * 80)
    print("DeerFlow Simple Researcher API 快速测试")
    print("=" * 80)
    print()
    
    # API 配置
    api_url = "http://localhost:8000/api/chat/stream"
    
    # 测试用例
    test_cases = [
        {
            "name": "测试1：查询汤包制作方法",
            "query": "汤包怎么做？",
        },
        {
            "name": "测试2：查询食材用量",
            "query": "南京汤包需要多少盐？",
        },
        {
            "name": "测试3：查询出品标准",
            "query": "汤包的出品标准是什么？",
        },
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'=' * 80}")
        print(f"{test_case['name']}")
        print(f"{'=' * 80}")
        print(f"查询: {test_case['query']}")
        print("-" * 80)
        
        # 构造请求
        request_data = {
            "messages": [
                {
                    "role": "user",
                    "content": test_case["query"]
                }
            ],
            "thread_id": f"test_{i:03d}",
            "enable_simple_research": True,
            "locale": "zh-CN",
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                print("\n🚀 发送请求...")
                
                async with client.stream("POST", api_url, json=request_data) as response:
                    if response.status_code != 200:
                        print(f"❌ 请求失败，状态码: {response.status_code}")
                        error_text = await response.aread()
                        print(f"错误信息: {error_text.decode()}")
                        continue
                    
                    print("✅ 请求成功，接收流式响应...\n")
                    
                    # 收集完整响应
                    full_response = []
                    event_count = 0
                    
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        
                        # 解析 SSE 格式
                        if line.startswith("data: "):
                            data = line[6:]  # 移除 "data: " 前缀
                            
                            if data == "[DONE]":
                                print("\n✅ 流式响应完成")
                                break
                            
                            try:
                                event_data = json.loads(data)
                                event_type = event_data.get("event", "unknown")
                                event_count += 1
                                
                                # 打印事件信息
                                if event_type == "metadata":
                                    print(f"📋 事件 {event_count}: 元数据")
                                elif event_type == "values":
                                    print(f"📦 事件 {event_count}: 状态更新")
                                    if "data" in event_data and "messages" in event_data["data"]:
                                        messages = event_data["data"]["messages"]
                                        if messages:
                                            last_msg = messages[-1]
                                            content = last_msg.get("content", "")
                                            msg_type = last_msg.get("type", "unknown")
                                            
                                            if content:
                                                print(f"   类型: {msg_type}")
                                                print(f"   内容: {content[:150]}...")
                                                full_response.append(content)
                                else:
                                    print(f"📨 事件 {event_count}: {event_type}")
                                
                            except json.JSONDecodeError as e:
                                print(f"⚠️  解析 JSON 失败: {e}")
                                print(f"   原始数据: {data[:200]}...")
                    
                    # 打印完整响应
                    if full_response:
                        print("\n" + "=" * 80)
                        print("完整响应内容:")
                        print("=" * 80)
                        for content in full_response:
                            print(content)
                            print()
                    
                    print(f"\n📊 统计: 共收到 {event_count} 个事件")
                    
        except httpx.ConnectError:
            print("\n❌ 无法连接到后端服务")
            print("请确保后端服务正在运行:")
            print("  docker ps | grep deer-flow-backend")
            print("如果服务未运行，请执行:")
            print("  cd /home/ubuntu/deer-flow && docker-compose up -d")
            break
        except Exception as e:
            print(f"\n❌ 测试失败")
            print(f"错误类型: {type(e).__name__}")
            print(f"错误信息: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("测试完成！")
    print("=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(test_api())
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试脚本执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

