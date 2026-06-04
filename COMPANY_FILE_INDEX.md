# 📑 公司文件索引（省Token导航）

> **用法**：新Agent接手时，先读此文件，按关键词找到目标文件，只读需要的部分。

## 全量文件树

```
Python_code/
├── README.md                              [必读] 总导航
├── COMPANY_STRUCTURE.md                   [必读] 组织架构与12部门职责
├── RESEARCH_ROADMAP.md                    [必读] 技术路线总览
├── COMPANY_FILE_INDEX.md                  [你在这里] 全文件索引
├── KNOWLEDGE_GRAPH.md                     [中枢] 公司知识图谱
├── TASK_TRACKER.md                        [动态] 任务进度追踪
├── config.py                              [配置] 全局配置
│
├── quant_framework/                       [代码] 量化工程 ✅代码开始产出
│   ├── data/raw/                          → 原始数据存储
│   ├── data/processed/                    → 清洗后数据
│   ├── data/fetchers/                     → ✅ yfinance_fetcher / alpha_vantage_fetcher / data_utils
│   ├── strategies/alpha/                  → Alpha因子
│   ├── strategies/signals/                → 🔵 canslm_screener / factor_calculator (生成中)
│   ├── backtest/engine/                   → 回测引擎
│   ├── backtest/results/                  → 回测结果
│   ├── risk/                              → 🔵 risk_metrics / portfolio_optimizer (生成中)
│   ├── execution/                         → 执行模块
│   ├── research/                          → 研究笔记
│   ├── utils/                             → 工具函数
│   └── config/                            → 量化配置
│
├── company/                               [管理] 公司管理体系
│   ├── departments/
│   │   ├── ceo_office/_INDEX.md           → CEO办公室
│   │   ├── strategy_research/_INDEX.md    → 策略研究部
│   │   ├── academic_research/_INDEX.md    → 学术研究部
│   │   ├── sentiment_intel/_INDEX.md      → 舆情情报部
│   │   ├── data_engineering/_INDEX.md     → 数据工程部
│   │   ├── backtest_engine/_INDEX.md      → 回测引擎部
│   │   ├── risk_management/_INDEX.md      → 风险管理部
│   │   ├── execution/_INDEX.md            → 交易执行部
│   │   ├── open_source_research/_INDEX.md → 开源研究院
│   │   ├── reporting/_INDEX.md            → 汇报展示部
│   │   ├── extreme_drive/_INDEX.md          → 极限驱动部
│   │   ├── continuous_evolution/_INDEX.md    → 持续进化部
│   │   ├── it_tech/_INDEX.md                 → IT技术部
│   │   ├── chairman_secretariat/_INDEX.md    → 董事长秘书处
│   │   └── knowledge_management/_INDEX.md    → 知识管理部
│   ├── chairman_office.html                  → 董事长Web办公室前端
│   ├── reports/                              → 向董事长汇报
│   ├── debates/                              → 跨部门辩论记录
│   └── decisions/                            → CEO技术决策
│
├── github_sync/                           [工具] GitHub同步
└── speedtest/                             [临时] 网速测试
```

## 按需求快速定位

| 你想做什么 | 读取这些文件 |
|------------|-------------|
| 了解全局 | README.md → COMPANY_STRUCTURE.md |
| 查某个部门在做什么 | company/departments/<部门>/_INDEX.md |
| 查任务进度 | TASK_TRACKER.md |
| 查技术决策历史 | company/decisions/*.md |
| 查部门间辩论 | company/debates/*.md |
| 查知识图谱 | KNOWLEDGE_GRAPH.md → 按部门链接进入 |
| 开始写代码 | quant_framework/<对应模块>/ |
| 向董事长汇报 | company/reports/ 下新建汇报文件 |
| 提交新研究成果 | 对应部门的 _INDEX.md + TASK_TRACKER.md |

## Token优化规则

1. **永远先读INDEX** — 不要直接遍历文件
2. **按需加载** — 每次只读1-2个文件，不要全量加载
3. **更新索引** — 每次新增/修改文件后，更新对应的_INDEX.md
4. **摘要原则** — 每个INDEX文件的第一段就是摘要，读完即可判断是否需要深入
