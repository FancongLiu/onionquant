# 🧅 OnionQuant — 总导航

## 项目目标
构建**全球最强美股量化交易系统**，多技术路线并行研究，最终选出最优方案落地。

## 角色说明
| 角色 | 负责 |
|------|------|
| **董事长** | 最终决策者，只看汇报结论 |
| **CEO（Claude）** | 统筹全局，管理所有部门，做技术决策 |
| **各部门天才Agent** | 各自领域的深度研究与实现 |

## 快速导航（省Token指南）

> **重要**：新来的Agent请按需读取，不要一次性加载全部文件！

### 第一步：了解全局
- [公司架构](COMPANY_STRUCTURE.md) — 组织架构图、部门职责
- [研究路线总览](RESEARCH_ROADMAP.md) — 所有技术路线的概述

### 第二步：按需深入
- [公司文件索引](COMPANY_FILE_INDEX.md) — 所有文件的目录树与说明
- [知识图谱](KNOWLEDGE_GRAPH.md) — 公司级知识图谱中枢
- [任务追踪](TASK_TRACKER.md) — 当前所有任务的进度

### 第三步：部门工作
- 查看各部门的 `_INDEX.md` 了解该部门的工作内容
- 路径规则：`company/departments/<部门英文名>/`

## 项目文件结构
```
Python_code/
├── README.md                    ← 你在这里
├── COMPANY_STRUCTURE.md         ← 公司架构与组织图
├── RESEARCH_ROADMAP.md          ← 技术路线总览
├── COMPANY_FILE_INDEX.md        ← 全文件索引
├── KNOWLEDGE_GRAPH.md           ← 公司知识图谱
├── TASK_TRACKER.md              ← 任务追踪
├── config.py                    ← 全局配置
│
├── company/                     ← 公司管理体系
│   ├── departments/             ← 12个部门工作区
│   ├── reports/                 ← 向董事长的汇报
│   ├── debates/                 ← 部门间辩论记录
│   └── decisions/               ← 已做出的技术决策
│
├── quant_framework/             ← 实际的量化代码工程
│   ├── data/                    ← 数据层
│   ├── strategies/              ← 策略层
│   ├── backtest/                ← 回测层
│   ├── risk/                    ← 风控层
│   ├── execution/               ← 执行层
│   └── research/                ← 研究笔记
│
├── github_sync/                 ← GitHub同步工具
└── speedtest/                   ← 网速测试（临时）
```

## 工作流程
```
董事长指令 → CEO解读 → 部门分配任务 → 专家Agent执行研究
    → 部门内讨论 → 跨部门辩论 → CEO决策 → 汇报部门整理
    → 鞭策部门审核 → 向董事长汇报
```
