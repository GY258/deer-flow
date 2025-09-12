# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os
import requests
import time
from typing import Annotated, Optional
from langchain_core.tools import tool
from .decorators import log_io

logger = logging.getLogger(__name__)

@tool
@log_io
def bm25_search_tool(
    query: Annotated[str, "The search query in Chinese"],
    limit: Annotated[int, "Number of top results to return"] = 3,
    include_snippets: Annotated[bool, "Whether to include document snippets"] = True,
    server_url: Annotated[Optional[str], "BM25 server URL"] = None,
) -> str:
    """Use this tool to search Chinese documents using BM25 retrieval.
    
    This tool searches a specialized Chinese document database containing:
    
    🍽️ 菜品相关文档:
    - 菜品SOP (Standard Operating Procedures) - 标准操作程序
    - 菜品制作流程和工艺标准
    - 菜品配方和配料清单
    - 菜品质量控制标准
    - 菜品成本核算和定价
    - 菜品营养分析和标签
    
    👥 公司管理文档:
    - 公司企业文化和价值观
    - 公司组织架构和部门职责
    - 公司管理制度和流程
    - 公司发展战略和规划
    - 公司品牌形象和宣传资料
    
    📚 培训资料:
    - 各岗位培训教材和手册
    - 新员工入职培训资料
    - 专业技能培训课程
    - 安全操作培训指南
    - 服务标准培训材料
    - 管理岗位培训内容
    
    🔧 操作流程:
    - 厨房操作流程和规范
    - 设备使用和维护指南
    - 食品安全操作程序
    - 清洁卫生标准流程
    - 库存管理和采购流程
    - 客户服务标准流程
    
    Best search strategies:
    - 菜品名称: "藕汤", "筒骨煨藕汤", "红烧肉"
    - SOP相关: "菜品SOP", "标准操作程序", "制作流程"
    - 培训相关: "培训资料", "岗位培训", "新员工培训"
    - 企业文化: "企业文化", "公司价值观", "品牌文化"
    - 流程相关: "操作流程", "工作流程", "服务流程"
    - 岗位相关: "厨师培训", "服务员培训", "管理培训"
    
    Args:
        query: The search query in Chinese
        limit: Number of top results to return (default: 3)
        include_snippets: Whether to include document snippets (default: True)
        server_url: BM25 server URL (default: http://localhost:5003)
        
    Returns:
        Search results as formatted string with titles, scores, and content snippets
    """
    try:
        # Resolve BM25 server URL from param or environment (fallback to localhost for local dev)
        if not server_url:
            server_url = os.getenv("BM25_SERVER_URL", "http://localhost:5003")
        # 使用POST方式调用BM25服务
        data = {
            "query": query,
            "limit": limit,
            "include_snippets": include_snippets
        }
        
        start_time = time.time()
        response = requests.post(
            f"{server_url}/search",
            json=data,
            timeout=10
        )
        end_time = time.time()
        
        response.raise_for_status()
        result = response.json()
        
        # 格式化结果
        formatted_results = []
        results = result.get('results', [])
        search_time = result.get('search_time_seconds', end_time - start_time)
        
        if not results:
            return f"未找到与 '{query}' 相关的结果"
        
        formatted_results.append(f"🔍 搜索: '{query}' (用时: {search_time:.3f}秒)")
        formatted_results.append(f"📊 找到 {len(results)} 个结果")
        formatted_results.append("")
        
        for i, doc in enumerate(results, 1):
            title = doc.get('title', 'N/A')
            score = doc.get('score', 0)
            snippet = doc.get('snippet', '')
            
            formatted_results.append(f"## 结果 {i}")
            formatted_results.append(f"**标题**: {title}")
            formatted_results.append(f"**评分**: {score:.3f}")
            
            if snippet:
                formatted_results.append(f"**内容片段**: {snippet}")
            
            formatted_results.append("")
        
        return "\n".join(formatted_results)
        
    except requests.exceptions.RequestException as e:
        error_msg = f"BM25搜索服务连接失败: {str(e)}"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"BM25搜索出错: {str(e)}"
        logger.error(error_msg)
        return error_msg

@tool
@log_io
def bm25_health_check_tool(
    server_url: Annotated[Optional[str], "BM25 server URL"] = None
) -> str:
    """Check the health status of BM25 search service.
    
    Args:
        server_url: BM25 server URL (default: http://localhost:5003)
        
    Returns:
        Health status information
    """
    try:
        if not server_url:
            server_url = os.getenv("BM25_SERVER_URL", "http://localhost:5003")
        response = requests.get(f"{server_url}/health", timeout=5)
        response.raise_for_status()
        data = response.json()
        
        status = data.get('status', 'unknown')
        doc_count = data.get('documents_count', 0)
        vocab_size = data.get('vocabulary_size', 0)
        
        return f"✅ BM25服务状态正常\n📊 文档数: {doc_count}\n📚 词汇量: {vocab_size}"
        
    except Exception as e:
        return f"❌ BM25服务状态检查失败: {str(e)}"

@tool
@log_io
def bm25_stats_tool(
    server_url: Annotated[Optional[str], "BM25 server URL"] = None
) -> str:
    """Get statistics from BM25 search service.
    
    Args:
        server_url: BM25 server URL (default: http://localhost:5003)
        
    Returns:
        Statistics information
    """
    try:
        if not server_url:
            server_url = os.getenv("BM25_SERVER_URL", "http://localhost:5003")
        response = requests.get(f"{server_url}/stats", timeout=5)
        response.raise_for_status()
        data = response.json()
        stats = data.get('statistics', {})
        
        doc_count = stats.get('documents_count', 0)
        vocab_size = stats.get('vocabulary_size', 0)
        avg_length = stats.get('average_document_length', 0)
        top_terms = stats.get('top_terms', [])
        
        result = [
            "📊 BM25服务统计信息:",
            f"📄 文档总数: {doc_count}",
            f"📚 词汇总量: {vocab_size}",
            f"📏 平均文档长度: {avg_length:.1f}",
        ]
        
        if top_terms:
            result.append("🔥 热门词汇:")
            for term_info in top_terms[:5]:
                term = term_info.get('term', '')
                freq = term_info.get('frequency', 0)
                result.append(f"   - {term}: {freq} 次")
        
        return "\n".join(result)
        
    except Exception as e:
        return f"❌ 统计信息获取失败: {str(e)}"

@tool
@log_io
def bm25_database_info_tool(
    server_url: Annotated[Optional[str], "BM25 server URL"] = None
) -> str:
    """Get information about the BM25 database content and capabilities.
    
    Args:
        server_url: BM25 server URL (default: http://localhost:5003)
        
    Returns:
        Database content information
    """
    # Keep signature consistent; this tool provides static info.
    return """
📚 BM25数据库内容说明:

🍽️ 菜品相关文档:
- 菜品SOP (标准操作程序)
- 菜品制作流程和工艺标准
- 菜品配方和配料清单
- 菜品质量控制标准
- 菜品成本核算和定价
- 菜品营养分析和标签

👥 公司管理文档:
- 公司企业文化和价值观
- 公司组织架构和部门职责
- 公司管理制度和流程
- 公司发展战略和规划
- 公司品牌形象和宣传资料

📚 培训资料:
- 各岗位培训教材和手册
- 新员工入职培训资料
- 专业技能培训课程
- 安全操作培训指南
- 服务标准培训材料
- 管理岗位培训内容

🔧 操作流程:
- 厨房操作流程和规范
- 设备使用和维护指南
- 食品安全操作程序
- 清洁卫生标准流程
- 库存管理和采购流程
- 客户服务标准流程

🔍 搜索建议:
- 菜品相关: "藕汤SOP", "筒骨煨藕汤制作流程", "红烧肉配方"
- SOP相关: "菜品SOP", "标准操作程序", "制作流程"
- 培训相关: "培训资料", "岗位培训", "新员工培训"
- 企业文化: "企业文化", "公司价值观", "品牌文化"
- 流程相关: "操作流程", "工作流程", "服务流程"
- 岗位相关: "厨师培训", "服务员培训", "管理培训"

💡 最佳实践:
- 优先使用BM25搜索内部文档和培训资料
- 结合web搜索获取最新行业信息
- 使用具体关键词提高搜索精度
- 根据查询类型选择合适的搜索策略
"""
