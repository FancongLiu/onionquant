# NautilusTrader 本地部署与接入研究报告

> 编写日期: 2026-05-17
> 编写团队: 回测引擎部
> 当前版本: NautilusTrader v1.226.x (2026年4月)

---

## 目录

1. [框架概述](#1-框架概述)
2. [安装步骤](#2-安装步骤)
3. [样例策略代码](#3-样例策略代码)
4. [核心概念速览](#4-核心概念速览)
5. [美股数据接入方案](#5-美股数据接入方案)
6. [与现有架构集成](#6-与现有架构集成)
7. [回测结果输出与分析对接](#7-回测结果输出与分析对接)
8. [替代方案对比与推荐](#8-替代方案对比与推荐)
9. [最终推荐结论](#9-最终推荐结论)

---

## 1. 框架概述

**NautilusTrader** 是一个高性能、开源、事件驱动的算法交易平台和回测引擎，核心组件使用 Rust 编写，提供 Python 接口。

### 核心特性

| 特性 | 说明 |
|------|------|
| **性能** | Rust/Cython 核心，纳秒级时间戳精度，支持 tick 级和订单簿回放 |
| **多资产支持** | 股票、期货、外汇、加密货币、期权、CFD |
| **代码复用** | 回测代码与实盘代码完全一致，无需修改 |
| **订单类型** | 支持 Market/Limit/Stop/IOC/FOK/GTC/GTD/Iceberg/OCO/OTO/Bracket |
| **风险控制** | 内置风险管理框架 |
| **License** | LGPL 2.1（商业友好） |
| **GitHub Stars** | ~16k+，社区活跃，双周发布 |

### 适用场景

- 高频/中频策略回测
- Tick 级和订单簿级别的精细回测
- 生产级实盘交易系统
- 多交易所、多资产类别的统一回测

---

## 2. 安装步骤

### 2.1 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10/11 x86_64, Linux x86_64/ARM64, macOS ARM64/x86_64 |
| Python | 3.12, 3.13, 3.14 |
| Rust (源码编译) | 1.95.0+ |

### 2.2 Windows 安装（推荐方式：PyPI）

```powershell
# 安装 uv（快速 Python 包管理器）
irm https://astral.sh/uv/install.ps1 | iex

# 创建并激活虚拟环境
uv venv
.venv\Scripts\activate

# 安装 NautilusTrader（核心包）
uv pip install nautilus_trader

# 可选：安装额外组件
uv pip install "nautilus_trader[ib]"             # Interactive Brokers 适配器
uv pip install "nautilus_trader[databento]"       # Databento 数据适配器
uv pip install "nautilus_trader[visualization]"   # Plotly 可视化
uv pip install "nautilus_trader[all]"             # 全部扩展
```

### 2.3 从 Nautech 官方源安装（获取夜版）

```powershell
# 稳定版
pip install -U nautilus_trader --index-url=https://packages.nautechsystems.io/simple

# 最新夜版（尝鲜新功能）
pip install -U nautilus_trader --pre --index-url=https://packages.nautechsystems.io/simple
```

### 2.4 Docker 部署

```powershell
docker pull ghcr.io/nautechsystems/nautilus_trader:latest
docker run -it --rm -v ${PWD}:/workspace ghcr.io/nautechsystems/nautilus_trader:latest bash
```

### 2.5 验证安装

```python
import nautilus_trader as nt
from nautilus_trader.model.identifiers import InstrumentId

print(f"NautilusTrader version: {nt.__version__}")
instrument_id = InstrumentId.from_str("AAPL.NASDAQ")
print(f"Test passed: {instrument_id}")
```

> **注意**: 避免使用 Conda 环境，推荐使用 "vanilla" CPython + `uv`。

---

## 3. 样例策略代码

### 3.1 简单 EMA 双均线交叉策略（可运行完整示例）

以下是一个完整的、可直接运行的 EMA 交叉回测，使用内置的测试数据。

```python
"""
NautilusTrader EMA Cross 回测示例
可直接运行，使用框架内置的测试数据
"""
import pandas as pd

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.examples.strategies.ema_cross import EMACross
from nautilus_trader.model.data import BarType
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.test_kit.providers import TestInstrumentProvider, TestDataProvider


def run_ema_cross_backtest():
    """运行 EMA 交叉策略回测并输出报告"""
    # ── 1. 配置引擎 ──────────────────────────────────
    config = BacktestEngineConfig(trader_id="BACKTESTER-001")
    engine = BacktestEngine(config=config)

    # ── 2. 添加交易所（虚拟 SIM 交易所） ──────────────
    SIM = Venue("SIM")
    engine.add_venue(
        venue=SIM,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(1_000_000, USD)],
    )

    # ── 3. 添加工具和数据 ─────────────────────────────
    instrument = TestInstrumentProvider.default_fx_ccy("EUR/USD")
    engine.add_instrument(instrument)

    bar_type = BarType.from_str("EUR/USD.SIM-1-MINUTE-BID-EXTERNAL")
    bars = TestDataProvider().read_csv_bars("fxcm-eurusd-1m.csv")
    engine.add_data(bars)

    # ── 4. 添加策略 ──────────────────────────────────
    strategy = EMACross(
        instrument_id=instrument.id,
        bar_type=bar_type,
        fast_ema_period=10,
        slow_ema_period=20,
    )
    engine.add_strategy(strategy)

    # ── 5. 运行回测 ──────────────────────────────────
    engine.run()

    # ── 6. 分析结果 ──────────────────────────────────
    # 生成报告（返回 pandas DataFrame）
    account_report = engine.trader.generate_account_report(SIM)
    orders_report = engine.trader.generate_orders_report()
    fills_report = engine.trader.generate_fills_report()
    positions_report = engine.trader.generate_positions_report()

    print("\n=== Account Report ===")
    print(account_report.to_string())

    print("\n=== Positions Report ===")
    print(positions_report.to_string())

    # 获取组合分析指标
    portfolio = engine.portfolio
    stats_pnls = portfolio.analyzer.get_performance_stats_pnls()
    stats_returns = portfolio.analyzer.get_performance_stats_returns()
    stats_general = portfolio.analyzer.get_performance_stats_general()

    print("\n=== Performance Stats ===")
    print(f"Total PnL: {stats_pnls}")
    print(f"Returns: {stats_returns}")
    print(f"General: {stats_general}")

    # ── 7. 清理 ──────────────────────────────────────
    engine.dispose()

    return {
        "account": account_report,
        "orders": orders_report,
        "fills": fills_report,
        "positions": positions_report,
        "stats": {
            "pnls": stats_pnls,
            "returns": stats_returns,
            "general": stats_general,
        },
    }


if __name__ == "__main__":
    results = run_ema_cross_backtest()

```

### 3.2 Tick 级 EMA TWAP 策略

如果需要更精细的 tick 级别回测，可以使用内置的 `EMACrossTWAP` 策略示例：

```python
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.examples.strategies.ema_cross_twap import (
    EMACrossTWAP,
    EMACrossTWAPConfig,
)
from nautilus_trader.examples.algorithms.twap import TWAPExecAlgorithm
from nautilus_trader.model.data import BarType
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
from nautilus_trader.test_kit.providers import TestDataProvider, TestInstrumentProvider
from decimal import Decimal

# ── 加载 tick 数据 ──────────────────────────────────
provider = TestDataProvider()
trades_df = provider.read_csv_ticks("binance/ethusdt-trades.csv")
ETHUSDT_BINANCE = TestInstrumentProvider.ethusdt_binance()

wrangler = TradeTickDataWrangler(instrument=ETHUSDT_BINANCE)
ticks = wrangler.process(trades_df)

# ── 配置引擎 ─────────────────────────────────────────
engine = BacktestEngine(config=BacktestEngineConfig(trader_id="BACKTESTER-001"))
engine.add_venue(
    venue=Venue("BINANCE"),
    oms_type=OmsType.NETTING,
    account_type=AccountType.CASH,
    base_currency=None,
    starting_balances=[Money(1_000_000.0, USDT), Money(10.0, ETH)],
)
engine.add_instrument(ETHUSDT_BINANCE)
engine.add_data(ticks)

# ── 策略 ─────────────────────────────────────────────
strategy_config = EMACrossTWAPConfig(
    instrument_id=ETHUSDT_BINANCE.id,
    bar_type=BarType.from_str("ETHUSDT.BINANCE-250-TICK-LAST-INTERNAL"),
    trade_size=Decimal("0.10"),
    fast_ema_period=10,
    slow_ema_period=20,
    twap_horizon_secs=10.0,
    twap_interval_secs=2.5,
)

strategy = EMACrossTWAP(config=strategy_config)
engine.add_strategy(strategy)
engine.add_exec_algorithm(TWAPExecAlgorithm())

engine.run()
```

### 3.3 自定义策略骨架

```python
from nautilus_trader.model.data import Bar, QuoteTick, TradeTick
from nautilus_trader.trading.strategy import Strategy


class MyCustomStrategy(Strategy):
    """
    自定义策略模板
    生命周期: on_start -> on_bar/on_quote_tick/on_trade_tick -> on_stop -> on_dispose
    """

    def on_start(self):
        """策略启动时调用：订阅数据、初始化指标"""
        self.subscribe_bars(self.config.bar_type)
        self.subscribe_quote_ticks(self.config.instrument_id)
        # self.register_indicator(self.config.bar_type, self.my_indicator)

    def on_bar(self, bar: Bar):
        """每根 K 线回调"""
        # 检查指标就绪状态
        # 执行信号逻辑
        # 提交订单：self.market_order(), self.limit_order(), 或 self.submit_order()
        pass

    def on_quote_tick(self, tick: QuoteTick):
        """Quote Tick 回调"""
        pass

    def on_trade_tick(self, tick: TradeTick):
        """Trade Tick 回调"""
        pass

    def on_stop(self):
        """策略停止时调用：平仓、取消订阅"""
        self.close_all_positions(self.config.instrument_id)

    def on_dispose(self):
        """策略销毁时调用：清理资源"""
        pass
```

---

## 4. 核心概念速览

| 概念 | 说明 |
|------|------|
| `Strategy` | 策略基类，实现 `on_start`, `on_bar`, `on_stop` 等生命周期方法 |
| `BacktestEngine` | 低层级回测 API，适合开发调试 |
| `BacktestNode` | 高层级回测 API，搭配 ParquetDataCatalog，易过渡到实盘 |
| `Instrument` | 交易工具（股票代码、合约规格等） |
| `BarType` | K线规格定义（工具.交易所-周期-价格类型-来源） |
| `OrderFactory` | 订单工厂，创建各种订单类型 |
| `DataCatalog` | 基于 Parquet 的数据目录，管理历史数据 |
| `LiveDataClient` | 实盘数据适配器基类，可继承实现自定义数据源 |

---

## 5. 美股数据接入方案

### 方案 A: 使用 Databento 适配器（推荐，需付费）

Databento 是 NautilusTrader 官方支持的机构级数据提供商，覆盖美股、期货、期权。

```python
# 安装
uv pip install "nautilus_trader[databento]"

# 使用 DatabentoDataLoader 加载历史数据
from nautilus_trader.adapters.databento.loader import DatabentoDataLoader
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

loader = DatabentoDataLoader()
catalog = ParquetDataCatalog(path="./catalog")

# 下载 AAPL 分钟线到本地 Parquet 目录
catalog = loader.load(
    catalog=catalog,
    instrument_id="AAPL.NASDAQ",
    dataset="GLBX.MDP3",
    start=pd.Timestamp("2025-01-01", tz="UTC"),
    end=pd.Timestamp("2025-12-31", tz="UTC"),
)
```

| 维度 | 说明 |
|------|------|
| 覆盖范围 | 美股、期货、期权全量数据 |
| 数据格式 | DBN (Databento Binary Encoding)，可直接加载到 NautilusTrader |
| 费用 | 按数据量付费 |
| 优点 | 官方适配器，稳定性好，支持 tick 级数据 |
| 缺点 | 需付费，没有免费额度 |

### 方案 B: 通过 Interactive Brokers 适配器（需 IBKR 账户）

```python
uv pip install "nautilus_trader[ib]"
```

IB 适配器支持回测和实盘，可以从 TWS/IB Gateway 获取历史数据。适用于：
- 已有 IB 账户的团队
- 需要同时做回测和实盘交易
- 数据量要求不高的场景

### 方案 C: 通过 yfinance 获取数据 + 自定义加载

NautilusTrader **没有官方 yfinance 适配器**，但可以通过社区项目或自行开发数据加载脚本来集成。

**方式 C1: CSV 文件加载（最简单）**

```python
import pandas as pd
from nautilus_trader.adapters.databento.loader import load_catalog_from_csv_parquet
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.core.timestamp import UnixMillis

def csv_to_nautilus_bars(csv_path: str, instrument_id: InstrumentId, venue: Venue):
    """
    将 yfinance 下载的 CSV 转换为 NautilusTrader Bar 对象

    yfinance CSV 格式预期列: Date, Open, High, Low, Close, Volume
    """
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    bars = []

    for _, row in df.iterrows():
        bar = Bar(
            open=row["Open"],
            high=row["High"],
            low=row["Low"],
            close=row["Close"],
            volume=row["Volume"],
            ts_event=UnixMillis(int(row["Date"].timestamp() * 1000)),
            ts_init=UnixMillis(int(row["Date"].timestamp() * 1000)),
        )
        bars.append(bar)

    return bars

# 使用示例
instrument_id = InstrumentId.from_str("AAPL.NASDAQ")
venue = Venue("NASDAQ")
bars = csv_to_nautilus_bars("AAPL.csv", instrument_id, venue)

engine = BacktestEngine(config=BacktestEngineConfig(trader_id="BACKTESTER-001"))
SIM = Venue("SIM")
engine.add_venue(venue=SIM, oms_type=..., account_type=..., ...)
engine.add_instrument(instrument)
engine.add_data(bars)
```

**方式 C2: ParquetDataCatalog 方式（推荐生产使用）**

```python
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.serialization.arrow.serializer import register_arrow

catalog = ParquetDataCatalog(path="./data/catalog")

# 写入数据到 Catalog
catalog.write_data(bars)

# 回测时从 Catalog 读取
from nautilus_trader.backtest.node import BacktestDataConfig, BacktestNode, BacktestRunConfig
from nautilus_trader.backtest.modules import SimulationModuleList

data_config = BacktestDataConfig(
    catalog_path=str(catalog.path),
    data_type=Bar,
    instrument_id=InstrumentId.from_str("AAPL.NASDAQ"),
    bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
    start=pd.Timestamp("2025-01-01", tz="UTC"),
    end=pd.Timestamp("2025-12-31", tz="UTC"),
)

run_config = BacktestRunConfig(
    engine=...,
    data=[data_config],
    strategies=[...],
)

node = BacktestNode(configs=[run_config])
results = node.run()
```

**方式 C3: 使用社区项目 momentum_NautilusTrader**

该社区项目 (`0a1b/momentum_NautilusTrader`) 展示了完整的 yfinance + NautilusTrader 集成流程，包含 SP500, NASDAQ100 等指数的动量策略回测。

### 方案 D: 自定义 LiveDataClient（全适配器）

当需要对接内部数据源时，可以实现完整的 `LiveDataClient` 适配器：

```python
from nautilus_trader.live.data_client import LiveDataClient
from nautilus_trader.model.identifiers import ClientId


class MyDataClient(LiveDataClient):
    """自定义数据适配器，对接内部数据 Pipeline"""

    def __init__(self, client_id: ClientId, ...):
        super().__init__(client_id)
        # 初始化内部数据连接

    async def _connect(self):
        """建立与内部数据服务的连接"""
        pass

    async def _disconnect(self):
        """断开连接"""
        pass

    async def _subscribe_bars(self, bar_type: BarType):
        """订阅 K 线数据"""
        pass

    async def _subscribe_quote_ticks(self, instrument_id: InstrumentId):
        """订阅 Quote Tick"""
        pass
```

开发者可以参考 `nautilus_trader/adapters/_template/data.py` 模板进行实现。

---

## 6. 与现有架构集成

### 6.1 数据 Pipeline 对接

NautilusTrader 的数据接入层支持分层抽象，便于对接现有数据 Pipeline：

```
[内部数据源] -> [ETL/清洗] -> [ParquetDataCatalog] -> [BacktestNode] -> [策略回测]
                    |
                    v
              [yfinance / 券商API] -> [CSV] -> [csv_to_nautilus_bars()] -> [BacktestEngine]
```

**推荐生产使用路径：**

1. 从内部数据 Pipeline 导出为 Parquet 格式
2. 使用 `ParquetDataCatalog` 管理数据
3. 通过 `BacktestDataConfig` 配置回测数据输入
4. 使用 `BacktestNode`（高层 API）运行回测
5. 同一套代码无缝过渡到实盘

### 6.2 数据格式约定

NautilusTrader 的 `ParquetDataCatalog` 数据目录结构：

```
catalog/
  data/
    bars/
      AAPL.NASDAQ/
        2025-01-01_2025-01-31.parquet
        2025-02-01_2025-02-28.parquet
    quote_ticks/
      AAPL.NASDAQ/
        ...
    trade_ticks/
      AAPL.NASDAQ/
        ...
    custom/
      <type_name>/
        ...
```

### 6.3 集成注意事项

1. **时间戳**: NautilusTrader 使用纳秒级 Unix 时间戳（`UnixNanos`），需要确保数据 Pipeline 中的时间戳精度
2. **工具定义**: 每个交易工具需要在 `Instrument` 对象中定义规格（最小价格变动、合约大小等）
3. **数据分片**: 建议按月份分片存储 Parquet 数据，以优化查询性能

---

## 7. 回测结果输出与分析对接

### 7.1 获取回测结果

```python
# 运行回测
engine.run()

# 生成结构化报表（返回 pandas DataFrame）
orders_df = engine.trader.generate_orders_report()       # 所有订单
positions_df = engine.trader.generate_positions_report()  # 持仓明细
fills_df = engine.trader.generate_fills_report()          # 成交明细
account_df = engine.trader.generate_account_report(venue)  # 账户状态变化

# 组合统计分析
portfolio = engine.portfolio
general_stats = portfolio.analyzer.get_performance_stats_general()
# 包含: 总 PnL, Sharpe Ratio, 胜率, 盈亏比, 最大回撤等
```

### 7.2 输出到分析系统

由于所有报告都是 pandas DataFrame，可以无缝输出到现有分析系统：

```python
# 输出到 CSV（导入数据库或分析系统）
orders_df.to_csv("backtest_orders.csv", index=False)
positions_df.to_csv("backtest_positions.csv", index=False)

# 输出到 Parquet（对接大数据 Pipeline）
orders_df.to_parquet("backtest_results/orders.parquet")
positions_df.to_parquet("backtest_results/positions.parquet")

# 直接写入数据库（SQLAlchemy）
orders_df.to_sql("backtest_orders", con=db_engine, if_exists="append")
positions_df.to_sql("backtest_positions", con=db_engine, if_exists="append")

# 生成交互式 HTML 报告（内置 Plotly 支持）
from nautilus_trader.analysis import create_tearsheet
create_tearsheet(
    orders=orders_df,
    fills=fills_df,
    positions=positions_df,
    account=account_df,
    output_path="backtest_report.html",
)
```

### 7.3 流式持久化（大规模回测）

对于大规模回测，可以使用 `StreamingFeatherWriter` 将结果流式写入磁盘（Feather/IPC 格式）：

```python
from nautilus_trader.serialization.feather.writer import StreamingFeatherWriter

writer = StreamingFeatherWriter(
    output_dir="./backtest_results",
    rotation_mode="SIZE",
    rotation_size_bytes=1073741824,  # 1GB 轮转
)
```

---

## 8. 替代方案对比与推荐

### 8.1 NautilusTrader vs LEAN (QuantConnect) vs Backtrader

| 维度 | NautilusTrader | LEAN (QuantConnect) | Backtrader |
|------|---------------|---------------------|------------|
| **语言** | Python (Rust 内核) | C# 内核 + Python API | 纯 Python |
| **性能** | 极高（Rust/Cython） | 高（C#） | 低 |
| **Star** | ~16k | ~18.7k | ~20.4k |
| **回测+实盘代码统一** | 是，完全一致 | 是，支持 | 需手动改造 |
| **Tick 级回测** | 原生支持 | 支持 | 不适用 |
| **数据源** | 自建 / Databento / IB / 自定义 | 内置 100+ 数据源 | 需自建 |
| **费用** | 免费 (LGPL 2.1) | 免费层 + 付费 $20-80/月 | 免费 (GPL v3) |
| **活跃度 (2025-2026)** | 非常活跃（双周发布） | 非常活跃 | **已停滞（~1年无更新）** |
| **美股支持** | Databento / IB 适配器 | 内置 | 需自建 |
| **学习曲线** | 较陡 | 中等 | 平缓 |
| **云服务** | 无（本地部署） | 有（Cloud IDE） | 无 |

### 8.2 其他值得关注的框架 (2025-2026)

| 框架 | 特点 | 适合场景 |
|------|------|----------|
| **VectorBT** | 向量化计算，Numba 加速，**比 Backtrader 快 10-100 倍** | 快速参数优化研究，不适合事件驱动策略 |
| **VnPy (VeighNa)** | 中国期货市场首选，40.5k Stars，C++ 扩展 | 中国 A 股、期货高频 |
| **Qlib (Microsoft)** | ML/AI 因子研究，2025 年整合 LLM | AI 量化研究 |
| **nanoback** (新) | C++20 引擎 + Python 绑定，含 WFO 和 Monte Carlo | 近生产级回测质量 |
| **kairos-engine** (新) | 异步 Actor 模型，已实盘部署 DCA 策略 | 轻量级回测+实盘，类似 Nautilus 但更轻 |
| **RustyBT** (新) | Rust + Polars，Decimal 精度，审计合规 | 对精度和合规性有要求的回测 |
| **wrtrade** (新) | 基于 Polars，**快 10-50 倍**，极简 API | 快速向量化回测 |

### 8.3 使用场景选择矩阵

| 需求 | 推荐方案 |
|------|----------|
| **Tick 级高精度回测 + 实盘部署** | **NautilusTrader** |
| **快速策略研究（分钟级 K 线）** | **VectorBT** |
| **中国 A 股/期货全栈** | **VnPy** |
| **一键云平台，不需本地部署** | **QuantConnect/LEAN** |
| **AI/ML 量化研究** | **Qlib** |
| **学习用 / 小规模回测** | Backtrader（已停滞）或 **NautilusTrader** |

---

## 9. 最终推荐结论

### 推荐: NautilusTrader

**理由：**

1. **性能最优** — Rust 内核提供纳秒级精度和 tick 级回测能力，远超纯 Python 框架
2. **代码复用** — 回测代码可直接用于实盘，降低维护成本
3. **开源免费** — LGPL 2.1 许可，商业友好，无隐藏费用
4. **持续活跃** — 2025-2026 年保持双周发布节奏，社区和核心团队都在持续贡献
5. **适配器架构** — 分层的数据适配器设计便于对接内部数据 Pipeline
6. **多资产统一** — 一套框架覆盖美股、期货、加密、外汇

### 实施建议

1. **短期（1-2周）**：使用 PyPI 安装 + 内置示例验证框架功能，确认满足基本回测需求
2. **中期（1-2月）**：开发内部数据源适配器，将现有数据 Pipeline 与 ParquetDataCatalog 对接
3. **长期（3-6月）**：逐步迁移实盘策略到 NautilusTrader，实现回测-实盘一体化

### 需要注意的风险

| 风险 | 说明 | 缓解措施 |
|------|------|----------|
| 学习曲线较陡 | 概念较多，文档以英文为主 | 参考本指南和官方快速入门 |
| 数据源需自建 | 没有内置免费数据 | 用 yfinance 做原型验证，Databento 做生产 |
| 美股适配器有限 | 官方仅 Databento 和 IB | 自定义适配器对接内部数据 |

---

### 参考链接

- NautilusTrader 官方文档: https://nautilustrader.io/docs
- GitHub 仓库: https://github.com/nautechsystems/nautilus_trader
- 官方示例: https://github.com/nautechsystems/nautilus_trader/tree/develop/examples/backtest
- Databento 适配器: https://github.com/nautechsystems/nautilus_trader/tree/develop/nautilus_trader/adapters/databento
- PyPI: https://pypi.org/project/nautilus_trader/
- 社区 yfinance 集成参考: https://github.com/0a1b/momentum_NautilusTrader
