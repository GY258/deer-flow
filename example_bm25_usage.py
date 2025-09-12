#!/usr/bin/env python3
"""
BM25集成使用示例 - 展示如何在DeerFlow中使用BM25搜索
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.workflow import run_agent_workflow_async

async def example_chinese_search():
    """示例：中文搜索功能"""
    print("🔍 中文搜索示例")
    print("=" * 50)
    
    # 示例查询
    queries = [
        "请搜索关于藕汤的中文资料",
        "筒骨煨藕汤的制作方法",
        "铫子筒骨煨藕汤产品标准",
        "请查找菜品SOP相关文档",
        "新员工培训资料有哪些",
        "公司企业文化内容"
    ]
    
    for query in queries:
        print(f"\n📝 查询: {query}")
        print("-" * 30)
        
        try:
            await run_agent_workflow_async(
                user_input=query,
                debug=False,
                max_plan_iterations=1,
                max_step_num=2,
                enable_background_investigation=True
            )
        except Exception as e:
            print(f"❌ 查询失败: {e}")
        
        print("\n" + "="*50)

def example_tool_direct_usage():
    """示例：直接使用BM25工具"""
    print("\n🛠️ 直接使用BM25工具示例")
    print("=" * 50)
    
    from src.tools.bm25_search import bm25_search_tool, bm25_health_check_tool, bm25_stats_tool, bm25_database_info_tool
    
    # 健康检查
    print("1. 健康检查:")
    health = bm25_health_check_tool.invoke()
    print(health)
    
    # 统计信息
    print("\n2. 统计信息:")
    stats = bm25_stats_tool.invoke()
    print(stats)
    
    # 数据库信息
    print("\n3. 数据库信息:")
    db_info = bm25_database_info_tool.invoke()
    print(db_info)
    
    # 搜索示例
    print("\n4. 搜索示例:")
    search_queries = ["藕汤", "筒骨煨藕汤", "产品标准", "培训资料", "企业文化"]
    
    for query in search_queries:
        print(f"\n搜索: '{query}'")
        result = bm25_search_tool.invoke(query)
        print(result)
        print("-" * 30)

def main():
    """主函数"""
    print("🚀 BM25集成使用示例")
    print("=" * 50)
    
    # 检查BM25服务
    try:
        import requests
        response = requests.get("http://localhost:5003/health", timeout=5)
        if response.status_code != 200:
            print("❌ BM25服务未运行，请先启动BM25服务")
            return
    except Exception as e:
        print(f"❌ 无法连接到BM25服务: {e}")
        print("请确保BM25服务正在运行在 http://localhost:5003")
        return
    
    print("✅ BM25服务运行正常")
    
    # 选择示例类型
    print("\n请选择示例类型:")
    print("1. 完整DeerFlow工作流示例")
    print("2. 直接使用BM25工具示例")
    print("3. 运行所有示例")
    
    choice = input("\n请输入选择 (1/2/3): ").strip()
    
    if choice == "1":
        asyncio.run(example_chinese_search())
    elif choice == "2":
        example_tool_direct_usage()
    elif choice == "3":
        example_tool_direct_usage()
        asyncio.run(example_chinese_search())
    else:
        print("❌ 无效选择")

if __name__ == "__main__":
    main()
