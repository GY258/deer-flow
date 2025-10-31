#!/usr/bin/env python3
"""
测试脚本：测试藕汤腥味问题
输入：今天店里的藕汤有点腥，这是什么原因怎么解决？
"""

import asyncio
import json
import logging
import httpx
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def test_api_endpoint():
    """测试后端 API 端点"""
    print("\n" + "=" * 80)
    print("测试 DeerFlow Simple Researcher API")
    print("=" * 80)
    
    # API 地址
    api_url = "http://localhost:8000/api/chat/stream"
    
    # 测试问题
    question = "今天店里的藕汤有点腥，这是什么原因怎么解决？"
    
    # 构造测试请求
    request_data = {
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ],
        "thread_id": f"test_lotus_soup_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "enable_simple_research": True,
        "locale": "zh-CN",
    }
    
    print(f"\nAPI URL: {api_url}")
    print(f"问题: {question}")
    print(f"Thread ID: {request_data['thread_id']}")
    print("-" * 80)
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            print("\n发送请求...")
            print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            async with client.stream("POST", api_url, json=request_data) as response:
                print(f"响应状态码: {response.status_code}")
                
                if response.status_code == 200:
                    print("\n✅ API 请求成功")
                    print("\n流式响应内容:")
                    print("-" * 80)
                    
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
                                event_count += 1
                                
                                # 检查是否有 content 字段（流式文本输出）
                                if "content" in event_data:
                                    content = event_data["content"]
                                    if content:
                                        # 实时打印内容（不换行）
                                        print(content, end='', flush=True)
                                        full_response.append(content)
                                
                            except json.JSONDecodeError as e:
                                print(f"\n⚠️  解析 JSON 失败: {e}")
                                print(f"   原始数据: {data[:200]}...")
                    
                    print("\n\n" + "=" * 80)
                    print("最终响应汇总")
                    print("=" * 80)
                    print(f"事件总数: {event_count}")
                    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    if full_response:
                        print("\n完整响应内容:")
                        print("-" * 80)
                        final_text = ''.join(full_response)
                        print(final_text)
                        print(f"\n总字数: {len(final_text)}")
                    else:
                        print("\n⚠️  未收集到完整响应内容")
                    
                    print(f"\n📊 统计: 共收到 {event_count} 个事件，收集到 {len(full_response)} 个文本片段")
                    
                else:
                    print(f"\n❌ API 请求失败")
                    error_content = await response.aread()
                    print(f"响应内容: {error_content.decode('utf-8')}")
                    
    except httpx.ConnectError:
        print("\n❌ 无法连接到后端服务")
        print("请确保后端服务正在运行:")
        print("  docker ps | grep deer-flow-backend")
        print("或者启动服务:")
        print("  docker-compose up -d")
    
    except httpx.ReadTimeout:
        print("\n❌ 请求超时")
        print("服务可能正在处理中，请增加超时时间或检查服务状态")
    
    except Exception as e:
        print(f"\n❌ API 测试失败")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        logger.error("API 测试失败", exc_info=True)


async def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("DeerFlow Simple Researcher 测试脚本")
    print("测试问题：藕汤腥味问题")
    print("=" * 80)
    
    await test_api_endpoint()
    
    print("\n测试完成！")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        logger.error("测试脚本执行失败", exc_info=True)
        exit(1)

