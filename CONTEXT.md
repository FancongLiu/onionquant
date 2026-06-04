# OnionQuant — 领域词汇表 (CONTEXT.md)

> 用途：Agent 和企业内所有人统一使用这些术语，避免同义替换导致的歧义。
> 规则：新增术语 → 新条目；模糊术语 → 澄清后更新；架构决策 → 写 ADR 而非 CONTEXT.md。
> 模式来源：mattpocock/skills — grill-with-docs

## 核心概念

- **因子 (Factor)**: 预测股票未来收益的信号变量。不是"特征"、"指标"、"信号"。
- **因子引擎 (Factor Engine)**: 计算、存储、管理因子的模块。输入原始数据 → 输出因子矩阵。
- **Alpha**: 因子对收益的解释力。不是"收益"、"超额收益"、"信号强度"的同义词。
- **因子中性化 (Neutralize)**: 剔除行业、市值等干扰因素对因子的影响。不是"去偏"、"正交化"。
- **因子标准化 (Standardize)**: Z-score 归一化 + 3-sigma 截尾（winsorization）。不是"归一化"、"缩放"。
- **因子组合 (Factor Combination)**: 将多个因子合并为综合信号。不是"因子融合"、"因子合并"。

## 策略相关

- **回测 (Backtest)**: 用历史数据模拟策略表现。不是"回溯"、"复盘"（复盘 = 项目总结）。
- **CAN SLIM**: William O'Neil 的 7 维度选股体系（Current earnings, Annual, New, Supply, Leader, Institutional, Market）。
- **日内动量 (Intraday Momentum)**: 当日开盘价 vs 前日收盘价的动量效应。学术名称：Overnight-Intraday Momentum。
- **VWAP (Volume-Weighted Average Price)**: 成交量加权均价。不是"加权均价"。
- **ATR (Average True Range)**: 基于真实波幅的波动率度量。不是标准差的直接替代。

## 数据相关

- **行情数据 (Market Data)**: OHLCV（Open, High, Low, Close, Volume）。不是"价格数据"、"K线数据"。
- **基本面数据 (Fundamentals)**: 财务报表数据（EPS, ROE, PE, PB 等）。不是"财务数据"、"财报"。
- **舆情数据 (Sentiment)**: 从新闻、社交媒体提取的情感信号。不是"情绪数据"、"NLP数据"。
- **替代数据 (Alternative Data)**: 非传统金融数据（卫星图、信用卡、Google Trends等）。不是"另类数据"。

## 基础设施

- **数据管道 (Data Pipeline)**: ETL 流程：拉取 → 清洗 → 存储 → 特征工程 → 因子计算。不是"数据流"。
- **因子快照 (Factor Snapshot)**: 某个时间点所有股票的因子值矩阵。TimescaleDB 存储为宽表。
- **Hypertable**: TimescaleDB 的分区表，按时间自动分片。不是"分区表"、"分表"。
- **Dagster Asset**: 数据资产的声明式定义，Dagster 的核心抽象。不是"任务"（task 是 Airflow 术语）。

## 虚拟公司

- **部门 (Department)**: 虚拟公司中的职能单元，每个部门有独立 _INDEX.md。不是"团队"、"组"。
- **董事长 (Chairman)**: 用户/决策者。Agent 通过 outbox 向董事长请示。
- **收件箱 (Inbox)**: 董事长 → Agent 的指令通道。`company/chairman_inbox/`。
- **发件箱 (Outbox)**: Agent → 董事长的请示通道。`company/chairman_outbox/`。
- **铁律 (Iron Rule)**: 不可妥协的规则（如"不手搓"、"不确定先问"）。不是"规则"、"policy"。

## 架构术语（来自 mattpocock/skills）

- **模块 (Module)**: 任何有接口和实现的东西（函数、类、包）。接口 = 调用方必须知道的一切。
- **深度 (Depth)**: 杠杆 — 小接口背后藏大量行为。深模块 = 高杠杆。浅模块 = 接口几乎和实现一样复杂。
- **接缝 (Seam)**: 接口所在处，行为可在此改变而不修改原地代码。不是"边界"、"API层"。
- **适配器 (Adapter)**: 满足接缝处接口的具体实现。1个适配器=假设缝，2个=真实缝。
- **局部性 (Locality)**: 变更、bug、知识集中在同一处。手搓代码分散在N个文件=局部性差。
- **杠杆 (Leverage)**: 调用方从深度获得的价值。Qlib 给 158 个因子 = 高杠杆。

## 禁止同义词

| 正确术语 | 禁止替换 |
|---------|---------|
| 因子 | 特征、指标 |
| 中性化 | 去偏、正交化 |
| 回测 | 回溯、复盘 |
| 发件箱 | 消息队列、通知 |
| 接缝 | 边界、接口层 |
| 模块 | 组件、服务、微服务 |
