# BM25中文检索服务集成指南

本指南介绍如何在DeerFlow中集成和使用BM25中文检索服务。

## 概述

BM25集成为DeerFlow添加了强大的中文文档检索能力，研究员智能体现在可以：

- 🔍 使用BM25算法搜索中文文档
- 📊 获取服务状态和统计信息
- 🎯 优先使用BM25搜索中文内容
- 🔄 在BM25搜索失败时回退到web搜索

## 文件结构

```
src/
├── tools/
│   └── bm25_search.py          # BM25检索工具
├── graph/
│   └── nodes.py                # 修改了researcher_node
└── prompts/
    └── researcher.md           # 更新了提示词模板

test_bm25_integration.py        # 集成测试脚本
example_bm25_usage.py           # 使用示例脚本
BM25_INTEGRATION_README.md      # 本说明文档
```

## 新增工具

### 1. bm25_search_tool
- **功能**: 搜索中文文档
- **参数**: 
  - `query`: 搜索查询（中文）
  - `limit`: 返回结果数量（默认3）
  - `include_snippets`: 是否包含文档片段（默认True）
  - `server_url`: BM25服务URL（默认http://localhost:5003）

### 2. bm25_health_check_tool
- **功能**: 检查BM25服务健康状态
- **返回**: 服务状态、文档数、词汇量

### 3. bm25_stats_tool
- **功能**: 获取BM25服务统计信息
- **返回**: 文档总数、词汇量、平均长度、热门词汇

## 使用方法

### 1. 启动BM25服务

确保你的BM25服务在 `http://localhost:5003` 运行：

```bash
# 启动BM25服务（根据你的部署方式）
./deploy.sh
# 或者
python your_bm25_server.py
```

### 2. 启动DeerFlow

```bash
# 启动DeerFlow
uv run main.py

# 或者使用交互模式
uv run main.py --interactive
```

### 3. 使用中文搜索

现在你可以使用中文查询，研究员会自动使用BM25工具：

```
请搜索关于藕汤的中文资料
筒骨煨藕汤的制作方法
铫子筒骨煨藕汤产品标准
```

## 测试和验证

### 1. 运行集成测试

```bash
python test_bm25_integration.py
```

这个脚本会测试：
- BM25工具功能
- 研究员节点集成
- 提示词模板更新

### 2. 运行使用示例

```bash
python example_bm25_usage.py
```

这个脚本提供：
- 完整工作流示例
- 直接工具使用示例

### 3. 手动测试

```python
from src.tools.bm25_search import bm25_search_tool

# 测试搜索
result = bm25_search_tool.invoke("藕汤")
print(result)
```

## API格式

BM25服务需要支持以下API格式：

### 健康检查
```
GET /health
Response: {
    "status": "healthy",
    "documents_count": 1000,
    "vocabulary_size": 5000
}
```

### 搜索
```
POST /search
Request: {
    "query": "搜索查询",
    "limit": 3,
    "include_snippets": true
}
Response: {
    "results": [
        {
            "title": "文档标题",
            "content": "文档内容",
            "score": 0.95,
            "snippet": "内容片段"
        }
    ],
    "search_time_seconds": 0.123
}
```

### 统计信息
```
GET /stats
Response: {
    "statistics": {
        "documents_count": 1000,
        "vocabulary_size": 5000,
        "average_document_length": 150.5,
        "top_terms": [
            {"term": "词汇", "frequency": 100}
        ]
    }
}
```

## 工作流程

1. **用户输入中文查询**
2. **协调器识别查询类型**
3. **规划器制定研究计划**
4. **研究员使用BM25工具搜索**
5. **整合搜索结果**
6. **报告员生成最终报告**

## 故障排除

### 1. BM25服务连接失败

```
❌ BM25搜索服务连接失败: Connection refused
```

**解决方案**:
- 检查BM25服务是否运行
- 确认服务地址为 `http://localhost:5003`
- 检查防火墙设置

### 2. 搜索结果为空

```
未找到与 '查询' 相关的结果
```

**解决方案**:
- 检查BM25服务是否有数据
- 尝试不同的搜索词
- 检查服务日志

### 3. 工具未加载

```
BM25搜索工具未启用
```

**解决方案**:
- 检查 `src/graph/nodes.py` 中的导入
- 确认 `src/tools/bm25_search.py` 存在
- 重启DeerFlow服务

## 配置选项

### 环境变量（可选）

```bash
# .env文件
BM25_SERVER_URL=http://localhost:5003
ENABLE_BM25_SEARCH=true
```

### 自定义服务器地址

```python
# 在工具调用时指定
result = bm25_search_tool.invoke(
    query="搜索查询",
    server_url="http://your-bm25-server:5003"
)
```

## 性能优化

1. **调整搜索限制**: 根据需要调整 `limit` 参数
2. **缓存结果**: 考虑在BM25服务端实现结果缓存
3. **并发搜索**: BM25工具支持并发调用
4. **超时设置**: 默认超时10秒，可根据需要调整

## 扩展功能

### 1. 添加更多BM25工具

```python
@tool
def bm25_advanced_search_tool(
    query: str,
    filters: dict = None,
    sort_by: str = "score"
) -> str:
    # 实现高级搜索功能
    pass
```

### 2. 集成其他检索服务

```python
@tool
def hybrid_search_tool(
    query: str,
    use_bm25: bool = True,
    use_web: bool = True
) -> str:
    # 实现混合搜索
    pass
```

## 贡献

如果你有改进建议或发现问题，请：

1. 提交Issue描述问题
2. 创建Pull Request提供修复
3. 更新文档说明变更

## 许可证

本集成遵循DeerFlow项目的MIT许可证。
