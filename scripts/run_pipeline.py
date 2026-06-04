#!/usr/bin/env python3
"""
run_pipeline.py — 一键E2E量化流水线

链式执行: 数据拉取 → 因子计算 → 信号生成 → 回测 → 报告

Usage:
    python scripts/run_pipeline.py --tickers AAPL,MSFT,NVDA --start 2024-01-01
    python scripts/run_pipeline.py --tickers AAPL,MSFT --mode full
    python scripts/run_pipeline.py --tickers SPY,QQQ --mode quick
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _read_pipeline_tickers() -> list[str]:
    """从 TASK_TRACKER.md 动态读取 PIPELINE_TICKERS 配置。

    迭代引擎更新 TASK_TRACKER.md 中的 PIPELINE_TICKERS 行后，
    每日流水线自动使用最新标的列表，无需手动修改 cron。
    """
    tracker_path = PROJECT_ROOT / "TASK_TRACKER.md"
    if not tracker_path.exists():
        return []
    text = tracker_path.read_text(encoding="utf-8")
    m = re.search(r"PIPELINE_TICKERS\s*\|\s*(.+?)\s*\|", text)
    if not m:
        return []
    raw = m.group(1).strip()
    return [t.strip().upper() for t in raw.split(",") if t.strip()]


def _read_pipeline_config(key: str, default: str = "") -> str:
    """从 TASK_TRACKER.md 的流水线配置表读取任意参数。"""
    tracker_path = PROJECT_ROOT / "TASK_TRACKER.md"
    if not tracker_path.exists():
        return default
    text = tracker_path.read_text(encoding="utf-8")
    m = re.search(rf"{key}\s*\|\s*(.+?)\s*\|", text)
    return m.group(1).strip() if m else default


def _alert_failure(tickers: list, step: str, error: str, mode: str = "full"):
    """Write pipeline failure alert to chairman_outbox for WeChat + SSE push."""
    from datetime import datetime as dt
    outbox_dir = PROJECT_ROOT / "company" / "chairman_outbox"
    outbox_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.now().strftime("%Y%m%d_%H%M%S")
    path = outbox_dir / f"ALERT_pipeline_failed_{ts}.md"
    path.write_text(
        f"# Pipeline FAILED\n"
        f"**优先级**: 高\n"
        f"**时间**: {dt.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"**模式**: {mode}\n"
        f"**标的**: {', '.join(tickers[:8])}{'...' if len(tickers) > 8 else ''}\n"
        f"**失败步骤**: {step}\n"
        f"**错误**: {error}\n"
        f"\n---\n建议: 检查数据源连接后重试 `python scripts/run_pipeline.py --tickers {','.join(tickers[:5])} --start 2025-01-01`",
        encoding="utf-8",
    )
    print(f"       [ALERT] Pipeline failure alert written to {path.name}")


def step1_fetch(tickers: list, start: str, end: str = None, save_parquet: bool = True):
    """Step 1: 拉取日线数据 + save to parquet for dashboard."""
    from quant_framework.data.fetchers.yfinance_fetcher import fetch_batch
    print(f"[1/5] Fetching {len(tickers)} tickers from {start}...")
    df = fetch_batch(tickers, start, end, source="auto")
    if df is None or df.empty:
        raise RuntimeError("No data fetched")
    print(f"       {len(df)} rows, {df['ticker'].nunique()} tickers")

    # T888/T891: Save to parquet for dashboard API consumption
    if save_parquet:
        import pandas as pd
        data_dir = Path(__file__).resolve().parent.parent / "quant_framework" / "data" / "raw"
        data_dir.mkdir(parents=True, exist_ok=True)
        out_path = data_dir / f"price_{datetime.now().strftime('%Y%m%d_%H%M')}.parquet"
        if isinstance(df, pd.DataFrame):
            df.to_parquet(out_path, index=False)
            print(f"       Saved to {out_path}")
        # Keep only latest 5 parquet files to avoid bloat
        existing = sorted(data_dir.glob("price_*.parquet"))
        for old in existing[:-5]:
            old.unlink()

    return df


def step2_factors(df):
    """Step 2: 计算因子."""
    from quant_framework.strategies.qlib_factor_engine import (
        compute_all_factors, neutralize_and_standardize,
    )
    print("[2/5] Computing factors...")
    factors = compute_all_factors(df)
    if "industry" in df.columns:
        factors = neutralize_and_standardize(factors, industry_col="industry")
    n_factors = len([c for c in factors.columns if c not in df.columns])
    print(f"       {n_factors} factors computed")
    return factors


def step3_signals(factor_df, price_series=None):
    """Step 3: 因子组合 → 信号（含集中度风控 T992）."""
    from quant_framework.strategies.factor_combiner import (
        equal_weighted_combine, generate_signals,
    )
    import numpy as np
    print("[3/5] Generating signals...")
    factor_cols = [c for c in factor_df.columns
                   if c not in {"ticker", "date", "close", "open", "high", "low",
                                "volume", "industry", "signal", "combined_score"}]
    combined = equal_weighted_combine(factor_df, factor_cols)

    # T992: 集中度风控参数
    MIN_POSITIONS = 5       # 每日最少持仓数
    MAX_POSITION_PCT = 0.25 # 单票最大权重 25%
    MAX_SECTOR_PCT = 0.40   # 单行业最大敞口 40%

    # 行业映射（用于敞口限制）
    SECTOR_MAP = {
        "DXYZ": "航天/SPAC", "RKLB": "航天", "LUNR": "航天", "RDW": "航天",
        "NVDA": "半导体/AI", "AMD": "半导体/AI", "AVGO": "半导体/AI", "ANET": "半导体/AI",
        "MU": "存储", "WDC": "存储", "SNDK": "存储", "STX": "存储",
        "LITE": "光模块", "COHR": "光模块",
        "BABA": "中国/电商", "JD": "中国/电商",
    }

    signals = generate_signals(combined, "combined_score", top_k=MIN_POSITIONS,
                               method="long_only", cross_sectional=True)

    # ── T992 风控: 权重上限 + 行业敞口限制 ──
    signals["weight"] = 1.0 / MIN_POSITIONS  # 默认等权

    # 单票权重上限 25%
    signals.loc[signals["weight"] > MAX_POSITION_PCT, "weight"] = MAX_POSITION_PCT

    # 按日期分组检查行业敞口
    if "date" in signals.columns:
        capped_dates = 0
        for dt, grp in signals.groupby("date"):
            # 计算各行业权重
            grp = grp.copy()
            grp["sector"] = grp["ticker"].map(SECTOR_MAP).fillna("其他")
            sector_wt = grp.groupby("sector")["weight"].sum()
            over_sectors = sector_wt[sector_wt > MAX_SECTOR_PCT]
            if len(over_sectors) > 0:
                # 对超限行业内的股票等比缩权
                for sec, total_wt in over_sectors.items():
                    sec_mask = (signals["date"] == dt) & (signals["ticker"].isin(
                        grp.loc[grp["sector"] == sec, "ticker"]))
                    scale = MAX_SECTOR_PCT / total_wt
                    signals.loc[sec_mask, "weight"] *= scale
                capped_dates += 1

    # 最少持仓数: 如果信号<MIN_POSITIONS, 降级为等权持有全部标的
    per_date_counts = signals.groupby("date").size() if "date" in signals.columns else pd.Series()
    if not per_date_counts.empty and (per_date_counts < MIN_POSITIONS).any():
        # 对不够的日期, 用全标的等权补足
        all_tickers = factor_df["ticker"].unique()
        for dt in per_date_counts[per_date_counts < MIN_POSITIONS].index:
            extra = pd.DataFrame({
                "date": dt, "ticker": list(all_tickers[:MIN_POSITIONS]),
                "signal": 1, "weight": 1.0 / MIN_POSITIONS,
                "combined_score": 0.0
            })
            signals = pd.concat([signals, extra], ignore_index=True)

    n_long = (signals.get("signal", 0) == 1).sum()
    n_dates = signals["date"].nunique() if "date" in signals.columns else 1
    avg_positions = n_long / max(n_dates, 1)
    print(f"       {n_long} long signals ({avg_positions:.1f}/day avg, "
          f"top_k={MIN_POSITIONS}, max_wt={MAX_POSITION_PCT:.0%}, max_sector={MAX_SECTOR_PCT:.0%})")
    return signals


def step4_backtest(signals_df, prices_df):
    """Step 4: 回测 (使用实际权重, 非二进制信号)."""
    from quant_framework.backtest.harness import vectorized_backtest
    print("[4/5] Running backtest...")
    pivot_prices = prices_df.pivot_table(
        index="date", columns="ticker", values="close", aggfunc="last"
    ).sort_index()
    # T992: 使用 weight 列而非 signal (0/1) — 确保权重加总≈1, 避免极端集中
    weight_col = "weight" if "weight" in signals_df.columns else "signal"
    pivot_signals = signals_df.pivot_table(
        index="date", columns="ticker", values=weight_col, aggfunc="last"
    ).sort_index().fillna(0)
    # 每行归一化, 确保权重和为1 (处理日期间 ticker 数不同)
    row_sums = pivot_signals.sum(axis=1)
    pivot_signals = pivot_signals.div(row_sums.where(row_sums > 0, 1), axis=0)
    result = vectorized_backtest(pivot_prices, pivot_signals)
    if "error" in result:
        print(f"       Error: {result['error']}")
        return result
    print(f"       Sharpe={result['sharpe_ratio']:.2f}, "
          f"Return={result['total_return']:.2%}, "
          f"MaxDD={result['max_drawdown']:.2%}")
    return result


def step5_report(bt_result, tickers, start, end):
    """Step 5: 生成报告."""
    print("[5/5] Generating report...")
    report = [
        "# 量化流水线报告",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**标的**: {', '.join(tickers)}",
        f"**区间**: {start} → {end or 'today'}",
        "",
        "## 回测结果",
        "",
        "| 指标 | 值 |",
        "|------|----|",
    ]
    metrics = [
        ("总收益", "total_return", ".2%"),
        ("年化收益", "annual_return", ".2%"),
        ("年化波动", "annual_volatility", ".2%"),
        ("Sharpe", "sharpe_ratio", ".2f"),
        ("Sortino", "sortino_ratio", ".2f"),
        ("Calmar", "calmar_ratio", ".2f"),
        ("最大回撤", "max_drawdown", ".2%"),
        ("胜率", "win_rate", ".1%"),
        ("盈亏比", "profit_factor", ".2f"),
    ]
    for label, key, fmt in metrics:
        if key in bt_result and bt_result[key] is not None:
            val = bt_result[key]
            if fmt.endswith("%"):
                # empyrical returns decimals (e.g. 0.0842), and Python's
                # .2% format specifier multiplies by 100 internally
                report.append(f"| {label} | {val:{fmt}} |")
            else:
                report.append(f"| {label} | {val:{fmt}} |")

    report.append("")
    report.append("*由 run_pipeline.py 自动生成*")
    text = "\n".join(report)

    reports_dir = PROJECT_ROOT / "company" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    path.write_text(text, encoding="utf-8")
    print(f"       Report saved to {path}")
    return text


def main():
    dynamic_tickers = _read_pipeline_tickers()
    default_tickers = ",".join(dynamic_tickers) if dynamic_tickers else "AAPL,MSFT,NVDA,GOOGL,AMZN"
    default_start = _read_pipeline_config("PIPELINE_START", "2024-01-01")
    default_mode = _read_pipeline_config("PIPELINE_MODE", "full")

    parser = argparse.ArgumentParser(description="E2E Quant Pipeline Runner")
    parser.add_argument("--tickers", default=default_tickers,
                        help="Comma-separated tickers (default: from TASK_TRACKER.md PIPELINE_TICKERS)")
    parser.add_argument("--start", default=default_start, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date (default: today)")
    parser.add_argument("--mode", default=default_mode,
                        choices=["full", "quick", "tune"],
                        help="full=全流程, quick=仅数据+因子, tune=全流程+自动调优")
    parser.add_argument("--tune-calls", type=int, default=30,
                        help="Bayesian optimization iterations (default: 30)")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    source = "TASK_TRACKER.md" if dynamic_tickers and args.tickers == default_tickers else "CLI"
    print(f"\n{'='*56}")
    print(f"  Quant Pipeline — {len(tickers)} tickers (source: {source}), {args.start} → {args.end or 'today'}")
    print(f"{'='*56}\n")

    try:
        df = step1_fetch(tickers, args.start, args.end)
    except Exception as e:
        _alert_failure(tickers, "step1_fetch", str(e), args.mode)
        raise

    try:
        factors = step2_factors(df)
    except Exception as e:
        _alert_failure(tickers, "step2_factors", str(e), args.mode)
        raise

    try:
        if args.mode == "quick":
            print("\n[Quick mode] Skipping signal generation and backtest.")
            return

        try:
            signals = step3_signals(factors, df["close"] if "close" in df.columns else None)
        except Exception as e:
            _alert_failure(tickers, "step3_signals", str(e), args.mode)
            raise

        try:
            bt = step4_backtest(signals, df)
        except Exception as e:
            _alert_failure(tickers, "step4_backtest", str(e), args.mode)
            raise
        report = step5_report(bt, tickers, args.start, args.end)
        print(f"\n{'='*56}")
        print(report)

        # T885: Auto-tuning mode
        if args.mode == "tune":
            print(f"\n{'='*56}")
            print("  Auto-Tuning Mode (T885)")
            print(f"{'='*56}\n")
            try:
                from quant_framework.strategies.auto_tuner import auto_tune, report_markdown as tune_report

                # Strategy simulator using pipeline as objective
                def strategy_sim(**params):
                    sim_factors = step2_factors(df)  # recompute with params
                    sim_signals = step3_signals(sim_factors, df["close"] if "close" in df.columns else None)
                    sim_bt = step4_backtest(sim_signals, df)
                    return {"sharpe": sim_bt.get("sharpe", 0), "return": sim_bt.get("total_return", 0)}

                base_params = {"lookback": 60, "risk_aversion": 2.5, "max_weight": 0.2, "vol_target": 0.15}
                param_bounds = {k: (v * 0.5, v * 2.0) for k, v in base_params.items()}

                tune_result = auto_tune(
                    strategy_sim, base_params, param_bounds,
                    n_calls=args.tune_calls, elasticity_threshold=0.1,
                )
                print(tune_report(tune_result))

                # Save tuning report
                tune_path = PROJECT_ROOT / "company" / "reports" / f"tune_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
                tune_path.write_text(tune_report(tune_result), encoding="utf-8")
                print(f"\nTuning report saved to {tune_path}")
            except ImportError:
                print("Auto-tuning skipped — skopt not available")
            except Exception as te:
                print(f"Auto-tuning failed (non-fatal): {te}")

    except Exception as e:
        print(f"\nPipeline FAILED: {e}")
        _alert_failure(tickers, "pipeline", str(e), args.mode)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
