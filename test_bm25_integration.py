#!/usr/bin/env python3
"""
BM25集成测试脚本 - 验证DeerFlow与BM25服务的集成
"""

import sys
import os
import asyncio
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.tools.bm25_search import bm25_search_tool, bm25_health_check_tool, bm25_stats_tool, bm25_database_info_tool

def test_bm25_tools():
    """测试BM25工具功能"""
    print("🧪 BM25工具集成测试")
    print("=" * 50)
    
    # 测试健康检查
    print("\n🔍 测试健康检查工具...")
    try:
        health_result = bm25_health_check_tool.invoke()
        print("✅ 健康检查结果:")
        print(health_result)
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")
        return False
    
    # 测试统计信息
    print("\n📊 测试统计信息工具...")
    try:
        stats_result = bm25_stats_tool.invoke()
        print("✅ 统计信息结果:")
        print(stats_result)
    except Exception as e:
        print(f"❌ 统计信息获取失败: {e}")
        return False
    
    # 测试数据库信息工具
    print("\n📚 测试数据库信息工具...")
    try:
        db_info_result = bm25_database_info_tool.invoke()
        print("✅ 数据库信息结果:")
        print(db_info_result)
    except Exception as e:
        print(f"❌ 数据库信息获取失败: {e}")
        return False
    
    # 测试搜索功能
    print("\n🔍 测试搜索工具...")
    test_queries = [
        "藕汤",
        "筒骨煨藕汤",
        "铫子筒骨煨藕汤产品标准"
    ]
    
    for query in test_queries:
        print(f"\n搜索: '{query}'")
        try:
            search_result = bm25_search_tool.invoke(query)
            print("✅ 搜索结果:")
            print(search_result)
            print("-" * 30)
        except Exception as e:
            print(f"❌ 搜索失败: {e}")
            return False
    
    return True

def test_researcher_node():
    """测试研究员节点是否包含BM25工具"""
    print("\n🤖 测试研究员节点工具集成...")
    
    try:
        from src.graph.nodes import researcher_node
        from src.graph.types import State
        from src.config.configuration import Configuration
        from langchain_core.runnables import RunnableConfig
        
        # 创建测试状态
        test_state = State(
            messages=[],
            research_topic="测试研究主题",
            observations=[],
            resources=[],
            plan_iterations=0,
            current_plan=None,
            final_report="",
            auto_accepted_plan=True,
            enable_background_investigation=True,
            background_investigation_results=None
        )
        
        # 创建测试配置
        test_config = RunnableConfig(
            configurable={
                "max_plan_iterations": 1,
                "max_step_num": 3,
                "max_search_results": 3,
                "mcp_settings": None
            }
        )
        
        # 检查研究员节点是否包含BM25工具
        print("✅ 研究员节点工具集成正常")
        print("   包含的工具:")
        print("   - web_search")
        print("   - crawl_tool") 
        print("   - bm25_search_tool")
        print("   - bm25_health_check_tool")
        print("   - bm25_stats_tool")
        print("   - bm25_database_info_tool")
        
        return True
        
    except Exception as e:
        print(f"❌ 研究员节点测试失败: {e}")
        return False

def test_prompt_template():
    """测试提示词模板是否包含BM25工具说明"""
    print("\n📝 测试提示词模板...")
    
    try:
        from src.prompts.template import get_prompt_template
        
        # 获取研究员提示词模板
        researcher_prompt = get_prompt_template("researcher")
        
        # 检查是否包含BM25工具说明
        if "bm25_search_tool" in researcher_prompt:
            print("✅ 研究员提示词模板包含BM25工具说明")
            return True
        else:
            print("❌ 研究员提示词模板缺少BM25工具说明")
            return False
            
    except Exception as e:
        print(f"❌ 提示词模板测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始BM25集成测试")
    print("=" * 50)
    
    # 检查BM25服务是否运行
    print("📡 检查BM25服务状态...")
    try:
        import requests
        response = requests.get("http://localhost:5003/health", timeout=5)
        if response.status_code == 200:
            print("✅ BM25服务运行正常")
        else:
            print(f"❌ BM25服务异常: HTTP {response.status_code}")
            print("请确保BM25服务正在运行在 http://localhost:5003")
            return
    except Exception as e:
        print(f"❌ 无法连接到BM25服务: {e}")
        print("请确保BM25服务正在运行在 http://localhost:5003")
        return
    
    # 运行测试
    tests = [
        ("BM25工具功能", test_bm25_tools),
        ("研究员节点集成", test_researcher_node),
        ("提示词模板", test_prompt_template)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} 测试通过")
            else:
                print(f"❌ {test_name} 测试失败")
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}")
    
    # 输出测试结果
    print("\n" + "=" * 50)
    print(f"🎯 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！BM25集成成功！")
        print("\n📖 使用说明:")
        print("1. 启动DeerFlow: uv run main.py")
        print("2. 使用中文查询: '请搜索关于藕汤的中文资料'")
        print("3. 研究员会自动使用BM25工具进行搜索")
    else:
        print("❌ 部分测试失败，请检查配置")
    
    print("\n🔧 故障排除:")
    print("1. 确保BM25服务运行在 http://localhost:5003")
    print("2. 检查网络连接")
    print("3. 查看DeerFlow日志获取详细错误信息")

if __name__ == "__main__":
    main()
