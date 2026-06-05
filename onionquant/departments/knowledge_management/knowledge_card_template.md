# 📇 知识卡片模板

## 模板

```yaml
id: "DEPT-XXX-001"
topic: "知识点标题"
type: "paper|tool|method|strategy|anti-pattern|conclusion|architecture|api"
summary: "一句话摘要（不超过50字）"
detail: |
  详细说明（可多行，但尽量精简）
conclusion: "我们的结论（如果已经有结论）"
confidence: "high|medium|low|unverified"
source:
  url: "https://..."
  file: "本地文件路径（如有）"
  date: "2026-05-17"
related_ids: ["DEPT-XXX-002", "DEPT-YYY-001"]
department: "部门英文名"
status: "researched|researching|todo|rejected|adopted"
created: "2026-05-17"
updated: "2026-05-17"
```

## 示例

```yaml
id: "OPEN-001"
topic: "Microsoft qlib - AI量化平台"
type: "tool"
summary: "微软开源的AI量化平台，支持因子挖掘、模型训练、回测、执行全流程"
detail: |
  qlib是微软开源的AI量化投资平台，覆盖数据→因子→模型→回测→执行全流程。
  核心优势：完整的AI模型集成(LSTM/GRU/Transformer等)，自动化因子挖掘。
  核心劣势：主要面向A股市场，美股需要数据适配。
  Stars: ~16k, 语言: Python, 许可证: MIT
conclusion: "适合作为AI量化能力参考和技术栈借鉴，但需要大量美股适配工作"
confidence: "high"
source:
  url: "https://github.com/microsoft/qlib"
  date: "2026-05-17"
related_ids: ["STRAT-003", "DATA-001"]
department: "open_source_research"
status: "researched"
created: "2026-05-17"
updated: "2026-05-17"
```
