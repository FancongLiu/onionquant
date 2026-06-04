"""
Quantitative analysis routes — factors, signals, backtest, optimization, strategies.
"""
import random
from fastapi import APIRouter

from .shared import (
    PROJECT_ROOT, QUANT_TICKERS, QUANT_FACTOR_NAMES,
)

router = APIRouter(tags=["quant"])


def _generate_factor_matrix():
    """Generate factor x ticker matrix from live data or synthetic fallback."""
    data_dir = PROJECT_ROOT / "quant_framework" / "data" / "raw"
    price_files = list(data_dir.glob("price_*.parquet")) if data_dir.exists() else []

    if price_files:
        try:
            import pandas as pd
            df = pd.concat([pd.read_parquet(f) for f in price_files[:5]])
            if "ticker" in df.columns and len(df) > 100:
                from quant_framework.strategies.qlib_factor_engine import compute_all_factors as compute_all
                result = compute_all(df, neutralize=False)
                factor_cols = [c for c in result.columns if c in QUANT_FACTOR_NAMES]
                stocks = sorted(df["ticker"].unique())[:30]
                data = {}
                for f in factor_cols[:20]:
                    data[f] = {}
                    for s in stocks:
                        srows = result.loc[df["ticker"] == s, f]
                        data[f][s] = float(srows.dropna().iloc[-1]) if len(srows.dropna()) > 0 else None
                return {"factors": factor_cols[:20], "stocks": stocks, "data": data, "source": "live"}
        except Exception:
            pass

    rng = random.Random(42)
    import numpy as np
    stocks = QUANT_TICKERS[:20]
    factors = QUANT_FACTOR_NAMES[:20]
    data = {}
    for fi, f in enumerate(factors):
        data[f] = {}
        base = rng.gauss(0, 0.5)
        for si, s in enumerate(stocks):
            val = base + rng.gauss(0, 0.3) * np.exp(-abs(fi - 10) / 5)
            val = max(-4.0, min(4.0, val)) if abs(val) < 5 else round(val, 3)
            data[f][s] = round(val, 3)
    return {"factors": factors, "stocks": stocks, "data": data, "source": "generated"}


@router.get("/api/quant/factors")
async def quant_factors():
    return _generate_factor_matrix()


@router.get("/api/quant/signals")
async def quant_signals():
    data_dir = PROJECT_ROOT / "quant_framework" / "data" / "raw"
    price_files = list(data_dir.glob("price_*.parquet")) if data_dir.exists() else []

    if price_files:
        try:
            import pandas as pd
            df = pd.concat([pd.read_parquet(f) for f in price_files[:5]])
            if "ticker" in df.columns and len(df) > 100:
                from quant_framework.strategies.qlib_factor_engine import compute_all_factors
                from quant_framework.strategies.factor_combiner import (
                    ic_weighted_combine, filter_factors_by_ic, generate_signals,
                )
                result = compute_all_factors(df)
                exclude = {"ticker", "date", "close", "open", "high", "low", "volume", "industry"}
                factor_cols = [c for c in result.columns if c not in exclude]
                active = filter_factors_by_ic(result, factor_cols, ic_threshold=0.02, min_factors=5)
                combined = ic_weighted_combine(result, active, result["close"], ic_threshold=0.0)
                signals = generate_signals(combined, "combined_score", top_k=15, method="long_short")
                longs = [{"ticker": row.get("ticker", "?"), "score": row.get("combined_score", 0)}
                         for _, row in signals[signals["signal"] == 1].nlargest(15, "combined_score").iterrows()]
                shorts = [{"ticker": row.get("ticker", "?"), "score": row.get("combined_score", 0)}
                          for _, row in signals[signals["signal"] == -1].nsmallest(15, "combined_score").iterrows()]
                return {"longs": longs, "shorts": shorts, "source": "live", "factors_used": len(active)}
        except Exception:
            pass

    rng = random.Random(42)
    def _make_sigs(n, sign):
        sigs = []
        used = set()
        for _ in range(n):
            t = rng.choice(QUANT_TICKERS)
            while t in used:
                t = rng.choice(QUANT_TICKERS)
            used.add(t)
            s = abs(rng.gauss(1.5, 0.5)) * sign
            sigs.append({"ticker": t, "score": round(s, 3)})
        return sigs if sign > 0 else sorted(sigs, key=lambda x: x["score"])

    return {"longs": _make_sigs(15, 1), "shorts": _make_sigs(15, -1), "source": "generated"}


@router.get("/api/quant/ic_trend")
async def quant_ic_trend():
    data_dir = PROJECT_ROOT / "quant_framework" / "data" / "raw"
    price_files = list(data_dir.glob("price_*.parquet")) if data_dir.exists() else []

    if price_files:
        try:
            import pandas as pd
            df = pd.concat([pd.read_parquet(f) for f in price_files[:5]])
            if "ticker" in df.columns and len(df) > 300:
                from quant_framework.strategies.qlib_factor_engine import compute_all_factors as compute_all
                from quant_framework.strategies.factor_combiner import rolling_ic_matrix
                result = compute_all(df, neutralize=False)
                exclude = {"ticker", "date", "close", "open", "high", "low", "volume", "industry"}
                factor_cols = [c for c in result.columns if c not in exclude][:5]
                if "close" in df.columns:
                    rolling_ic = rolling_ic_matrix(result, factor_cols, df["close"], window=21)
                    series = {}
                    for col in factor_cols:
                        ic_col = f"{col}_IC"
                        if ic_col in rolling_ic.columns:
                            vals = rolling_ic[ic_col].dropna()
                            if len(vals) >= 20:
                                step = max(1, len(vals) // 250)
                                series[col] = [round(float(v), 4) for v in vals.iloc[::step].tolist()]
                    if series:
                        return {"series": series, "source": "live"}
        except Exception:
            pass

    rng = random.Random(42)
    series = {}
    n_pts = 252
    factors_to_show = ["mom_21d", "rev_5d", "vol_21d", "val_bp", "rsi_14"]
    for fi, f in enumerate(factors_to_show):
        trend = []
        val = rng.gauss(0.02, 0.01)
        for _ in range(n_pts):
            val += rng.gauss(0, 0.003)
            val *= 0.97
            val += rng.gauss(0.01, 0.004)
            trend.append(round(val, 4))
        series[f] = trend
    return {"series": series, "source": "generated"}


@router.get("/api/quant/risk")
async def quant_risk():
    try:
        from quant_framework.risk.risk_metrics import (
            sharpe_ratio, sortino_ratio, max_drawdown, ann_vol, var_historical,
        )
        data_dir = PROJECT_ROOT / "quant_framework" / "data" / "raw"
        price_files = list(data_dir.glob("price_*.parquet")) if data_dir.exists() else []
        if price_files:
            import pandas as pd
            df = pd.concat([pd.read_parquet(f) for f in price_files[:5]])
            if "close" in df.columns and len(df) > 50:
                df["ret"] = df.groupby("ticker")["close"].pct_change()
                returns = df["ret"].dropna()
                if len(returns) > 100:
                    eq = (1 + returns).cumprod().values
                    return {
                        "sharpe": round(sharpe_ratio(returns.values), 2),
                        "sortino": round(sortino_ratio(returns.values), 2),
                        "max_drawdown": round(max_drawdown(eq), 4),
                        "var95": round(var_historical(returns.values, 0.95), 4),
                        "annual_volatility": round(ann_vol(returns.values), 4),
                        "calmar": round(sharpe_ratio(returns.values) / max(abs(max_drawdown(eq)), 0.001), 2),
                    }
    except Exception:
        pass

    return {
        "sharpe": 1.24, "sortino": 1.67, "max_drawdown": -0.0872,
        "var95": -0.0143, "annual_volatility": 0.152, "calmar": 1.42,
        "source": "generated",
    }


@router.get("/api/quant/optimize/bl")
async def bl_optimization():
    result = {"weights": [], "metrics": {}, "source": "generated"}
    data_dir = PROJECT_ROOT / "quant_framework" / "data" / "raw"
    price_files = list(data_dir.glob("price_*.parquet")) if data_dir.exists() else []

    if price_files:
        try:
            import pandas as pd
            df = pd.concat([pd.read_parquet(f) for f in price_files[:5]])
            if "close" in df.columns and "ticker" in df.columns and len(df) > 100:
                prices = df.pivot_table(index="date", columns="ticker", values="close").dropna(axis=1)
                if not prices.empty and len(prices.columns) >= 3:
                    from quant_framework.risk.portfolio_optimizer import bl_optimize
                    opt = bl_optimize(prices, view_strength=0.3)
                    if "weights" in opt:
                        w = opt["weights"]
                        top = sorted(w.items(), key=lambda x: abs(x[1]), reverse=True)[:10]
                        result["weights"] = [
                            {"ticker": t, "weight": round(float(wt), 4)}
                            for t, wt in top
                        ]
                        result["metrics"] = {
                            "expected_return": round(float(opt.get("expected_return", 0)), 4),
                            "expected_volatility": round(float(opt.get("expected_volatility", 0)), 4),
                            "sharpe": round(float(opt.get("expected_return", 0)) / max(float(opt.get("expected_volatility", 0)), 0.001), 3),
                        }
                        result["source"] = "live"
        except Exception as e:
            result["error"] = str(e)[:200]

    if result["source"] == "generated":
        result["weights"] = [
            {"ticker": "AAPL", "weight": 0.18},
            {"ticker": "MSFT", "weight": 0.15},
            {"ticker": "NVDA", "weight": 0.12},
            {"ticker": "GOOGL", "weight": 0.10},
            {"ticker": "AMZN", "weight": 0.09},
            {"ticker": "META", "weight": 0.08},
            {"ticker": "TSLA", "weight": 0.06},
            {"ticker": "JPM", "weight": 0.05},
        ]
        result["metrics"] = {"expected_return": 0.12, "expected_volatility": 0.15, "sharpe": 0.80}

    return result


@router.get("/api/quant/optimize")
async def portfolio_optimization(method: str = "mv"):
    """General portfolio optimization endpoint.

    Args:
        method: mv | rp (risk parity) | hrp | bl (black-litterman) | kelly
    """
    result: dict = {"method": method, "weights": [], "metrics": {}, "source": "generated"}
    data_dir = PROJECT_ROOT / "quant_framework" / "data" / "raw"
    price_files = list(data_dir.glob("price_*.parquet")) if data_dir.exists() else []

    if price_files:
        try:
            import pandas as pd
            df = pd.concat([pd.read_parquet(f) for f in price_files[:5]])
            if "close" in df.columns and "ticker" in df.columns and len(df) > 100:
                prices = df.pivot_table(index="date", columns="ticker", values="close").dropna(axis=1)
                if not prices.empty and len(prices.columns) >= 3:
                    returns = prices.pct_change().dropna()
                    from quant_framework.risk.portfolio_optimizer import (
                        mean_variance_optimize, risk_parity, hierarchical_risk_parity,
                        bl_optimize, kelly_criterion,
                    )
                    method_map = {
                        "mv": mean_variance_optimize,
                        "rp": risk_parity,
                        "hrp": hierarchical_risk_parity,
                        "bl": lambda r: bl_optimize(r),
                        "kelly": kelly_criterion,
                    }
                    opt_fn = method_map.get(method, mean_variance_optimize)
                    try:
                        opt = opt_fn(returns.values)
                    except Exception:
                        opt = mean_variance_optimize(returns.values)  # fallback to MV
                    if "weights" in opt:
                        w = opt["weights"]
                        tickers_list = list(returns.columns[:len(w)])
                        top = sorted(zip(tickers_list, w), key=lambda x: abs(x[1]), reverse=True)[:12]
                        result["weights"] = [
                            {"ticker": t, "weight": round(float(wt), 4)}
                            for t, wt in top if abs(wt) > 0.0001
                        ]
                        result["metrics"] = {
                            "expected_return": round(float(opt.get("expected_return", 0)), 4),
                            "expected_risk": round(float(opt.get("expected_risk", 0)), 4),
                            "sharpe": round(float(opt.get("expected_return", 0)) / max(float(opt.get("expected_risk", 0)), 0.0001), 3) if opt.get("expected_risk", 0) > 0 else 0,
                        }
                        result["source"] = "live"
        except Exception as e:
            result["error"] = str(e)[:200]

    return result


@router.get("/api/backtest/equity")
async def backtest_equity_curve():
    data_dir = PROJECT_ROOT / "quant_framework" / "data" / "raw"
    price_files = list(data_dir.glob("price_*.parquet")) if data_dir.exists() else []

    result = {"equity": None, "drawdown": None, "dates": None, "source": "generated"}

    if price_files:
        try:
            import pandas as pd
            import numpy as np
            df = pd.concat([pd.read_parquet(f) for f in price_files[:5]])
            if "close" in df.columns and "ticker" in df.columns and len(df) > 50:
                prices = df.pivot_table(index="date", columns="ticker", values="close").dropna(axis=1)
                if not prices.empty and len(prices.columns) >= 2:
                    rets = prices.pct_change().dropna()
                    eq_w = rets.mean(axis=1)
                    equity = (1 + eq_w).cumprod()
                    peak = equity.expanding().max()
                    dd = (equity - peak) / peak

                    step = max(1, len(equity) // 500)
                    result["equity"] = [round(float(v), 4) for v in equity.iloc[::step].tolist()]
                    result["drawdown"] = [round(float(v), 4) for v in dd.iloc[::step].tolist()]
                    result["dates"] = [str(d).split(" ")[0] for d in equity.index[::step].tolist()]
                    result["source"] = "live"
        except Exception as e:
            result["error"] = str(e)[:200]

    if result["source"] == "generated":
        import numpy as np
        rng = np.random.default_rng(42)
        n = 252
        rets = rng.normal(0.08 / 252, 0.15 / np.sqrt(252), n)
        equity = (1 + rets).cumprod()
        peak = np.maximum.accumulate(equity)
        dd = (equity - peak) / peak
        result["equity"] = [round(float(v), 4) for v in equity.tolist()]
        result["drawdown"] = [round(float(v), 4) for v in dd.tolist()]

    return result


@router.get("/api/quant/strategies/compare")
async def strategy_comparison():
    result = {"strategies": [], "ranking": [], "source": "generated"}
    data_dir = PROJECT_ROOT / "quant_framework" / "data" / "raw"
    price_files = list(data_dir.glob("price_*.parquet")) if data_dir.exists() else []

    if price_files:
        try:
            import pandas as pd
            import numpy as np
            from quant_framework.backtest.harness import vectorized_backtest, compare_strategies

            df = pd.concat([pd.read_parquet(f) for f in price_files[:5]])
            if "close" in df.columns and "ticker" in df.columns and len(df) > 100:
                prices = df.pivot_table(index="date", columns="ticker", values="close").dropna(axis=1)

                if not prices.empty and len(prices.columns) >= 3:
                    rets = prices.pct_change()
                    tickers = prices.columns.tolist()
                    strategies = {}

                    ew = pd.DataFrame(1.0 / len(tickers), index=prices.index, columns=tickers)
                    strategies["Equal-Weight"] = vectorized_backtest(prices, ew)

                    mom = rets.rolling(21).mean().shift(1)
                    mom_w = mom.div(mom.abs().sum(axis=1), axis=0).fillna(1.0 / len(tickers))
                    strategies["Momentum-21d"] = vectorized_backtest(prices, mom_w)

                    vol = rets.rolling(63).std()
                    rp = (1.0 / vol.replace(0, np.nan)).div(
                        (1.0 / vol.replace(0, np.nan)).sum(axis=1), axis=0
                    ).fillna(1.0 / len(tickers))
                    strategies["Risk-Parity"] = vectorized_backtest(prices, rp)

                    sma50 = prices.rolling(50).mean()
                    sma200 = prices.rolling(200).mean()
                    trend_w = pd.DataFrame(0.0, index=prices.index, columns=tickers)
                    for t in tickers:
                        trend_w[t] = np.where(sma50[t] > sma200[t], 1.0, -1.0)
                    trend_w = trend_w.div(trend_w.abs().sum(axis=1), axis=0).fillna(0)
                    strategies["Trend-50/200"] = vectorized_backtest(prices, trend_w)

                    comp_df = compare_strategies(strategies)
                    result["strategies"] = comp_df.to_dict(orient="records")
                    best = comp_df.sort_values("sharpe_ratio", ascending=False)
                    result["ranking"] = [r["strategy"] for _, r in best.iterrows()]
                    result["best"] = {
                        "name": best.iloc[0]["strategy"],
                        "sharpe": round(float(best.iloc[0].get("sharpe_ratio", 0)), 3),
                    }
                    result["source"] = "live"
                    # Extract equity curves for overlay chart
                    eq = {}
                    for name, s in strategies.items():
                        if "equity_curve" in s and "equity_dates" in s:
                            eq[name] = {"dates": s["equity_dates"], "values": s["equity_curve"]}
                    if eq:
                        result["equity_curves"] = eq
        except Exception as e:
            result["error"] = str(e)[:200]

    if result["source"] == "generated":
        result["strategies"] = [
            {"strategy": "Momentum-21d", "sharpe_ratio": 0.82, "total_return": 0.15, "max_drawdown": -0.12,
             "sortino_ratio": 1.15, "calmar_ratio": 1.25, "win_rate": 0.54, "profit_factor": 1.6,
             "annual_return": 0.15, "annual_volatility": 0.18},
            {"strategy": "Risk-Parity", "sharpe_ratio": 0.95, "total_return": 0.11, "max_drawdown": -0.06,
             "sortino_ratio": 1.42, "calmar_ratio": 1.83, "win_rate": 0.58, "profit_factor": 1.9,
             "annual_return": 0.11, "annual_volatility": 0.12},
            {"strategy": "Equal-Weight", "sharpe_ratio": 0.65, "total_return": 0.10, "max_drawdown": -0.15,
             "sortino_ratio": 0.88, "calmar_ratio": 0.67, "win_rate": 0.51, "profit_factor": 1.3,
             "annual_return": 0.10, "annual_volatility": 0.16},
            {"strategy": "Trend-50/200", "sharpe_ratio": 0.71, "total_return": 0.13, "max_drawdown": -0.10,
             "sortino_ratio": 0.95, "calmar_ratio": 1.30, "win_rate": 0.52, "profit_factor": 1.45,
             "annual_return": 0.13, "annual_volatility": 0.18},
        ]
        result["ranking"] = ["Risk-Parity", "Momentum-21d", "Trend-50/200", "Equal-Weight"]
        result["best"] = {"name": "Risk-Parity", "sharpe": 0.95}
        # Synthetic equity curves for demo
        import numpy as np
        np.random.seed(42)
        n = 252
        dates = [str(pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)) for i in range(n)]
        eq = {}
        profiles = {
            "Momentum-21d": (0.15, 0.18), "Risk-Parity": (0.11, 0.12),
            "Equal-Weight": (0.10, 0.16), "Trend-50/200": (0.13, 0.18),
        }
        for name, (ret, vol) in profiles.items():
            daily_ret = ret / 252
            daily_vol = vol / np.sqrt(252)
            noise = np.random.normal(daily_ret, daily_vol, n)
            eq[name] = {"dates": dates, "values": [round(float(v), 2) for v in (100000 * (1 + noise).cumprod())]}
        result["equity_curves"] = eq

    return result


@router.get("/api/quant/risk/enhanced")
async def quant_risk_enhanced():
    data_dir = PROJECT_ROOT / "quant_framework" / "data" / "raw"
    price_files = list(data_dir.glob("price_*.parquet")) if data_dir.exists() else []

    result = {"var_backtest": None, "stress_scores": None, "source": "generated"}

    if price_files:
        try:
            import pandas as pd
            df = pd.concat([pd.read_parquet(f) for f in price_files[:5]])
            if "close" in df.columns and "ticker" in df.columns and len(df) > 100:
                df["ret"] = df.groupby("ticker")["close"].pct_change()
                returns = df["ret"].dropna()

                if len(returns) > 200:
                    from quant_framework.risk.stress_testing import var_backtest, portfolio_stress_test
                    from quant_framework.risk.risk_metrics import var_historical

                    var95 = var_historical(returns.values, 0.95)
                    var_series = pd.Series(var95, index=returns.index)
                    vb = var_backtest(returns, var_series, cl=0.95)
                    result["var_backtest"] = {
                        "exceedances": vb.get("exceedances", 0),
                        "expected": vb.get("expected", 0),
                        "ratio": round(vb.get("ratio", 0), 3),
                        "kupiec_pvalue": round(vb.get("kupiec_p", 1), 4),
                        "verdict": "PASS" if vb.get("kupiec_p", 0) > 0.05 else "FAIL",
                    }

                    stress = portfolio_stress_test(returns.values, weights=None)
                    result["stress_scores"] = {
                        name: {
                            "sharpe_impact": round(data.get("sharpe_impact", 0), 3),
                            "var95_impact": round(data.get("var95_impact", 0), 3),
                        }
                        for name, data in stress.get("scenarios", {}).items()
                    }
                    result["source"] = "live"
        except Exception as e:
            result["error"] = str(e)[:200]

    if result["source"] == "generated":
        result["var_backtest"] = {
            "exceedances": 12, "expected": 10, "ratio": 1.2,
            "kupiec_pvalue": 0.42, "verdict": "PASS",
        }
        result["stress_scores"] = {
            "2008金融危机": {"sharpe_impact": -2.1, "var95_impact": 0.045},
            "2020新冠": {"sharpe_impact": -1.8, "var95_impact": 0.038},
            "2022加息": {"sharpe_impact": -1.2, "var95_impact": 0.022},
        }
    return result


@router.get("/api/quant/market")
async def quant_market():
    try:
        from quant_framework.data.fetchers.yfinance_fetcher import _fetch_via_yfinance
        from datetime import date, timedelta
        stocks = []
        tickers = QUANT_TICKERS[:10]
        start = (date.today() - timedelta(days=5)).isoformat()
        for t in tickers:
            df = _fetch_via_yfinance(t, start, None)
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                prev = df.iloc[-2] if len(df) > 1 else latest
                chg = (latest["close"] - prev["close"]) / prev["close"] * 100 if prev["close"] else 0
                stocks.append({
                    "ticker": t,
                    "price": round(float(latest["close"]), 2),
                    "change_pct": round(float(chg), 2),
                    "volume": int(latest.get("volume", 0)),
                })
            if stocks:
                return {"stocks": stocks, "source": "live"}
    except Exception:
        pass

    rng = random.Random(42)
    stocks = []
    for t in QUANT_TICKERS[:15]:
        price = rng.uniform(20, 500)
        chg = rng.gauss(0, 1.5)
        vol = rng.randint(500000, 50000000)
        stocks.append({"ticker": t, "price": round(price, 2), "change_pct": round(chg, 2), "volume": vol})
    return {"stocks": sorted(stocks, key=lambda x: x["change_pct"], reverse=True), "source": "generated"}


@router.get("/api/backtest/param_sweep")
async def param_sweep():
    result = {"heatmap": [], "x_labels": [], "y_labels": [], "best": None, "source": "generated"}
    data_dir = PROJECT_ROOT / "quant_framework" / "data" / "raw"
    price_files = list(data_dir.glob("price_*.parquet")) if data_dir.exists() else []

    if price_files:
        try:
            import pandas as pd
            import numpy as np
            from quant_framework.backtest.harness import vectorized_backtest

            df = pd.concat([pd.read_parquet(f) for f in price_files[:5]])
            if "close" in df.columns and "ticker" in df.columns and len(df) > 100:
                prices = df.pivot_table(index="date", columns="ticker", values="close").dropna(axis=1)
                if not prices.empty and len(prices.columns) >= 3:
                    rets = prices.pct_change().dropna()
                    tickers = prices.columns.tolist()

                    lookbacks = [5, 10, 21, 42, 63, 126]
                    thresholds = [0.0, 0.01, 0.02, 0.03, 0.05]

                    heatmap = []
                    best_sharpe = -999
                    best_params = None

                    for lb in lookbacks:
                        row = []
                        mom = rets.rolling(lb).mean().shift(1)
                        for th in thresholds:
                            w = pd.DataFrame(0.0, index=rets.index, columns=tickers)
                            for t in tickers:
                                w[t] = np.where(mom[t] > th, 1.0, np.where(mom[t] < -th, -1.0, 0))
                            w_sum = w.abs().sum(axis=1).replace(0, 1)
                            w = w.div(w_sum, axis=0).fillna(0)
                            bt = vectorized_backtest(prices, w)
                            sr = bt.get("sharpe_ratio", 0) or 0
                            row.append(round(float(sr), 3))
                            if sr > best_sharpe:
                                best_sharpe = sr
                                best_params = {"lookback": lb, "threshold": th}
                        heatmap.append(row)

                    result["heatmap"] = heatmap
                    result["x_labels"] = [f"{t:.2f}" for t in thresholds]
                    result["y_labels"] = [str(lb) for lb in lookbacks]
                    result["best"] = {"lookback": best_params["lookback"], "threshold": best_params["threshold"], "sharpe": round(best_sharpe, 3)}
                    result["source"] = "live"
        except Exception as e:
            result["error"] = str(e)[:200]

    if result["source"] == "generated":
        import numpy as np
        rng_np = np.random.default_rng(42)
        lookbacks = [5, 10, 21, 42, 63, 126]
        thresholds = [0.0, 0.01, 0.02, 0.03, 0.05]
        heatmap = []
        for lb in lookbacks:
            row = [round(float(0.3 + 0.04 * np.log(lb) + 0.02 / max(th, 0.005) + rng_np.normal(0, 0.05)), 3) for th in thresholds]
            heatmap.append(row)
        result["heatmap"] = heatmap
        result["x_labels"] = [f"{t:.2f}" for t in thresholds]
        result["y_labels"] = [str(lb) for lb in lookbacks]
        best_row = int(np.argmax([max(r) for r in heatmap]))
        best_col = int(np.argmax(heatmap[best_row]))
        result["best"] = {"lookback": lookbacks[best_row], "threshold": thresholds[best_col], "sharpe": heatmap[best_row][best_col]}

    return result


@router.get("/api/factor/decay")
async def factor_decay_alerts():
    try:
        from quant_framework.strategies.factor_decay import check_decay_alerts, report_markdown
        from quant_framework.strategies.factor_combiner import _cs_ic_series
        from scripts.run_pipeline import step1_fetch, step2_factors

        tickers = QUANT_TICKERS[:15]
        df = step1_fetch(tickers, "2025-01-01")
        factors = step2_factors(df)
        factor_cols = [c for c in factors.columns if c not in ("ticker", "date", "close")]

        ic_df = _cs_ic_series(factors, factor_cols)
        if ic_df.empty:
            return {"alerts": [], "status": "no_data", "message": "Insufficient data for IC computation"}

        alerts = check_decay_alerts(ic_df, factor_df=factors, factor_cols=factor_cols)
        report = report_markdown(alerts, ic_df)

        return {
            "alerts": [
                {"factor": a.factor, "type": a.alert_type, "severity": a.severity,
                 "detail": a.detail, "metric": a.metric_value, "threshold": a.threshold,
                 "timestamp": a.timestamp}
                for a in alerts
            ],
            "count": len(alerts),
            "critical": sum(1 for a in alerts if a.severity == "critical"),
            "warning": sum(1 for a in alerts if a.severity == "warning"),
            "report": report,
            "status": "ok",
        }
    except Exception as e:
        return {"alerts": [], "status": "error", "message": str(e)}


@router.get("/api/strategy/sensitivity")
async def strategy_sensitivity():
    try:
        import numpy as np
        import pandas as pd
        from quant_framework.strategies.sensitivity import sensitivity_matrix, report_markdown
        from quant_framework.strategies.factor_combiner import (
            ic_weighted_combine, filter_factors_by_ic, generate_signals,
        )
        from quant_framework.backtest.harness import vectorized_backtest

        # Use real pipeline data for strategy sensitivity
        data_dir = PROJECT_ROOT / "quant_framework" / "data" / "raw"
        price_files = list(data_dir.glob("price_*.parquet")) if data_dir.exists() else []

        if price_files:
            df = pd.concat([pd.read_parquet(f) for f in price_files[:5]])
            if "close" in df.columns and "ticker" in df.columns and len(df) > 200:
                from quant_framework.strategies.qlib_factor_engine import compute_all_factors
                factors = compute_all_factors(df)
                exclude = {"ticker", "date", "close", "open", "high", "low", "volume", "industry"}
                factor_cols = [c for c in factors.columns if c not in exclude]
                active = filter_factors_by_ic(factors, factor_cols, ic_threshold=0.02, min_factors=3)

                prices = factors.pivot_table(index="date", columns="ticker", values="close").dropna(axis=1)

                def real_strategy(ic_shrinkage=0.2, ic_horizon=21, top_k=20):
                    result = ic_weighted_combine(factors, active, factors["close"],
                                                  ic_shrinkage=ic_shrinkage)
                    signals = generate_signals(result, "combined_score", top_k=int(top_k),
                                               method="long_only")
                    pivot_s = signals.pivot_table(index="date", columns="ticker",
                                                  values="signal", aggfunc="last").sort_index().fillna(0)
                    bt = vectorized_backtest(prices, pivot_s)
                    return {"sharpe": bt.get("sharpe_ratio", 0) or 0}

                base_params = {"ic_shrinkage": 0.2, "ic_horizon": 21, "top_k": 20}
                df = sensitivity_matrix(real_strategy, base_params, list(base_params.keys()),
                                        perturb_pct=0.2)
                report = report_markdown(df)
                return {"results": df.to_dict(orient="records"), "report": report, "status": "ok"}

        # Fallback: toy strategy
        from quant_framework.strategies.sensitivity import sensitivity_matrix as sm, report_markdown as rm
        def toy(**kw):
            return {"sharpe": 1.5 + np.random.default_rng(42).normal(0, 0.1)}
        base = {"shrinkage": 0.2, "horizon": 21}
        df = sm(toy, base, list(base.keys()), perturb_pct=0.2)
        return {"results": df.to_dict(orient="records"), "report": rm(df), "status": "ok", "source": "generated"}
    except Exception as e:
        return {"results": [], "status": "error", "message": str(e)}


# ═══════════════════════════════════════════════════════════════
# Stock Recommendation Engine (with plain-language explanations)
# ═══════════════════════════════════════════════════════════════

_FACTOR_HUMAN_NAMES_CN = {
    "mom_21d": "21日动量", "mom_5d": "5日动量", "mom_63d": "63日动量",
    "rev_5d": "5日反转", "rev_21d": "21日反转",
    "vol_21d": "21日波动率", "vol_63d": "63日波动率",
    "val_bp": "账面市值比(价值)", "val_ep": "盈利市值比(价值)",
    "val_sp": "营收市值比(价值)", "val_cf": "现金流市值比(价值)",
    "quality_roe": "ROE(质量)", "quality_roa": "ROA(质量)",
    "quality_gross_margin": "毛利率(质量)", "quality_accruals": "应计利润(质量)",
    "size_log_mcap": "规模因子", "liquidity_turnover": "换手率",
    "growth_sue": "标准化意外盈利(增长)", "growth_egr": "盈利增长率(增长)",
    "rsi_14": "RSI-14", "bb_20_2": "布林带位置",
    "ma_cross_50_200": "均线交叉(50/200)",
    "leverage_de": "负债权益比(杠杆)", "beta_63d": "63日Beta",
    "skew_21d": "21日偏度", "kurt_21d": "21日峰度",
}

_FACTOR_CATEGORIES_CN = {
    "动量类": ["mom_21d", "mom_5d", "mom_63d", "rsi_14"],
    "反转类": ["rev_5d", "rev_21d"],
    "价值类": ["val_bp", "val_ep", "val_sp", "val_cf"],
    "质量类": ["quality_roe", "quality_roa", "quality_gross_margin", "quality_accruals"],
    "波动类": ["vol_21d", "vol_63d", "beta_63d", "skew_21d", "kurt_21d"],
    "技术类": ["bb_20_2", "ma_cross_50_200"],
    "规模/流动性": ["size_log_mcap", "liquidity_turnover"],
    "增长类": ["growth_sue", "growth_egr"],
    "杠杆类": ["leverage_de"],
}


def _explain_factor(name: str, value: float, z_score: float) -> dict:
    """Generate a plain-Chinese explanation for a single factor's contribution."""
    display = _FACTOR_HUMAN_NAMES_CN.get(name, name)
    if z_score > 1.5:
        direction = "极强看涨信号"
        strength = "high_positive"
    elif z_score > 0.5:
        direction = "看涨"
        strength = "positive"
    elif z_score < -1.5:
        direction = "极强看跌信号"
        strength = "high_negative"
    elif z_score < -0.5:
        direction = "看跌"
        strength = "negative"
    else:
        direction = "中性"
        strength = "neutral"

    return {
        "factor": name,
        "display_name": display,
        "raw_value": round(value, 4) if value is not None else None,
        "z_score": round(z_score, 4),
        "direction": direction,
        "strength": strength,
    }


def _generate_recommendation_reason(
    ticker: str,
    score: float,
    signal: int,
    factor_details: list[dict],
    method: str = "ic_weighted",
) -> str:
    """Generate a natural-language Chinese rationale for a stock pick."""
    parts = []
    direction_word = "看好" if signal == 1 else "看空"

    if method == "ic_weighted":
        parts.append(f"综合{len(factor_details)}个有效因子计算，{ticker}得分{score:.3f}，整体{direction_word}。")
    elif method == "ml":
        parts.append(f"机器学习模型预测{direction_word}，{ticker}综合得分{score:.3f}。")
    else:
        parts.append(f"{ticker}复合得分{score:.3f}，信号为{direction_word}。")

    # Find strongest supporting and opposing factors
    if factor_details:
        pos_factors = [f for f in factor_details if f["z_score"] > 0.3]
        neg_factors = [f for f in factor_details if f["z_score"] < -0.3]
        pos_factors.sort(key=lambda x: -x["z_score"])
        neg_factors.sort(key=lambda x: x["z_score"])

        if pos_factors:
            names = "、".join(f["display_name"] for f in pos_factors[:3])
            parts.append(f"最强支撑因子：{names}。")
        if neg_factors and signal == 1:
            names = "、".join(f["display_name"] for f in neg_factors[:2])
            parts.append(f"需注意负面信号：{names}偏弱。")
        elif neg_factors and signal == -1:
            names = "、".join(f["display_name"] for f in neg_factors[:2])
            parts.append(f"看空依据：{names}显著偏弱。")

    # Conviction level
    abs_score = abs(score)
    if abs_score > 2.0:
        parts.append("信号强度：极高，统计置信度高。")
    elif abs_score > 1.0:
        parts.append("信号强度：中高，建议参考仓位不超过组合的10%。")
    elif abs_score > 0.5:
        parts.append("信号强度：中等，建议结合其他信息判断。")
    else:
        parts.append("信号强度：偏低，可能不适合作为独立交易依据。")

    return "".join(parts)


@router.get("/api/quant/recommendations")
async def stock_recommendations():
    """
    Generate stock recommendations with factor attribution and
    plain-Chinese explanations suitable for non-quant users.
    """
    result: dict = {
        "recommendations": [],
        "summary": "",
        "method": "ic_weighted",
        "source": "generated",
        "generated_at": datetime.now().isoformat(),
    }
    data_dir = PROJECT_ROOT / "quant_framework" / "data" / "raw"
    price_files = list(data_dir.glob("price_*.parquet")) if data_dir.exists() else []

    if price_files:
        try:
            import pandas as pd
            import numpy as np
            from quant_framework.strategies.qlib_factor_engine import compute_all_factors
            from quant_framework.strategies.factor_combiner import (
                ic_weighted_combine, filter_factors_by_ic, generate_signals,
            )

            df = pd.concat([pd.read_parquet(f) for f in price_files[:5]])
            if "close" not in df.columns or "ticker" not in df.columns:
                raise ValueError("Data missing required columns")

            factors = compute_all_factors(df, neutralize=True)
            exclude = {"ticker", "date", "close", "open", "high", "low", "volume", "industry"}
            factor_cols = [c for c in factors.columns if c not in exclude]
            if len(factor_cols) < 3:
                raise ValueError(f"Only {len(factor_cols)} factor columns found")

            # Filter factors by IC quality
            active = filter_factors_by_ic(factors, factor_cols, ic_threshold=0.02, min_factors=5)
            if len(active) < 3:
                active = factor_cols[:8]  # fallback to top 8

            # Combine and generate signals
            combined = ic_weighted_combine(factors, active, factors["close"], ic_threshold=0.0)
            signals = generate_signals(combined, "combined_score", top_k=15, method="long_short")

            # Get latest date
            latest_date = signals["date"].max() if "date" in signals.columns else None
            latest = signals[signals["date"] == latest_date] if latest_date is not None else signals

            # Compute factor-level z-scores for attribution
            factor_means = factors[active].mean()
            factor_stds = factors[active].std().replace(0, 1.0)

            recommendations = []
            for _, row in latest.iterrows():
                ticker = str(row.get("ticker", "?"))
                score = float(row.get("combined_score", 0))
                sig = int(row.get("signal", 0))
                if sig == 0:
                    continue

                # Get this stock's factor values
                stock_rows = factors[factors["ticker"] == ticker]
                if stock_rows.empty:
                    continue
                latest_factors = stock_rows.iloc[-1]

                # Compute z-scores for each factor
                factor_details = []
                category_contrib = {}
                for f in active:
                    if f in latest_factors.index and f in factor_means.index:
                        val = float(latest_factors[f])
                        z = (val - float(factor_means[f])) / float(factor_stds[f]) if float(factor_stds[f]) > 0 else 0
                        detail = _explain_factor(f, val, z)
                        factor_details.append(detail)

                        # Aggregate by category
                        for cat, cat_factors in _FACTOR_CATEGORIES_CN.items():
                            if f in cat_factors:
                                category_contrib.setdefault(cat, []).append(z)
                                break

                # Summarize category contributions
                cat_summary = {}
                for cat, zs in category_contrib.items():
                    avg_z = sum(zs) / len(zs) if zs else 0
                    cat_summary[cat] = {
                        "average_z_score": round(avg_z, 3),
                        "direction": "看涨" if avg_z > 0.3 else "看跌" if avg_z < -0.3 else "中性",
                        "factors_count": len(zs),
                    }

                reason = _generate_recommendation_reason(ticker, score, sig, factor_details)

                recommendations.append({
                    "ticker": ticker,
                    "signal": "看涨" if sig == 1 else "看跌",
                    "signal_raw": sig,
                    "score": round(score, 4),
                    "conviction": "高" if abs(score) > 2 else "中" if abs(score) > 1 else "低",
                    "category_contributions": cat_summary,
                    "top_factors": sorted(factor_details, key=lambda x: -abs(x["z_score"]))[:5],
                    "reason": reason,
                })

            # Sort by conviction
            recommendations.sort(key=lambda x: -abs(x["score"]))

            # Generate overall summary
            long_count = sum(1 for r in recommendations if r["signal_raw"] == 1)
            short_count = sum(1 for r in recommendations if r["signal_raw"] == -1)
            high_conv = sum(1 for r in recommendations if r["conviction"] == "高")

            result["recommendations"] = recommendations[:20]
            result["summary"] = (
                f"基于{len(active)}个有效因子，生成了{len(recommendations)}条交易建议"
                f"（{long_count}条看涨，{short_count}条看跌），其中{high_conv}条高置信度。"
                f"数据日期：{str(latest_date).split(' ')[0] if latest_date else '最新'}。"
            )
            result["factors_used"] = len(active)
            result["source"] = "live"

        except Exception as e:
            result["error"] = str(e)[:300]
            result["summary"] = f"实时数据计算出错：{str(e)[:100]}。使用模拟数据。"
    else:
        result["summary"] = "暂无实时数据文件。请先运行数据管道。"

    # Fallback to generated data
    if result["source"] != "live":
        rng = random.Random(42)
        import numpy as np
        recommendations = []
        tickers_pool = QUANT_TICKERS[:20]
        rng.shuffle(tickers_pool)
        factor_names_sample = list(_FACTOR_HUMAN_NAMES_CN.keys())
        rng.shuffle(factor_names_sample)

        for i, t in enumerate(tickers_pool[:12]):
            sig = 1 if rng.random() > 0.35 else -1
            score = round(abs(rng.gauss(1.5, 0.7)) * (1 if sig == 1 else -1), 3)
            top_factors = []
            cat_summary = {}
            for fi in range(min(5, len(factor_names_sample))):
                fn = factor_names_sample[fi]
                z = round(rng.gauss(0.5 if sig == 1 else -0.5, 0.8), 3)
                detail = _explain_factor(fn, 0, z)
                top_factors.append(detail)
                for cat, cat_factors in _FACTOR_CATEGORIES_CN.items():
                    if fn in cat_factors:
                        cat_summary.setdefault(cat, {"zs": [], "n": 0})
                        cat_summary[cat]["zs"].append(z)
                        cat_summary[cat]["n"] += 1

            cat_out = {}
            for cat, v in cat_summary.items():
                avg_z = sum(v["zs"]) / len(v["zs"]) if v["zs"] else 0
                cat_out[cat] = {
                    "average_z_score": round(avg_z, 3),
                    "direction": "看涨" if avg_z > 0.3 else "看跌" if avg_z < -0.3 else "中性",
                    "factors_count": v["n"],
                }

            reason = _generate_recommendation_reason(t, score, sig, top_factors, method="ic_weighted")

            recommendations.append({
                "ticker": t,
                "signal": "看涨" if sig == 1 else "看跌",
                "signal_raw": sig,
                "score": score,
                "conviction": "高" if abs(score) > 2 else "中" if abs(score) > 1 else "低",
                "category_contributions": cat_out,
                "top_factors": top_factors,
                "reason": reason,
            })

        recommendations.sort(key=lambda x: -abs(x["score"]))
        result["recommendations"] = recommendations[:15]
        long_count = sum(1 for r in recommendations[:15] if r["signal_raw"] == 1)
        short_count = sum(1 for r in recommendations[:15] if r["signal_raw"] == -1)
        result["summary"] = (
            f"基于模拟因子数据，生成了{len(recommendations[:15])}条示例建议"
            f"（{long_count}条看涨，{short_count}条看跌）。"
            f"启动数据管道后切换到实时计算。"
        )

    return result
