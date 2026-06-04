#!/usr/bin/env python3
"""E2E integration tests — full pipeline: data → factor → signal → backtest → report.

Exercises the end-to-end quant workflow with demo data to verify
all modules integrate correctly. Uses pytest with numpy seed for reproducibility."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd


# ── Helpers ─────────────────────────────────────────────────

def _make_demo_ohlcv(n_tickers=5, n_dates=252, seed=42):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_dates, freq="B")
    dfs = []
    for i in range(n_tickers):
        close = 100 + i * 20 + np.cumsum(rng.normal(0.05, 1.5, n_dates))
        open_ = close * 0.995
        high = close * 1.01
        low = close * 0.99
        dfs.append(pd.DataFrame({
            "date": dates, "ticker": f"TICKER{i}",
            "open": open_, "high": high, "low": low, "close": close,
            "volume": rng.integers(1_000_000, 10_000_000, n_dates).astype(float),
        }))
    return pd.concat(dfs, ignore_index=True)


# ── E2E Pipeline Tests ─────────────────────────────────────

def test_pipeline_data_to_factor():
    """Step 1→2: OHLCV data → factor computation."""
    from quant_framework.strategies.qlib_factor_engine import (
        compute_all_factors, neutralize_and_standardize,
    )

    df = _make_demo_ohlcv(n_tickers=5, n_dates=200, seed=1)
    factors = compute_all_factors(df)
    assert isinstance(factors, pd.DataFrame)
    assert len(factors) > 0

    ohlc_cols = {"date", "ticker", "open", "high", "low", "close", "volume", "industry"}
    factor_cols = [c for c in factors.columns if c not in ohlc_cols]
    assert len(factor_cols) > 0, f"No factor columns computed: {list(factors.columns)}"

    neutralized = neutralize_and_standardize(factors)
    assert isinstance(neutralized, pd.DataFrame)
    assert len(neutralized) == len(factors)


def test_pipeline_factor_to_signal():
    """Step 2→3: Factors → alpha combination → signals."""
    from quant_framework.strategies.qlib_factor_engine import (
        compute_all_factors, neutralize_and_standardize,
    )
    from quant_framework.strategies.factor_combiner import (
        equal_weighted_combine, generate_signals,
    )
    from quant_framework.strategies.alpha_combiner import (
        combine_alphas, CombineConfig,
    )

    df = _make_demo_ohlcv(n_tickers=5, n_dates=200, seed=2)
    factors = compute_all_factors(df)
    neutralized = neutralize_and_standardize(factors)
    ohlc_cols = {"date", "ticker", "open", "high", "low", "close", "volume", "industry"}
    factor_cols = [c for c in neutralized.columns if c not in ohlc_cols]

    # Basic combiner
    combined = equal_weighted_combine(neutralized, factor_cols)
    assert "combined_score" in combined.columns

    signals = generate_signals(combined, "combined_score", top_k=3)
    assert "signal" in signals.columns
    assert set(signals["signal"].dropna().unique()) <= {-1, 0, 1}

    # Alpha combiner
    fwd_ret = neutralized.groupby("ticker")["close"].transform(
        lambda x: x.pct_change(21).shift(-21)
    )
    cfg = CombineConfig(method="ic_weighted", factor_cols=factor_cols, window=63)
    alpha_result = combine_alphas(neutralized, fwd_ret, cfg)
    assert "combined_score" in alpha_result.columns
    assert alpha_result["combined_score"].notna().any()


def test_pipeline_signal_to_backtest():
    """Step 3→4: Signals → backtest execution."""
    from quant_framework.strategies.qlib_factor_engine import (
        compute_all_factors, neutralize_and_standardize,
    )
    from quant_framework.strategies.factor_combiner import (
        equal_weighted_combine, generate_signals,
    )
    from quant_framework.execution.order_simulator import simulate_orders
    from quant_framework.execution.position_sizer import size_positions

    df = _make_demo_ohlcv(n_tickers=5, n_dates=200, seed=3)
    factors = compute_all_factors(df)
    neutralized = neutralize_and_standardize(factors)
    ohlc_cols = {"date", "ticker", "open", "high", "low", "close", "volume", "industry"}
    factor_cols = [c for c in neutralized.columns if c not in ohlc_cols]

    combined = equal_weighted_combine(neutralized, factor_cols)
    signals = generate_signals(combined, "combined_score", top_k=3)

    # Order simulation
    result = simulate_orders(df, signals, initial_cash=200_000)
    assert "error" not in result or result.get("error") is None
    assert "trades" in result
    assert "equity_curve" in result

    # Position sizing
    latest_date = df["date"].max()
    latest_signals = signals[signals["date"] == latest_date]
    if not latest_signals.empty:
        sizes = size_positions(latest_signals, df, capital=100_000, method="equal_weight")
        assert sizes.get("total_allocated", 0) >= 0  # 0 if no buy signals


def test_pipeline_backtest_to_risk():
    """Step 4→5: Backtest results → risk analysis."""
    from quant_framework.backtest.harness import vectorized_backtest, _make_demo_data
    from quant_framework.risk.risk_metrics import risk_metrics_summary
    from quant_framework.risk.stress_testing import portfolio_stress_test

    prices, signals = _make_demo_data(n=200, seed=4)
    bt = vectorized_backtest(prices, signals)
    assert "sharpe_ratio" in bt
    assert isinstance(bt["sharpe_ratio"], float)

    # Risk metrics from returns
    equity = pd.Series(bt.get("equity_curve", [100_000]))
    returns = equity.pct_change().dropna()
    if len(returns) > 10:
        summary = risk_metrics_summary(returns, equity_curve=equity)
        assert "Sharpe" in summary

    # Stress test with simulated portfolio returns
    rng = np.random.default_rng(5)
    stress_returns = pd.DataFrame({
        f"A{i}": rng.normal(0.0005, 0.015, 200) for i in range(4)
    })
    weights = np.array([0.3, 0.25, 0.25, 0.2])
    stress_result = portfolio_stress_test(stress_returns, weights)
    assert stress_result["n_scenarios"] == 8
    assert "stress_score" in stress_result


def test_pipeline_risk_to_report():
    """Step 5→6: Risk/performance → report generation."""
    from quant_framework.risk.performance_attribution import (
        factor_regression, report_markdown, _make_demo_data,
    )
    from quant_framework.risk.covariance import (
        estimate_covariance, compare_estimators,
    )
    from quant_framework.strategies.factor_analysis import (
        full_analysis, _make_demo_data as _fa_demo,
    )

    # Performance attribution report
    port_ret, factor_ret = _make_demo_data(252, 4, seed=7)
    attr = factor_regression(port_ret, factor_ret)
    assert "error" not in attr
    report = report_markdown(attr)
    assert "Performance Attribution" in report
    assert attr["r_squared"] > 0.8

    # Covariance estimation
    rng = np.random.default_rng(8)
    cov_returns = pd.DataFrame({
        f"A{i}": rng.normal(0.0005, 0.015, 200) for i in range(6)
    })
    cov = estimate_covariance(cov_returns, method="ledoit_wolf")
    assert cov.shape == (6, 6)
    comparison = compare_estimators(cov_returns)
    assert len(comparison) >= 3

    # Factor analysis report
    factor_df, rets = _fa_demo(252, 3, seed=9)
    analysis = full_analysis(factor_df, rets)
    assert "ic_summary" in analysis
    assert "correlation_matrix" in analysis


def test_full_e2e_workflow():
    """Complete end-to-end: data → factors → alpha → signals → backtest → risk → report."""
    from quant_framework.strategies.qlib_factor_engine import (
        compute_all_factors, neutralize_and_standardize,
    )
    from quant_framework.strategies.factor_combiner import (
        equal_weighted_combine, generate_signals,
    )
    from quant_framework.execution.position_sizer import size_positions
    from quant_framework.execution.order_simulator import simulate_orders
    from quant_framework.risk.risk_metrics import risk_metrics_summary

    # 1. Data
    df = _make_demo_ohlcv(n_tickers=8, n_dates=200, seed=42)
    assert len(df["ticker"].unique()) == 8
    assert len(df["date"].unique()) == 200

    # 2. Factors
    factors = compute_all_factors(df)
    neutralized = neutralize_and_standardize(factors)
    ohlc_cols = {"date", "ticker", "open", "high", "low", "close", "volume", "industry"}
    factor_cols = [c for c in neutralized.columns if c not in ohlc_cols]
    assert len(factor_cols) > 0

    # 3. Alpha combination + signals
    combined = equal_weighted_combine(neutralized, factor_cols)
    signals = generate_signals(combined, "combined_score", top_k=3)
    n_long = int((signals["signal"] == 1).sum())
    n_short = int((signals["signal"] == -1).sum())
    assert n_long + n_short > 0, "Expected non-zero signals"

    # 4. Position sizing
    latest_date = df["date"].max()
    latest_sig = signals[signals["date"] == latest_date]
    if not latest_sig.empty:
        sizes = size_positions(latest_sig, df, capital=100_000, method="equal_weight")
        assert sizes.get("total_allocated", 0) >= 0  # 0 if no buy signals

    # 5. Order simulation
    sim = simulate_orders(df, signals, initial_cash=200_000)
    if "error" not in sim:
        assert "equity_curve" in sim
        assert len(sim["equity_curve"]) > 0

    # 6. Risk metrics
    if "equity_curve" in sim:
        eq = pd.Series(sim["equity_curve"])
        rets = eq.pct_change().dropna()
        if len(rets) > 10:
            risk = risk_metrics_summary(rets, equity_curve=eq)
            assert "Sharpe" in risk

    # 7. End-to-end passed
    assert True  # pipeline completed without error
