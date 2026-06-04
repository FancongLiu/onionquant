"""
日内动量策略 (Intraday Momentum Strategy for SPY)
=================================================

原始出处 (Original Source):
  - Concretum Group: "Beat the Market: An Effective Intraday Momentum
    Strategy for the S&P500 ETF (SPY)"
  - 论文 / Paper: Zarattini, Aziz, Barbon (SSRN 4824172)
  - 报告回报: 1985% 总回报 (2007–2024), 年化 19.6%, Sharpe 1.33
  - 官方代码 / Official Code:
    https://concretumgroup.com/python-backtesting-beat-the-market...
    https://github.com/Branly76/Intraday-strategy-Beat-the-market-for-SPY-

改编说明 (Adaptation Notes):
  - 原代码使用 Polygon.io / Alpaca 的 1 分钟级别数据，获得极高回报
  - 本版使用 yfinance 获取 30 分钟 / 1 小时级别数据，便于独立运行
  - 核心逻辑 (Noise Area, VWAP, Sigma_Open, 波动率目标仓位) 与原版一致
  - 因数据频率和区间不同，回测结果与原报告不可直接比较

核心逻辑 (Core Logic):
  1. VWAP: 每日从开盘起累积计算
  2. Move from Open = abs(close / open - 1)
  3. Sigma_Open = 同时间窗口 14 天滚动均值 (shift 1)
  4. 上轨 UB = max(open, prev_close) * (1 + BAND_MULT * sigma_open)
  5. 下轨 LB = min(open, prev_close) * (1 - BAND_MULT * sigma_open)
  6. 做多: close > UB & close > VWAP; 做空: close < LB & close < VWAP
  7. 信号 forward-fill, shift(1) 防前视偏差
  8. 仓位: 波动率目标 2%, 最大 4 倍杠杆
"""

import numpy as np
import pandas as pd
import yfinance as yf
import warnings

warnings.filterwarnings("ignore")

# ── 参数 ────────────────────────────────────────────────────────────
TICKER = "SPY"
INTERVAL = "1h"  # '30m'(最长 60d) 或 '1h'(最长 730d)
PERIOD = "700d"
AUM_0 = 100_000.0
COMMISSION = 0.0035  # 每股佣金 (USD)
MIN_COMM = 0.35
BAND_MULT = 1.0  # 通道倍数
TARGET_VOL = 0.02  # 目标日波动率
MAX_LEVERAGE = 4.0
ROLL_WIN = 14  # Sigma_Open 滚动窗口
VOL_WIN = 21  # 波动率滚动窗口 (交易日)


import logging

logger = logging.getLogger(__name__)


def fetch_data(ticker=TICKER, period=PERIOD, interval=INTERVAL):
    """yfinance 获取 SPY 日内 + 每日数据."""
    logger.info("Fetching %s %s, period=%s", ticker, interval, period)
    intra = yf.download(
        ticker, period=period, interval=interval, progress=False, auto_adjust=False
    )
    intra.columns = [c[0].lower() for c in intra.columns]
    intra.index = intra.index.tz_convert("US/Eastern")
    intra = intra.between_time("09:30", "16:00").copy()
    intra.index.name = "datetime"
    intra = intra.reset_index()
    intra["date"] = intra["datetime"].dt.date

    daily = yf.download(
        ticker, period="2y", interval="1d", progress=False, auto_adjust=False
    )
    daily.columns = [c[0].lower() for c in daily.columns]
    # 仅保留收盘价用于波动率
    daily = daily[["close"]].copy()
    daily["ret"] = daily["close"].pct_change()

    logger.info("Got %d bars, %d trading days", len(intra), intra["date"].nunique())
    return intra, daily


def calc_indicators(df, daily):
    """计算 VWAP, Move from Open, Sigma_Open, 滚动波动率."""
    df = df.copy()
    dates = df["date"].unique()
    daily_rets = daily["ret"].dropna()

    # VWAP & Move from Open (按日)
    for d in dates:
        mask = df["date"] == d
        day = df.loc[mask]
        if len(day) < 1:
            continue
        hlc = (day["high"] + day["low"] + day["close"]) / 3
        cum_vh = (day["volume"] * hlc).cumsum()
        cum_v = day["volume"].cumsum()
        df.loc[mask, "vwap"] = cum_vh / cum_v
        op = day["open"].iloc[0]
        df.loc[mask, "move_open"] = abs(day["close"] / op - 1)

    # SPY 滚动波动率 (从 daily 计算)
    vol_map = {}
    for i, d in enumerate(dates):
        # 找到相应日期的 daily 数据
        try:
            loc = daily_rets.index.get_loc(pd.Timestamp(d), method="nearest")
            if loc >= VOL_WIN - 1:
                vol_map[d] = daily_rets.iloc[loc - VOL_WIN + 1 : loc + 1].std()
            else:
                vol_map[d] = np.nan
        except (KeyError, TypeError):
            vol_map[d] = np.nan
    df["spy_dvol"] = df["date"].map(vol_map)

    # Sigma_Open: 按同时间窗口分组, 滚动 ROLL_WIN 天均值, shift 1
    time_key = df["datetime"].dt.time
    df["sigma_open"] = df.groupby(time_key)["move_open"].transform(
        lambda x: x.rolling(ROLL_WIN, min_periods=ROLL_WIN - 1).mean().shift(1)
    )
    return df


def run_backtest(df):
    """使用 Backtrader Cerebro 引擎执行日内动量策略回测 (v2).

    保留核心信号逻辑 (Noise Area / VWAP / Sigma_Open),
    回测引擎替换为 Backtrader (事件驱动 + 内置分析器).
    """
    import backtrader as bt

    class NoiseAreaStrategy(bt.Strategy):
        params = dict(
            band_mult=BAND_MULT,
            target_vol=TARGET_VOL,
            max_leverage=MAX_LEVERAGE,
        )

        def __init__(self):
            self.order = None

        def next(self):
            if self.order:
                return

            d = self.datas[0]
            dt = d.datetime.date(0)
            # Match current day's pre-computed signals
            today = df[df["date"] == dt]
            if len(today) == 0 or today["sigma_open"].isna().all():
                return

            cd = today
            prev_day = df[df["date"] < dt]
            if len(prev_day) == 0:
                return
            prev_close = prev_day["close"].iloc[-1]
            op = cd["open"].iloc[0]
            sigma = cd["sigma_open"].values
            ub = max(op, prev_close) * (1 + self.p.band_mult * sigma)
            lb = min(op, prev_close) * (1 - self.p.band_mult * sigma)
            cp = cd["close"].values
            v = cd["vwap"].values

            sig = np.zeros(len(cp))
            sig[(cp > ub) & (cp > v)] = 1
            sig[(cp < lb) & (cp < v)] = -1
            signal = int(sig[-1]) if len(sig) > 0 else 0

            spx_vol = cd["spy_dvol"].iloc[0]
            vol_mult = (
                min(self.p.target_vol / spx_vol, self.p.max_leverage)
                if not np.isnan(spx_vol)
                else 1.0
            )

            pos = self.position
            if signal == 1 and pos.size == 0:
                size = int(self.broker.getvalue() / d.close[0] * vol_mult * 0.95)
                self.order = self.buy(size=size)
            elif signal == -1 and pos.size == 0:
                size = int(self.broker.getvalue() / d.close[0] * vol_mult * 0.95)
                self.order = self.sell(size=size)
            elif signal == 0 and pos.size != 0:
                self.order = self.close()

        def notify_order(self, order):
            if order.status in [order.Completed, order.Canceled, order.Margin]:
                self.order = None

    # Build Cerebro
    cerebro = bt.Cerebro()
    cerebro.addstrategy(NoiseAreaStrategy)
    cerebro.broker.setcash(AUM_0)
    cerebro.broker.setcommission(commission=COMMISSION)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.02)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

    # Feed data as daily bars (backtrader data feed)
    daily_bars = (
        df.groupby("date")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .reset_index()
    )
    daily_bars["date"] = pd.to_datetime(daily_bars["date"])
    daily_bars = daily_bars.set_index("date").sort_index()

    data = bt.feeds.PandasData(dataname=daily_bars)
    cerebro.adddata(data)

    results = cerebro.run()
    strat_analysis = results[0]

    # Extract metrics
    sharpe = strat_analysis.analyzers.sharpe.get_analysis()
    dd = strat_analysis.analyzers.drawdown.get_analysis()

    # Build result DataFrame (keep AUM_SPX from original data)
    dates_list = df["date"].unique()
    strat = pd.DataFrame(index=dates_list)
    strat["ret"] = 0.0
    strat["ret_spy"] = 0.0
    strat["AUM"] = AUM_0

    for i in range(1, len(dates_list)):
        cur, prev = dates_list[i], dates_list[i - 1]
        cd = df[df["date"] == cur]
        pd_ = df[df["date"] == prev]
        if len(cd) > 0 and len(pd_) > 0:
            strat.loc[cur, "ret_spy"] = cd["close"].iloc[-1] / pd_["close"].iloc[-1] - 1

    strat["AUM"] = float(cerebro.broker.getvalue())
    strat["AUM_SPX"] = AUM_0 * (1 + strat["ret_spy"]).cumprod()
    return strat, {
        "sharpe": round(sharpe.get("sharperatio", 0) or 0, 2),
        "max_drawdown": round(dd.get("max", {}).get("drawdown", 0) / 100, 4),
        "final_value": round(cerebro.broker.getvalue(), 2),
    }


def print_stats(strat, bt_metrics=None):
    """输出绩效指标."""
    r = strat["ret_spy"].dropna()
    if len(r) == 0:
        logger.warning("No valid trading data")
        return

    cum_s = float(np.prod(1 + r)) - 1
    ann_s = float(np.prod(1 + r) ** (252 / len(r)) - 1)

    print("\n" + "=" * 58)
    print("  Intraday Momentum Strategy - Backtest Results (Backtrader v2)")
    print("=" * 58)
    if bt_metrics:
        print(f"  {'Backtrader Final Value':<28} ${bt_metrics['final_value']:>12,.2f}")
        print(f"  {'Backtrader Sharpe':<28} {bt_metrics['sharpe']:>12.2f}")
        print(f"  {'Backtrader Max DD':<28} {bt_metrics['max_drawdown'] * 100:>10.1f}%")
    print(f"  {'SPY B&H Return':<28} {cum_s * 100:>10.1f}%")
    print(f"  {'SPY B&H Ann. Return':<28} {ann_s * 100:>10.1f}%")
    print(f"  {'Trading Days':<28} {len(r):>12}")
    print("=" * 58)


def main():
    """主流程 (v2: Backtrader 回测引擎)."""
    print("=" * 58)
    print("  Intraday Momentum Strategy (Backtrader v2)")
    print("  Concretum Group 'Beat the Market' (SSRN 4824172)")
    print("=" * 58)

    intra, daily = fetch_data()
    df = calc_indicators(intra, daily)
    strat, bt_metrics = run_backtest(df)
    print_stats(strat, bt_metrics)

    print("\n[Done] Core logic (Noise Area/VWAP/Sigma_Open/Vol Target)")
    print("       v2: Backtrader event-driven engine + built-in analyzers")
    print("       Performance differs due to data resolution (1h vs 1min).")
    return df, strat


if __name__ == "__main__":
    df, strat = main()
