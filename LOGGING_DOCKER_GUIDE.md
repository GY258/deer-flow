# Docker环境下的日志查看指南

## 📋 概述

已经在 `docker-compose.yml` 中添加了日志目录映射：
```yaml
volumes:
  - ./logs:/app/logs  # 映射日志目录到宿主机
```

这样你就可以**直接在宿主机上查看日志**，无需进入Docker容器！

## 🚀 快速开始

### 方式一：在宿主机直接查看（推荐）✨

日志目录已经映射到宿主机，可以直接使用日志查看工具：

```bash
# 在项目根目录运行（无需进Docker）
python3 view_request_logs.py --summary

# 查看最近10条日志
python3 view_request_logs.py --limit 10 --verbose

# 搜索特定内容
python3 view_request_logs.py --search "用户问题"

# 实时监控日志
tail -f logs/requests/requests_2025_10.jsonl
```

### 方式二：进入Docker容器查看

如果你需要在容器内部查看（通常不需要）：

```bash
# 进入后端容器
docker exec -it deer-flow-backend bash

# 在容器内查看日志
cd /app
python view_request_logs.py --summary

# 退出容器
exit
```

## 🔄 应用配置更改

如果你是第一次添加日志映射，需要重启容器：

```bash
# 停止服务
docker-compose down

# 重新启动服务（会应用新的卷映射）
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志确认服务正常
docker-compose logs -f backend
```

## 📁 日志文件位置

### 宿主机上
```
/home/ubuntu/deer-flow/logs/requests/
├── requests_2025_10.jsonl
└── requests_2025_11.jsonl
```

### Docker容器内
```
/app/logs/requests/
├── requests_2025_10.jsonl
└── requests_2025_11.jsonl
```

两个位置的文件是**完全同步**的（通过Docker卷映射）。

## 💡 推荐使用方式

### 日常查看（宿主机）
```bash
# 1. 查看今天的请求统计
python3 view_request_logs.py --summary

# 2. 查看最近的错误
python3 view_request_logs.py --type error --limit 10

# 3. 搜索特定用户的请求
python3 view_request_logs.py --search "用户ID"

# 4. 导出月度报告
python3 view_request_logs.py --export monthly_report.json
```

### 实时监控（宿主机）
```bash
# 监控新增的日志
tail -f logs/requests/requests_2025_10.jsonl

# 使用jq美化输出
tail -f logs/requests/requests_2025_10.jsonl | jq '.'

# 只显示请求类型的日志
tail -f logs/requests/requests_2025_10.jsonl | jq 'select(.type=="request")'
```

### 容器日志（Docker）
```bash
# 查看后端容器的实时日志（应用日志，不是请求日志）
docker-compose logs -f backend

# 查看最近100行
docker-compose logs --tail=100 backend

# 查看所有容器的日志
docker-compose logs -f
```

## 🔍 检查日志映射是否生效

运行以下命令确认映射正常：

```bash
# 1. 检查宿主机上的日志目录
ls -lh /home/ubuntu/deer-flow/logs/requests/

# 2. 发送一个测试请求（假设服务运行在8000端口）
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "测试日志"}],
    "thread_id": "test_123",
    "enable_simple_research": true
  }'

# 3. 立即查看日志（应该能看到新记录）
python3 view_request_logs.py --limit 1 --verbose

# 4. 确认宿主机和容器内的文件是同步的
docker exec deer-flow-backend ls -lh /app/logs/requests/
```

## 📊 查看不同类型的日志

```bash
# 查看所有请求
python3 view_request_logs.py --type request

# 查看所有prompts
python3 view_request_logs.py --type prompt --limit 20

# 查看所有响应
python3 view_request_logs.py --type response

# 查看所有错误
python3 view_request_logs.py --type error --verbose
```

## 🐛 故障排查

### 问题1: 日志目录不存在

```bash
# 创建日志目录
mkdir -p /home/ubuntu/deer-flow/logs/requests

# 设置正确的权限
chmod -R 755 /home/ubuntu/deer-flow/logs

# 重启容器
docker-compose restart backend
```

### 问题2: 权限问题

```bash
# 检查目录权限
ls -la /home/ubuntu/deer-flow/logs/

# 修改所有者（如果需要）
sudo chown -R $USER:$USER /home/ubuntu/deer-flow/logs/

# 或者给予所有用户写权限
chmod -R 777 /home/ubuntu/deer-flow/logs/
```

### 问题3: 日志没有生成

```bash
# 1. 检查容器是否运行
docker-compose ps

# 2. 查看容器日志，看是否有错误
docker-compose logs backend | grep -i error

# 3. 进入容器测试日志系统
docker exec -it deer-flow-backend python test_request_logging.py

# 4. 检查卷映射是否正确
docker inspect deer-flow-backend | grep -A 10 Mounts
```

### 问题4: 看不到最新的日志

```bash
# 可能是缓存问题，尝试：
# 1. 刷新文件系统
sync

# 2. 使用 -f 参数实时查看
tail -f logs/requests/requests_2025_10.jsonl

# 3. 检查文件修改时间
stat logs/requests/requests_2025_10.jsonl
```

## 📦 备份日志

### 方式一：直接在宿主机备份
```bash
# 压缩备份
tar -czf logs_backup_$(date +%Y%m%d).tar.gz logs/

# 复制到备份目录
cp -r logs/ /backup/logs_$(date +%Y%m%d)/

# 同步到远程服务器
rsync -avz logs/ user@remote:/backup/deer-flow-logs/
```

### 方式二：从容器导出
```bash
# 从容器复制日志到宿主机
docker cp deer-flow-backend:/app/logs ./logs_backup

# 压缩
tar -czf logs_backup_$(date +%Y%m%d).tar.gz logs_backup/
```

## 🎯 最佳实践

1. **优先使用宿主机查看**：速度快，无需进容器
2. **定期备份**：日志文件会持续增长，定期备份重要日志
3. **监控磁盘空间**：使用 `df -h` 检查磁盘使用情况
4. **日志分析**：使用日志查看工具进行筛选和分析
5. **权限管理**：确保日志目录有正确的读写权限

## 📈 性能监控

```bash
# 查看日志文件大小
du -sh logs/requests/*

# 查看磁盘使用情况
df -h /home/ubuntu/deer-flow/logs/

# 统计请求数量
cat logs/requests/requests_2025_10.jsonl | wc -l

# 分析最活跃的时间段
cat logs/requests/requests_2025_10.jsonl | \
  jq -r '.timestamp' | \
  cut -d'T' -f1 | \
  sort | uniq -c
```

## 🔗 相关命令速查

```bash
# Docker相关
docker-compose up -d              # 启动服务
docker-compose down               # 停止服务
docker-compose restart backend    # 重启后端
docker-compose logs -f backend    # 查看后端日志
docker exec -it deer-flow-backend bash  # 进入容器

# 日志查看（宿主机）
python3 view_request_logs.py --summary          # 摘要
python3 view_request_logs.py --limit 10         # 最近10条
python3 view_request_logs.py --type error       # 错误日志
python3 view_request_logs.py --search "关键词"   # 搜索

# 文件操作
tail -f logs/requests/requests_2025_10.jsonl    # 实时查看
cat logs/requests/*.jsonl | wc -l               # 统计总数
du -sh logs/requests/                           # 查看大小
```

## 📞 需要帮助？

如果遇到问题：
1. 查看 [LOGGING_QUICKSTART.md](LOGGING_QUICKSTART.md) - 快速开始
2. 查看 [REQUEST_LOGGING.md](REQUEST_LOGGING.md) - 完整文档
3. 运行 `python3 test_request_logging.py` 测试日志系统
4. 检查容器日志 `docker-compose logs backend`

---

**总结**: 添加了卷映射后，你可以**直接在宿主机上查看日志**，无需进入Docker容器。这是最方便的方式！✨

