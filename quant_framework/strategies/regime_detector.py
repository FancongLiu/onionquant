"""
regime_detector.py — 市场状态检测 (Market Regime Detection)

使用 statsmodels MarkovRegression (Markov Switching Dynamic Regression)
进行市场状态识别：牛市/熊市/震荡市的概率分类。

不手搓状态空间模型 — 全部委托 statsmodels。

Usage:
    python regime_detector.py --input prices.parquet
"""

import argparse
import warnings
from typing import Dict, Optional

import numpy as np
import pandas as pd
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

warnings.filterwarnings("ignore")


def detect_regimes(returns: pd.Series, n_regimes: int = 2,
                   switch_variance: bool = True, **kwargs) -> Dict:
    """使用 Markov Switching 模型检测市场状态。

    Args:
        returns: 日收益率序列
        n_regimes: 状态数量 (2=牛/熊, 3=牛/熊/震荡)
        switch_variance: 是否切换方差 (推荐 True)

    Returns:
        dict with:
          - smoothed_probs: DataFrame of regime probabilities (T × n_regimes)
          - regime_labels: Series of most-likely regime per date
          - regime_stats: per-regime mean/vol/sharpe/frequency
          - model: fitted MarkovRegression (for inspection)
          - aic, bic: information criteria
    """
    r = returns.dropna()
    if len(r) < 60:
        return {"error": f"insufficient data: {len(r)} rows"}

    model = MarkovRegression(
        endog=r.values,
        k_regimes=n_regimes,
        trend='c',
        switching_variance=switch_variance,
        **kwargs,
    )
    result = model.fit(search_reps=10, maxiter=300, disp=False)

    probs = result.smoothed_marginal_probabilities
    prob_df = pd.DataFrame(
        probs, index=r.index[-len(probs):],
        columns=[f"regime_{i}" for i in range(n_regimes)],
    )
    regime_idx = prob_df.values.argmax(axis=1)
    regime_labels = pd.Series(regime_idx, index=prob_df.index)

    # Per-regime statistics
    regime_stats = {}
    for i in range(n_regimes):
        mask = regime_labels == i
        regime_ret = r.loc[prob_df.index][mask]
        ann_mean = float(regime_ret.mean() * 252) if len(regime_ret) > 0 else np.nan
        ann_vol = float(regime_ret.std() * np.sqrt(252)) if len(regime_ret) > 1 else np.nan
        freq = mask.mean()
        regime_stats[f"regime_{i}"] = {
            "annual_return": round(ann_mean, 4),
            "annual_vol": round(ann_vol, 4),
            "sharpe": round(ann_mean / ann_vol, 2) if ann_vol and ann_vol > 0 else 0.0,
            "frequency": round(float(freq), 4),
            "label": _regime_label(ann_mean, ann_vol),
        }

    return {
        "smoothed_probs": prob_df,
        "regime_labels": regime_labels,
        "regime_stats": regime_stats,
        "aic": round(result.aic, 1),
        "bic": round(result.bic, 1),
        "n_regimes": n_regimes,
    }


def _regime_label(ann_ret: float, ann_vol: float) -> str:
    """启发式状态标签。"""
    if np.isnan(ann_ret) or np.isnan(ann_vol):
        return "unknown"
    if ann_ret > 0.10 and ann_vol < 0.35:
        return "bull"
    elif ann_ret < -0.05:
        return "bear"
    else:
        return "sideways"


def classify_current(returns: pd.Series, n_regimes: int = 2) -> Dict:
    """快速分类当前市场状态 (使用最近 252 个交易日)。"""
    r = returns.dropna().tail(252)
    if len(r) < 60:
        return {"error": "insufficient recent data"}
    result = detect_regimes(r, n_regimes=n_regimes)
    if "error" in result:
        return result
    current_prob = result["smoothed_probs"].iloc[-1]
    current_regime = int(current_prob.values.argmax())
    return {
        "current_regime": current_regime,
        "regime_prob": {f"regime_{i}": round(float(current_prob.iloc[i]), 4)
                        for i in range(n_regimes)},
        "label": result["regime_stats"][f"regime_{current_regime}"]["label"],
    }


def regime_transition_matrix(result: Dict) -> Optional[pd.DataFrame]:
    """从 fitted 结果提取状态转移矩阵 (需重新拟合提取 params)."""
    if "error" in result:
        return None
    # Transition probabilities are stored in model param_names as 'p[0->0]', etc.
    # Use simpler approach: empirical transition count
    labels = result["regime_labels"]
    n = result["n_regimes"]
    if labels is None or len(labels) < 2:
        return None
    tm = np.zeros((n, n))
    for t in range(1, len(labels)):
        frm = int(labels.iloc[t - 1])
        to = int(labels.iloc[t])
        tm[frm, to] += 1
    tm = tm / tm.sum(axis=1, keepdims=True)
    return pd.DataFrame(
        tm,
        index=[f"from_{i}" for i in range(n)],
        columns=[f"to_{i}" for i in range(n)],
    )


# ─── Rolling regime (lightweight, no MS model) ───────────────────
def rolling_regime_simple(returns: pd.Series, window: int = 63,
                          vol_threshold: float = 0.20) -> pd.DataFrame:
    """轻量滚动状态分类 (基于收益+波动率，不依赖 Markov 模型)。

    Returns:
        DataFrame with columns: regime (bull/bear/sideways), ann_ret, ann_vol
    """
    r = returns.dropna()
    roll_ret = r.rolling(window).mean() * 252
    roll_vol = r.rolling(window).std() * np.sqrt(252)

    def _label(ret, vol):
        if pd.isna(ret) or pd.isna(vol):
            return "unknown"
        if ret > 0.10 and vol < vol_threshold:
            return "bull"
        elif ret < -0.05:
            return "bear"
        else:
            return "sideways"

    regime = pd.Series(
        [_label(ret, vol) for ret, vol in zip(roll_ret, roll_vol)],
        index=r.index,
    )
    return pd.DataFrame({
        "regime": regime,
        "ann_ret": roll_ret,
        "ann_vol": roll_vol,
    }, index=r.index)


# ─── Demo ────────────────────────────────────────────────────────
def _make_demo_returns(n: int = 500, seed: int = 42) -> pd.Series:
    """Generate returns with regime shifts for demonstration."""
    np.random.seed(seed)
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    regimes = np.zeros(n, dtype=int)
    regimes[:200] = 0  # bull
    regimes[200:350] = 1  # bear
    regimes[350:] = 0  # bull again

    rets = np.zeros(n)
    for i in range(n):
        if regimes[i] == 0:
            rets[i] = np.random.normal(0.12 / 252, 0.15 / np.sqrt(252))
        else:
            rets[i] = np.random.normal(-0.08 / 252, 0.35 / np.sqrt(252))

    return pd.Series(rets, index=dates)


# ─── CLI ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Market Regime Detection (statsmodels)")
    parser.add_argument("--input", help="Input parquet/csv with 'close' column")
    parser.add_argument("--column", default="close", help="Price column name")
    parser.add_argument("--n-regimes", type=int, default=2, help="Number of regimes (2 or 3)")
    parser.add_argument("--simple", action="store_true", help="Use rolling (lightweight) instead of Markov")
    args = parser.parse_args()

    if args.input:
        df = pd.read_parquet(args.input) if args.input.endswith(".parquet") else pd.read_csv(args.input)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
        prices = df[args.column]
        returns = prices.pct_change().dropna()
    else:
        print("No --input; using synthetic regime-shift demo data\n")
        returns = _make_demo_returns()

    if args.simple:
        result = rolling_regime_simple(returns)
        print("Rolling Regime Classification (last 10 days):")
        print(result.tail(10).to_string())
        counts = result["regime"].value_counts()
        print(f"\nRegime distribution:\n{counts.to_string()}")
        return

    result = detect_regimes(returns, n_regimes=args.n_regimes)
    if "error" in result:
        print(f"Error: {result['error']}")
        return

    print(f"\n{'='*56}")
    print(f"  Markov Switching Regime Detection ({args.n_regimes} regimes)")
    print(f"{'='*56}")
    print(f"  AIC: {result['aic']}, BIC: {result['bic']}")

    print("\n  Regime Statistics:")
    for name, stats in result["regime_stats"].items():
        print(f"    {name} ({stats['label']}): "
              f"ret={stats['annual_return']:.2%} "
              f"vol={stats['annual_vol']:.2%} "
              f"sharpe={stats['sharpe']:.2f} "
              f"freq={stats['frequency']:.1%}")

    current = classify_current(returns, n_regimes=args.n_regimes)
    if "error" not in current:
        print(f"\n  Current Regime: {current['label']} "
              f"(regime {current['current_regime']}, "
              f"prob={current['regime_prob']})")

    tm = regime_transition_matrix(result)
    if tm is not None:
        print("\n  Transition Matrix:")
        print(tm.to_string())


if __name__ == "__main__":
    main()
