"""Parameter sensitivity analysis — perturb key params, measure output impact.

Identifies which parameters most affect strategy performance, guiding tuning priorities.
T879: Sensitivity analysis module using numpy finite-difference approach."""

import numpy as np
import pandas as pd
from typing import Dict, List, Callable
import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SensitivityResult:
    param: str
    base_value: float
    perturb_pct: float
    output_change_pct: float
    elasticity: float  # output% / param%
    direction: str  # "same" or "opposite"
    impact_rank: int = 0


def perturb_and_evaluate(
    fn: Callable[..., Dict],
    base_params: Dict[str, float],
    param_name: str,
    perturbation: float = 0.20,
    output_key: str = "sharpe",
) -> SensitivityResult:
    """Perturb one parameter +/- perturbation and measure output change.

    Args:
        fn: Strategy function taking **params → dict with output_key.
        base_params: Baseline parameter values.
        param_name: Which parameter to perturb.
        perturbation: Fractional change (0.20 = ±20%).
        output_key: Which output metric to track (e.g. 'sharpe', 'return').
    """
    base_val = base_params[param_name]
    results = {}

    for label, mult in [
        ("base", 1.0),
        ("up", 1 + perturbation),
        ("down", 1 - perturbation),
    ]:
        test_params = {**base_params}
        test_params[param_name] = base_val * mult
        try:
            out = fn(**test_params)
            results[label] = out.get(output_key, 0)
        except Exception:
            results[label] = results.get("base", 0)

    base = results.get("base", 0)
    if abs(base) < 1e-10:
        return SensitivityResult(
            param=param_name,
            base_value=base_val,
            perturb_pct=perturbation,
            output_change_pct=0,
            elasticity=0,
            direction="flat",
        )

    up_change = (results.get("up", base) - base) / abs(base)
    down_change = (results.get("down", base) - base) / abs(base)
    avg_change = (abs(up_change) + abs(down_change)) / 2

    return SensitivityResult(
        param=param_name,
        base_value=base_val,
        perturb_pct=perturbation,
        output_change_pct=round(avg_change * 100, 2),
        elasticity=round(avg_change / perturbation, 3),
        direction="same" if up_change * down_change > 0 else "opposite",
    )


def sensitivity_matrix(
    fn: Callable[..., Dict],
    base_params: Dict[str, float],
    param_names: List[str],
    perturbation: float = 0.20,
    output_key: str = "sharpe",
) -> pd.DataFrame:
    """Run sensitivity analysis across multiple parameters.

    Returns DataFrame sorted by impact (highest first).
    """
    results = []
    for p in param_names:
        sr = perturb_and_evaluate(fn, base_params, p, perturbation, output_key)
        results.append(sr)

    # Rank by elasticity magnitude
    sorted_results = sorted(results, key=lambda x: abs(x.elasticity), reverse=True)
    for i, r in enumerate(sorted_results):
        r.impact_rank = i + 1

    df = pd.DataFrame(
        [
            {
                "param": r.param,
                "base_value": r.base_value,
                "perturb_±%": f"±{r.perturb_pct:.0%}",
                "output_change_%": r.output_change_pct,
                "elasticity": r.elasticity,
                "direction": r.direction,
                "impact_rank": r.impact_rank,
            }
            for r in sorted_results
        ]
    )
    return df


def report_markdown(df: pd.DataFrame, output_key: str = "sharpe") -> str:
    """Generate sensitivity analysis markdown report."""
    lines = [
        "# Parameter Sensitivity Analysis",
        f"**Output metric**: {output_key} | **Generated**: {datetime.now().isoformat()}",
        "",
    ]

    if df.empty:
        lines.append("No results.")
        return "\n".join(lines)

    high = df[abs(df["elasticity"]) > 0.5]
    medium = df[(abs(df["elasticity"]) > 0.1) & (abs(df["elasticity"]) <= 0.5)]
    low = df[abs(df["elasticity"]) <= 0.1]

    if len(high) > 0:
        lines.append("## 🔴 High Sensitivity (elasticity > 0.5)")
        lines.append("| Param | Base | Output Δ% | Elasticity | Direction |")
        lines.append("|-------|------|-----------|------------|-----------|")
        for _, r in high.iterrows():
            lines.append(
                f"| **{r['param']}** | {r['base_value']:.3f} | {r['output_change_%']:.1f}% | {r['elasticity']:.3f} | {r['direction']} |"
            )
        lines.append("")

    if len(medium) > 0:
        lines.append("## 🟡 Medium Sensitivity (0.1 < elasticity ≤ 0.5)")
        lines.append("| Param | Base | Output Δ% | Elasticity |")
        lines.append("|-------|------|-----------|-----------|")
        for _, r in medium.iterrows():
            lines.append(
                f"| {r['param']} | {r['base_value']:.3f} | {r['output_change_%']:.1f}% | {r['elasticity']:.3f} |"
            )
        lines.append("")

    if len(low) > 0:
        lines.append("## 🟢 Low Sensitivity (elasticity ≤ 0.1)")
        lines.append(f"Parameters: {', '.join(low['param'].tolist())}")

    lines.append("")
    lines.append(
        "**Recommendation**: Focus tuning efforts on 🔴 high-sensitivity parameters first."
    )
    return "\n".join(lines)


if __name__ == "__main__":
    # Demo: sensitivity of a toy strategy
    def toy_strategy(lookback=60, risk_aversion=2.5, max_weight=0.2, vol_target=0.15):
        rng = np.random.default_rng(42)
        sharpe = 1.5 + 0.01 * (lookback - 60) / 10
        sharpe -= 0.3 * abs(risk_aversion - 2.5)
        sharpe -= 0.5 * max(0, max_weight - 0.3)
        sharpe += 0.2 * (vol_target - 0.15) / 0.05
        sharpe += rng.normal(0, 0.05)
        return {"sharpe": sharpe, "return": 0.12 + rng.normal(0, 0.01)}

    params = {
        "lookback": 60,
        "risk_aversion": 2.5,
        "max_weight": 0.2,
        "vol_target": 0.15,
    }
    df = sensitivity_matrix(toy_strategy, params, list(params.keys()))
    print(report_markdown(df))
