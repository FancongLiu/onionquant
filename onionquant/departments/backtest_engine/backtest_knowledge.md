# 回测引擎知识图谱

> 领域知识的结构化表示，涵盖回测引擎的核心概念、技术方案、优化手段及其关系。
> 版本: v1.0 | 更新: 2026-05-17

---

## 1. 核心概念 (Core Concepts)

```
回测引擎 (Backtest Engine)
    ├── 按执行模式
    │   ├── [EVENT_DRIVEN]  事件驱动模式
    │   │   └── 逐 Bar/Tick 执行策略逻辑，模拟真实事件流
    │   │   ├── 代表: Backtrader, Zipline, LEAN, NautilusTrader, vnpy
    │   │   └── 优势: 模拟精度高，适合复杂订单逻辑
    │   │
    │   ├── [VECTORIZED]  向量化模式
    │   │   └── 一次性在整个数据集上计算信号和持仓
    │   │   ├── 代表: VectorBT, Qlib
    │   │   └── 优势: 速度极快，适合参数扫描
    │   │
    │   └── [HYBRID]  混合模式
    │       └── 向量化计算指标 + 事件驱动执行策略
    │       ├── 代表: backtesting.py, RustyBT
    │       └── 优势: 兼顾速度与精度
    │
    ├── 按数据粒度
    │   ├── TICK_LEVEL (毫秒/微秒级)
    │   ├── OHLCV (1m/5m/1h/1d)
    │   └── SNAPSHOT (定频采样)
    │
    └── 按部署方式
        ├── LOCAL (本地部署)
        ├── CLOUD (云端托管)
        └── HYBRID (本地开发+云端回测)
```

---

## 2. 工程架构 (Architecture)

```
典型事件驱动回测引擎架构

┌──────────────────────────────────────────────────────────────┐
│                      User Layer (用户层)                      │
│  Strategy A │ Strategy B │ Research Notebook │ 分析工具      │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                    Engine Layer (引擎层)                      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │                   Event Bus / MessageBus              │    │
│  │  (market_data | orders | fills | signals | risk)      │    │
│  └──┬──────┬──────┬──────┬──────┬───────────────────────┘    │
│     │      │      │      │      │                            │
│     ▼      ▼      ▼      ▼      ▼                            │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐                        │
│  │Data│ │Stra│ │Port│ │Risk│ │Exec│                        │
│  │Hdlr│ │tegy│ │folio│ │Mgr │ │Hdlr│                        │
│  └────┘ └────┘ └────┘ └────┘ └────┘                        │
│                                                              │
└──────────────────────────────────┬───────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────┐
│                  Infrastructure Layer (基础设施层)             │
│                                                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────────────────┐   │
│  │  Data Store │ │ Order Book │ │  Performance Analyzer │   │
│  │ (Parquet/   │ │ Simulation │ │  (Sharpe/DD/Metrics)  │   │
│  │  Arrow/HDF5)│ │            │ │                       │   │
│  └────────────┘ └────────────┘ └────────────────────────┘   │
│                                                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────────────────┐   │
│  │  Slippage  │ │ Commission │ │  Market Impact Model   │   │
│  │  Models    │ │  Models    │ │  (Almgren-Chriss etc.) │   │
│  └────────────┘ └────────────┘ └────────────────────────┘   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 关键技术决策点

```
Component_Sourcing: 数据接入
    ├── 内建数据 (QuantConnect 100+ sources, vnpy CTP)
    ├── 自带数据 (文件: CSV/Parquet/Arrow/HDF5)
    └── 外部 API (IBKR, CCXT, Alpaca, Polygon)

Order_Execution: 订单执行模型
    ├── Immediate (立即成交)
    ├── VolumeShare (按成交量比例)
    ├── OrderBookWalk (逐档吃单)
    └── Almgren-Chriss (市场冲击模型)

Portfolio_Accounting: 组合记账
    ├── SingleAsset (单一资产)
    ├── MultiAsset (多资产)
    └── MultiCurrency (多币种)

Risk_Management: 风控模型
    ├── PositionSizing (头寸规模)
    ├── StopLoss (止损)
    ├── MaxDrawdown (最大回撤)
    └── VaR/CVaR (在险价值)
```

---

## 3. 技术栈全景 (Technology Landscape)

```
                    ┌──────────────────────────────────────────┐
                    │      QUANT BACKTESTING STACK 2025        │
                    └──────────────────────────────────────────┘

LANGUAGE LAYER
    ├── Python (主力): 策略开发、数据分析
    │   ├── pandas / polars → 数据操作
    │   ├── numpy / numba → 数值计算加速
    │   └── scipy / sklearn → 统计分析/ML
    ├── Rust (核心引擎): NautilusTrader, GlowBack
    │   └── PyO3 / maturin → Python 绑定
    ├── C# (全栈): QuantConnect LEAN
    └── C++ (特定场景): AlphaMatrix (C++ gateway), vnpy (部分模块)

PERFORMANCE LAYER
    ├── [ACCELERATION] 加速技术
    │   ├── Numba JIT (@njit) → 50-200x 加速
    │   ├── Numba CUDA (@cuda) → 100x+ (GPU加速)
    │   ├── Rust PyO3 绑定 → 10-100x
    │   ├── Cython → 2-10x
    │   └── CuPy → GPU 数组计算
    │
    ├── [PARALLELISM] 并行策略
    │   ├── Multiprocessing (多进程) → 参数网格搜索
    │   ├── Ray → 分布式计算集群
    │   ├── Dask → 大规模并行 DataFrame
    │   └── Numba prange → 多线程并行循环
    │
    └── [DATA_ENGINEERING] 数据工程优化
        ├── Parquet / Arrow / ORC → 列式存储
        ├── Memory Mapping (mmap) → 超大文件
        ├── float32 精度 → 内存减半
        └── Chunked Processing → 分块处理防 OOM

STORAGE LAYER
    ├── Parquet (+50-80% 压缩比 vs CSV)
    ├── Arrow (零拷贝列式格式)
    ├── HDF5 (Zipline 传统格式)
    └── SQL / ClickHouse / InfluxDB (时间序列库)

BROKER INTEGRATION LAYER
    ├── Interactive Brokers (IBKR / TWS) → 美股主流
    ├── CCXT → 统一加密交易所接口
    ├── CTP (中国期货)
    ├── Alpaca → 零佣金美股
    └── Oanda / FXCM → 外汇

DATA PROVIDER LAYER
    ├── Polygon / IQFeed / Quandl → 美股数据
    ├── Bloomberg / Refinitiv → 机构级
    ├── Yahoo Finance / Alpha Vantage → 免费
    └── AKShare / Tushare → A股数据
```

---

## 4. 滑点与市场冲击模型 (Slippage & Impact Models)

```
SLIPPAGE_MODEL HIERARCHY

[FIXED_MODELS]  固定滑点
    ├── FixedSlippage: 每笔固定金额 (如 $0.01/股)
    └── FixedBasisPointsSlippage: 固定基点 (如 5 bps)

[VOLUME_MODELS]  成交量相关
    ├── VolumeShareSlippage: 订单大小/成交量比率
    │   formula: slippage = base_spread * (order_volume / bar_volume)^power
    └── VolumeShareDecimal: + 波动率调整

[ORDER_BOOK_MODELS]  订单簿模型
    ├── BidAskSpreadSlippage: 买卖价差
    └── OrderBookWalk: 逐级吃单直到订单完全成交

[IMPACT_MODELS]  市场冲击模型
    └── Almgren-Chriss Model
        ├── Permanent Impact (永久冲击)
        │   formula: I_permanent = gamma * sigma * (Q / V)^alpha
        └── Temporary Impact (临时冲击)
            formula: I_temporary = eta * sigma * (Q / (V * delta))^beta
        ├── Parameters:
        │   gamma, eta → 冲击系数
        │   sigma → 年化波动率
        │   Q → 订单数量 | V → 日均成交量
        │   delta → 相对时间跨度
        │   alpha, beta → 冲击指数 (通常 ~0.3-0.6)
        └── 实现: Quant Trade Simulator, Crypto Trade Simulator

[ML_MODELS]  机器学习滑点预测
    ├── Linear Regression → 滑点估计
    ├── Logistic Regression → 吃单/挂单概率
    └── Deep Learning → LSTM 时序预测
```

---

## 5. 风险评估与过拟合检测 (Risk & Overfitting)

```
OVERFITTING_DETECTION
    ├── Walk-Forward Analysis (滚动交叉验证)
    ├── Monte Carlo Simulation (蒙特卡洛模拟)
    │   └── 随机打乱交易序列 → 评估策略鲁棒性
    ├── Deflated Sharpe Ratio (DSR)
    │   └── 修正多重测试偏差的夏普比率
    ├── NumPy of False Strategies (随机策略分布)
    ├── Cross-Validation (时间序列交叉验证)
    └── Out-of-Sample Testing (样本外测试)

PERFORMANCE_METRICS
    ├── Return Metrics
    │   ├── CAGR (复合年化增长率)
    │   ├── Total Return (总收益率)
    │   └── Annualized Volatility (年化波动率)
    ├── Risk Metrics
    │   ├── Max Drawdown (最大回撤)
    │   ├── VaR / CVaR (在险价值)
    │   └── Downside Deviation (下行偏差)
    ├── Risk-Adjusted Metrics
    │   ├── Sharpe Ratio (夏普比率)
    │   ├── Sortino Ratio (索提诺比率)
    │   ├── Calmar Ratio (卡玛比率)
    │   └── Information Ratio (信息比率)
    └── Statistical Tests
        ├── T-test on Strategy Returns
        ├── Stationarity Test (平稳性检验)
        └── Correlation Analysis (相关性分析)
```

---

## 6. 方案对比矩阵 (Solution Matrix)

```
HIGH_PERFORMANCE_PYTHON_ENGINES (GitHub 2025)
    │ Stars  │ Engine        │ Pattern       │ Language   │ Speed Profile │ Best Use
    ├── ~19k │ backtrader    │ Event-Driven  │ Python     │ ★★☆☆☆        │ 学习/小型
    ├── ~16k │ nautilus_tdr  │ Event-Driven  │ Rust+Python│ ★★★★★        │ 生产级/高性能
    ├── ~16k │ qlib          │ AI/Vectorized │ Python     │ ★★★★☆        │ AI量化研究
    ├── ~13k │ zipline-rel   │ Event-Driven  │ Python     │ ★★☆☆☆        │ 因子研究(衰退)
    ├── ~8.3k│ backtesting.py│ Hybrid        │ Python     │ ★★★☆☆        │ 轻量通用
    ├── ~7k  │ vectorbt      │ Vectorized    │ Python     │ ★★★★★        │ 参数优化
    ├── ~3.9k│ hftbacktest   │ Tick-Level    │ Python     │ ★★★★★        │ HFT/做市
    └── New  │ rustybt       │ Hybrid        │ Rust+Python│ ★★★★☆        │ Zipline替代

COMMERCIAL_PLATFORMS
    │ Platform       │ Pricing         │ Language   │ Asset Class      │ Best Use
    ├── QuantConnect  │ $0-$80+/mo     │ C#/Python  │ Multi-Asset      │ 专业量化
    ├── QuantRocket   │ Subscription   │ Python     │ IB-Focused       │ IB重度用户
    ├── TradingView   │ $0-$50/mo      │ PineScript │ Stocks/Crypto    │ 可视化验证
    ├── Amibroker     │ $199-$399 一次性│ AFL       │ US Stocks        │ 极速扫描
    ├── MultiCharts   │ 高价许可       │ EasyLang   │ Futures          │ 专业期货
    └── NinjaTrader   │ $0-$1000+     │ C#         │ Futures          │ 期货/日交易
    
CUSTOM_BUILD_OPTIONS
    │ Approach                │ Est. Effort │ Performance │ Flexibility │ Risk
    ├── Pure Python Event     │ 3-4 wk MVP  │ ★★☆☆☆      │ ★★★★★       │ 中
    ├── Python + Numba        │ 4-6 wk      │ ★★★★☆      │ ★★★★★       │ 低中
    ├── Rust Core + PyO3      │ 8-12 wk     │ ★★★★★      │ ★★★★★       │ 高
    └── NautilusTrader Fork   │ 2-4 wk      │ ★★★★★      │ ★★★★☆       │ 低
```

---

## 7. 关键关系图 (Key Relationships)

```
# 关系类型:
# [uses] → A 使用 B
# [implemented_by] → A 由 B 实现
# [competes_with] → A 与 B 竞争
# [supersedes] → A 替代 B
# [based_on] → A 基于 B
# [depends_on] → A 依赖 B

# 引擎-技术关系
NautilusTrader --uses--> Rust (tokio + PyO3)
NautilusTrader --uses--> Python (策略接口)
NautilusTrader --supersedes--> Backtrader
NautilusTrader --competes_with--> QuantConnect LEAN

QuantConnect LEAN --uses--> C# (核心引擎)
QuantConnect LEAN --uses--> Python (算法接口)
QuantConnect LEAN --depends_on--> Docker (本地部署)

VectorBT --uses--> NumPy + Numba + Pandas
VectorBT --competes_with--> Backtrader (性能维度的降维打击)
VectorBT --used_for--> Parameter Optimization

Backtrader --superseded_by--> NautilusTrader (生产替代)
Backtrader --still_relevant_for--> Learning/Education

# 加速技术-引擎关系
Numba JIT --used_by--> VectorBT
Numba CUDA --used_by--> Custom Engines (GPU加速)
Rust PyO3 --used_by--> NautilusTrader
Rust PyO3 --used_by--> GlowBack
Polars --used_by--> RustyBT

# 数据关系
Parquet --replaces--> CSV (5-10x faster reads)
Arrow --enables--> Zero-Copy Data Sharing
Memory Mapping --enables--> Super-Large Dataset Processing

# 部署关系
LEAN CLI Local Dev --> LEAN Cloud Backtest --> LEAN Cloud Live
NautilusTrader Local Dev --> NautilusTrader Live (same code path)
vnpy Local (CTP) --> vnpy Live (CTP Gateway)
```

---

## 8. 技术债务与迁移路径 (Migration Paths)

```
Legacy → Modern Migration Paths

BACKTRADER USERS:
    Backtrader (2019, 停更)
        ├── 需要高性能 → VectorBT (研究层) + NautilusTrader (回测层)
        ├── 需要事件驱动 → NautilusTrader (API 不同, 需重写策略)
        └── 需要实盘 → vnpy (中国市场) 或 QuantConnect (全球市场)

ZIPLINE USERS:
    Zipline (Quantopian 关闭)
        ├── 最小改动 → Zipline-Reloaded (临时过渡)
        ├── 现代化改造 → RustyBT (兼容 API, 高性能)
        └── 更换引擎 → NautilusTrader (完全重写, 最佳长期方案)

自研 PURE PYTHON:
    Custom Python Engine (早期手工实现)
        ├── 性能不足 → 嵌入 Numba JIT (最小改动)
        ├── 架构重构 → 迁移至 NautilusTrader 架构 (推荐)
        └── 完全重写 → Rust + PyO3 (高成本高收益)
```

---

## 9. 推荐阅读与参考 (References)

### 开源项目
- NautilusTrader: https://github.com/nautechsystems/nautilus_trader
- QuantConnect LEAN: https://github.com/QuantConnect/Lean
- VectorBT: https://github.com/polakowo/vectorbt
- backtesting.py: https://github.com/kernc/backtesting.py
- vnpy: https://github.com/vnpy/vnpy
- Qlib: https://github.com/microsoft/qlib
- hftbacktest: https://github.com/nkaz001/hftbacktest
- RustyBT: https://github.com/jerryinyang/rustybt
- Zipline-Reloaded: https://github.com/stefan-jansen/zipline-reloaded

### 关键文献
- Almgren & Chriss (2001): "Optimal Execution of Portfolio Transactions"
- QuantConnect LEAN Architecture: https://www.lean.io/docs/
- NVIDIA GPU Backtesting Blog: https://developer.nvidia.com/blog/gpu-accelerate-algorithmic-trading-simulations-by-over-100x-with-numba/
- AWS Scaling Backtesting: https://aws.amazon.com/blogs/industries/scaling-backtesting-for-algorithmic-trading-with-aws-and-coiled/
- Machine Learning for Trading (Stefan Jansen): https://github.com/stefan-jansen/machine-learning-for-trading

---

## 10. 图谱变更日志

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2026-05-17 | 初始版本，覆盖主要框架、架构模式、性能优化技术、迁移路径 |
