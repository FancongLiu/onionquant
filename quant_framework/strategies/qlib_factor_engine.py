"""
qlib_factor_engine.py — 因子引擎 (v3: Safe Pandas, No eval())

使用 Qlib Alpha158 因子定义 + pandas 安全计算。
不再使用 eval() 表达式解析器。

架构:
  - factor_calculator.py: 单个因子计算 + 标准化
  - factor_combiner.py:   因子组合 + 信号生成
  - qlib_factor_engine.py: 一站式入口 + 配置驱动

Usage:
    python qlib_factor_engine.py --input data.parquet --output factors.csv
    python qlib_factor_engine.py --input data.parquet --alpha158 --output factors.csv
"""

import argparse
import warnings
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ─── Safe Factor Functions ───
# Each function takes a DataFrame, returns a Series.
# No eval(), no string-parsed expressions at runtime.


def _pct(col: str, window: int):
    """Price % change."""
    return lambda df: df[col].pct_change(window)


def _rolling_mean(col: str, window: int):
    return lambda df: df[col].rolling(window).mean()


def _rolling_std(col: str, window: int):
    return lambda df: df[col].rolling(window).std()


def _rolling_sum(col: str, window: int):
    return lambda df: df[col].rolling(window).sum()


def _rolling_corr(c1: str, c2: str, window: int):
    return lambda df: df[c1].rolling(window).corr(df[c2])


def _shift(col: str, n: int):
    return lambda df: df[col].shift(n)


def _log(col: str):
    return lambda df: np.log(df[col].clip(lower=1e-12))


def _rank(col: str):
    return lambda df: df[col].rank(pct=True)


# ─── Factor Registry ───
# name → (function, direction)

FACTOR_REGISTRY = {
    # Momentum (Qlib Alpha158)
    "mom_1d": (_pct("close", 1), 1),
    "mom_5d": (_pct("close", 5), 1),
    "mom_10d": (_pct("close", 10), 1),
    "mom_21d": (_pct("close", 21), 1),
    "mom_63d": (_pct("close", 63), 1),
    "mom_126d": (_pct("close", 126), 1),
    "mom_252d": (_pct("close", 252), 1),
    # Reversal
    "rev_5d": (lambda df: -df["close"].pct_change(5), 1),
    "rev_10d": (lambda df: -df["close"].pct_change(10), 1),
    "rev_21d": (lambda df: -df["close"].pct_change(21), 1),
    # Volatility (low vol = positive)
    "vol_5d": (lambda df: -df["close"].pct_change().rolling(5).std(), 1),
    "vol_21d": (lambda df: -df["close"].pct_change().rolling(21).std(), 1),
    "vol_63d": (lambda df: -df["close"].pct_change().rolling(63).std(), 1),
    # Turnover
    "turn_5d": (lambda df: df["volume"].rolling(5).mean(), -1),
    "turn_21d": (lambda df: df["volume"].rolling(21).mean(), -1),
    # Size
    "size_log": (lambda df: -np.log(df["close"].clip(lower=1)), 1),
    # Volatility of returns
    "std_5d": (lambda df: df["close"].pct_change().rolling(5).std(), -1),
    "std_21d": (lambda df: df["close"].pct_change().rolling(21).std(), -1),
    # Correlation
    "corr_vp_21d": (_rolling_corr("volume", "close", 21), -1),
    # Value
    "pe": (lambda df: -df.get("pe_ratio", 0), 1),
    "pb": (lambda df: -df.get("pb_ratio", 0), 1),
    "ps": (lambda df: -df.get("ps_ratio", 0), 1),
    # Quality
    "roe": (lambda df: df.get("roe", 0), 1),
    "gross_margin": (lambda df: df.get("gross_margin", 0), 1),
    "debt_ratio": (lambda df: -df.get("debt_to_equity", 0.5), 1),
    # Growth
    "eps_growth": (lambda df: df.get("eps_growth_quarterly", 0), 1),
    "rev_growth": (lambda df: df.get("revenue_growth", 0), 1),
}

FACTOR_GROUPS = {
    "momentum": [
        "mom_1d",
        "mom_5d",
        "mom_10d",
        "mom_21d",
        "mom_63d",
        "mom_126d",
        "mom_252d",
    ],
    "reversal": ["rev_5d", "rev_10d", "rev_21d"],
    "volatility": ["vol_5d", "vol_21d", "vol_63d", "std_5d", "std_21d"],
    "turnover": ["turn_5d", "turn_21d"],
    "size": ["size_log"],
    "value": ["pe", "pb", "ps"],
    "quality": ["roe", "gross_margin", "debt_ratio"],
    "growth": ["eps_growth", "rev_growth"],
    "correlation": ["corr_vp_21d"],
}


def compute_all_factors(
    df: pd.DataFrame, factors: Optional[list] = None
) -> pd.DataFrame:
    """安全计算所有因子（无 eval()）。

    Args:
        df: OHLCV DataFrame
        factors: 因子名列表，None=全部

    Returns:
        DataFrame with factor columns
    """
    result = df.copy()
    names = factors if factors else list(FACTOR_REGISTRY.keys())

    for name in names:
        if name not in FACTOR_REGISTRY:
            continue
        fn, _ = FACTOR_REGISTRY[name]
        try:
            result[name] = fn(df)
        except Exception:
            result[name] = np.nan

    return result


def neutralize_and_standardize(
    factor_df: pd.DataFrame, industry_col: str = "industry", sigma: float = 3.0
) -> pd.DataFrame:
    """行业中性化 + Z-score 标准化 + sigma 截尾。

    使用 median/MAD 而非 mean/std 以提高稳健性。
    """
    result = factor_df.copy()
    factor_cols = [c for c in result.columns if c in FACTOR_REGISTRY]

    # 行业中性化
    if industry_col in result.columns:
        for col in factor_cols:
            if col not in result.columns:
                continue
            ind_mean = result.groupby(industry_col)[col].transform("mean")
            result[col] = result[col] - ind_mean

    # Z-score 标准化 (MAD-based)
    for col in factor_cols:
        if col not in result.columns:
            continue
        values = result[col].astype(float).dropna()
        if len(values) < 5:
            continue
        med = values.median()
        mad = (values - med).abs().median() * 1.4826
        if mad == 0:
            mad = values.std()
        if mad == 0:
            continue
        result.loc[result[col].notna(), col] = (
            result.loc[result[col].notna(), col] - med
        ).clip(-sigma * mad, sigma * mad) / mad

    return result


def generate_report(factor_df: pd.DataFrame) -> str:
    """生成因子摘要报告。"""
    factor_cols = [c for c in factor_df.columns if c in FACTOR_REGISTRY]
    lines = [
        "## Factor Engine Report",
        "",
        "| Factor | Mean | Std | Direction | Group |",
        "|--------|------|-----|-----------|-------|",
    ]

    group_map = {}
    for g, names in FACTOR_GROUPS.items():
        for n in names:
            group_map[n] = g

    for col in factor_cols:
        vals = factor_df[col].dropna()
        if len(vals) < 5:
            continue
        _, direction = FACTOR_REGISTRY.get(col, (None, 0))
        dir_label = {1: "long", -1: "short"}.get(direction, "neutral")
        grp = group_map.get(col, "-")
        lines.append(
            f"| {col} | {vals.mean():.4f} | {vals.std():.4f} | {dir_label} | {grp} |"
        )

    return "\n".join(lines)


# ─── CLI ───
def main():
    parser = argparse.ArgumentParser(description="Safe Factor Engine (no eval)")
    parser.add_argument("--input", required=True, help="Input parquet/csv file")
    parser.add_argument("--output", default="factors.csv", help="Output file")
    parser.add_argument(
        "--factors", nargs="*", default=None, help="Specific factors to compute"
    )
    parser.add_argument(
        "--group", default=None, help="Factor group name (momentum, value, etc.)"
    )
    parser.add_argument(
        "--no-neutralize", action="store_true", help="Skip neutralization"
    )
    parser.add_argument("--report", action="store_true", help="Print factor report")
    args = parser.parse_args()

    # Load data
    df = (
        pd.read_parquet(args.input)
        if args.input.endswith(".parquet")
        else pd.read_csv(args.input)
    )

    # Select factors
    factor_list = args.factors
    if args.group and args.group in FACTOR_GROUPS:
        factor_list = FACTOR_GROUPS[args.group]

    # Compute
    result = compute_all_factors(df, factor_list)
    if not args.no_neutralize:
        result = neutralize_and_standardize(result)

    # Save
    if args.output.endswith(".parquet"):
        result.to_parquet(args.output, index=False)
    else:
        result.to_csv(args.output, index=False)

    computed = [c for c in result.columns if c in FACTOR_REGISTRY]
    print(f"Computed {len(computed)} factors → {args.output}")
    print(
        f"  Groups: {list(set(FACTOR_GROUPS[g] for g in FACTOR_GROUPS if any(f in computed for f in FACTOR_GROUPS[g])))}"
    )  # noqa

    if args.report:
        print(generate_report(result))


if __name__ == "__main__":
    main()
