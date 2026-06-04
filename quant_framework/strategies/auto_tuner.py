"""Auto-tuner: sensitivity-guided Bayesian optimization (T880).

1. Run sensitivity analysis → identify high-elasticity parameters.
2. Only tune sensitive params (reducing search space).
3. skopt Bayesian optimization on reduced param space.
4. Report before/after with improvement quantification.

Integrates with sensitivity.py and optimizer.py."""

import numpy as np
from typing import Dict, List, Callable, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class TuneResult:
    best_params: Dict[str, float]
    baseline_params: Dict[str, float]
    best_score: float
    baseline_score: float
    improvement_pct: float
    n_iterations: int
    tuned_params: List[str]
    history: List[Dict] = field(default_factory=list)


def auto_tune(
    fn: Callable[..., Dict],
    base_params: Dict[str, float],
    param_bounds: Dict[str, Tuple[float, float]],
    output_key: str = "sharpe",
    n_calls: int = 50,
    elasticity_threshold: float = 0.1,
    maximize: bool = True,
) -> TuneResult:
    """Sensitivity-guided auto-tuning.

    1. Run sensitivity analysis on all tunable params.
    2. Only tune params with |elasticity| > threshold.
    3. Bayesian optimization via skopt on reduced space.
    """
    from quant_framework.strategies.sensitivity import sensitivity_matrix

    # Step 1: Sensitivity analysis
    param_names = list(param_bounds.keys())
    sens_df = sensitivity_matrix(
        fn, base_params, param_names, perturbation=0.20, output_key=output_key
    )

    # Step 2: Filter sensitive params
    sensitive = sens_df[abs(sens_df["elasticity"]) > elasticity_threshold]
    if sensitive.empty:
        logger.warning("No params above elasticity threshold — tuning all")
        sensitive = sens_df

    tuned_params = sensitive["param"].tolist()
    logger.info(f"Tuning {len(tuned_params)}/{len(param_names)} params: {tuned_params}")

    # Step 3: Baseline
    baseline = fn(**base_params).get(output_key, 0)
    direction = 1 if maximize else -1

    # Step 4: Bayesian optimization on reduced space
    try:
        from skopt import gp_minimize
        from skopt.space import Real
        from skopt.utils import use_named_args

        space = [
            Real(param_bounds[p][0], param_bounds[p][1], name=p) for p in tuned_params
        ]

        @use_named_args(space)
        def objective(**kwargs):
            test_params = {**base_params, **kwargs}
            try:
                score = fn(**test_params).get(output_key, baseline)
            except Exception:
                score = baseline
            return -direction * score  # skopt minimizes

        result = gp_minimize(
            objective, space, n_calls=n_calls, random_state=42, noise=0.01
        )
        best_score = -direction * result.fun

        # Build best params dict
        best_params = dict(base_params)
        for p, val in zip(tuned_params, result.x):
            best_params[p] = float(val)

        history = [
            {"iter": i, "params": dict(zip(tuned_params, x)), "score": -direction * y}
            for i, (x, y) in enumerate(zip(result.x_iters, result.func_vals))
        ]
        history.sort(key=lambda h: h["score"], reverse=maximize)

        return TuneResult(
            best_params=best_params,
            baseline_params=base_params,
            best_score=round(best_score, 6),
            baseline_score=round(baseline, 6),
            improvement_pct=round(
                (best_score - baseline) / max(abs(baseline), 1e-10) * 100, 2
            ),
            n_iterations=n_calls,
            tuned_params=tuned_params,
            history=history[:10],
        )

    except ImportError:
        # Fallback: grid search on sensitive params
        logger.warning("skopt not available — using grid search fallback")
        return _grid_tune(
            fn, base_params, param_bounds, tuned_params, output_key, maximize
        )


def _grid_tune(fn, base_params, bounds, tuned_params, output_key, maximize):
    """Grid search fallback when skopt is unavailable."""
    best_params = dict(base_params)
    best_score = fn(**base_params).get(output_key, 0)
    direction = 1 if maximize else -1

    for p in tuned_params:
        lo, hi = bounds[p]
        for val in np.linspace(lo, hi, 10):
            test = {**best_params, p: float(val)}
            try:
                score = fn(**test).get(output_key, best_score)
            except Exception:
                continue
            if direction * score > direction * best_score:
                best_score = score
                best_params[p] = float(val)

    return TuneResult(
        best_params=best_params,
        baseline_params=base_params,
        best_score=round(best_score, 6),
        baseline_score=round(fn(**base_params).get(output_key, 0), 6),
        improvement_pct=round(
            (best_score - fn(**base_params).get(output_key, 0))
            / max(abs(fn(**base_params).get(output_key, 0)), 1e-10)
            * 100,
            2,
        ),
        n_iterations=len(tuned_params) * 10,
        tuned_params=tuned_params,
    )


def report_markdown(result: TuneResult) -> str:
    """Generate auto-tuning report."""
    lines = [
        "# Auto-Tuning Report",
        f"**Improvement**: {result.improvement_pct:+.2f}% over baseline",
        f"**Best score**: {result.best_score:.4f} (baseline: {result.baseline_score:.4f})",
        f"**Tuned params**: {', '.join(result.tuned_params)}",
        f"**Iterations**: {result.n_iterations}",
        "",
        "## Best Parameters",
        "| Param | Baseline | Tuned | Change |",
        "|-------|----------|-------|--------|",
    ]
    for p in result.tuned_params:
        bl = result.baseline_params.get(p, "—")
        tuned = result.best_params.get(p, "—")
        change = (
            f"{tuned - bl:.4f}"
            if isinstance(bl, (int, float)) and isinstance(tuned, (int, float))
            else "—"
        )
        lines.append(f"| {p} | {bl} | {tuned} | {change} |")

    if result.history:
        lines.append("\n## Top 5 Trials")
        lines.append("| Rank | Score | Params |")
        lines.append("|------|-------|--------|")
        for i, h in enumerate(result.history[:5]):
            params_str = ", ".join(f"{k}={v:.3f}" for k, v in h["params"].items())
            lines.append(f"| {i + 1} | {h['score']:.4f} | {params_str} |")

    return "\n".join(lines)
