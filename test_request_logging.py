#!/usr/bin/env python3
# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
测试请求日志系统
"""

import sys
from pathlib import Path

# 确保可以导入src模块
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.request_logger import get_request_logger


def test_request_logger():
    """测试请求日志系统的基本功能"""
    
    print("=" * 80)
    print("测试请求日志系统")
    print("=" * 80)
    
    # 获取日志记录器
    logger = get_request_logger()
    print(f"✅ 日志记录器初始化成功")
    print(f"📁 日志目录: {logger.log_dir}")
    print(f"📄 当前日志文件: {logger.current_log_file}")
    
    # 测试记录请求
    print("\n1️⃣  测试记录请求...")
    request_id = logger.log_request(
        thread_id="test_thread_001",
        user_query="测试用户问题：汤包怎么做？",
        messages=[
            {"role": "user", "content": "测试用户问题：汤包怎么做？"}
        ],
        request_metadata={
            "test": True,
            "max_plan_iterations": 1,
            "enable_simple_research": True,
        }
    )
    print(f"✅ 请求已记录，request_id: {request_id}")
    
    # 测试记录prompt
    print("\n2️⃣  测试记录Prompt...")
    logger.log_prompt(
        request_id=request_id,
        agent_name="researcher",
        prompt="这是一个测试prompt，用于演示日志记录功能。\n包含多行内容...",
        prompt_metadata={
            "event_type": "message_chunk",
            "langgraph_node": "researcher",
        }
    )
    print(f"✅ Prompt已记录")
    
    # 测试记录工具调用
    print("\n3️⃣  测试记录工具调用...")
    logger.log_prompt(
        request_id=request_id,
        agent_name="researcher",
        prompt='Tool Call: web_search\nArgs: {"query": "汤包制作方法"}',
        prompt_metadata={
            "event_type": "tool_call",
            "tool_name": "web_search",
        }
    )
    print(f"✅ 工具调用已记录")
    
    # 测试记录响应
    print("\n4️⃣  测试记录响应...")
    logger.log_response(
        request_id=request_id,
        final_result="这是测试的最终结果：汤包的制作方法包括准备馅料、和面、包制、蒸制等步骤...",
        intermediate_results=[
            {
                "agent": "researcher",
                "content": "搜索结果1...",
                "finish_reason": "stop",
                "timestamp": "2025-10-23T10:30:00",
            },
            {
                "agent": "reporter",
                "content": "生成报告...",
                "finish_reason": "stop",
                "timestamp": "2025-10-23T10:31:00",
            },
        ],
        response_metadata={
            "total_events": 25,
            "success": True,
        }
    )
    print(f"✅ 响应已记录")
    
    # 测试记录错误
    print("\n5️⃣  测试记录错误...")
    error_request_id = logger.log_request(
        thread_id="test_thread_002",
        user_query="这是一个会出错的请求",
        messages=[{"role": "user", "content": "这是一个会出错的请求"}],
    )
    logger.log_error(
        request_id=error_request_id,
        error_message="Connection timeout",
        error_details={
            "error_type": "TimeoutError",
            "timeout_seconds": 30,
        }
    )
    print(f"✅ 错误已记录")
    
    # 读取日志
    print("\n6️⃣  测试读取日志...")
    logs = logger.read_logs(limit=10)
    print(f"✅ 成功读取 {len(logs)} 条日志")
    
    # 显示最近的几条日志
    print("\n📋 最近的日志条目:")
    for i, log in enumerate(logs[-5:], 1):
        print(f"  {i}. 类型: {log.get('type')}, 请求ID: {log.get('request_id', '')[:50]}...")
    
    # 显示日志文件列表
    print("\n📁 日志文件列表:")
    log_files = logger.get_log_files()
    for log_file in log_files:
        size = log_file.stat().st_size
        print(f"  - {log_file.name} ({size} 字节)")
    
    print("\n" + "=" * 80)
    print("✅ 所有测试通过！")
    print("=" * 80)
    print(f"\n💡 提示：使用以下命令查看日志：")
    print(f"   python view_request_logs.py --limit 10 --verbose")
    print(f"   python view_request_logs.py --summary")


if __name__ == "__main__":
    try:
        test_request_logger()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

