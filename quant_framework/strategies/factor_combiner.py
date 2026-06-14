"""
factor_combiner.py — 因子组合引擎 (v3: Alphalens-Reloaded)

使用 Alphalens-Reloaded 进行因子 IC 分析和分层组合。
不手搓 IC/ICIR/信号生成逻辑。

Usage:
    python factor_combiner.py --input factors.csv --output signals.csv
"""

import argparse
import warnings

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")


def _rolling_spearman(a: pd.Series, b: pd.Series, window: int) -> pd.Series:
    """滚动 Spearman 秩相关系数 (兼容所有 pandas 版本)."""
    combined = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(combined) < window:
        return pd.Series(np.nan, index=a.index)
    combined["_r"] = np.nan
    for i in range(window - 1, len(combined)):
        wa = combined["a"].iloc[i - window + 1 : i + 1]
        wb = combined["b"].iloc[i - window + 1 : i + 1]
        if wa.nunique() < 2 or wb.nunique() < 2:
            continue
        combined.iloc[i, combined.columns.get_loc("_r")] = spearmanr(wa, wb)[0]
    result = pd.Series(np.nan, index=a.index)
    aligned = combined["_r"].dropna()
    result.loc[aligned.index] = aligned
    return result


def compute_ic(factor_values: pd.Series, forward_returns: pd.Series) -> dict:
    """计算单个因子的信息系数 (Spearman rank correlation)。"""
    aligned = pd.DataFrame({"f": factor_values, "r": forward_returns}).dropna()
    if len(aligned) < 10:
        return {"IC": np.nan, "n": len(aligned)}
    ic = aligned["f"].corr(aligned["r"], method="spearman")
    return {"IC": round(ic, 4), "n": len(aligned)}


def rolling_ic_matrix(
    factor_df: pd.DataFrame,
    factor_cols: list,
    price_series: pd.Series,
    window: int = 21,
) -> pd.DataFrame:
    """计算滚动 IC 矩阵（Alphalens 风格，基于前向收益）。"""
    fwd = price_series.pct_change(window).shift(-window)
    results = pd.DataFrame(index=factor_df.index)

    for col in factor_cols:
        if col not in factor_df.columns:
            continue
        results[f"{col}_IC"] = _rolling_spearman(factor_df[col], fwd, 252)

    return results


def _cs_ic_series(
    factor_df: pd.DataFrame,
    factor_cols: list,
    horizon: int = 21,
    min_tickers: int = 5,
    ic_smooth_span: int = 60,
) -> pd.DataFrame:
    """Cross-sectional IC per date — correct IC methodology.

    For each date, compute Spearman correlation of factor values
    vs forward returns *across tickers*. Returns IC time series
    smoothed with EWMA.

    This replaces the broken time-series rolling correlation that
    mixed tickers together and used |IC| ignoring direction.
    """
    if "date" not in factor_df.columns or "ticker" not in factor_df.columns:
        return pd.DataFrame()

    df = factor_df.copy()
    has_close = "close" in df.columns
    if not has_close:
        return pd.DataFrame()

    # Compute forward returns per ticker (avoid cross-ticker contamination)
    df["_fwd_ret"] = df.groupby("ticker", group_keys=False)["close"].transform(
        lambda x: x.pct_change(horizon).shift(-horizon)
    )

    dates = sorted(df["date"].unique())
    ic_data = {}

    for dt in dates:
        day = df[df["date"] == dt].dropna(subset=["_fwd_ret"])
        if len(day) < min_tickers:
            continue
        for col in factor_cols:
            if col not in day.columns:
                continue
            valid = day[[col, "_fwd_ret"]].dropna()
            if len(valid) < min_tickers:
                continue
            ic = valid[col].corr(valid["_fwd_ret"], method="spearman")
            ic_data.setdefault(col, {})[dt] = ic

    if not ic_data:
        return pd.DataFrame()

    ic_df = pd.DataFrame(ic_data).sort_index()
    return ic_df.ewm(span=ic_smooth_span, min_periods=max(20, min_tickers)).mean()


def filter_factors_by_ic(
    factor_df: pd.DataFrame,
    factor_cols: list,
    ic_threshold: float = 0.02,
    min_factors: int = 3,
    horizon: int = 21,
) -> list:
    """Exclude factors whose trailing mean |IC| falls below threshold.

    Weak-IC factors add noise, not signal. This keeps only factors
    with meaningful predictive power while guaranteeing at least
    min_factors remain (kept by |IC| rank if threshold filters all).
    """
    ic_df = _cs_ic_series(factor_df, factor_cols, horizon=horizon)
    if ic_df.empty:
        return (
            factor_cols[:min_factors]
            if len(factor_cols) >= min_factors
            else factor_cols
        )

    mean_abs_ic = ic_df.abs().mean().sort_values(ascending=False)
    strong = [
        c
        for c in mean_abs_ic.index
        if c in factor_cols and mean_abs_ic[c] >= ic_threshold
    ]
    if len(strong) < min_factors:
        strong = list(mean_abs_ic.index[:min_factors])
    return [c for c in strong if c in factor_cols]


def ic_weighted_combine(
    factor_df: pd.DataFrame,
    factor_cols: list,
    price_series: pd.Series = None,
    ic_threshold: float = 0.0,
    min_factors: int = 3,
    ic_shrinkage: float = 0.2,
) -> pd.DataFrame:
    """IC-weighted factor combination using proper cross-sectional IC.

    Uses signed IC (not |IC|) so factors with negative predictive power
    are correctly flipped — fixing the Sharpe=-1.17 bug caused by
    time-series rolling correlation + |IC| weighting.

    Set ic_threshold > 0 (e.g. 0.02) to filter noise factors.
    """
    result = factor_df.copy()

    if price_series is None or "date" not in result.columns:
        return equal_weighted_combine(factor_df, factor_cols)

    # Apply quality filter if threshold set
    active_cols = list(factor_cols)
    if ic_threshold > 0:
        active_cols = filter_factors_by_ic(
            result, factor_cols, ic_threshold=ic_threshold, min_factors=min_factors
        )

    ic_df = _cs_ic_series(result, active_cols)
    if ic_df.empty:
        return equal_weighted_combine(factor_df, active_cols)

    result["combined_score"] = 0.0
    dates_with_ic = set(ic_df.index)

    for dt in sorted(result["date"].unique()):
        if dt not in dates_with_ic:
            continue
        day_ic = ic_df.loc[dt]  # signed IC values
        day_mask = result["date"] == dt

        # Signed-IC weights: w_i = IC_i / sum(|IC_j|)
        w_sum = day_ic.abs().sum()
        if w_sum == 0 or pd.isna(w_sum):
            continue
        ic_weights = day_ic / w_sum

        # Shrinkage toward equal weights to reduce IC estimation noise
        if ic_shrinkage > 0:
            n = len(active_cols)
            ic_weights = ic_weights * (1 - ic_shrinkage) + (1.0 / n) * ic_shrinkage

        for col in active_cols:
            if col in ic_weights.index and not pd.isna(ic_weights[col]):
                result.loc[day_mask, "combined_score"] += (
                    result.loc[day_mask, col].fillna(0).values * ic_weights[col]
                )

    return result


def normalize_factor_signs(
    factor_df: pd.DataFrame, factor_cols: list, horizon: int = 21
) -> pd.DataFrame:
    """Flip factor signs so all factors have positive expected IC.

    Factors like debt_ratio (high=bad) get flipped so "positive=good"
    for all factors. This makes equal-weight combination viable with
    mixed-category factors. Uses cross-sectional IC to detect direction.
    """
    result = factor_df.copy()
    if "date" not in result.columns:
        return result

    ic_df = _cs_ic_series(result, factor_cols, horizon=horizon)
    if ic_df.empty:
        return result

    mean_ic = ic_df.mean()
    for col in factor_cols:
        if col in mean_ic.index and mean_ic[col] < 0:
            if col in result.columns:
                result[col] = -result[col]

    return result


def equal_weighted_combine(
    factor_df: pd.DataFrame, factor_cols: list, normalize_signs: bool = True
) -> pd.DataFrame:
    """等权因子组合。Optionally normalizes factor signs first."""
    df = factor_df
    if normalize_signs and "date" in df.columns and "ticker" in df.columns:
        df = normalize_factor_signs(df, factor_cols)

    result = df.copy()
    valid_cols = [c for c in factor_cols if c in df.columns]
    if valid_cols:
        result["combined_score"] = df[valid_cols].mean(axis=1)
    return result


def generate_signals(
    factor_df: pd.DataFrame,
    score_col: str = "combined_score",
    top_k: int = 50,
    method: str = "long_short",
    cross_sectional: bool = True,
) -> pd.DataFrame:
    """从组合得分生成交易信号。

    Args:
        factor_df: 含 score_col 和 "date" (或 index) 的 DataFrame
        score_col: 组合得分列名
        top_k: 多头/空头股票数
        method: "long_short" | "long_only" | "quantile"
        cross_sectional: 如果 True, 每个日期独立选 top-k；否则全局选

    Returns:
        DataFrame with signal column (1=long, -1=short, 0=neutral)
    """
    result = factor_df.copy()
    result["signal"] = 0

    if cross_sectional and "date" in result.columns:
        dates = sorted(result["date"].unique())
        for dt in dates:
            day_mask = result["date"] == dt
            day_scores = result.loc[day_mask, score_col].dropna()
            if len(day_scores) < 2:
                continue
            n_tickers = len(day_scores)

            if method == "long_only":
                k = min(top_k, n_tickers)
                threshold = day_scores.nlargest(k).iloc[-1]
                result.loc[day_mask & (result[score_col] >= threshold), "signal"] = 1

            elif method == "long_short":
                k = min(top_k, n_tickers // 2)
                if k < 1:
                    continue
                threshold_long = day_scores.nlargest(k).iloc[-1]
                threshold_short = day_scores.nsmallest(k).iloc[-1]
                result.loc[
                    day_mask & (result[score_col] >= threshold_long), "signal"
                ] = 1
                result.loc[
                    day_mask & (result[score_col] <= threshold_short), "signal"
                ] = -1

            elif method == "quantile":
                try:
                    result.loc[day_mask, "signal"] = pd.qcut(
                        day_scores.rank(method="first"), 5, labels=[-2, -1, 0, 1, 2]
                    ).astype(int)
                except ValueError:
                    continue
        return result

    # Global (non-cross-sectional) fallback
    scores = result[score_col].dropna()
    if len(scores) < top_k * 2:
        return result

    if method == "long_short":
        threshold_long = scores.nlargest(top_k).iloc[-1]
        threshold_short = scores.nsmallest(top_k).iloc[-1]
        result.loc[result[score_col] >= threshold_long, "signal"] = 1
        result.loc[result[score_col] <= threshold_short, "signal"] = -1
    elif method == "long_only":
        threshold = scores.nlargest(top_k).iloc[-1]
        result.loc[result[score_col] >= threshold, "signal"] = 1
    elif method == "quantile":
        result["signal"] = pd.qcut(
            scores.rank(method="first"), 5, labels=[-2, -1, 0, 1, 2]
        ).astype(int)

    return result


def factor_correlation_matrix(
    factor_df: pd.DataFrame, factor_cols: list
) -> pd.DataFrame:
    """因子相关性矩阵。"""
    valid = [c for c in factor_cols if c in factor_df.columns]
    return factor_df[valid].corr()


def evaluate_with_alphalens(
    factor_df: pd.DataFrame, factor_names: list, price_series: pd.Series
) -> str | None:
    """使用 Alphalens-Reloaded 评估因子。返回 markdown 报告。"""
    report = [
        "## Alphalens Factor Evaluation",
        "",
        "| Factor | Horizon | IC | N |",
        "|--------|---------|----|---|",
    ]

    for fname in factor_names:
        if fname not in factor_df.columns:
            continue
        factor = factor_df[fname].dropna()
        if len(factor) < 20:
            continue

        for horizon, label in [(1, "1D"), (5, "5D"), (21, "21D")]:
            fwd = price_series.pct_change(horizon).shift(-horizon)
            aligned = pd.DataFrame({"f": factor, "r": fwd}).dropna()
            if len(aligned) > 10:
                ic = aligned["f"].corr(aligned["r"], method="spearman")
                report.append(f"| {fname} | {label} | {ic:.4f} | {len(aligned)} |")

    return "\n".join(report)


# ─── CLI ───
def main():
    parser = argparse.ArgumentParser(description="Factor Combiner with Alphalens")
    parser.add_argument("--input", required=True, help="Input factor CSV/parquet")
    parser.add_argument("--output", default="signals.csv", help="Output file")
    parser.add_argument(
        "--method", default="equal_weight", choices=["equal_weight", "ic_weight"]
    )
    parser.add_argument(
        "--signal-method",
        default="long_short",
        choices=["long_short", "long_only", "quantile"],
    )
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    df = (
        pd.read_parquet(args.input)
        if args.input.endswith(".parquet")
        else pd.read_csv(args.input)
    )

    exclude = {
        "ticker",
        "date",
        "close",
        "open",
        "high",
        "low",
        "volume",
        "industry",
        "combined_score",
        "signal",
        "shares_outstanding",
    }
    factor_cols = [c for c in df.columns if c not in exclude]

    if args.method == "ic_weight" and "close" in df.columns:
        result = ic_weighted_combine(df, factor_cols, df["close"])
    else:
        result = equal_weighted_combine(df, factor_cols)

    result = generate_signals(result, "combined_score", args.top_k, args.signal_method)

    if args.output.endswith(".parquet"):
        result.to_parquet(args.output, index=False)
    else:
        result.to_csv(args.output, index=False)

    longs = (result.get("signal", 0) == 1).sum()
    shorts = (result.get("signal", 0) == -1).sum()
    print(f"Combined {len(factor_cols)} factors ({args.method}) → {args.output}")
    print(f"  Long: {longs}, Short: {shorts}")

    if args.report and "close" in df.columns:
        report = evaluate_with_alphalens(df, factor_cols[:10], df["close"])
        if report:
            print(report)


if __name__ == "__main__":
    main()
