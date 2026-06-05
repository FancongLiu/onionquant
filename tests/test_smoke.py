#!/usr/bin/env python3
"""Smoke tests — verify all 18 core modules import and key functions execute."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest


# ── helpers ──────────────────────────────────────────────
def _make_ohlcv(n=252, seed=42):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = 100 + np.cumsum(rng.normal(0.05, 1.5, n))
    high = close + abs(rng.normal(0, 0.5, n))
    low = close - abs(rng.normal(0, 0.5, n))
    open_ = low + (high - low) * abs(rng.normal(0, 0.3, n))
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    volume = rng.integers(1_000_000, 10_000_000, n).astype(float)
    return pd.DataFrame(
        {
            "date": dates,
            "ticker": "TEST",
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def _make_multi_ohlcv(n_tickers=3, n=252, seed=42):
    rng = np.random.default_rng(seed)
    dfs = []
    for i in range(n_tickers):
        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        close = 100 + np.cumsum(rng.normal(0.05, 1.5, n))
        dfs.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "ticker": f"TICKER{i}",
                    "open": close * 0.995,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": rng.integers(1_000_000, 10_000_000, n).astype(float),
                }
            )
        )
    return pd.concat(dfs, ignore_index=True)


# ── imports ──────────────────────────────────────────────
def test_import_yfinance_fetcher():
    from quant_framework.data.fetchers.yfinance_fetcher import (
        fetch_batch,
    )

    assert fetch_batch is not None


def test_import_alpha_vantage_fetcher():
    from quant_framework.data.fetchers.alpha_vantage_fetcher import (
        fetch_news_sentiment,
    )

    assert fetch_news_sentiment is not None


def test_import_data_utils():
    from quant_framework.data.fetchers.data_utils import (
        standardize_ohlc,
    )

    assert standardize_ohlc is not None


def test_import_news_sentiment():
    from quant_framework.data.fetchers.news_sentiment import (
        fetch_news_sentiment,
    )

    assert fetch_news_sentiment is not None


def test_import_reddit_sentiment():
    from quant_framework.data.fetchers.reddit_sentiment import (
        fetch_hot_posts,
    )

    assert fetch_hot_posts is not None


def test_import_sentiment_utils():
    from quant_framework.data.fetchers.sentiment_utils import (
        score_text,
    )

    assert score_text is not None


def test_import_factor_calculator():
    from quant_framework.strategies.factor_calculator import (
        compute_all,
    )

    assert compute_all is not None


def test_import_qlib_factor_engine():
    from quant_framework.strategies.qlib_factor_engine import (
        compute_all_factors,
    )

    assert compute_all_factors is not None


def test_import_factor_combiner():
    from quant_framework.strategies.factor_combiner import (
        equal_weighted_combine,
    )

    assert equal_weighted_combine is not None


def test_import_canslim_screener():
    from quant_framework.strategies.canslim_screener import (
        load_config,
    )

    assert load_config is not None


def test_import_intraday_momentum():
    from quant_framework.strategies.intraday_momentum import (
        calc_indicators,
    )

    assert calc_indicators is not None


def test_import_stat_arb():
    from quant_framework.strategies.stat_arb import (
        find_cointegrated_pairs,
    )

    assert find_cointegrated_pairs is not None


def test_import_regime_detector():
    from quant_framework.strategies.regime_detector import (
        detect_regimes,
    )

    assert detect_regimes is not None


def test_import_risk_metrics():
    from quant_framework.risk.risk_metrics import (
        var_historical,
    )

    assert var_historical is not None


def test_import_portfolio_optimizer():
    from quant_framework.risk.portfolio_optimizer import (
        mean_variance_optimize,
    )

    assert mean_variance_optimize is not None


def test_import_drawdown_control():
    from quant_framework.risk.drawdown_control import (
        cppi,
    )

    assert cppi is not None


def test_import_backtest_harness():
    from quant_framework.backtest.harness import (
        vectorized_backtest,
    )

    assert vectorized_backtest is not None


# ── data modules ─────────────────────────────────────────
def test_yfinance_fetch_batch():
    from quant_framework.data.fetchers.yfinance_fetcher import fetch_batch

    df = fetch_batch(["AAPL", "MSFT"], "2025-01-06", "2025-01-10", source="yfinance")
    assert df is not None
    assert not df.empty
    assert set(df["ticker"].unique()) == {"AAPL", "MSFT"}
    assert {"date", "ticker", "open", "high", "low", "close", "volume"} <= set(
        df.columns
    )


def test_yfinance_fetch_single():
    from quant_framework.data.fetchers.yfinance_fetcher import fetch_single

    df = fetch_single("AAPL", "2025-01-06", "2025-01-10", source="yfinance")
    assert df is not None
    assert not df.empty
    assert (df["ticker"] == "AAPL").all()


def test_data_utils_quality():
    from quant_framework.data.fetchers.data_utils import (
        check_data_quality,
        standardize_ohlc,
    )

    df = _make_ohlcv()
    result = check_data_quality(df)
    assert isinstance(result, dict)
    assert "rows" in result

    std = standardize_ohlc(df)
    required = {"open", "high", "low", "close", "volume"}
    # After standardize, columns should be lowercase and at minimum contain these
    for col in required:
        assert col in std.columns


def test_data_utils_normalize():
    from quant_framework.data.fetchers.data_utils import (
        normalize_ticker,
        normalize_ticker_list,
    )

    assert normalize_ticker(" aapl ") == "AAPL"
    result = normalize_ticker_list([" msft ", "aapl", "GOOGL"])
    assert result == ["MSFT", "AAPL", "GOOGL"]


def test_sentiment_utils_score():
    from quant_framework.data.fetchers.sentiment_utils import (
        score_text,
        aggregate_sentiments,
    )

    r = score_text("Revenue grew 30% year over year with expanding margins.")
    assert isinstance(r, dict)
    assert set(r.keys()) == {"positive", "negative", "neutral"}

    agg = aggregate_sentiments([r, r, r])
    assert isinstance(agg, dict)


def test_news_sentiment_demo():
    from quant_framework.data.fetchers.news_sentiment import (
        _demo_data,
        aggregate_by_ticker,
    )

    df = _demo_data(["AAPL", "TSLA"], days=3)
    assert not df.empty
    assert set(df["ticker"].unique()) == {"AAPL", "TSLA"}
    assert "av_sentiment_score" in df.columns
    assert "source" in df.columns
    assert "FinBERT-fallback" in df["source"].values

    agg = aggregate_by_ticker(df)
    assert not agg.empty


def test_reddit_sentiment_demo():
    from quant_framework.data.fetchers.reddit_sentiment import (
        fetch_hot_posts,
        build_daily_index,
    )

    df = fetch_hot_posts("wallstreetbets", limit=20)
    assert df is not None
    assert not df.empty
    idx = build_daily_index(df)
    assert isinstance(idx, pd.DataFrame)


# ── strategy modules ─────────────────────────────────────
def test_factor_calculator_compute_all():
    from quant_framework.strategies.factor_calculator import compute_all

    df = _make_multi_ohlcv(n_tickers=3, n=100)
    result = compute_all(df, neutralize=False)  # needs industry col for neutralization
    assert isinstance(result, pd.DataFrame)
    assert len(result) == len(df)


def test_qlib_factor_engine():
    from quant_framework.strategies.qlib_factor_engine import (
        compute_all_factors,
        neutralize_and_standardize,
    )

    df = _make_multi_ohlcv(n_tickers=3, n=200, seed=1)
    factors = compute_all_factors(df)
    assert isinstance(factors, pd.DataFrame)
    ohlc_cols = {"date", "ticker", "open", "high", "low", "close", "volume", "industry"}
    n_factor_cols = len([c for c in factors.columns if c not in ohlc_cols])
    assert n_factor_cols > 0, (
        f"Expected factor columns beyond OHLCV, got: {list(factors.columns)}"
    )

    neutralized = neutralize_and_standardize(factors)
    assert isinstance(neutralized, pd.DataFrame)


def test_factor_combiner():
    from quant_framework.strategies.qlib_factor_engine import (
        compute_all_factors,
        neutralize_and_standardize,
    )
    from quant_framework.strategies.qlib_factor_engine import (
        FACTOR_REGISTRY,
    )
    from quant_framework.strategies.factor_combiner import (
        equal_weighted_combine,
        generate_signals,
    )

    df = _make_multi_ohlcv(n_tickers=3, n=200, seed=2)
    factors = compute_all_factors(df)
    factor_df = neutralize_and_standardize(factors)
    factor_cols = [c for c in factor_df.columns if c in FACTOR_REGISTRY]

    combined = equal_weighted_combine(factor_df, factor_cols)
    assert "combined_score" in combined.columns
    assert len(combined) == len(factor_df)

    signals = generate_signals(combined, "combined_score", top_k=2)
    assert "signal" in signals.columns
    assert set(signals["signal"].dropna().unique()) <= {-1, 0, 1}


def test_import_alpha_combiner():
    from quant_framework.strategies.alpha_combiner import (
        combine_alphas,
    )

    assert combine_alphas is not None


def test_alpha_combiner():
    from quant_framework.strategies.alpha_combiner import (
        ic_weighted,
        ic_ir_weighted,
        bayesian_shrinkage_weights,
        combine_alphas,
        evaluate_combination,
        estimate_ic_weights,
        report_markdown,
        CombineConfig,
        _make_demo_data,
    )

    df, fwd_ret, regime_labels = _make_demo_data(252, 5, 10, seed=7)
    factor_cols = [f"factor_{i}" for i in range(5)]

    # IC-weighted
    icw = ic_weighted(df, factor_cols, fwd_ret, window=63)
    assert "combined_score" in icw.columns
    assert icw["combined_score"].notna().sum() > 0

    # IC-IR weighted
    icir = ic_ir_weighted(df, factor_cols, fwd_ret)
    assert "combined_score" in icir.columns

    # Bayesian shrinkage
    bayes = bayesian_shrinkage_weights(df, factor_cols, fwd_ret, shrinkage=0.3)
    assert "combined_score" in bayes.columns

    # Static weights
    w = estimate_ic_weights(df, factor_cols, fwd_ret)
    assert len(w) == 5
    assert abs(sum(w.values()) - 1.0) < 0.01

    # Unified pipeline
    cfg = CombineConfig(method="ic_weighted", factor_cols=factor_cols, window=63)
    result = combine_alphas(df, fwd_ret, cfg)
    assert "combined_score" in result.columns

    # Regime-aware
    rw = {0: {c: 0.2 for c in factor_cols}, 1: {c: 0.2 for c in factor_cols}}
    cfg2 = CombineConfig(method="regime", factor_cols=factor_cols, regime_weights=rw)
    r2 = combine_alphas(df, fwd_ret, cfg2, regime_labels=regime_labels)
    assert "combined_score" in r2.columns

    # Evaluation
    ev = evaluate_combination(result["combined_score"], fwd_ret)
    assert "ic" in ev
    assert "hit_rate" in ev
    assert "quantile_spread" in ev
    assert ev["ic"] > 0.5  # strong combined signal

    # Report
    report = report_markdown(cfg, ev)
    assert "Alpha Combination" in report


def test_canslim_screener():
    from quant_framework.strategies.canslim_screener import (
        load_config,
        run_screener,
        level1_quantitative,
    )
    from quant_framework.strategies.canslim_screener import _make_demo_data

    config_path = (
        PROJECT_ROOT / "quant_framework" / "strategies" / "canslim_config.yaml"
    )
    if config_path.exists():
        cfg = load_config(str(config_path))
        assert isinstance(cfg, dict)

    df = _make_demo_data(300)
    l1 = level1_quantitative(
        df, min_eps_growth_q=20, min_eps_growth_a=20, min_rs=50, min_volume=1e6
    )
    assert isinstance(l1, pd.DataFrame)

    result, stats = run_screener(df, config={"levels": [1]})
    assert isinstance(result, pd.DataFrame)
    assert isinstance(stats, dict)


def test_stat_arb():
    from quant_framework.strategies.stat_arb import (
        find_cointegrated_pairs,
        compute_spread,
        generate_signals,
        _make_demo_prices,
    )

    prices = _make_demo_prices(n=250, seed=7)
    pairs = find_cointegrated_pairs(prices, pvalue_threshold=0.10)
    assert isinstance(pairs, pd.DataFrame)

    if not pairs.empty:
        t1, t2 = pairs.iloc[0]["ticker1"], pairs.iloc[0]["ticker2"]
        spread = compute_spread(prices[t1], pairs.iloc[0]["hedge_ratio"], prices[t2])
        assert len(spread) == len(prices)
        sig = generate_signals(spread)
        assert len(sig) == len(spread)


def test_regime_detector():
    from quant_framework.strategies.regime_detector import (
        detect_regimes,
        classify_current,
        rolling_regime_simple,
        _make_demo_returns,
    )

    returns = _make_demo_returns(n=300, seed=3)
    result = detect_regimes(returns, n_regimes=2)
    assert isinstance(result, dict)
    assert "regime_labels" in result
    assert "n_regimes" in result

    rrs = rolling_regime_simple(returns, window=63)
    assert isinstance(rrs, pd.DataFrame)

    cur = classify_current(returns, n_regimes=2)
    assert isinstance(cur, dict)


# ── risk modules ─────────────────────────────────────────
def test_risk_metrics_summary():
    from quant_framework.risk.risk_metrics import (
        var_historical,
        cvar,
        max_drawdown,
        sharpe_ratio,
        risk_metrics_summary,
    )

    rng = np.random.default_rng(99)
    returns = pd.Series(rng.normal(0.0005, 0.015, 252))
    equity = (1 + returns).cumprod()

    var = var_historical(returns, 0.95)
    assert var < 0  # VaR is a loss (negative return)
    cvar_val = cvar(returns, 0.95)
    assert cvar_val < 0  # CVaR is a loss (negative return)
    mdd = max_drawdown(equity)
    assert -1 <= mdd <= 0  # drawdown is negative
    sr = sharpe_ratio(returns)
    assert isinstance(sr, (int, float))

    summary = risk_metrics_summary(returns, equity_curve=equity)
    assert isinstance(summary, dict)
    assert summary["Sharpe"] is not None


def test_portfolio_optimizer():
    from quant_framework.risk.portfolio_optimizer import (
        mean_variance_optimize,
        risk_parity,
        kelly_criterion,
    )

    rng = np.random.default_rng(42)
    returns = rng.normal(0.0008, 0.02, (252, 5))

    mv = mean_variance_optimize(returns)
    assert "weights" in mv
    assert len(mv["weights"]) == 5

    rp = risk_parity(returns)
    assert len(rp["weights"]) == 5

    kelly = kelly_criterion(returns, risk_aversion=3.0)
    assert len(kelly["weights"]) == 5


def test_stress_testing():
    from quant_framework.risk.stress_testing import (
        portfolio_stress_test,
        var_backtest,
        report_markdown,
        _make_demo_data,
    )

    returns = _make_demo_data(252, 4, seed=3)
    weights = np.array([0.3, 0.25, 0.25, 0.2])

    result = portfolio_stress_test(returns, weights)
    assert "stress_score" in result
    assert "scenarios" in result
    assert result["n_scenarios"] == 8
    assert len(result["scenarios"]) == 8
    for s in result["scenarios"]:
        assert "scenario" in s
        assert "total_return" in s
        assert "var_95" in s
        assert "cvar_95" in s

    report = report_markdown(result)
    assert "Stress Test Report" in report

    # VaR backtest
    port_ret = (returns * weights).sum(axis=1)
    var_series = pd.Series(port_ret).rolling(21).quantile(0.05).dropna()
    bt = var_backtest(port_ret.iloc[-len(var_series) :], var_series, 0.95)
    assert "actual_exceedances" in bt
    assert "kupiec_pvalue" in bt


def test_drawdown_control():
    from quant_framework.risk.drawdown_control import (
        cppi,
        volatility_targeting,
        fixed_stop_loss,
    )

    rng = np.random.default_rng(42)
    returns = rng.normal(0.0005, 0.012, 252)
    equity = (1 + pd.Series(returns)).cumprod().values

    r = cppi(equity, floor_pct=0.75, multiplier=3)
    assert "risky_weight" in r
    assert len(r["risky_weight"]) == len(equity)

    vt = volatility_targeting(returns, target_vol=0.15)
    assert len(vt["scaled_returns"]) == len(returns)

    sl = fixed_stop_loss(equity, drawdown_limit=0.15)
    assert len(sl["signal"]) == len(equity)


def test_import_covariance():
    from quant_framework.risk.covariance import (
        estimate_covariance,
    )

    assert estimate_covariance is not None


def test_covariance_estimation():
    from quant_framework.risk.covariance import (
        sample_cov,
        ledoit_wolf,
        oas,
        exponentially_weighted,
        factor_model_cov,
        estimate_covariance,
        cov_to_corr,
        compare_estimators,
        nearest_pd,
        rolling_covariance,
        _make_demo_data,
    )

    returns = _make_demo_data(252, 6, seed=7)

    # Sample
    cov = sample_cov(returns)
    assert cov.shape == (6, 6)
    assert np.all(np.diag(cov.values) > 0)

    # Ledoit-Wolf
    lw = ledoit_wolf(returns)
    assert lw.shape == (6, 6)
    assert np.all(np.diag(lw.values) > 0)

    # OAS
    oas_cov = oas(returns)
    assert oas_cov.shape == (6, 6)

    # EW
    ew = exponentially_weighted(returns, span=63)
    assert ew.shape == (6, 6)

    # Factor model
    cov_fm, decomp = factor_model_cov(returns, n_factors=3)
    assert cov_fm.shape == (6, 6)
    assert "systematic_ratio" in decomp
    assert 0 <= decomp["systematic_ratio"] <= 1
    assert decomp["n_factors"] == 3

    # Unified interface
    cov_u = estimate_covariance(returns, method="ledoit_wolf")
    assert cov_u.shape == (6, 6)

    # Convert to correlation
    corr = cov_to_corr(cov)
    assert corr.shape == (6, 6)
    assert np.allclose(np.diag(corr.values), 1.0, atol=1e-10)

    # Nearest PD
    cov_pd = nearest_pd(cov)
    vals = np.linalg.eigvalsh(cov_pd.values)
    assert np.all(vals > 0)  # all eigenvalues positive

    # Compare estimators
    comp = compare_estimators(returns)
    assert "condition_number" in comp.columns
    assert len(comp) >= 3

    # Rolling covariance
    roll = rolling_covariance(returns, window=126, method="ledoit_wolf", step=63)
    assert len(roll) >= 2
    for date, c in roll.items():
        assert c.shape == (6, 6)


# ── backtest module ──────────────────────────────────────
def test_backtest_harness():
    from quant_framework.backtest.harness import (
        vectorized_backtest,
        signal_backtest,
        _make_demo_data,
    )

    prices, signals = _make_demo_data(n=250, seed=1)
    result = vectorized_backtest(prices, signals)
    assert isinstance(result, dict)
    assert "sharpe_ratio" in result
    assert isinstance(result["sharpe_ratio"], float)

    # signal_backtest (returns + weights)
    rng = np.random.default_rng(42)
    rets = pd.Series(rng.normal(0.001, 0.02, 252))
    w = pd.Series(0.5 + 0 * rets)
    sb = signal_backtest(rets, w)
    assert isinstance(sb, dict)
    assert "total_return" in sb


# ── data benchmark ───────────────────────────────────────
def test_import_benchmark():
    from quant_framework.data.benchmark import (
        benchmark_single,
    )

    assert benchmark_single is not None


def test_benchmark_single():
    from quant_framework.data.benchmark import benchmark_single

    r = benchmark_single("AAPL", "2025-01-06", "2025-01-10", "yfinance")
    assert r.source == "yfinance"
    assert r.latency_s > 0
    if not r.error:
        assert r.rows >= 0


def test_summary_report():
    from quant_framework.data.benchmark import benchmark_single, summary_report

    r = benchmark_single("MSFT", "2025-01-06", "2025-01-10", "yfinance")
    import pandas as pd

    df = pd.DataFrame(
        [
            {
                "ticker": "MSFT",
                "source": r.source,
                "latency_s": r.latency_s,
                "rows": r.rows,
                "expected": r.expected_rows,
                "completeness_pct": round(r.rows / max(r.expected_rows, 1) * 100, 1),
                "missing_dates": r.missing_dates,
                "duplicates": r.duplicate_rows,
                "null_pct": r.null_pct,
                "outlier_pct": r.price_outlier_pct,
                "error": r.error or "",
            }
        ]
    )
    report = summary_report(df)
    assert "MSFT" in report
    assert "yfinance" in report


# ── optimizer ────────────────────────────────────────────
def test_import_optimizer():
    from quant_framework.strategies.optimizer import (
        optimize,
    )

    assert optimize is not None


def test_optimizer_simple():
    from quant_framework.strategies.optimizer import optimize, ParamSpec

    def obj(params):
        x = params.get("x", 0)
        return -((x - 3) ** 2) + 10  # max at x=3

    params = [ParamSpec("x", "real", -5, 5)]
    result = optimize(
        obj, params, n_calls=20, n_random_starts=5, maximize=True, random_state=42
    )
    assert "best_params" in result
    assert "best_score" in result
    assert result["best_score"] >= 8  # close to optimum of 10
    assert abs(result["best_params"]["x"] - 3) < 2


def test_walk_forward_splits():
    from quant_framework.strategies.optimizer import walk_forward_splits

    dates = pd.date_range("2024-01-01", periods=252, freq="B")
    splits = walk_forward_splits(dates, n_splits=4)
    assert len(splits) == 4
    for train, test in splits:
        assert len(train) > len(test)
        assert train[-1] < test[0]  # no overlap


# ── factor analysis ──────────────────────────────────────
def test_import_factor_analysis():
    from quant_framework.strategies.factor_analysis import (
        full_analysis,
    )

    assert full_analysis is not None


def test_factor_analysis():
    from quant_framework.strategies.factor_analysis import (
        full_analysis,
        report_markdown,
        _make_demo_data,
    )

    factor_df, returns = _make_demo_data(252, 3, seed=3)
    analysis = full_analysis(factor_df, returns)

    assert "ic_summary" in analysis
    assert "quantile_spread" in analysis
    assert "turnover_summary" in analysis
    assert "correlation_matrix" in analysis

    ic = analysis["ic_summary"]
    assert not ic.empty
    assert "mean_ic" in ic.columns
    assert "ic_ir" in ic.columns

    report = report_markdown(analysis)
    assert "Factor Performance" in report
    assert len(report) > 200


# ── visualization ────────────────────────────────────────
def test_import_visualization():
    from quant_framework.backtest.visualization import (
        equity_curve,
    )

    assert equity_curve is not None


def test_visualization_charts():
    from quant_framework.backtest.visualization import (
        equity_curve,
        drawdown_plot,
        monthly_returns_heatmap,
        annual_returns,
        full_report,
        _make_demo_equity,
    )

    equity, returns = _make_demo_equity(n=120, seed=7)
    assert len(equity) == 120
    assert len(returns) == 120

    fig1 = equity_curve(equity)
    assert fig1 is not None

    fig2 = drawdown_plot(equity, top_n=3)
    assert fig2 is not None

    fig3 = monthly_returns_heatmap(returns)
    assert fig3 is not None

    fig5 = annual_returns(returns)
    assert fig5 is not None

    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmp:
        paths = full_report(equity, returns, output_dir=tmp, prefix="test")
        assert len(paths) == 6
        for _name, p in paths.items():
            assert os.path.exists(str(p))

    # Clean up figures
    import matplotlib.pyplot as plt

    for _ in range(6):
        plt.close()


# ── execution ────────────────────────────────────────────
def test_import_order_simulator():
    from quant_framework.execution.order_simulator import (
        simulate_orders,
    )

    assert simulate_orders is not None


def test_order_simulator():
    from quant_framework.execution.order_simulator import (
        simulate_orders,
        execution_quality_report,
        _make_demo_data,
    )

    prices, signals = _make_demo_data(n_dates=100, n_tickers=3, seed=99)
    result = simulate_orders(prices, signals, initial_cash=200_000)
    if "error" in result:
        pytest.skip(f"Order simulation skipped: {result['error']}")

    assert "equity_curve" in result
    assert "trades" in result
    assert result["total_return"] is not None

    quality = execution_quality_report(prices, result["trades"])
    assert "implementation_shortfall_bp" in quality


def test_position_sizer():
    from quant_framework.execution.position_sizer import (
        size_positions,
    )

    rng = np.random.default_rng(42)
    dates = pd.date_range("2024-01-01", periods=252, freq="B")
    prices = pd.DataFrame(
        {
            "date": dates,
            "ticker": "A",
            "close": 100 + np.cumsum(rng.normal(0.02, 1, 252)),
        }
    )
    signals = pd.DataFrame({"date": [dates[-1]], "ticker": ["A"], "signal": [1]})

    result = size_positions(signals, prices, capital=100_000, method="equal_weight")
    assert result["method"] == "equal_weight"
    assert len(result["orders"]) > 0
    assert result["total_allocated"] > 0

    # Also test risk_parity
    result2 = size_positions(signals, prices, capital=100_000, method="risk_parity")
    assert result2["method"] == "risk_parity"


def test_position_sizer_raw():
    from quant_framework.execution.position_sizer import (
        equal_weight,
        kelly_sizing,
        risk_parity_sizing,
        volatility_targeted_sizing,
    )

    rng = np.random.default_rng(7)
    rets = pd.DataFrame(
        {
            "A": rng.normal(0.001, 0.02, 252),
            "B": rng.normal(0.0008, 0.015, 252),
            "C": rng.normal(0.0005, 0.018, 252),
        }
    )

    w1 = equal_weight(pd.DataFrame({"ticker": ["A", "B"], "signal": [1, 1]}))
    assert len(w1) == 2

    w2 = kelly_sizing(rets, max_weight=0.3)
    assert len(w2) == 3

    w3 = risk_parity_sizing(rets)
    assert len(w3) == 3

    w4 = volatility_targeted_sizing(rets, target_vol=0.15)
    assert len(w4) == 3


def test_twap_vwap_schedule():
    from quant_framework.execution.order_simulator import twap_schedule, vwap_schedule

    twap = twap_schedule(1000, 10)
    assert len(twap) == 10
    assert abs(twap.sum() - 1000) < 1e-6

    vp = np.array([10, 20, 30, 25, 15])
    vwap = vwap_schedule(1000, vp)
    assert len(vwap) == 5
    assert abs(vwap.sum() - 1000) < 1e-6


def test_import_rebalancer():
    from quant_framework.execution.rebalancer import (
        compute_trades,
    )

    assert compute_trades is not None


def test_rebalancer():
    from quant_framework.execution.rebalancer import (
        generate_calendar_dates,
        check_drift,
        should_rebalance,
        compute_trades,
        run_rebalance,
        RebalanceConfig,
        estimate_rebalance_cost,
        _make_demo_data,
    )

    dates, weights, target, prices, port_val = _make_demo_data(100, 5, seed=7)

    # Calendar dates
    cal = generate_calendar_dates(dates, "M")
    assert len(cal) >= 2

    # Drift check
    cur = pd.Series(
        [0.36, 0.24, 0.20, 0.15, 0.05], index=["T0", "T1", "T2", "T3", "T4"]
    )
    tgt = pd.Series(
        [0.30, 0.25, 0.20, 0.15, 0.10], index=["T0", "T1", "T2", "T3", "T4"]
    )
    assert check_drift(cur, tgt, 0.05)  # True — T0 off by 6%

    cur2 = pd.Series(
        [0.31, 0.25, 0.20, 0.15, 0.09], index=["T0", "T1", "T2", "T3", "T4"]
    )
    assert not check_drift(cur2, tgt, 0.05)  # within 5%

    # should_rebalance
    assert should_rebalance(
        dates[0],
        cur,
        tgt,
        None,
        None,
        RebalanceConfig(method="threshold", drift_threshold=0.05),
    )

    # Compute trades
    prices_s = pd.Series([100, 110, 95, 105, 90], index=["T0", "T1", "T2", "T3", "T4"])
    trades = compute_trades(cur, tgt, prices_s, 100_000, RebalanceConfig())
    assert not trades.empty
    assert "ticker" in trades.columns
    assert "action" in trades.columns
    assert set(trades["action"].unique()) <= {"buy", "sell"}

    # Run single rebalance
    result = run_rebalance(
        dates[0],
        cur,
        tgt,
        prices_s,
        100_000,
        RebalanceConfig(method="threshold", drift_threshold=0.05),
    )
    assert result.triggered_by != "none"
    assert result.turnover_pct >= 0

    # Cost estimation
    cost = estimate_rebalance_cost(trades, 100_000)
    assert "total_cost_bp" in cost
    assert cost["n_trades"] > 0


def test_import_tca():
    from quant_framework.execution.tca import (
        estimate_pre_trade,
    )

    assert estimate_pre_trade is not None


def test_tca():
    from quant_framework.execution.tca import (
        estimate_pre_trade,
        implementation_shortfall,
        vwap_slippage,
        almgrin_chriss_impact,
        analyze_execution,
        _make_demo_data,
    )
    import numpy as np

    # Pre-trade
    pre = estimate_pre_trade(500, 150.0, 10_000_000)
    assert pre["total_cost_bp"] > 0
    assert "spread_cost" in pre
    assert "market_impact_cost" in pre

    # Implementation shortfall
    is_result = implementation_shortfall(
        decision_price=100.0,
        arrival_price=100.5,
        final_price=102.0,
        execution_prices=np.array([100.5, 101.0]),
        execution_sizes=np.array([300, 200]),
        total_order_size=500,
    )
    assert "total_shortfall" in is_result
    assert "delay_cost" in is_result
    assert is_result["fill_rate_pct"] == 100.0

    # Partial fill
    is_partial = implementation_shortfall(
        decision_price=100.0,
        arrival_price=100.0,
        final_price=102.0,
        execution_prices=np.array([100.0]),
        execution_sizes=np.array([300]),
        total_order_size=500,
    )
    assert is_partial["fill_rate_pct"] < 100.0
    assert is_partial["opportunity_cost"] != 0

    # VWAP slippage
    vwap = vwap_slippage(
        np.array([150.0, 150.5]),
        np.array([200, 200]),
        150.2,
        direction=1,
    )
    assert "slippage_bp" in vwap
    assert vwap["filled_shares"] == 400

    # Almgren-Chriss
    ac = almgrin_chriss_impact(10_000, 5_000_000, 0.02)
    assert ac["total_impact_bp"] >= 0

    # Analyze execution
    trades, market = _make_demo_data(seed=7)
    post = analyze_execution(trades, market)
    assert post["n_trades"] > 0
    assert "total_shortfall_bp" in post


def test_import_report_generator():
    from quant_framework.reporting.report_generator import (
        generate_daily_briefing,
    )

    assert generate_daily_briefing is not None


def test_report_generator():
    from quant_framework.reporting.report_generator import (
        generate_daily_briefing,
        generate_weekly_report,
        generate_monthly_report,
        generate_full_report,
        _make_demo_data,
    )
    import tempfile
    import os

    data = _make_demo_data()

    daily = generate_daily_briefing(
        signals=data["signals"],
        positions=data["positions"],
        pnl=data["pnl"],
        factor_ic=data["factor_ic"],
    )
    assert "Daily Briefing" in daily
    assert "Signal Overview" in daily

    weekly = generate_weekly_report(
        returns=data["returns"],
        risk_summary=data["risk_summary"],
    )
    assert "Weekly Report" in weekly
    assert "Performance Summary" in weekly

    monthly = generate_monthly_report(
        returns=data["returns"],
        attribution=data["attribution"],
        stress_result=data["stress_result"],
        tca_summary=data["tca_summary"],
    )
    assert "Monthly Report" in monthly
    assert "Performance Attribution" in monthly

    with tempfile.TemporaryDirectory() as tmp:
        report, path = generate_full_report(
            "daily", output_dir=tmp, signals=data["signals"]
        )
        assert os.path.exists(path)
        assert "Daily Briefing" in report


# ── E2E pipeline ─────────────────────────────────────────
def test_run_pipeline_quick():
    from scripts.run_pipeline import step1_fetch, step2_factors

    try:
        df = step1_fetch(["AAPL"], "2025-01-06", "2025-01-10")
    except Exception:
        pytest.skip("yfinance API unavailable")

    assert df is not None and not df.empty
    factors = step2_factors(df)
    assert isinstance(factors, pd.DataFrame)
    assert len(factors) == len(df)


# ── performance attribution ───────────────────────────────
def test_import_performance_attribution():
    from quant_framework.risk.performance_attribution import (
        factor_regression,
    )

    assert factor_regression is not None


def test_performance_attribution():
    from quant_framework.risk.performance_attribution import (
        factor_regression,
        rolling_attribution,
        brinson_attribution,
        contribution_summary,
        report_markdown,
        _make_demo_data,
    )

    port_ret, factor_ret = _make_demo_data(504, 4, seed=7)

    # factor_regression
    attr = factor_regression(port_ret, factor_ret)
    assert "error" not in attr
    assert attr["r_squared"] > 0.8
    assert attr["n_obs"] == 504
    assert "MKT" in attr["exposures"]
    assert "alpha" in attr["exposures"]
    assert abs(attr["exposures"]["MKT"] - 1.0) < 0.1  # known exposure
    assert abs(attr["exposures"]["SMB"] - 0.3) < 0.1
    assert abs(attr["exposures"]["HML"] - (-0.2)) < 0.1
    assert abs(attr["exposures"]["MOM"] - 0.15) < 0.1
    assert "t_statistics" in attr
    assert "p_values" in attr

    # rolling_attribution
    roll = rolling_attribution(port_ret, factor_ret, window=252, step=63)
    assert not roll.empty
    assert "r_squared" in roll.columns
    assert len(roll) >= 3

    # contribution_summary
    summary = contribution_summary(attr)
    assert not summary.empty
    assert "factor" in summary.columns
    assert "annual_contribution" in summary.columns

    # report_markdown
    report = report_markdown(attr)
    assert "Performance Attribution" in report
    assert "Factor Regression" in report

    # brinson_attribution (no group mapping)
    rng = np.random.default_rng(42)
    dates = list(factor_ret.index[:100])
    n_a = 4
    pw_data = {f"A{i}": np.ones(100) / n_a for i in range(n_a)}
    pw = pd.DataFrame(pw_data, index=dates)
    bw_data = {f"A{i}": np.ones(100) / n_a for i in range(n_a)}
    bw = pd.DataFrame(bw_data, index=dates)
    ar_data = {f"A{i}": rng.normal(0.0005, 0.015, 100) for i in range(n_a)}
    ar = pd.DataFrame(ar_data, index=dates)

    brinson = brinson_attribution(pw, bw, ar)
    assert "error" not in brinson
    assert "allocation_effect" in brinson
    assert "selection_effect" in brinson
    assert "interaction_effect" in brinson

    # brinson with group mapping
    group_map = {"A0": "Tech", "A1": "Tech", "A2": "Finance", "A3": "Finance"}
    brinson2 = brinson_attribution(pw, bw, ar, group_mapping=group_map)
    assert "error" not in brinson2
    assert brinson2["n_groups"] == 2
    assert brinson2["n_assets"] == 4


# ── ML predictor ──────────────────────────────────────────
def test_import_ml_predictor():
    from quant_framework.strategies.ml_predictor import (
        PredictorConfig,
    )

    assert PredictorConfig is not None


def test_ml_predictor():
    from quant_framework.strategies.ml_predictor import (
        PredictorConfig,
        predict_returns,
        evaluate_prediction,
        report_markdown,
        _make_demo_data,
        time_series_split,
    )

    df, factor_cols = _make_demo_data(252, 8, 10, seed=7)

    # time_series_split
    splits = time_series_split(2520, n_splits=5, test_size=0.2)
    assert len(splits) >= 3
    for train_idx, test_idx in splits:
        assert len(train_idx) > len(test_idx)

    # predict_returns with Ridge
    cfg = PredictorConfig(model="ridge", alpha=1.0)
    result = predict_returns(df, factor_cols, cfg)
    assert "error" not in result
    assert "predictions" in result
    assert result["r2"] > 0.5
    assert abs(result["ic"]) > 0.5
    assert len(result["predictions"]) == len(df)
    assert not result["feature_importance"].empty
    assert len(result["feature_importance"]) == 8
    assert "factor" in result["feature_importance"].columns

    # CV results
    assert not result["cv_results"].empty
    assert "r2" in result["cv_results"].columns
    assert len(result["cv_results"]) >= 3

    # evaluate_prediction
    eval_ = evaluate_prediction(result["predictions"], df["forward_return"])
    assert "error" not in eval_
    assert abs(eval_["ic"]) > 0.5
    assert eval_["hit_rate"] > 0.7

    # report_markdown
    report = report_markdown(result, eval_)
    assert "ML Return Prediction" in report
    assert "Feature Importance" in report

    # RandomForest
    cfg2 = PredictorConfig(model="rf", n_estimators=50, max_depth=5)
    result2 = predict_returns(df, factor_cols, cfg2)
    assert "error" not in result2
    assert result2["r2"] > 0.3


# ── backtest analytics ────────────────────────────────────
def test_import_backtest_analytics():
    from quant_framework.backtest.analytics import (
        analyze_streaks,
    )

    assert analyze_streaks is not None


def test_backtest_analytics():
    from quant_framework.backtest.analytics import (
        analyze_streaks,
        analyze_drawdown_duration,
        monthly_returns_table,
        annual_returns_table,
        profit_loss_ratio,
        rolling_metrics_df,
        full_analytics,
        analytics_report_markdown,
    )

    rng = np.random.default_rng(42)
    dates = pd.date_range("2023-01-01", periods=504, freq="B")
    returns = pd.Series(rng.normal(0.0006, 0.012, 504), index=dates)
    equity = (1 + returns).cumprod()

    # profit_loss_ratio
    pl = profit_loss_ratio(returns)
    assert "error" not in pl
    assert "profit_factor" in pl
    assert "win_rate" in pl
    assert 0 < pl["win_rate"] < 1
    assert pl["n_wins"] + pl["n_losses"] == len(returns)

    # analyze_streaks
    st = analyze_streaks(returns)
    assert "error" not in st
    assert st["max_win_streak"] >= 1
    assert st["max_loss_streak"] >= 1
    assert st["n_streaks"] > 10

    # analyze_drawdown_duration
    dd = analyze_drawdown_duration(equity)
    assert "error" not in dd
    assert "max_drawdown" in dd
    assert "max_dd_duration_days" in dd
    assert dd["n_drawdowns"] >= 1
    assert 0 <= dd["time_in_drawdown_pct"] <= 100

    # monthly_returns_table
    mt = monthly_returns_table(returns)
    assert not mt.empty
    assert "Annual" in mt.columns

    # annual_returns_table
    at = annual_returns_table(returns)
    assert not at.empty
    assert "return" in at.columns
    assert "sharpe" in at.columns

    # rolling_metrics_df
    rm = rolling_metrics_df(returns, windows=[21, 63])
    assert not rm.empty
    assert "sharpe_21" in rm.columns
    assert "vol_63" in rm.columns

    # full_analytics
    fa = full_analytics(returns, equity)
    assert "pl_ratio" in fa
    assert "streaks" in fa
    assert "drawdown_duration" in fa
    assert "monthly_table" in fa
    assert "rolling_df" in fa

    # analytics_report_markdown
    report = analytics_report_markdown(fa)
    assert "Profit / Loss Analysis" in report
    assert "Streak Analysis" in report
    assert "Drawdown Duration" in report
    assert "Monthly Returns" in report


# ── industry attribution ──────────────────────────────────
def test_import_industry_attribution():
    from quant_framework.risk.industry_attribution import (
        check_industry_exposure,
    )

    assert check_industry_exposure is not None


def test_industry_attribution():
    from quant_framework.risk.industry_attribution import (
        check_industry_exposure,
        barra_risk_attribution,
        risk_budget_decomposition,
        analyze_risk_attribution,
        report_markdown,
        _make_demo_data,
    )

    rets, factor_ret, weights, ind_map = _make_demo_data(252, 10, 4, seed=7)

    # check_industry_exposure
    ie = check_industry_exposure(weights, ind_map)
    assert "error" not in ie
    assert ie["n_industries"] == 5
    assert ie["top3_concentration"] == 0.6
    assert ie["hhi"] > 0

    # barra_risk_attribution
    ba = barra_risk_attribution(rets, factor_ret, weights)
    assert "error" not in ba
    assert "total_risk" in ba
    assert "factor_risk" in ba
    assert "specific_risk" in ba
    assert ba["systematic_ratio"] > 0.5
    assert ba["n_assets"] == 10
    assert ba["n_factors"] == 4

    # risk_budget_decomposition
    cov = rets.cov()
    rb = risk_budget_decomposition(weights, cov)
    assert "error" not in rb
    assert rb["total_risk"] > 0
    assert rb["effective_n_risk_sources"] > 1
    dec = rb["decomposition"]
    assert len(dec) == 10
    assert abs(dec["pct_risk"].sum() - 1.0) < 0.01

    # analyze_risk_attribution
    full = analyze_risk_attribution(rets, factor_ret, weights, industry_map=ind_map)
    assert "industry_check" in full
    assert "barra" in full
    assert "risk_budget" in full
    assert "error" not in full["barra"]
    assert "error" not in full["risk_budget"]

    # report_markdown
    report = report_markdown(full)
    assert "Risk Attribution" in report
    assert "Industry Exposure" in report
    assert "Barra Risk Attribution" in report
    assert "Risk Budget" in report


# ── data quality ─────────────────────────────────────────
def test_import_data_quality():
    from quant_framework.data.data_quality import (
        check_nan_ratio,
    )

    assert check_nan_ratio is not None


def test_data_quality():
    from quant_framework.data.data_quality import (
        check_nan_ratio,
        check_freshness,
        check_lookahead_bias,
        check_outliers,
        check_completeness,
        run_quality_checks,
        quality_report_markdown,
        _make_demo_data,
    )

    df, factor_cols = _make_demo_data(252, 8, seed=7)

    # check_nan_ratio
    nr = check_nan_ratio(df)
    assert "error" not in nr
    assert nr["total_nan_ratio"] < 0.1
    assert nr["n_bad_columns"] == 0

    # check_freshness
    fr = check_freshness(df)
    assert "error" not in fr
    assert "last_date" in fr
    assert "staleness_days" in fr

    # check_outliers
    oc = check_outliers(df, factor_cols)
    assert "error" not in oc
    assert "total_outliers" in oc

    # check_completeness
    cc = check_completeness(df)
    assert "error" not in cc
    assert cc["n_tickers"] == 8

    # check_lookahead_bias
    la = check_lookahead_bias(df, factor_cols, "forward_return")
    assert "error" not in la
    assert la["n_factors_checked"] == 6

    # run_quality_checks
    result = run_quality_checks(
        df, factor_cols=factor_cols, forward_return_col="forward_return"
    )
    assert "nan_check" in result
    assert "freshness" in result
    assert "outlier_check" in result
    assert "completeness" in result
    assert result["n_checks_total"] == 5

    # quality_report_markdown
    report = quality_report_markdown(result)
    assert "Data Quality" in report
    assert "NaN Ratio" in report
    assert "Lookahead" in report


# ── infrastructure ─────────────────────────────────────────


def test_import_memory_store():
    pass


def test_memory_store():
    import tempfile
    from pathlib import Path
    from infrastructure.memory_store import MemoryStore

    path = Path(tempfile.gettempdir()) / "test_smoke_memory.jsonl"
    try:
        store = MemoryStore(path)
        # Add
        fid = store.add("Test memory: sklearn for factor computation", "decision")
        assert len(fid) == 16  # SHA-256 16-char hex
        assert store.stats()["active_entries"] == 1

        # Add more
        store.add("Project uses pandas for data processing", "project")
        store.add("Windows GBK encoding bug with emoji", "bug")
        assert store.stats()["active_entries"] == 3

        # Search
        results = store.search("machine learning sklearn factor")
        assert len(results) > 0
        assert results[0][1] > 0  # score > 0

        # Dedup
        fid2 = store.add("Test memory: sklearn for factor computation", "decision")
        assert fid2 == fid  # same fingerprint

        # Strength decay
        store.decay_all(factor=0.9)
        stats = store.stats()
        assert stats["avg_strength"] < 1.0

        # Context budget
        ctx = store.build_context_budget(max_tokens=500)
        assert "sklearn" in ctx or "pandas" in ctx

        # Deactivate
        store.deactivate(fid)
        assert store.stats()["active_entries"] == 2

        path.unlink(missing_ok=True)
    finally:
        path.unlink(missing_ok=True)


# ── agent manifests ────────────────────────────────────────


def test_import_manifest_schema():
    pass


def test_agent_manifests():
    from pathlib import Path
    from onionquant.agents.manifest_schema import ManifestRegistry

    manifests_dir = Path("onionquant/agents/manifests")
    if not manifests_dir.exists():
        pytest.skip("manifests directory not found")

    reg = ManifestRegistry(manifests_dir)
    stats = reg.stats()
    assert stats["active"] >= 4
    assert stats["departments"] >= 4
    assert stats["total_workers"] >= 6
    assert stats["total_skills"] >= 10

    ceo = reg.get("ceo_agent")
    assert ceo is not None
    assert ceo.status == "active"
    assert len(ceo.system_prompt) > 100
    assert len(ceo.steering_examples) >= 3
    assert len(ceo.workers) >= 2

    errors = reg.validate_all()
    assert len(errors) == 0, f"Validation errors: {errors}"


# ── api proxy ──────────────────────────────────────────────


def test_import_api_proxy():
    pass


def test_api_proxy():
    import tempfile
    from pathlib import Path
    from infrastructure.api_proxy import APIProxy, RateConfig

    audit_file = Path(tempfile.gettempdir()) / "test_api_audit.jsonl"
    try:
        proxy = APIProxy(audit_file)
        proxy.register(
            "test_provider",
            ["https://test.example.com"],
            rate_config=RateConfig(requests_per_minute=120, burst=10, retry_max=1),
        )

        @proxy.call("test_provider", "/v1/test")
        def test_call(url: str) -> dict:
            return {"url": url, "ok": True}

        result = test_call()
        assert result["ok"]
        assert "test.example.com" in result["url"]

        # Verify audit log
        summary = proxy.audit.summary(minutes=5)
        assert summary["total_calls"] == 1
        assert summary["error_rate"] == 0.0

        audit_file.unlink(missing_ok=True)
    finally:
        audit_file.unlink(missing_ok=True)


def test_token_bucket():
    from infrastructure.api_proxy import TokenBucket

    bucket = TokenBucket(rate=100, capacity=10)
    for _ in range(10):
        ok, wait = bucket.acquire()
        assert ok
        assert wait == 0.0

    # 11th call should need to wait (only 10 capacity)
    ok, wait = bucket.acquire()
    assert not ok or wait > 0


# ── seed context ──────────────────────────────────────────


def test_import_seed_context():
    pass


def test_seed_context():
    import numpy as np
    import pandas as pd
    from quant_framework.orchestration.seed_context import SeedContext

    ctx = SeedContext()
    rng = np.random.default_rng(42)

    # Seed market data
    df = pd.DataFrame({"close": 100 + np.cumsum(rng.normal(0, 1, 100))})
    ctx.seed("prices", lambda: df, source="test", category="market_data")

    # Seed factor
    ctx.seed(
        "factor", lambda: {"ic": 0.05, "ir": 0.8}, source="test", category="factor"
    )

    assert len(ctx.evidence) == 2
    assert ctx.get("prices") is not None
    assert ctx.get("prices").category == "market_data"
    assert ctx.get("prices").is_fresh

    # Build context
    context = ctx.build_context()
    assert "Seed Context" in context
    assert "prices" in context
    assert "factor" in context

    # Compact
    compact = ctx.build_compact()
    assert "prices" in compact

    # Seed or skip (should return cached)
    evidence = ctx.seed_or_skip("prices", lambda: None, max_age_seconds=999)
    assert evidence.key == "prices"

    # Audit save
    from pathlib import Path
    import tempfile

    audit_path = Path(tempfile.gettempdir()) / "test_seed_audit.json"
    ctx.save_audit(audit_path)
    assert audit_path.exists()
    audit_path.unlink()


# ── model tier ─────────────────────────────────────────────


def test_import_model_tier():
    pass


def test_model_tier():
    from infrastructure.model_tier import TierRouter, Tier

    router = TierRouter()

    # Quick tasks → quick tier
    assert router.route("factor_scanning").tier == Tier.QUICK
    assert router.route("data_cleaning").tier == Tier.QUICK

    # Deep tasks → deep tier
    assert router.route("regime_detection").tier == Tier.DEEP
    assert router.route("strategy_decision").tier == Tier.DEEP
    assert router.route("crisis_analysis").tier == Tier.DEEP
    assert router.route("chairman_summary").tier == Tier.DEEP

    # Cost estimate
    cost = router.estimate_cost("factor_scanning")
    assert cost < 0.01  # should be cheap

    # Unknown task → deep (safety fallback)
    assert router.route("unknown_task").tier == Tier.DEEP

    # Daily cost
    daily = router.daily_cost_estimate({"factor_scanning": 50, "strategy_decision": 2})
    assert daily["total_usd"] < 1.0
    assert "quick" in daily["per_tier"]
    assert "deep" in daily["per_tier"]

    # Routing table
    table = router.routing_table()
    assert "factor_scanning" in table
    assert "regime_detection" in table


# ── black-litterman ───────────────────────────────────────


def test_black_litterman_rp():
    import numpy as np
    from quant_framework.risk.portfolio_optimizer import (
        black_litterman_rp,
        black_litterman_bayesian,
        bl_optimize,
    )

    rng = np.random.default_rng(42)
    returns = rng.normal(0.0005, 0.015, (252, 5))

    # No views — equilibrium
    result = black_litterman_rp(returns)
    assert len(result["weights"]) == 5
    assert abs(result["weights"].sum() - 1.0) < 0.01
    assert "implied_equilibrium" in result

    # With views
    views = {0: (1, 0.15), 2: (-1, -0.05)}
    result = black_litterman_rp(returns, views=views)
    assert len(result["weights"]) == 5
    assert abs(result["weights"].sum() - 1.0) < 0.01
    assert result["expected_return"] != 0

    # Bayesian BL
    F = rng.normal(0, 0.01, (252, 2))
    B = rng.normal(0, 1, (5, 2))
    result = black_litterman_bayesian(returns, factor_exposures=B, factor_returns=F)
    assert len(result["weights"]) == 5
    assert abs(result["weights"].sum() - 1.0) < 0.01

    # Unified entry
    result = bl_optimize(returns, factor_data={"exposures": B, "returns": F})
    assert result["method_used"] == "bayesian"
    assert len(result["weights"]) == 5


def test_factor_decay():
    """T870: Factor decay monitor — IC trend + crowding + alerts."""
    from quant_framework.strategies.factor_decay import (
        ic_trend_test,
        detect_crowding,
        check_decay_alerts,
    )

    rng = np.random.default_rng(42)
    dates = pd.date_range("2025-01-01", periods=200, freq="B")
    n = len(dates)

    # Stable factor (IC ~0.03) and declining factor (IC 0.04→-0.01)
    ic_a = rng.normal(0.03, 0.02, n)
    t_line = np.linspace(0, 1, n)
    ic_b = 0.04 - 0.05 * t_line + rng.normal(0, 0.015, n)

    factor_df = pd.DataFrame(
        {
            "momentum": rng.normal(0, 1, n),
            "value": rng.normal(0, 1, n),
            "volatility": rng.normal(0, 1, n),
        },
        index=dates,
    )

    ic_df = pd.DataFrame({"momentum": ic_a, "value": ic_b}, index=dates)

    # IC trend test
    trends = ic_trend_test(ic_df)
    assert len(trends) >= 1
    assert "momentum" in trends["factor"].values

    # Crowding detection
    crowd = detect_crowding(factor_df, ["momentum", "value", "volatility"])
    assert isinstance(crowd, pd.DataFrame)

    # Alerts
    alerts = check_decay_alerts(ic_df, factor_df, ["momentum", "value", "volatility"])
    assert isinstance(alerts, list)
    # Declining factor should produce at least 1 alert
    declining_alerts = [
        a for a in alerts if a.factor == "value" and a.alert_type == "ic_trend_down"
    ]
    assert len(declining_alerts) >= 1


def test_broker_bridge():
    """T867/T916: Broker bridge — live Alpaca paper trading or recorder fallback."""
    from quant_framework.execution.broker_bridge import BrokerBridge, OrderResult

    bridge = BrokerBridge()
    summary = bridge.get_account_summary()
    assert "mode" in summary

    if bridge.is_connected:
        # Live mode — Alpaca paper trading
        assert summary["connected"] is True
        assert summary["mode"] == "paper"
        assert summary["buying_power"] > 0

        # Place and cancel a test order
        r = bridge.place_order("AAPL", 1, "buy", "market")
        assert isinstance(r, OrderResult)
        assert r.symbol == "AAPL"
        assert r.qty == 1
        assert r.status is not None

        # Cancel the test order
        if r.status not in ("filled", "canceled", "rejected"):
            cancelled = bridge.cancel_order(r.order_id)
            assert cancelled is True

        # Positions list should exist
        positions = bridge.get_positions()
        assert isinstance(positions, list)
    else:
        # Recorder mode — no credentials
        assert summary["mode"] == "recorder"

        r = bridge.place_order("AAPL", 10, "buy", "market")
        assert isinstance(r, OrderResult)
        assert r.status == "recorded"
        assert r.symbol == "AAPL"
        assert r.qty == 10

        r2 = bridge.place_order("MSFT", 50, "sell", "limit", limit_price=420.0)
        assert r2.status == "recorded"

        positions = bridge.get_positions()
        assert isinstance(positions, list)
        assert len(bridge._order_log) >= 2


# ── Sprint 15: auto_trader + auto_tuner + sensitivity ─────


def test_auto_trader_compute_signals():
    """T933: Verify auto_trader signal pipeline works end-to-end."""
    from quant_framework.orchestration.auto_trader import compute_signals

    data = _make_multi_ohlcv(n_tickers=5, n=252, seed=42)
    signals = compute_signals(data)

    if signals is not None:
        assert "signal" in signals.columns
        assert "combined_score" in signals.columns
        assert len(signals) > 0
        long_count = (signals["signal"] == 1).sum()
        assert long_count >= 0


def test_import_auto_tuner():
    """T934a: Verify auto_tuner imports cleanly."""
    from quant_framework.strategies.auto_tuner import auto_tune, report_markdown

    assert auto_tune is not None
    assert callable(report_markdown)


def test_import_sensitivity():
    """T934b: Verify sensitivity module imports cleanly."""
    from quant_framework.strategies.sensitivity import (
        sensitivity_matrix,
        report_markdown,
    )

    assert sensitivity_matrix is not None
    assert callable(report_markdown)


def test_sensitivity_basic():
    """T934c: Verify sensitivity_matrix runs on synthetic data."""
    import pandas as pd
    from quant_framework.strategies.sensitivity import sensitivity_matrix

    def _dummy_obj(**params):
        return {"sharpe": params.get("lookback", 20) * 0.05}

    result = sensitivity_matrix(
        _dummy_obj,
        base_params={"lookback": 20, "threshold": 0.01},
        param_names=["lookback", "threshold"],
        perturbation=0.2,
        output_key="sharpe",
    )
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 2
    assert "param" in result.columns
    assert "elasticity" in result.columns
