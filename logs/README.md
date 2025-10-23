# 日志目录

此目录用于存储DeerFlow的各种日志文件。

## 子目录

### requests/
存储API请求日志，包括：
- 用户问题
- 生成的Prompts
- 最终响应结果
- 错误信息

日志文件格式: `requests_YYYY_MM.jsonl`

**重要**: 日志文件不会自动删除，请定期审查和备份。

## 查看日志

使用日志查看工具：
```bash
# 从项目根目录运行
python3 view_request_logs.py --summary
```

详细文档：
- 快速开始: [LOGGING_QUICKSTART.md](../LOGGING_QUICKSTART.md)
- 完整文档: [REQUEST_LOGGING.md](../REQUEST_LOGGING.md)

