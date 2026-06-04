"""
factor_calculator.py — DEPRECATED 兼容层 (v4)

因子计算、中性化、标准化全部委托给 qlib_factor_engine (Safe Pandas, 无 eval())。
仅保留: Alphalens 因子评估 (evaluate_factor) + CLI 入口。
新代码请直接使用 qlib_factor_engine.py。本文件将在 v5 移除。
"""

import argparse
import warnings
from typing import Optional

warnings.warn(
    "factor_calculator.py is deprecated, use qlib_factor_engine.py instead",
    DeprecationWarning,
    stacklevel=2,
)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from quant_framework.strategies.qlib_factor_engine import (  # noqa: E402
    compute_all_factors,
    neutralize_and_standardize,
    FACTOR_REGISTRY,
)

warnings.filterwarnings("ignore")

# ─── 别名 (向后兼容) ───
ALPHA_FACTORS = FACTOR_REGISTRY
compute_factors = compute_all_factors


def neutralize_industry(
    factor_df: pd.DataFrame, industry_col: str = "industry"
) -> pd.DataFrame:
    """行业中性化 (兼容 wrapper，不标准化)."""
    result = factor_df.copy()
    factor_cols = [c for c in result.columns if c in FACTOR_REGISTRY]
    if industry_col not in result.columns or not factor_cols:
        return result
    for col in factor_cols:
        grp_mean = result.groupby(industry_col)[col].transform("mean")
        result[col] = result[col] - grp_mean
    return result


def standardize(factor_df: pd.DataFrame, sigma: float = 3.0) -> pd.DataFrame:
    """Z-score 标准化 + sigma 截尾 (兼容 wrapper，不中性化)."""
    result = factor_df.copy()
    factor_cols = [c for c in result.columns if c in FACTOR_REGISTRY]
    for col in factor_cols:
        x = result[col].values
        med = np.nanmedian(x)
        mad = np.nanmedian(np.abs(x - med))
        if mad == 0 or np.isnan(mad):
            continue
        z = (x - med) / (mad * 1.4826)
        z = np.clip(z, -sigma, sigma)
        result[col] = z
    return result


def compute_all(
    df: pd.DataFrame, neutralize: bool = True, factors: Optional[list] = None
) -> pd.DataFrame:
    """一站式：计算因子 → 中性化 → 标准化 (v4: 委托 qlib_factor_engine)."""
    result = compute_all_factors(df, factors)
    if neutralize:
        result = neutralize_and_standardize(result)
    else:
        result = standardize(result)
    return result


# ─── Alphalens 集成 (唯一保留的手工逻辑，无等价开源库) ───
def evaluate_factor(
    factor_df: pd.DataFrame, factor_name: str, price_series: pd.Series
) -> dict:
    """使用 Alphalens-Reloaded 评估单因子。"""
    try:
        import alphalens as al
    except ImportError:
        return {"error": "alphalens not installed"}
    aligned = pd.DataFrame(
        {
            "factor": factor_df[factor_name],
            "price": price_series,
        }
    ).dropna()
    if len(aligned) < 20:
        return {"error": f"insufficient data: {len(aligned)} rows"}
    factor = aligned["factor"]
    prices = aligned["price"]
    try:
        factor_data = al.utils.get_clean_factor_and_forward_returns(
            factor,
            prices,
            quantiles=5,
            periods=(1, 5, 21),
        )
        ic = al.performance.factor_information_coefficient(factor_data)
        ic_summary = ic.mean()
        return {
            "factor": factor_name,
            "IC_1D": round(float(ic_summary.get(1, 0)), 4),
            "IC_5D": round(float(ic_summary.get(5, 0)), 4),
            "IC_21D": round(float(ic_summary.get(21, 0)), 4),
            "n_obs": len(factor_data),
        }
    except Exception as e:
        return {"error": str(e), "factor": factor_name}


def report_factors(factor_df: pd.DataFrame) -> str:
    """生成因子摘要报告 (v4: 使用 FACTOR_REGISTRY)."""
    lines = [
        "## Factor Report",
        "",
        "| Factor | Direction | Mean | Std |",
        "|--------|-----------|------|-----|",
    ]
    for name in FACTOR_REGISTRY:
        if name in factor_df.columns:
            col = factor_df[name].dropna()
            if len(col) > 0:
                _, direction = FACTOR_REGISTRY[name]
                dir_label = "long" if direction == 1 else "short"
                lines.append(
                    f"| {name} | {dir_label} | {col.mean():.4f} | {col.std():.4f} |"
                )
    return "\n".join(lines)


# ─── CLI ───
def main():
    parser = argparse.ArgumentParser(
        description="Factor Calculator (v4: qlib_factor_engine wrapper)"
    )
    parser.add_argument("--input", required=True, help="Input OHLCV CSV/parquet")
    parser.add_argument("--output", default="factors.parquet", help="Output file")
    parser.add_argument(
        "--no-neutralize", action="store_true", help="Skip industry neutralization"
    )
    parser.add_argument("--report", action="store_true", help="Print factor report")
    parser.add_argument(
        "--eval", dest="eval_factor", help="Evaluate single factor with Alphalens"
    )
    args = parser.parse_args()

    df = (
        pd.read_parquet(args.input)
        if args.input.endswith(".parquet")
        else pd.read_csv(args.input)
    )
    result = compute_all(df, neutralize=not args.no_neutralize)

    if args.output.endswith(".parquet"):
        result.to_parquet(args.output, index=False)
    else:
        result.to_csv(args.output, index=False)

    factor_cols = [c for c in result.columns if c in FACTOR_REGISTRY]
    print(f"Computed {len(factor_cols)} factors → {args.output}")

    if args.report:
        print(report_factors(result))

    if args.eval_factor and "close" in df.columns:
        r = evaluate_factor(result, args.eval_factor, df["close"])
        print(r)


if __name__ == "__main__":
    main()
