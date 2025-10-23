# Simple Researcher Node 测试文档

本文档说明如何测试 DeerFlow 后端的 `simple_researcher_node` 功能（餐饮智能助手节点）。

## 测试脚本说明

我们提供了三个测试脚本，分别用于不同层级的测试：

### 1. `test_api_quick.py` - 快速 API 测试（推荐）

**用途**: 快速测试后端 HTTP API 端点，最简单直接的测试方式。

**特点**:
- 无需依赖项目内部代码
- 直接测试 HTTP API
- 流式输出测试结果
- 适合快速验证后端功能

**使用方法**:
```bash
# 确保后端服务正在运行
docker ps | grep deer-flow-backend

# 运行测试
python3 test_api_quick.py
```

**依赖**: 需要安装 `httpx`
```bash
pip install httpx
```

---

### 2. `test_simple_api.sh` - Shell 脚本测试

**用途**: 使用 curl 命令测试 API 端点。

**特点**:
- 纯 shell 脚本，无需 Python 依赖
- 使用 curl 发送请求
- 适合在服务器环境快速测试

**使用方法**:
```bash
# 运行测试
./test_simple_api.sh
```

**依赖**: 需要 `curl` 命令（通常系统自带）

---

### 3. `test_simple_researcher.py` - 完整测试套件

**用途**: 多层级测试，包括单元测试、集成测试和端到端测试。

**特点**:
- 可以测试单个函数 (`simple_researcher_node`)
- 可以测试完整图流程 (`simple_graph`)
- 可以测试 HTTP API 端点
- 提供交互式菜单选择测试模式

**使用方法**:
```bash
# 运行测试（会显示交互式菜单）
python3 test_simple_researcher.py

# 选项说明:
# 1. 测试 simple_researcher_node 函数 (单元测试)
# 2. 测试 simple_graph 流程 (集成测试)
# 3. 测试后端 API 端点 (端到端测试)
# 4. 运行所有测试
```

**依赖**: 需要项目的完整依赖
```bash
# 在项目环境中运行
uv run python test_simple_researcher.py
```

---

## 测试前准备

### 1. 确保后端服务正在运行

```bash
# 查看服务状态
docker ps | grep deer-flow

# 如果服务未运行，启动服务
cd /home/ubuntu/deer-flow
docker-compose up -d

# 查看服务日志
docker logs -f deer-flow-backend
```

### 2. 确保 BM25 搜索服务正在运行

`simple_researcher_node` 依赖 BM25 搜索服务来检索内部文档。

```bash
# 查看 BM25 服务状态
docker ps | grep chinese-search

# 如果需要启动 BM25 服务
cd /home/ubuntu/chinese-bm25-search
docker-compose up -d
```

### 3. 检查配置文件

确保 `conf.yaml` 中配置了正确的 LLM 和工具设置：

```yaml
# conf.yaml 示例
llm:
  provider: "openai"  # 或其他 LLM 提供商
  model: "gpt-4"
  
tools:
  search_engine: "tavily"  # 或 "duckduckgo"
```

---

## 测试用例说明

所有测试脚本都包含以下测试用例：

### 测试用例 1: 查询菜品制作方法
- **查询**: "汤包怎么做？"
- **预期**: 返回汤包的制作方法，如果 BM25 搜索到相关文档，应引用文档内容

### 测试用例 2: 查询食材用量
- **查询**: "南京汤包需要多少盐？"
- **预期**: 返回具体的盐用量，应严格引用文档中的数据

### 测试用例 3: 查询出品标准
- **查询**: "汤包的出品标准是什么？"
- **预期**: 返回出品标准的详细说明

### 测试用例 4: 查询不存在的内容（仅在完整测试套件中）
- **查询**: "披萨怎么做？"
- **预期**: 说明文档中未找到相关信息，提供一般性建议

---

## 测试结果分析

### 成功的测试结果应包含：

1. **搜索状态消息**: "🔍 正在搜索内部文档..."
2. **搜索结果消息**: "✅ 搜索完成" + 找到的文件列表
3. **专业解答**: 基于搜索结果的详细回答

### 示例输出：

```
📦 事件 1: 状态更新
   类型: ai
   内容: 🔍 正在搜索内部文档...

📦 事件 2: 状态更新
   类型: ai
   内容: ✅ 搜索完成
📄 搜索到的文件：
- nanjing_tangbao.md

📦 事件 3: 状态更新
   类型: ai
   内容: 根据内部文档，南京汤包的制作方法如下：...
```

---

## 常见问题

### Q1: 测试脚本报错 "无法连接到后端服务"

**解决方法**:
```bash
# 检查后端服务状态
docker ps | grep deer-flow-backend

# 重启后端服务
cd /home/ubuntu/deer-flow
docker-compose restart backend

# 查看日志排查问题
docker logs deer-flow-backend
```

### Q2: 搜索结果为空或提示 "搜索服务暂时不可用"

**解决方法**:
```bash
# 检查 BM25 服务状态
docker ps | grep chinese-search

# 测试 BM25 服务
curl http://localhost:5003/health

# 查看 BM25 服务日志
docker logs chinese-search-api
```

### Q3: LLM 调用失败

**解决方法**:
- 检查 `.env` 文件中的 API 密钥是否正确
- 检查 `conf.yaml` 中的 LLM 配置
- 查看后端日志确认错误信息

### Q4: Python 依赖缺失

**解决方法**:
```bash
# 使用 uv 运行（推荐）
uv run python test_simple_researcher.py

# 或安装依赖
pip install httpx
```

---

## 调试技巧

### 1. 查看详细日志

```bash
# 实时查看后端日志
docker logs -f deer-flow-backend

# 查看最近 100 行日志
docker logs --tail 100 deer-flow-backend
```

### 2. 进入容器调试

```bash
# 进入后端容器
docker exec -it deer-flow-backend /bin/sh

# 在容器内测试
uv run python -c "from src.graph.nodes import simple_researcher_node; print('Import OK')"
```

### 3. 测试 BM25 搜索

```bash
# 直接测试 BM25 API
curl -X POST http://localhost:5003/search \
  -H "Content-Type: application/json" \
  -d '{"query": "汤包", "limit": 2}'
```

---

## 性能测试

如果需要进行性能测试，可以使用以下命令：

```bash
# 使用 ab (Apache Bench) 进行压力测试
ab -n 100 -c 10 -p request.json -T application/json \
  http://localhost:8000/api/chat/stream

# request.json 内容:
{
  "messages": [{"role": "user", "content": "汤包怎么做？"}],
  "thread_id": "perf_test",
  "enable_simple_research": true,
  "locale": "zh-CN"
}
```

---

## 贡献测试用例

如果您想添加新的测试用例，请编辑相应的测试脚本：

1. 在 `test_api_quick.py` 中的 `test_cases` 列表添加新用例
2. 在 `test_simple_api.sh` 中添加新的 curl 命令
3. 在 `test_simple_researcher.py` 中的 `test_cases` 列表添加新用例

---

## 联系与支持

如有问题或建议，请提交 Issue 或联系开发团队。

