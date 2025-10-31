#!/usr/bin/env python3
"""
批量测试脚本：测试多个餐饮问题
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


# 测试问题列表
TEST_QUESTIONS = [
    {
        "id": 1,
        "name": "藕汤腥味问题",
        "question": "今天店里的藕汤有点腥，这是什么原因怎么解决？"
    }
#     {
#         "id": 2,
#         "name": "猪肝炒制问题",
#         "question": "店里面师傅今天猪肝炒的不好，应该怎么复盘调整"
#     },
#     {
#         "id": 3,
#         "name": "藕汤浓度问题",
#         "question": "今天店里面的藕汤不够浓，是什么原因"
#     },
#     {
#         "id": 4,
#         "name": "藕汤咸度问题",
#         "question": "今天店里面的藕汤太咸了，是什么原因，如何排查"
#     }
]


async def test_single_question(question_data, api_url):
    """测试单个问题"""
    question_id = question_data["id"]
    question_name = question_data["name"]
    question_text = question_data["question"]
    
    print("\n" + "=" * 80)
    print(f"测试 {question_id}/{len(TEST_QUESTIONS)}: {question_name}")
    print("=" * 80)
    print(f"问题: {question_text}")
    print("-" * 80)
    
    # 构造测试请求
    thread_id = f"test_batch_{question_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    request_data = {
        "messages": [
            {
                "role": "user",
                "content": question_text
            }
        ],
        "thread_id": thread_id,
        "enable_simple_research": True,
        "locale": "zh-CN",
    }
    
    start_time = datetime.now()
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            full_response = []
            event_count = 0
            
            async with client.stream("POST", api_url, json=request_data) as response:
                if response.status_code != 200:
                    print(f"\n❌ 请求失败，状态码: {response.status_code}")
                    error_text = await response.aread()
                    print(f"错误信息: {error_text.decode()}")
                    return None
                
                print("\n响应内容:")
                print("-" * 80)
                
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    
                    if line.startswith("data: "):
                        data = line[6:]
                        
                        if data == "[DONE]":
                            break
                        
                        try:
                            event_data = json.loads(data)
                            event_count += 1
                            
                            if "content" in event_data:
                                content = event_data["content"]
                                if content:
                                    print(content, end='', flush=True)
                                    full_response.append(content)
                        
                        except json.JSONDecodeError as e:
                            logger.warning(f"JSON 解析错误: {e}")
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            print("\n" + "-" * 80)
            print(f"✅ 测试完成")
            print(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"耗时: {duration:.1f} 秒")
            
            if full_response:
                final_text = ''.join(full_response)
                print(f"响应字数: {len(final_text)}")
                print(f"事件数量: {event_count}")
                return {
                    "question_id": question_id,
                    "question_name": question_name,
                    "question_text": question_text,
                    "response": final_text,
                    "duration": duration,
                    "event_count": event_count,
                    "success": True
                }
            else:
                print("⚠️  未收集到响应内容")
                return {
                    "question_id": question_id,
                    "question_name": question_name,
                    "question_text": question_text,
                    "success": False,
                    "error": "No response collected"
                }
    
    except httpx.ConnectError:
        print("\n❌ 无法连接到后端服务")
        print("请确保后端服务正在运行:")
        print("  docker ps | grep deer-flow-backend")
        return {
            "question_id": question_id,
            "success": False,
            "error": "Connection failed"
        }
    
    except httpx.ReadTimeout:
        print("\n❌ 请求超时")
        return {
            "question_id": question_id,
            "success": False,
            "error": "Request timeout"
        }
    
    except Exception as e:
        print(f"\n❌ 测试失败: {type(e).__name__}: {str(e)}")
        logger.error("测试失败", exc_info=True)
        return {
            "question_id": question_id,
            "success": False,
            "error": str(e)
        }


async def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("DeerFlow Simple Researcher 批量测试脚本")
    print("=" * 80)
    print(f"测试问题数量: {len(TEST_QUESTIONS)}")
    
    api_url = "http://localhost:8000/api/chat/stream"
    print(f"API URL: {api_url}")
    
    overall_start = datetime.now()
    results = []
    
    # 逐个测试问题
    for question_data in TEST_QUESTIONS:
        result = await test_single_question(question_data, api_url)
        if result:
            results.append(result)
        
        # 在问题之间稍作停顿
        if question_data["id"] < len(TEST_QUESTIONS):
            print("\n⏸️  等待 2 秒后继续下一个测试...")
            await asyncio.sleep(2)
    
    overall_end = datetime.now()
    total_duration = (overall_end - overall_start).total_seconds()
    
    # 打印汇总报告
    print("\n\n" + "=" * 80)
    print("测试汇总报告")
    print("=" * 80)
    print(f"总测试时间: {total_duration:.1f} 秒")
    print(f"测试问题数: {len(TEST_QUESTIONS)}")
    
    success_count = sum(1 for r in results if r.get("success", False))
    print(f"成功: {success_count}")
    print(f"失败: {len(results) - success_count}")
    
    if success_count > 0:
        print("\n详细结果:")
        print("-" * 80)
        for result in results:
            if result.get("success"):
                print(f"\n✅ 测试 {result['question_id']}: {result['question_name']}")
                print(f"   耗时: {result['duration']:.1f}秒")
                print(f"   字数: {len(result['response'])}")
                print(f"   事件: {result['event_count']}")
            else:
                print(f"\n❌ 测试 {result.get('question_id', '?')}: 失败")
                print(f"   错误: {result.get('error', 'Unknown error')}")
    
    # 保存详细结果到文件
    output_file = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": overall_start.isoformat(),
                "total_duration": total_duration,
                "results": results
            }, f, ensure_ascii=False, indent=2)
        print(f"\n📄 详细结果已保存到: {output_file}")
    except Exception as e:
        logger.error(f"保存结果文件失败: {e}")
    
    print("\n" + "=" * 80)
    print("测试完成！")
    print("=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        logger.error("测试脚本执行失败", exc_info=True)
        exit(1)

