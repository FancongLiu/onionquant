"""
canslim_screener.py — CAN SLIM 三级漏斗筛选

支持 --config 加载外部 YAML 配置, 无 --config 时使用默认值(向后兼容).

Level 1 (量化初筛):
  - 当季EPS增长 > 25%
  - 年度EPS增长 > 25% (近3年)
  - 股价相对强度(RS) > 80 (近12月涨幅排前20%)
  - 成交量 > 日均1000万美元
  - 机构持股增长 > 0 (optional)

Level 2 (质量+成长):
  - ROE > 15%
  - 毛利率 > 40%
  - 负债权益比 < 行业均值
  - 营收增速 > 20%

Level 3 (动量+技术):
  - 绝对动量: 近12月收益 > 0
  - 相对动量: 近6月收益 > S&P500
  - 距52周高点 < 15%

Usage:
    python canslim_screener.py --input data.parquet --output screened.csv
    python canslim_screener.py --input data.parquet --config canslim_config.yaml
"""

import argparse
import logging
import warnings
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore")


# ──────────────────────────────────────────────
# Config Loader
# ──────────────────────────────────────────────
def load_config(path: str) -> dict:
    """Load YAML config and return the 'screener' section."""
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("screener", {})


# ──────────────────────────────────────────────
# Level 1: Quantitative Screening
# ──────────────────────────────────────────────
def level1_quantitative(df: pd.DataFrame,
                        min_eps_growth_q: float = 25.0,
                        min_eps_growth_a: float = 25.0,
                        min_rs: float = 80.0,
                        min_volume: float = 1e7,
                        require_inst_own_growth: bool = False) -> pd.DataFrame:
    """Apply CAN SLIM Level 1 quantitative filters."""
    mask = pd.Series(True, index=df.index)

    mask &= df.get("eps_growth_quarterly", 0) > min_eps_growth_q
    mask &= df.get("eps_growth_annual_3y", 0) > min_eps_growth_a
    mask &= df.get("rs_rating", 0) > min_rs
    mask &= df.get("avg_daily_volume", 0) > min_volume

    if require_inst_own_growth and "inst_ownership_growth" in df:
        mask &= df["inst_ownership_growth"] > 0

    return df.loc[mask].copy()


# ──────────────────────────────────────────────
# Level 2: Quality + Growth
# ──────────────────────────────────────────────
def level2_quality_growth(df: pd.DataFrame,
                          min_roe: float = 15.0,
                          min_gross_margin: float = 40.0,
                          min_rev_growth: float = 20.0,
                          debt_to_equity_mode: str = "industry",
                          max_debt_to_equity: float = 2.0) -> pd.DataFrame:
    """Apply CAN SLIM Level 2 quality and growth filters."""
    mask = pd.Series(True, index=df.index)

    mask &= df.get("roe", 0) > min_roe
    mask &= df.get("gross_margin", 0) > min_gross_margin
    mask &= df.get("revenue_growth", 0) > min_rev_growth

    # Debt-to-equity filtering by mode
    if debt_to_equity_mode == "industry" and "debt_to_equity" in df and "industry" in df:
        ind_means = df.groupby("industry")["debt_to_equity"].transform("mean")
        mask &= df["debt_to_equity"] < ind_means
    elif debt_to_equity_mode == "median" and "debt_to_equity" in df:
        mask &= df["debt_to_equity"] < df["debt_to_equity"].median()
    elif debt_to_equity_mode == "absolute" and "debt_to_equity" in df:
        mask &= df["debt_to_equity"] < max_debt_to_equity
    elif "debt_to_equity" in df:
        # Fallback: industry if available, otherwise median
        if "industry" in df:
            ind_means = df.groupby("industry")["debt_to_equity"].transform("mean")
            mask &= df["debt_to_equity"] < ind_means
        else:
            mask &= df["debt_to_equity"] < df["debt_to_equity"].median()

    return df.loc[mask].copy()


# ──────────────────────────────────────────────
# Level 3: Momentum + Technical
# ──────────────────────────────────────────────
def level3_momentum_technical(df: pd.DataFrame,
                              sp500_return: float = 0.0,
                              max_dist_52w_high: float = 15.0,
                              check_absolute_momentum: bool = True,
                              check_relative_momentum: bool = True) -> pd.DataFrame:
    """Apply CAN SLIM Level 3 momentum and technical filters."""
    mask = pd.Series(True, index=df.index)

    # Absolute momentum: 12-month return > 0
    if check_absolute_momentum:
        mask &= df.get("return_12m", 0) > 0

    # Relative momentum: 6-month return > S&P500
    if check_relative_momentum:
        mask &= df.get("return_6m", 0) > sp500_return

    # Distance from 52-week high
    if "price" in df and "high_52w" in df:
        dist_pct = (df["high_52w"] - df["price"]) / df["high_52w"] * 100
        mask &= dist_pct < max_dist_52w_high
    elif "pct_from_52w_high" in df:
        mask &= df["pct_from_52w_high"] < max_dist_52w_high

    return df.loc[mask].copy()


# ──────────────────────────────────────────────
# Scoring
# ──────────────────────────────────────────────
DEFAULT_WEIGHTS: Dict[str, float] = {
    "eps_growth_quarterly": 0.20,
    "eps_growth_annual_3y": 0.15,
    "rs_rating": 0.15,
    "roe": 0.10,
    "gross_margin": 0.05,
    "revenue_growth": 0.10,
    "return_12m": 0.10,
    "return_6m": 0.10,
    "inst_ownership_growth": 0.05,
}


def compute_score(row: pd.Series, weights: Dict[str, float] = None) -> float:
    """Composite score based on key CAN SLIM metrics (percentile-based)."""
    if weights is None:
        weights = DEFAULT_WEIGHTS
    score = 0.0
    for col, w in weights.items():
        if col in row and not np.isnan(row[col]):
            score += w * row[col]
    return score


def run_screener(df: pd.DataFrame,
                 sp500_return: float = 0.0,
                 verbose: bool = True,
                 config: dict = None) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Run the full 3-level CAN SLIM screener with optional YAML config.

    Parameters
    ----------
    df : DataFrame
        Stock data with required columns.
    sp500_return : float
        S&P500 return (%) for relative momentum comparison.
    verbose : bool
        Print progress.
    config : dict, optional
        Config dict loaded from YAML (the 'screener' section).
        When None, uses hardcoded defaults.

    Returns
    -------
    result : DataFrame of stocks that pass all 3 levels, with composite score.
    counts : dict of counts at each level.
    """
    cfg = config or {}
    l1_cfg = cfg.get("level1", {})
    l2_cfg = cfg.get("level2", {})
    l3_cfg = cfg.get("level3", {})
    scoring_cfg = cfg.get("scoring", {})
    funnel_cfg = cfg.get("funnel", {})
    industry_neutral = cfg.get("industry_neutral", False)

    counts: Dict[str, int] = {}
    total = len(df)
    counts["total"] = total

    # Level 1
    enable_l1 = funnel_cfg.get("enable_level1", True)
    if enable_l1:
        l1 = level1_quantitative(df, **l1_cfg)
        counts["level1"] = len(l1)
        if verbose:
            logger.info("Level 1: %d / %d passed quantitative screen", counts['level1'], total)
    else:
        l1 = df.copy()
        counts["level1"] = total
        if verbose:
            print("[Level 1] skipped (disabled in config)")

    # Level 2
    enable_l2 = funnel_cfg.get("enable_level2", True)
    if enable_l2:
        l2 = level2_quality_growth(l1, **l2_cfg)
        counts["level2"] = len(l2)
        if verbose:
            logger.info("Level 2: %d / %d passed quality+growth screen", counts['level2'], counts['level1'])
    else:
        l2 = l1.copy()
        counts["level2"] = counts["level1"]
        if verbose:
            print("[Level 2] skipped (disabled in config)")

    # Level 3
    enable_l3 = funnel_cfg.get("enable_level3", True)
    if enable_l3:
        l3 = level3_momentum_technical(l2, sp500_return=sp500_return, **l3_cfg)
        counts["level3"] = len(l3)
        if verbose:
            logger.info("Level 3: %d / %d passed momentum+technical screen", counts['level3'], counts['level2'])
    else:
        l3 = l2.copy()
        counts["level3"] = counts["level2"]
        if verbose:
            print("[Level 3] skipped (disabled in config)")

    # Scoring
    l3 = l3.copy()
    weights = scoring_cfg.get("weights", DEFAULT_WEIGHTS)

    if industry_neutral and "industry" in l3:
        # Industry-neutral percentile scoring
        for col in list(weights.keys()):
            pct_col = col + "_pct"
            l3[pct_col] = l3.groupby("industry")[col].rank(pct=True)
        pct_weights = {k + "_pct": v for k, v in weights.items()}
    else:
        # Global percentile scoring
        for col in weights:
            pct_col = col + "_pct"
            if col in l3:
                l3[pct_col] = l3[col].rank(pct=True)
        pct_weights = {k + "_pct": v for k, v in weights.items()}

    l3["canslim_score"] = l3.apply(compute_score, axis=1, args=(pct_weights,))
    l3 = l3.sort_values("canslim_score", ascending=False)

    if verbose:
        print("\nTop 10 by CAN SLIM score:")
        cols = ["ticker", "canslim_score", "eps_growth_quarterly", "rs_rating", "roe"]
        cols = [c for c in cols if c in l3.columns]
        print(l3[cols].head(10).to_string(index=False))

    return l3, counts


# ──────────────────────────────────────────────
# Demo / Synthetic Data
# ──────────────────────────────────────────────
def _make_demo_data(n: int = 500) -> pd.DataFrame:
    np.random.seed(42)
    industries = ["Tech", "Healthcare", "Finance", "Consumer", "Energy"]
    data = {
        "ticker": [f"TICK{i:04d}" for i in range(n)],
        "industry": np.random.choice(industries, n),
        "eps_growth_quarterly": np.random.normal(30, 20, n),
        "eps_growth_annual_3y": np.random.normal(28, 15, n),
        "rs_rating": np.random.uniform(0, 100, n),
        "avg_daily_volume": np.random.uniform(5e6, 5e8, n),
        "inst_ownership_growth": np.random.normal(5, 10, n),
        "roe": np.random.normal(18, 10, n),
        "gross_margin": np.random.normal(45, 15, n),
        "debt_to_equity": np.random.exponential(1.0, n),
        "revenue_growth": np.random.normal(22, 15, n),
        "return_12m": np.random.normal(15, 25, n),
        "return_6m": np.random.normal(8, 15, n),
        "price": np.random.uniform(10, 500, n),
        "high_52w": np.random.uniform(15, 550, n),
    }
    df = pd.DataFrame(data)
    df["high_52w"] = np.maximum(df["high_52w"], df["price"] * 1.02)
    return df


# ──────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="CAN SLIM 三级筛选器")
    parser.add_argument("--input", type=str, default=None,
                        help="输入 parquet 文件路径 (省略则使用合成数据演示)")
    parser.add_argument("--output", type=str, default="screened.csv",
                        help="输出 CSV 路径 (默认 screened.csv)")
    parser.add_argument("--sp500-return", type=float, default=5.0,
                        help="S&P500 近6月收益率 (%)")
    parser.add_argument("--config", type=str, default=None,
                        help="YAML 配置文件路径 (省略则使用硬编码默认值)")
    args = parser.parse_args()

    # Load config
    cfg = load_config(args.config) if args.config else {}

    if args.input:
        df = pd.read_parquet(args.input)
        print(f"Loaded {len(df)} stocks from {args.input}")
    else:
        print("No --input provided; generating synthetic demo data...")
        df = _make_demo_data(500)

    result, counts = run_screener(df, sp500_return=args.sp500_return, config=cfg)

    # Save
    out_cols = ["ticker", "industry", "canslim_score",
                "eps_growth_quarterly", "rs_rating", "roe",
                "return_12m", "return_6m"]
    out_cols = [c for c in out_cols if c in result.columns]
    result[out_cols].to_csv(args.output, index=False)
    print(f"\nSaved {len(result)} screened stocks to {args.output}")

    # Summary
    print(f"\n{'='*40}")
    print("CAN SLIM Screening Summary")
    print(f"{'='*40}")
    for k, v in counts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
