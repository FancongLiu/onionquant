# 美股量化交易数据基础设施调研报告（第一轮）

> **调研日期：** 2026-05-17
> **调研人：** 首席数据架构师
> **范围：** 数据源、Pipeline 技术栈、特征存储、数据质量、编排调度

---

## 一、数据源对比

### 1.1 主流 API 综合对比表

| 维度 | yfinance | Alpha Vantage | Polygon.io | Finnhub | Tiingo | EODHD | Databento |
|------|----------|---------------|------------|---------|--------|-------|-----------|
| **费用** | 免费 | 免费 / $30-250/月 | 免费 / $29-79+/月 | 免费 / $80+/月 | ~$30/月 | $20-100/月 | 按量计费 |
| **实时性** | 15分钟延迟 | 15分钟延迟 | WebSocket实时(付费) | 20分钟延迟(免费版) | 实时(付费) | 实时(付费) | 实时 |
| **覆盖范围** | 美股/全球权益、期权、ETF、外汇、加密 | 美股、外汇、加密、技术指标 | 美股、期权、加密、外汇(偏美国) | 美股、加密、外汇、新闻 | 美股+加密 | 全球60+市场 | 美股深度数据 |
| **数据质量** | 中（爬虫不稳定，2025年Yahoo频繁封禁） | 中（免费层偶有空隙） | 低-中（Trustpilot 2.3/5，价格错误、分红缺失） | 中 | 高（无生存偏差） | 高 | 机构级 |
| **接入难度** | ⭐⭐⭐⭐⭐（pip install，无需key） | ⭐⭐⭐⭐（REST API） | ⭐⭐⭐（SDK齐全） | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **免费层限制** | 约2000次/小时（不可靠） | 5次/分钟，500次/天 | 5次/分钟，2年历史 | 60次/分钟 | 无免费层 | 有试用 | 无免费 |
| **期权数据** | 基础链 | 有限 | 有但质量差 | 有限 | 有限 | 好 | 好 |
| **生存偏差** | 高（退市股消失） | 有限 | 有限 | 有限 | 无（重要优势） | 有限 | 无 |
| **技术支持** | 社区 | 邮件 | 差（多个用户反馈黑洞） | 邮件/文档 | 好 | 好 | 企业级 |
| **2025年评级** | ⚠️ 不稳定（Yahoo主动封禁） | ⚠️ 可用但速率限制严重 | ⚠️ 质量下降明显 | ✅ 性价比之选 | ✅ 强烈推荐 | ✅ 强烈推荐 | ✅ 机构首选 |

### 1.2 IEX Cloud 关停后的格局变化

IEX Cloud 已于 **2024年8月31日正式关停**。原用户迁移路径：
- **Polygon.io** — 功能最接近，但费用从 $9-20/月升至 $29-99+/月
- **Tiingo** ($10/月) — 性价比替代
- **Interactive Brokers API** ($1.50/数据流/月) — 极低成本但需IB账户

### 1.3 学术数据源：WRDS / CRSP

| 特性 | 说明 |
|------|------|
| **提供方** | 宾夕法尼亚大学沃顿商学院 |
| **核心库** | CRSP（1925年起美股价格/收益/成交量）、Compustat（财务基本面）、CCM（CRSP+Compustat关联库） |
| **访问条件** | 仅限学术机构订阅，需用学校邮箱注册，双因素认证 |
| **费用** | 机构订阅制（通常由大学图书馆支付），个人无需付费 |
| **适用范围** | 学术研究、非商业用途 |
| **优势** | 权威性极高、无生存偏差、可做事件研究、资产定价研究 |

### 1.4 政府/免费可靠数据源

| 数据源 | 内容 | 访问方式 |
|--------|------|----------|
| **SEC EDGAR** | 公司财务报表(10-K/10-Q/XBRL) | 无需Key，加User-Agent头即可 |
| **FRED (圣路易斯联储)** | 816,000+经济时间序列(GDP/CPI/失业率/利率) | 免费API Key（即时注册） |
| **Treasury.gov** | 美国国债、拍卖、债券利率 | 无需Key |

### 1.5 免费方案推荐矩阵

| 使用场景 | 推荐方案 | 原因 |
|----------|----------|------|
| 快速原型/学习 | yfinance | 免费、无需Key、覆盖面广（容忍偶尔断服） |
| 轻量分析+技术指标 | Alpha Vantage | 免费层自带MACD/RSI等技术指标 |
| 高吞吐需求+新闻 | Finnhub | 免费层60次/分钟，包含公司新闻 |
| 基本面分析 | SEC EDGAR | 完全免费、无速率限制 |
| 宏观/经济背景 | FRED API | 81.6万+经济指标序列 |

### 1.6 付费方案推荐

| 使用场景 | 推荐方案 | 月费 | 关键优势 |
|----------|----------|------|----------|
| 严肃回测（个人） | Tiingo | ~$30 | 无生存偏差、数据干净 |
| 实时交易（美股） | Polygon.io | $99+ | WebSocket实时流 |
| 期权分析 | EODHD / Databento | $20-100+ | 高质量期权数据 |
| 机构级可靠性 | Databento / Nasdaq Data Link | 按量 | 机构级深度数据 |
| 宏观经济研究 | FRED + SEC EDGAR | 免费 | 权威经济指标+基本面 |

---

## 二、数据 Pipeline 技术栈选型

### 2.1 推荐架构图（ASCII Art）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        数据源层 (Data Sources)                           │
│  ┌──────────┐ ┌──────────┐ ┌───────┐ ┌──────────┐ ┌───────────────┐   │
│  │ Tiingo   │ │ Finnhub  │ │FRED   │ │SEC EDGAR │ │ WRDS/CRSP     │   │
│  │ REST API │ │ WebSocket│ │REST   │ │XBRL     │ │ (学术)       │   │
│  └────┬─────┘ └────┬─────┘ └───┬───┘ └────┬─────┘ └──────┬────────┘   │
│       │            │           │          │              │            │
└───────┼────────────┼───────────┼──────────┼──────────────┼────────────┘
        │            │           │          │              │
        ▼            ▼           ▼          ▼              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     采集层 (Ingestion)                                   │
│  ┌───────────────────────────────────────────────────────────┐         │
│  │  数据采集服务 (Python + httpx/aiohttp + WebSocket)          │         │
│  │  - 定时调度：APScheduler / Airflow Sensor                   │         │
│  │  - 增量拉取：只拉最新变动                                  │         │
│  │  - 限流控制：令牌桶算法 + 指数退避重试                      │         │
│  │  - 异常处理：断线重连 + 死信队列                            │         │
│  └──────────────────────┬────────────────────────────────────┘         │
└─────────────────────────┼───────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     原始数据层 (Raw / Bronze)                            │
│  ┌───────────────────────────────────────────────────────────┐         │
│  │  Apache Parquet + Hive分区                                 │         │
│  │  └── market_data/trades/symbol=MSFT/year=2026/month=05/   │         │
│  │      raw_trades_2026-05-17.parquet                         │         │
│  │  - 格式：Parquet (ZSTD压缩)                                │         │
│  │  - 分区策略：symbol + date                                 │         │
│  │  - 数据集：raw_trades, raw_quotes, raw_bars               │         │
│  └──────────────────────┬────────────────────────────────────┘         │
└─────────────────────────┼───────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     清洗与转换层 (ETL / Silver)                          │
│  ┌───────────────────────────────────────────────────────────┐         │
│  │  计算引擎：Polars (优于Pandas 5-100x)                       │         │
│  │  ┌────────────────────────────────────────────────────┐    │         │
│  │  │  数据质量门禁 (Great Expectations)                    │    │         │
│  │  │  - 架构校验：列类型、列存在性                        │    │         │
│  │  │  - 完整性检查：非空约束                              │    │         │
│  │  │  - 业务规则：借贷平衡、时间戳顺序                    │    │         │
│  │  │  - 异常检测：行数波动、价格范围                      │    │         │
│  │  └────────────────────────────────────────────────────┘    │         │
│  │  处理步骤：                                                │         │
│  │  1. 列类型规范化 (Decimal代替Float存价格)                  │         │
│  │  2. 时间戳统一为 UTC+0                                    │         │
│  │  3. 去重 (symbol + timestamp去重)                         │         │
│  │  4. 异常值过滤 (价格/成交量超出N个标准差)                  │         │
│  │  5. 缺失值插值 (前向填充/行业截面中位数)                   │         │
│  └──────────────────────┬────────────────────────────────────┘         │
└─────────────────────────┼───────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     特征工程层 (Gold + Feature Store)                     │
│  ┌───────────────────────────────────────────────────────────┐         │
│  │  离线特征 (Feast Offline Store)    在线特征 (Feast Online)  │         │
│  │  ┌────────────────┐  ┌──────────────┐                     │         │
│  │  │ DuckDB/Parquet │  │ Redis/       │                     │         │
│  │  │ + Time Travel  │  │ DragonflyDB  │                     │         │
│  │  └────────────────┘  └──────────────┘                     │         │
│  │  特征包含：                                                 │         │
│  │  - 基础OHLCV、收益率、对数收益率                            │         │
│  │  - 技术指标：RSI、MACD、布林带、ATR                         │         │
│  │  - 微观结构：买卖价差、订单不平衡度                          │         │
│  │  - 宏观因子：利率差分、VIX、行业轮动                        │         │
│  │  - 点时间一致性保证 (Point-in-Time Correctness)             │         │
│  └──────────────────────┬────────────────────────────────────┘         │
└─────────────────────────┼───────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     存储与分析层 (Storage & Serving)                     │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐        │
│  │ PostgreSQL +   │  │ DuckDB (本地   │  │ Grafana / Streamlit│        │
│  │ TimescaleDB    │  │ 快速分析)      │  │ 可视化监控         │        │
│  │ (时序超表)     │  └────────────────┘  └────────────────────┘        │
│  └────────────────┘                                                   │
│  - 连续聚合视图 (1秒→1分→1时→1天)                                     │
│  - 金融超函数 (candlestick_agg, vwap, 滚动统计)                       │
└─────────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     编排与监控层 (Orchestration & Observability)          │
│  ┌───────────────────────────────────────────────────────────┐         │
│  │  工作流编排：Prefect (或 Airflow 3.0)                       │         │
│  │  - 定时采集：每个交易日按NYSE时间调度                        │         │
│  │  - 事件驱动：盘后批量处理 + 盘中增量更新                     │         │
│  │  - 依赖管理：上下游任务依赖、重试与告警                      │         │
│  │  - 数据血缘：OpenLineage + Marquez                          │         │
│  └───────────────────────────────────────────────────────────┘         │
│  ┌───────────────────────────────────────────────────────────┐         │
│  │  数据质量监控：Great Expectations + 自定义校验规则           │         │
│  │  - 日活 dq: 数据新鲜度、完整性、一致性                      │         │
│  │  - 异常告警：Slack/Email/PagerDuty                         │         │
│  └───────────────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心技术选型建议

#### 存储

| 组件 | 推荐 | 备选 | 理由 |
|------|------|------|------|
| **原始数据湖** | Apache Parquet (ZSTD) | Delta Lake / Iceberg | 列存+高压缩比(可达91.6%压缩)，Hive分区，兼容Polars/DuckDB |
| **时序数据库** | TimescaleDB (PostgreSQL扩展) | ClickHouse, InfluxDB | 完整SQL兼容、金融超函数(candlestick_agg)、连续聚合自动刷新 |
| **本地快速分析** | DuckDB | SQLite | 嵌入式OLAP，直接在Parquet上查询，零配置 |
| **特征在线存储** | Redis / DragonflyDB | ScyllaDB | 毫秒级查找，Feast原生支持 |

#### 计算

| 组件 | 推荐 | 备选 | 理由 |
|------|------|------|------|
| **DataFrame引擎** | **Polars** | Pandas, DuckDB | 5-100x性能提升，Rust实现，原生多线程，惰性查询优化器 |
| **大规模处理** | DuckDB (单机) / Spark (集群) | Dask | DuckDB TPC-H SF-100仅需19.65s，超Pandas 94x |
| **流处理** | Kafka + Flink | Spark Streaming | 实时Tick数据处理 |

> **Polars vs Pandas 关键基准 (2025)**
> - 过滤操作: Pands 0.074s vs Polars 0.018s (**4x**)
> - 聚合操作: 0.186s vs 0.008s (**22x**)
> - GroupBy: 0.087s vs 0.011s (**8x**)
> - 50M行金融Tick数据: 83.4s vs 7.1s (**11.7x**)
> - TPC-H SF-10: 365.7s vs 3.89s (**94x**)

#### 编排调度

| 维度 | Airflow | Prefect | Dagster |
|------|---------|---------|---------|
| **开发者体验** | 复杂(DAG定义+Jinja) | ⭐ 简单(@flow/@task装饰器) | 中等(Asset-centric) |
| **动态工作流** | 弱(静态DAG) | ⭐ 强(运行时动态) | 中 |
| **事件驱动** | Airflow 3.0新加 | ⭐ 原生支持 | 中 |
| **数据血缘** | 需OpenLineage | 待完善 | ⭐ 原生Asset lineage |
| **社区规模** | ⭐⭐⭐⭐⭐ 最大 | ⭐⭐⭐⭐ 快速增长 | ⭐⭐⭐ |
| **运维复杂度** | 高(Scheduler+DB+Worker) | ⭐ 低(Prefect Cloud) | 中 |
| **dbt集成** | 差(BashOperator) | 中 | ⭐ 最佳 |
| **适用场景** | 传统批量ETL大厂 | **事件驱动/动态Pipeline** | 数据资产管理优先 |

> **推荐：Prefect**（中小团队/事件驱动/Dynamic workflow）或 **Airflow 3.0**（大厂/已有投资/批量为主）

#### 数据质量

| 工具 | 评级 | 核心能力 |
|------|------|----------|
| **Great Expectations** | ⭐⭐⭐⭐⭐ | 架构校验、完整性、业务规则、版本化、与Dagster/Prefect原生集成 |
| **dbt test** | ⭐⭐⭐⭐ | 与dbt转换管道集成，适合ELT模式 |
| **Soda Core** | ⭐⭐⭐⭐ | 开源SQL校验，轻量级 |

> GX在金融场景典型应用：FinTrust Bank案例将报表错误率从5%降至0.25%

### 2.3 特征存储：Feast

| 维度 | 说明 |
|------|------|
| **推荐理由** | 开源（Linux基金会），统一在线+离线特征，点时间一致性 |
| **离线存储** | DuckDB / BigQuery / Snowflake（历史训练数据+时间旅行） |
| **在线存储** | Redis / DragonflyDB（<10ms查询） |
| **金融应用** | 欺诈检测、实时风险评分、信用评分卡 |
| **版本管理** | 特征版本化、原子回滚（回滚时间从37分钟降至42秒） |
| **竞品** | Hopsworks（复杂聚合更强）、Tecton（商业版） |

---

## 三、GitHub 开源项目参考

### 3.1 完整数据Pipeline项目

| 项目 | 技术栈 | 亮点 |
|------|--------|------|
| [martinkilombe/financial-data-pipeline](https://github.com/martinkilombe/financial-data-pipeline) | Python 3.12+, PostgreSQL, Polygon.io+yFinance, SQLAlchemy, Alembic | 双数据源融合、NYSE时间感知调度、每日5万+记录 |
| [tiiimcheeen/Stock-Data-Pipeline](https://github.com/tiiimcheeen/Stock-Data-Pipeline) | Dagster, BigQuery, dbt, yfinance | 生产级ELT、dbt转换、自动邮件报表 |
| [Si944-byte/Finance-Data-OS](https://github.com/Si944-byte/Finance-Data-OS) | 自研 + Power BI | 端到端大数据系统、特征存储、回测框架 |
| [zsvoboda/ngods-stocks](https://github.com/zsvoboda/ngods-stocks) | Spark, Iceberg, Trino, dbt, Dagster | 现代数据栈完整Demo、容器化部署、ARIMA预测 |
| [ljwoodley/nasdaq100_elt](https://github.com/ljwoodley/nasdaq100_elt) | Dagster, dbt, DuckDB, Quarto | Nasdaq-100 ELT管道、OHLC+CAGR可视化 |

### 3.2 金融数据仓库

| 项目 | 说明 |
|------|------|
| [joemccann/market-data-warehouse](https://github.com/joemccann/market-data-warehouse) | 本地优先金融数仓，Parquet+DuckDB+ClickHouse，Medallion架构 |
| [Arctic (Man AHL)](https://www.mongodb.com/company/newsroom/press-releases/man-ahl-arctic-open-source) | 知名量化基金开源的高频Tick存储，25x性能提升 |
| [Flyanakin/CountMoney](https://github.com/flyanakin/CountMoney) | 极简低成本的金融数据Pipeline，仅需Python+SQL |

### 3.3 量化研究工具

| 项目 | 说明 |
|------|------|
| [stock-prediction-mlops](https://github.com/hifahd/stock-prediction-mlops) | 端到端MLOps，146+技术指标，MLflow追踪，81.7% AUC |
| [FinML-Toolkit](https://github.com/a-dorgham/FinML-Toolkit) | LSTM/GRU/Transformer模型+特征工程 |
| [paper-data](https://pypi.org/project/paper-data/) | YAML配置驱动资产定价研究Pipeline，Polars引擎 |
| [macrosynergy (J.P. Morgan)](https://pypi.org/project/macrosynergy/1.5.0/) | 量化宏观研究包，信号构建+组合优化+可视化 |

---

## 四、推荐实施方案

### 4.1 免费方案（个人/研究用）

```
数据源: yfinance (快速原型) + FRED (宏观) + SEC EDGAR (基本面)
↓
采集: Python httpx + 简单定时脚本 (APScheduler)
↓
存储: DuckDB (本地湖仓一体) / Parquet文件
↓
转换: Polars (5-100x性能)
↓
计算: DuckDB SQL 分析
↓
编排: Prefect (免费社区版)
↓
质量: Great Expectations (OOS核心)
↓
可视化: Streamlit / Grafana
↓
特征存储: 简单Parquet分区 (初期无需Feast)
```

**总成本：$0/月**（仅需计算资源 + 存储成本）

### 4.2 付费生产方案（团队/基金用）

```
数据源: Tiingo ($30/月) + Finnhub ($80/月) + FRED (免费)
↓
采集: Python + Kafka (实时) / Airflow (批量)
↓
存储: PostgreSQL + TimescaleDB (时序) + Parquet数据湖 (S3/OSS)
↓
转换: Polars (高性能DataFrame)
↓
质量: Great Expectations + 自定义监控
↓
编排: Prefect Cloud ($100/月) 或 Airflow 3.0 (自托管)
↓
特征存储: Feast (开源) + Redis (在线)
↓
可视化: Grafana + Streamlit
↓
回测: 自研/QuantConnect/Backtrader
```

**预估月成本：$160-250/月**（软件/API订阅，不含计算资源）

### 4.3 机构级方案

```
数据源: Databento / Nasdaq Data Link + WRDS/CRSP (学术)
↓
采集: Kafka + Flink (实时流)
↓
存储: Apache Iceberg (数据湖) + ClickHouse (OLAP) + Redis (在线)
↓
转换: Spark/Polars (分布式)
↓
质量: Great Expectations + dbt test + 血缘追踪
↓
编排: Airflow 3.0 (企业) + Dagster (dbt密集型)
↓
特征存储: Tecton (商业) 或 Feast (开源定制)
↓
可视化: Grafana + 自研Dashboard
↓
ML平台: MLflow / Kubeflow
```

**预估月成本：$2,000-10,000+/月**

---

## 五、关键结论与建议

### 5.1 核心推荐

1. **数据源决策**：放弃 yfinance 用于生产（Yahoo 2025年主动封禁），转向 Tiingo（个人性价比首选）或 Finnhub（免费层最慷慨）
2. **计算引擎迁移**：立即从 Pandas 迁移到 Polars，金融场景下可获 5-100x 性能提升，尤其在聚合/GroupBy/大数据量场景
3. **存储选型**：Parquet (ZSTD) 作为统一存储格式，TimescaleDB 处理时序实时查询，DuckDB 作为本地分析层
4. **编排选择**：中小团队优先 Prefect（开发者体验+事件驱动），大厂用 Airflow 3.0（生态成熟度）
5. **数据质量**：Great Expectations 作为金融数据质量门禁标准，从 Bronze 到 Gold 层层校验

### 5.2 需要进一步调研的领域

- [ ] 各数据源的实际数据质量对比（抽样验证误差率）
- [ ] 实时流处理方案（Kafka + Flink vs Pulsar + Spark Streaming）
- [ ] 回测引擎选型（QuantConnect, Backtrader, Zipline, 自研）
- [ ] 因子挖掘与特征工程最佳实践
- [ ] 数据合规（GDPR/SEC规则对数据存储的影响）
- [ ] 成本模型（云存储+计算全链路成本估算）
