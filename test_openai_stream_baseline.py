#!/usr/bin/env python3
"""
基线对照测试：直接测试 OpenAI API 的流式输出

这个脚本用于验证 OpenAI API 本身是否支持逐 token 流式输出。
如果这里也无法流式输出，问题在模型或 SDK；如果这里可以流式输出，问题在 LangGraph/服务端。
"""

import os
import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from openai import OpenAI
from src.config import load_yaml_config

def test_openai_direct_stream():
    """直接使用 OpenAI SDK 测试流式输出"""
    print("=" * 60)
    print("基线测试：直接调用 OpenAI API (跳过 LangGraph/服务端)")
    print("=" * 60)
    
    # 从配置文件读取 API 配置
    conf_path = project_root / "conf.yaml"
    if not conf_path.exists():
        print(f"❌ 配置文件不存在: {conf_path}")
        return
    
    conf = load_yaml_config(str(conf_path))
    basic_model = conf.get("BASIC_MODEL", {})
    
    api_key = basic_model.get("api_key") or os.getenv("OPENAI_API_KEY")
    base_url = basic_model.get("base_url", "https://api.openai.com/v1")
    model = basic_model.get("model", "gpt-4o-mini")
    
    if not api_key:
        print("❌ 未找到 API key，请检查 conf.yaml 或 OPENAI_API_KEY 环境变量")
        return
    
    print(f"📋 配置信息:")
    print(f"   Model: {model}")
    print(f"   Base URL: {base_url}")
    print(f"   API Key: {api_key[:20]}...")
    print()
    
    # 创建 OpenAI 客户端
    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )
    
    print("🚀 开始流式请求...")
    print("-" * 60)
    
    try:
        # 流式请求
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "count to 10 slowly"}],
            stream=True,
        )
        
        print("📥 接收到流式响应，开始逐 token 输出：")
        print()
        
        token_count = 0
        start_time = time.time()
        first_token_time = None
        
        for chunk in stream:
            # delta 是 ChoiceDelta 对象，不是字典，需要直接访问属性
            delta = chunk.choices[0].delta if chunk.choices else None
            content = delta.content if delta and hasattr(delta, 'content') else ""
            if content:
                if first_token_time is None:
                    first_token_time = time.time()
                    first_token_delay = first_token_time - start_time
                    print(f"[TTFB: {first_token_delay:.2f}s] ", end="", flush=True)
                
                print(content, end="", flush=True)
                token_count += 1
                
                # 每个 token 之间添加小延迟以便观察
                time.sleep(0.01)
        
        print()
        print()
        print("-" * 60)
        
        if first_token_time:
            total_time = time.time() - start_time
            streaming_duration = time.time() - first_token_time
            print(f"✅ 测试完成")
            print(f"   总 token 数: {token_count}")
            print(f"   首 token 延迟 (TTFB): {first_token_delay:.2f}s")
            print(f"   总耗时: {total_time:.2f}s")
            print(f"   流式传输耗时: {streaming_duration:.2f}s")
            print()
            
            # 判断是否真的在流式输出
            if token_count > 1 and first_token_delay < total_time * 0.5:
                print("✅ 结论：模型端确实在逐 token 推送（流式输出正常）")
                print("   → 如果 LangGraph 中不是流式的，问题在 LangGraph/服务端")
            elif first_token_delay > total_time * 0.8:
                print("⚠️  结论：模型端可能是一次性返回（大部分内容在最后）")
                print("   → 问题可能在模型或 SDK 配置")
            else:
                print("⚠️  结论：流式输出表现异常，需要进一步排查")
        else:
            print("❌ 未收到任何 token 内容")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_openai_direct_stream()

