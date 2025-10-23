# 请求日志系统说明文档

## 概述

DeerFlow的请求日志系统用于记录所有API请求的详细信息，包括：
- 用户问题
- 生成的Prompts
- 最终响应结果
- 错误信息

所有日志以**追加模式**写入文件，**不会被删除**，方便定期审查和分析。

## 日志文件位置

默认日志目录: `logs/requests/`

日志文件命名格式: `requests_YYYY_MM.jsonl`
- 按月份自动轮转
- 使用JSONL格式（每行一个JSON对象）
- 示例: `requests_2025_10.jsonl`

您可以通过环境变量 `REQUEST_LOG_DIR` 自定义日志目录：
```bash
export REQUEST_LOG_DIR="/path/to/custom/logs"
```

## 日志内容

### 1. 请求日志 (type: "request")

记录用户发起的请求：

```json
{
  "request_id": "thread_123_2025-10-23T10:30:00.000000",
  "thread_id": "thread_123",
  "timestamp": "2025-10-23T10:30:00.000000",
  "type": "request",
  "user_query": "汤包怎么做？",
  "messages": [
    {
      "role": "user",
      "content": "汤包怎么做？"
    }
  ],
  "metadata": {
    "max_plan_iterations": 1,
    "max_step_num": 3,
    "enable_simple_research": true,
    "report_style": "academic"
  }
}
```

### 2. Prompt日志 (type: "prompt")

记录系统生成的Prompts和工具调用：

```json
{
  "request_id": "thread_123_2025-10-23T10:30:00.000000",
  "timestamp": "2025-10-23T10:30:15.000000",
  "type": "prompt",
  "agent_name": "researcher",
  "prompt": "Based on the user query...",
  "metadata": {
    "event_type": "message_chunk",
    "langgraph_node": "researcher",
    "checkpoint_ns": "..."
  }
}
```

### 3. 响应日志 (type: "response")

记录最终响应结果：

```json
{
  "request_id": "thread_123_2025-10-23T10:30:00.000000",
  "timestamp": "2025-10-23T10:31:00.000000",
  "type": "response",
  "final_result": "汤包的制作方法...",
  "intermediate_results": [
    {
      "agent": "researcher",
      "content": "搜索结果...",
      "finish_reason": "stop",
      "timestamp": ""
    }
  ],
  "metadata": {
    "total_events": 25
  }
}
```

### 4. 错误日志 (type: "error")

记录处理过程中的错误：

```json
{
  "request_id": "thread_123_2025-10-23T10:30:00.000000",
  "timestamp": "2025-10-23T10:30:45.000000",
  "type": "error",
  "error_message": "Connection timeout",
  "error_details": {
    "error_type": "TimeoutError",
    "thread_id": "thread_123"
  }
}
```

## 查看日志

### 使用日志查看工具

我们提供了一个方便的日志查看工具 `view_request_logs.py`：

#### 基本用法

```bash
# 查看所有日志摘要
python view_request_logs.py --summary

# 查看最近10条日志
python view_request_logs.py --limit 10

# 查看详细信息
python view_request_logs.py --limit 10 --verbose
```

#### 筛选日志

```bash
# 只查看请求类型的日志
python view_request_logs.py --type request

# 查看特定请求ID的所有日志
python view_request_logs.py --request-id "thread_123_2025-10-23T10:30:00.000000"

# 查看特定线程的所有日志
python view_request_logs.py --thread-id "thread_123"

# 按时间范围筛选
python view_request_logs.py --start-date "2025-10-23T00:00:00" --end-date "2025-10-23T23:59:59"

# 搜索包含特定文本的日志
python view_request_logs.py --search "汤包"
```

#### 导出日志

```bash
# 导出筛选后的日志到JSON文件
python view_request_logs.py --type response --export responses.json

# 导出今天的所有日志
python view_request_logs.py --start-date "2025-10-23T00:00:00" --export today_logs.json
```

### 手动查看日志文件

日志使用JSONL格式，每行一个JSON对象，可以使用以下方式查看：

```bash
# 查看最新的日志文件
tail -f logs/requests/requests_2025_10.jsonl

# 使用jq美化输出
cat logs/requests/requests_2025_10.jsonl | jq '.'

# 筛选特定类型的日志
cat logs/requests/requests_2025_10.jsonl | jq 'select(.type == "request")'

# 统计日志数量
wc -l logs/requests/requests_2025_10.jsonl
```

## 日志管理

### 日志轮转

日志按月自动轮转，每个月会创建一个新的日志文件。旧的日志文件会保留，不会被删除。

### 日志备份

建议定期备份日志文件：

```bash
# 创建备份脚本
#!/bin/bash
BACKUP_DIR="/path/to/backup/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"
cp -r logs/requests/* "$BACKUP_DIR/"
echo "Logs backed up to $BACKUP_DIR"
```

### 日志清理

如果需要清理旧日志（不推荐，除非磁盘空间不足）：

```bash
# 删除3个月前的日志（请谨慎操作）
find logs/requests -name "requests_*.jsonl" -mtime +90 -delete
```

## 性能考虑

1. **异步写入**: 日志写入使用线程锁保证安全，不会阻塞主线程
2. **按月轮转**: 避免单个文件过大，提高读写效率
3. **追加模式**: 使用追加模式写入，保证数据不丢失
4. **JSONL格式**: 每行一个JSON对象，方便逐行处理大文件

## 隐私和安全

⚠️ **重要提示**: 日志文件包含用户查询和系统响应的完整内容，请注意保护：

1. **访问控制**: 确保日志目录只有授权人员可以访问
2. **敏感信息**: 不要在日志中记录密码、密钥等敏感信息
3. **数据保护**: 遵守相关的数据保护法规
4. **定期审查**: 定期审查日志内容，确保合规

## 故障排查

### 日志没有生成

检查以下几点：

1. 日志目录权限是否正确
2. 磁盘空间是否充足
3. 查看应用日志是否有错误信息

### 日志文件损坏

如果日志文件损坏（JSON解析失败）：

```bash
# 找出有问题的行
cat logs/requests/requests_2025_10.jsonl | while read line; do
  echo "$line" | jq '.' > /dev/null 2>&1 || echo "Error: $line"
done
```

## 常见问题

**Q: 日志会影响性能吗？**
A: 影响很小。日志使用异步写入，不会阻塞主线程。

**Q: 日志文件会变得很大吗？**
A: 日志按月轮转，单个文件大小取决于请求量。建议定期备份和归档旧日志。

**Q: 可以禁用日志吗？**
A: 不建议禁用，但可以通过修改代码实现。

**Q: 如何在Docker环境中使用？**
A: 确保日志目录映射到宿主机：
```yaml
volumes:
  - ./logs:/app/logs
```

## 联系支持

如有问题或建议，请联系开发团队或提交Issue。

