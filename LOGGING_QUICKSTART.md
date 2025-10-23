# 日志系统快速开始

## 🚀 快速概览

DeerFlow现在会自动记录所有API请求的详细信息，包括用户问题、生成的prompts和最终结果。所有日志都保存在 `logs/requests/` 目录中，**永久保留不会删除**。

## 📁 日志位置

```
logs/requests/
├── requests_2025_10.jsonl  # 2025年10月的日志
├── requests_2025_11.jsonl  # 2025年11月的日志
└── ...
```

日志按月自动轮转，每个文件包含该月的所有请求记录。

## 🔍 快速查看日志

### 1. 查看日志摘要

```bash
python3 view_request_logs.py --summary
```

输出示例：
```
日志摘要
================================================================================
总条目数: 150

按类型统计:
  request        :    50 ( 33.3%)
  prompt         :    60 ( 40.0%)
  response       :    48 ( 32.0%)
  error          :     2 (  1.3%)
```

### 2. 查看最近的请求

```bash
python3 view_request_logs.py --limit 10
```

### 3. 查看详细信息

```bash
python3 view_request_logs.py --limit 5 --verbose
```

### 4. 搜索特定内容

```bash
# 搜索包含"汤包"的所有日志
python3 view_request_logs.py --search "汤包"

# 查看特定类型的日志
python3 view_request_logs.py --type response --limit 10

# 查看特定请求的完整流程
python3 view_request_logs.py --request-id "YOUR_REQUEST_ID"
```

### 5. 导出日志

```bash
# 导出今天的所有响应
python3 view_request_logs.py --type response --export today_responses.json

# 导出筛选后的日志
python3 view_request_logs.py --search "error" --export errors.json
```

## 📋 日志内容说明

### 请求日志 (request)
记录用户发起的请求和配置参数

### Prompt日志 (prompt)
记录系统生成的prompts和工具调用

### 响应日志 (response)
记录最终响应结果和中间步骤

### 错误日志 (error)
记录处理过程中的错误

## 🔧 测试日志系统

运行测试脚本验证日志系统是否正常工作：

```bash
python3 test_request_logging.py
```

## 🗂️ 查看原始日志文件

日志使用JSONL格式（每行一个JSON对象）：

```bash
# 查看最新日志
tail -n 20 logs/requests/requests_2025_10.jsonl

# 实时监控日志
tail -f logs/requests/requests_2025_10.jsonl

# 使用jq美化输出
cat logs/requests/requests_2025_10.jsonl | jq '.'

# 统计日志数量
wc -l logs/requests/requests_2025_10.jsonl
```

## 📊 常用命令速查

```bash
# 查看今天的所有请求
python3 view_request_logs.py --type request

# 查看最近的错误
python3 view_request_logs.py --type error --limit 10 --verbose

# 搜索特定用户的请求
python3 view_request_logs.py --thread-id "user_123"

# 按时间范围筛选
python3 view_request_logs.py --start-date "2025-10-23T00:00:00" \
                             --end-date "2025-10-23T23:59:59"

# 查看帮助
python3 view_request_logs.py --help
```

## 🔐 重要提示

⚠️ **日志文件包含完整的用户查询和系统响应，请妥善保管！**

- 确保日志目录访问权限正确
- 定期备份重要日志
- 遵守数据保护法规

## 📚 更多信息

详细文档请参阅: [REQUEST_LOGGING.md](REQUEST_LOGGING.md)

## 💡 小贴士

1. 日志文件使用追加模式，不会丢失数据
2. 日志按月自动轮转，避免单文件过大
3. 使用 `--verbose` 标志查看完整内容
4. 使用 `--export` 功能备份和分析日志
5. 日志写入不会影响API性能

## 🐛 故障排查

如果日志没有生成，检查：
1. `logs/requests/` 目录是否存在且有写权限
2. 磁盘空间是否充足
3. 查看应用日志是否有错误信息

```bash
# 检查目录权限
ls -la logs/requests/

# 检查磁盘空间
df -h

# 测试日志系统
python3 test_request_logging.py
```

