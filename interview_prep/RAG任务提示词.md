# OnionQuant RAG 模块 — Agent 实施任务

## 背景
OnionQuant 是一个多智能体量化分析系统。在 `company/reports/` 目录下有 70+ 份历史研究报告（Markdown 格式），目前靠文件系统搜索，无法做语义检索。需要给项目加上 RAG 模块，让用户能用自然语言搜索历史研报。

## 你的任务

### Phase 1：技术选型（先研究，再动手）
研究以下问题，给出推荐方案：
1. Embedding 模型：中文研报用哪个模型？候选：BGE-large-zh、BGE-M3、text2vec-large-chinese
2. 向量数据库：本地运行用哪个？候选：ChromaDB、Qdrant(Qdrant 内存版)
3. 分块策略：研报通常是 2000-5000 字，怎么分块？
4. 检索方式：纯向量检索？还是混合检索（BM25 + 向量）？
5. 要不要 Reranking？

要求：方案必须能在 16GB 内存 Windows 电脑上本地运行，不需要 GPU，不需要云服务。

### Phase 2：实施
1. 在 `onionquant/` 下创建 `rag/` 模块
2. 实现文档加载（读取 reports/ 目录下所有 .md 文件）
3. 实现分块 + Embedding + 向量存储
4. 实现检索接口（输入查询，返回最相关的 Top-K 文档片段）
5. 实现一个简单的 FastAPI 端点，挂到现有 server.py 上

### Phase 3：更新文件
1. 更新 `pyproject.toml` 加新依赖
2. 更新 `README.md` 在 Technical Stack 表里加一行 RAG
3. 如果创建了新 skill，写 SKILL.md

## 约束
- Python 3.12，用 `pip install` 安装依赖
- 所有依赖添加到 `requirements.txt`
- 代码风格和项目现有代码一致
- 不引入 Docker
- 研报目录路径：`company/reports/`
- 向量数据存储目录：`onionquant/rag/vector_store/`
