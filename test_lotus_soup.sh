#!/bin/bash
# 测试脚本：测试藕汤腥味问题
# 输入：今天店里的藕汤有点腥，这是什么原因怎么解决？

echo "=========================================="
echo "测试 DeerFlow Simple Researcher API"
echo "测试问题：藕汤腥味问题"
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

# API 地址
API_URL="http://localhost:8000/api/chat/stream"

# 生成 thread_id
THREAD_ID="test_lotus_soup_$(date +%Y%m%d_%H%M%S)"

echo "API URL: $API_URL"
echo "Thread ID: $THREAD_ID"
echo "问题: 今天店里的藕汤有点腥，这是什么原因怎么解决？"
echo "------------------------------------------"
echo ""

# 发送请求
echo "发送请求..."
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

curl -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -d "{
    \"messages\": [
      {
        \"role\": \"user\",
        \"content\": \"今天店里的藕汤有点腥，这是什么原因怎么解决？\"
      }
    ],
    \"thread_id\": \"$THREAD_ID\",
    \"enable_simple_research\": true,
    \"locale\": \"zh-CN\"
  }" \
  --no-buffer \
  2>/dev/null

echo ""
echo ""
echo "=========================================="
echo "测试完成！"
echo "结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

