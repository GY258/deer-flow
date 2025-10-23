#!/usr/bin/env python3
# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
日志查看工具 - 用于查看和分析请求日志
支持筛选、搜索和格式化输出
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


def load_logs(log_dir: str = "logs/requests", limit: int = None) -> List[Dict[str, Any]]:
    """
    加载日志文件
    
    Args:
        log_dir: 日志目录
        limit: 限制读取的条目数
    
    Returns:
        日志条目列表
    """
    log_path = Path(log_dir)
    if not log_path.exists():
        print(f"❌ 日志目录不存在: {log_dir}")
        return []
    
    # 获取所有日志文件，按时间排序
    log_files = sorted(log_path.glob("requests_*.jsonl"), reverse=True)
    
    if not log_files:
        print(f"❌ 没有找到日志文件: {log_dir}")
        return []
    
    print(f"📁 找到 {len(log_files)} 个日志文件")
    
    entries = []
    for log_file in log_files:
        print(f"📄 读取: {log_file.name}")
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            entries.append(entry)
                            
                            if limit and len(entries) >= limit:
                                return entries
                        except json.JSONDecodeError as e:
                            print(f"⚠️  解析失败: {e}")
                            continue
        except Exception as e:
            print(f"❌ 读取文件失败 {log_file}: {e}")
    
    return entries


def filter_logs(
    entries: List[Dict[str, Any]],
    log_type: str = None,
    request_id: str = None,
    thread_id: str = None,
    start_date: str = None,
    end_date: str = None,
    search_text: str = None,
) -> List[Dict[str, Any]]:
    """
    筛选日志条目
    
    Args:
        entries: 日志条目列表
        log_type: 日志类型 (request/prompt/response/error)
        request_id: 请求ID
        thread_id: 线程ID
        start_date: 开始日期 (ISO格式)
        end_date: 结束日期 (ISO格式)
        search_text: 搜索文本
    
    Returns:
        筛选后的日志条目列表
    """
    filtered = entries
    
    if log_type:
        filtered = [e for e in filtered if e.get("type") == log_type]
    
    if request_id:
        filtered = [e for e in filtered if e.get("request_id") == request_id]
    
    if thread_id:
        filtered = [e for e in filtered if e.get("thread_id") == thread_id]
    
    if start_date:
        start = datetime.fromisoformat(start_date)
        filtered = [
            e for e in filtered
            if datetime.fromisoformat(e.get("timestamp", "")) >= start
        ]
    
    if end_date:
        end = datetime.fromisoformat(end_date)
        filtered = [
            e for e in filtered
            if datetime.fromisoformat(e.get("timestamp", "")) <= end
        ]
    
    if search_text:
        search_lower = search_text.lower()
        filtered = [
            e for e in filtered
            if search_lower in json.dumps(e, ensure_ascii=False).lower()
        ]
    
    return filtered


def format_entry(entry: Dict[str, Any], verbose: bool = False) -> str:
    """
    格式化单个日志条目
    
    Args:
        entry: 日志条目
        verbose: 是否显示详细信息
    
    Returns:
        格式化的字符串
    """
    entry_type = entry.get("type", "unknown")
    timestamp = entry.get("timestamp", "")
    request_id = entry.get("request_id", "")
    
    lines = []
    lines.append("=" * 80)
    lines.append(f"类型: {entry_type.upper()} | 时间: {timestamp}")
    lines.append(f"请求ID: {request_id}")
    
    if entry_type == "request":
        lines.append(f"线程ID: {entry.get('thread_id', '')}")
        lines.append(f"用户问题: {entry.get('user_query', '')}")
        
        if verbose:
            lines.append("\n消息列表:")
            for msg in entry.get("messages", []):
                lines.append(f"  - {msg.get('role', '')}: {msg.get('content', '')[:100]}...")
            
            lines.append("\n元数据:")
            lines.append(json.dumps(entry.get("metadata", {}), ensure_ascii=False, indent=2))
    
    elif entry_type == "prompt":
        lines.append(f"Agent: {entry.get('agent_name', '')}")
        prompt = entry.get("prompt", "")
        lines.append(f"\nPrompt ({len(prompt)} 字符):")
        if verbose:
            lines.append(prompt)
        else:
            lines.append(prompt[:200] + "..." if len(prompt) > 200 else prompt)
        
        if verbose and entry.get("metadata"):
            lines.append("\n元数据:")
            lines.append(json.dumps(entry.get("metadata", {}), ensure_ascii=False, indent=2))
    
    elif entry_type == "response":
        final_result = entry.get("final_result", "")
        lines.append(f"\n最终结果 ({len(final_result)} 字符):")
        if verbose:
            lines.append(final_result)
        else:
            lines.append(final_result[:300] + "..." if len(final_result) > 300 else final_result)
        
        if verbose:
            intermediate = entry.get("intermediate_results", [])
            if intermediate:
                lines.append(f"\n中间结果 ({len(intermediate)} 条):")
                for i, result in enumerate(intermediate, 1):
                    lines.append(f"  {i}. Agent: {result.get('agent', '')}")
                    lines.append(f"     内容: {result.get('content', '')[:100]}...")
            
            lines.append("\n元数据:")
            lines.append(json.dumps(entry.get("metadata", {}), ensure_ascii=False, indent=2))
    
    elif entry_type == "error":
        lines.append(f"错误消息: {entry.get('error_message', '')}")
        
        if verbose and entry.get("error_details"):
            lines.append("\n错误详情:")
            lines.append(json.dumps(entry.get("error_details", {}), ensure_ascii=False, indent=2))
    
    lines.append("=" * 80)
    return "\n".join(lines)


def export_logs(entries: List[Dict[str, Any]], output_file: str):
    """
    导出日志到文件
    
    Args:
        entries: 日志条目列表
        output_file: 输出文件路径
    """
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        print(f"✅ 已导出 {len(entries)} 条日志到: {output_file}")
    except Exception as e:
        print(f"❌ 导出失败: {e}")


def print_summary(entries: List[Dict[str, Any]]):
    """
    打印日志摘要统计
    
    Args:
        entries: 日志条目列表
    """
    total = len(entries)
    type_counts = {}
    
    for entry in entries:
        entry_type = entry.get("type", "unknown")
        type_counts[entry_type] = type_counts.get(entry_type, 0) + 1
    
    print("\n" + "=" * 80)
    print("日志摘要")
    print("=" * 80)
    print(f"总条目数: {total}")
    print("\n按类型统计:")
    for entry_type, count in sorted(type_counts.items()):
        percentage = (count / total * 100) if total > 0 else 0
        print(f"  {entry_type.ljust(15)}: {count:5d} ({percentage:5.1f}%)")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="查看和分析DeerFlow请求日志",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 查看最近10条日志
  python view_request_logs.py --limit 10
  
  # 查看所有请求类型的日志
  python view_request_logs.py --type request
  
  # 查看特定请求ID的所有日志
  python view_request_logs.py --request-id "abc123"
  
  # 搜索包含特定文本的日志
  python view_request_logs.py --search "汤包"
  
  # 导出筛选后的日志
  python view_request_logs.py --type response --export output.json
  
  # 查看详细信息
  python view_request_logs.py --limit 5 --verbose
        """
    )
    
    parser.add_argument(
        "--log-dir",
        default="logs/requests",
        help="日志目录路径 (默认: logs/requests)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="限制读取的日志条目数"
    )
    parser.add_argument(
        "--type",
        choices=["request", "prompt", "response", "error"],
        help="筛选日志类型"
    )
    parser.add_argument(
        "--request-id",
        help="筛选特定请求ID"
    )
    parser.add_argument(
        "--thread-id",
        help="筛选特定线程ID"
    )
    parser.add_argument(
        "--start-date",
        help="开始日期 (ISO格式，如 2025-01-01T00:00:00)"
    )
    parser.add_argument(
        "--end-date",
        help="结束日期 (ISO格式，如 2025-12-31T23:59:59)"
    )
    parser.add_argument(
        "--search",
        help="搜索包含指定文本的日志"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细信息"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="只显示摘要统计"
    )
    parser.add_argument(
        "--export",
        help="导出筛选后的日志到JSON文件"
    )
    
    args = parser.parse_args()
    
    # 加载日志
    print("📖 正在加载日志...")
    entries = load_logs(log_dir=args.log_dir, limit=args.limit)
    
    if not entries:
        print("没有找到日志条目")
        sys.exit(1)
    
    print(f"✅ 加载了 {len(entries)} 条日志\n")
    
    # 筛选日志
    if any([args.type, args.request_id, args.thread_id, args.start_date, args.end_date, args.search]):
        print("🔍 正在筛选日志...")
        entries = filter_logs(
            entries,
            log_type=args.type,
            request_id=args.request_id,
            thread_id=args.thread_id,
            start_date=args.start_date,
            end_date=args.end_date,
            search_text=args.search,
        )
        print(f"✅ 筛选后剩余 {len(entries)} 条日志\n")
    
    # 显示摘要
    if args.summary:
        print_summary(entries)
        sys.exit(0)
    
    # 导出日志
    if args.export:
        export_logs(entries, args.export)
        sys.exit(0)
    
    # 显示日志
    print_summary(entries)
    print("\n详细日志:\n")
    
    for entry in entries:
        print(format_entry(entry, verbose=args.verbose))
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ 用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

