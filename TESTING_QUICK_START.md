# 测试快速开始指南

## 🚀 快速测试 Simple Researcher Node

### 最简单的方式（推荐）

```bash
cd /home/ubuntu/deer-flow
./test_simple_api.sh
```

这个脚本会：
- ✅ 检查后端服务是否运行
- ✅ 测试两个查询示例
- ✅ 显示流式响应结果

---

## 📋 所有测试脚本

| 脚本 | 用途 | 运行命令 |
|------|------|----------|
| `test_simple_api.sh` | 最简单的 curl 测试 | `./test_simple_api.sh` |
| `test_api_quick.py` | Python API 测试 | `python3 test_api_quick.py` |
| `test_simple_researcher.py` | 完整测试套件 | `uv run python test_simple_researcher.py` |

---

## 🔍 测试什么？

这些脚本测试 **Simple Researcher Node** 功能，这是一个餐饮智能助手节点，用于：

1. 🔎 搜索内部文档（使用 BM25 搜索）
2. 📚 基于搜索结果生成专业回答
3. 💬 流式返回响应内容

---

## ⚙️ 前置条件

### 1. 确保服务运行

```bash
# 查看服务状态
docker ps | grep deer-flow

# 如果没有运行，启动服务
docker-compose up -d
```

### 2. 检查服务健康

```bash
# 检查后端 API
curl http://localhost:8000/api/config

# 检查 BM25 搜索服务
curl http://localhost:5003/health
```

---

## 📖 测试示例

### 示例 1: 使用 Shell 脚本

```bash
./test_simple_api.sh
```

**输出示例**:
```
==========================================
测试 DeerFlow Simple Researcher API
==========================================

✅ 后端服务正在运行

测试 API 端点: http://localhost:8000/api/chat/stream
------------------------------------------

📝 测试用例 1: 查询汤包制作方法

event: message_chunk
data: {"content": "🔍 正在搜索内部文档..."}

event: message_chunk
data: {"content": "✅ 搜索完成\n📄 搜索到的文件：\n- nanjing_tangbao.md"}

event: message_chunk
data: {"content": "根据内部文档，南京汤包的制作方法..."}
```

### 示例 2: 使用 Python 脚本

```bash
python3 test_api_quick.py
```

或使用 uv（推荐）:

```bash
uv run python test_api_quick.py
```

---

## 🐛 故障排查

### 问题 1: 无法连接到后端服务

```bash
# 检查服务状态
docker ps | grep deer-flow-backend

# 重启服务
docker-compose restart backend

# 查看日志
docker logs -f deer-flow-backend
```

### 问题 2: BM25 搜索失败

```bash
# 检查 BM25 服务
docker ps | grep chinese-search

# 测试 BM25 API
curl -X POST http://localhost:5003/search \
  -H "Content-Type: application/json" \
  -d '{"query": "汤包", "limit": 2}'
```

### 问题 3: Python 依赖缺失

```bash
# 安装 httpx
pip install httpx

# 或使用 uv（推荐）
uv pip install httpx
```

---

## 📚 详细文档

- **详细测试指南**: `TEST_SIMPLE_RESEARCHER.md`
- **测试总结报告**: `TEST_SUMMARY.md`
- **项目 README**: `README.md`

---

## 💡 提示

1. **首次运行**: 使用 `./test_simple_api.sh`，最简单快速
2. **调试问题**: 使用 `test_api_quick.py`，有详细的错误信息
3. **完整测试**: 使用 `test_simple_researcher.py`，包含多层级测试

---

## 🎯 测试目标

测试脚本验证以下功能：

- ✅ HTTP API 端点正常工作
- ✅ BM25 搜索集成正常
- ✅ 流式响应正常输出
- ✅ LLM 生成回答正常
- ✅ 错误处理机制正常

---

## 📞 获取帮助

如有问题，请查看：
1. 后端日志: `docker logs deer-flow-backend`
2. BM25 日志: `docker logs chinese-search-api`
3. 详细文档: `TEST_SIMPLE_RESEARCHER.md`

---

**快速开始，立即测试！** 🚀

