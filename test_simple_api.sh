#!/bin/bash
# 快速测试脚本：测试 simple_researcher API 端点

echo "=========================================="
echo "测试 DeerFlow Simple Researcher API"
echo "=========================================="
echo ""

# 检查后端服务是否运行
echo "检查后端服务状态..."
if ! docker ps | grep -q deer-flow-backend; then
    echo "❌ 后端服务未运行，请先启动服务"
    echo "运行: docker-compose up -d"
    exit 1
fi

echo "✅ 后端服务正在运行"
echo ""

# 测试 API 端点
API_URL="http://localhost:8000/api/chat/stream"

echo "测试 API 端点: $API_URL"
echo "------------------------------------------"
echo ""

# 测试用例 1: 查询汤包制作方法
echo "📝 测试用例 1: 查询汤包制作方法"
echo ""

curl -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "汤包怎么做？"
      }
    ],
    "thread_id": "test_001",
    "enable_simple_research": true,
    "locale": "zh-CN"
  }' \
  --no-buffer \
  2>/dev/null

echo ""
echo ""
echo "=========================================="
echo ""

# 测试用例 2: 查询食材用量
echo "📝 测试用例 2: 查询食材用量"
echo ""

curl -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "南京汤包需要多少盐？"
      }
    ],
    "thread_id": "test_002",
    "enable_simple_research": true,
    "locale": "zh-CN"
  }' \
  --no-buffer \
  2>/dev/null

echo ""
echo ""
echo "=========================================="
echo "测试完成！"
echo "=========================================="

