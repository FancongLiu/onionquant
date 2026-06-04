#!/usr/bin/env python3
"""Strategy parameter optimization — Bayesian (skopt) + walk-forward CV.

Uses scikit-optimize for Bayesian optimization. Walk-forward cross-validation
ensures time-series-aware evaluation (no lookahead bias)."""

import numpy as np
import pandas as pd
from typing import Dict, List, Callable, Tuple, Any
from dataclasses import dataclass, field
import warnings
import logging

logger = logging.getLogger(__name__)

try:
    from skopt import gp_minimize
    from skopt.space import Real, Integer, Categorical
    from skopt.utils import use_named_args

    HAS_SKOPT = True
except ImportError:
    HAS_SKOPT = False


@dataclass
class ParamSpec:
    name: str
    type: str  # "real" | "integer" | "categorical"
    low: float = 0
    high: float = 1
    choices: List[Any] = field(default_factory=list)


def _build_space(params: List[ParamSpec]) -> List:
    """Convert ParamSpec list to skopt space."""
    space = []
    for p in params:
        if p.type == "real":
            space.append(Real(p.low, p.high, name=p.name))
        elif p.type == "integer":
            space.append(Integer(int(p.low), int(p.high), name=p.name))
        elif p.type == "categorical":
            space.append(Categorical(p.choices, name=p.name))
        else:
            raise ValueError(f"Unknown param type: {p.type}")
    return space


def _params_to_dict(params: List[ParamSpec], values: List[Any]) -> Dict[str, Any]:
    return {p.name: v for p, v in zip(params, values)}


def walk_forward_splits(
    dates: pd.DatetimeIndex, n_splits: int = 5, train_frac: float = 0.6
) -> List[Tuple[pd.DatetimeIndex, pd.DatetimeIndex]]:
    """Generate walk-forward train/test splits (expanding window)."""
    n = len(dates)
    test_size = int(n * (1 - train_frac) / n_splits)
    splits = []
    for i in range(n_splits):
        split_idx = n - test_size * (n_splits - i)
        test_start = min(split_idx, n - test_size)
        train_dates = dates[:test_start]
        test_dates = dates[test_start : test_start + test_size]
        if len(test_dates) > 0:
            splits.append((train_dates, test_dates))
    return splits


def optimize(
    objective_fn: Callable[[Dict[str, Any]], float],
    params: List[ParamSpec],
    n_calls: int = 50,
    n_random_starts: int = 10,
    maximize: bool = True,
    random_state: int = 42,
    verbose: bool = False,
) -> Dict:
    """Bayesian optimization of strategy parameters.

    Parameters
    ----------
    objective_fn: function(params_dict) → float (metric to optimize)
    params: list of ParamSpec defining the search space
    n_calls: total number of function evaluations
    n_random_starts: initial random exploration calls
    maximize: True to maximize objective, False to minimize
    random_state: random seed for reproducibility
    verbose: print progress

    Returns
    -------
    dict with best_params, best_score, trace (list of (params, score)), convergence
    """
    if not HAS_SKOPT:
        return _grid_search_fallback(objective_fn, params, maximize, verbose)

    space = _build_space(params)
    sign = -1 if maximize else 1

    trace: List[Tuple[Dict, float]] = []

    @use_named_args(space)
    def _objective(**kwargs):
        score = objective_fn(kwargs)
        trace.append((dict(kwargs), score))
        if verbose and len(trace) % 10 == 0:
            best = (
                max(trace, key=lambda x: x[1])
                if maximize
                else min(trace, key=lambda x: x[1])
            )
            logger.info("Bayesian opt: %d/%d best=%.4f", len(trace), n_calls, best[1])
        return sign * score

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = gp_minimize(
            _objective,
            space,
            n_calls=n_calls,
            n_random_starts=n_random_starts,
            random_state=random_state,
            verbose=False,
        )

    best_score = -result.fun if maximize else result.fun
    best_params = _params_to_dict(params, result.x)

    # Convergence: best-so-far curve
    convergence = []
    best_so_far = -float("inf") if maximize else float("inf")
    for __, score in trace:
        best_so_far = max(best_so_far, score) if maximize else min(best_so_far, score)
        convergence.append(best_so_far)

    return {
        "best_params": best_params,
        "best_score": best_score,
        "trace": trace,
        "convergence": convergence,
        "n_evals": len(trace),
    }


def _grid_search_fallback(objective_fn, params, maximize, verbose):
    """Fallback grid/exhaustive search when skopt unavailable."""
    import itertools

    def _gen_values(p):
        if p.type == "categorical":
            return p.choices
        elif p.type == "integer":
            step = max(1, int((p.high - p.low) / 5))
            return list(range(int(p.low), int(p.high) + 1, step))
        else:
            return list(np.linspace(p.low, p.high, 6))

    grids = {p.name: _gen_values(p) for p in params}
    keys = list(grids.keys())
    best_score = -float("inf") if maximize else float("inf")
    best_params = {}
    trace = []

    total = 1
    for v in grids.values():
        total *= len(v)
    i = 0
    for combo in itertools.product(*grids.values()):
        kwargs = dict(zip(keys, combo))
        score = objective_fn(kwargs)
        trace.append((kwargs, score))
        if (maximize and score > best_score) or (not maximize and score < best_score):
            best_score = score
            best_params = kwargs
        i += 1
        if verbose and i % 20 == 0:
            logger.info("Grid search: %d/%d best=%.4f", i, total, best_score)

    convergence = []
    best_so_far = -float("inf") if maximize else float("inf")
    for __, score in trace:
        best_so_far = max(best_so_far, score) if maximize else min(best_so_far, score)
        convergence.append(best_so_far)

    return {
        "best_params": best_params,
        "best_score": best_score,
        "trace": trace,
        "convergence": convergence,
        "n_evals": len(trace),
    }


def optimize_walk_forward(
    strategy_fn: Callable[[pd.DataFrame, Dict[str, Any]], pd.DataFrame],
    objective_fn: Callable[[pd.DataFrame, pd.DataFrame], float],
    data: pd.DataFrame,
    params: List[ParamSpec],
    n_splits: int = 4,
    n_calls: int = 40,
    maximize: bool = True,
    random_state: int = 42,
    verbose: bool = False,
) -> Dict:
    """Optimize strategy parameters with walk-forward cross-validation.

    Parameters
    ----------
    strategy_fn: (prices_subset, params) → signals_df
    objective_fn: (signals_df, prices_df) → float (metric to optimize)
    data: full OHLCV DataFrame with 'date' column
    params: search space
    n_splits: number of walk-forward splits
    n_calls: Bayesian optimization calls per split
    maximize: True to maximize objective
    random_state: seed
    verbose: print progress

    Returns
    -------
    dict with best_params, cv_scores, per_split_results
    """
    dates = pd.to_datetime(data["date"].dropna().unique())
    dates = pd.DatetimeIndex(sorted(dates))
    splits = walk_forward_splits(dates, n_splits=n_splits)

    all_results = []
    for split_i, (train_dates, test_dates) in enumerate(splits):
        train_data = data[data["date"].isin(train_dates)]
        test_data = data[data["date"].isin(test_dates)]

        def _obj(kwargs):
            sig = strategy_fn(pd.concat([train_data, test_data]), kwargs)
            test_signals = sig[sig["date"].isin(test_dates)]
            if test_signals.empty:
                return 0.0 if maximize else 1e10
            return objective_fn(test_signals, test_data)

        if verbose:
            logger.info(
                "Walk-forward split %d/%d: train=%d test=%d",
                split_i + 1,
                len(splits),
                len(train_dates),
                len(test_dates),
            )

        result = optimize(
            _obj,
            params,
            n_calls=n_calls,
            maximize=maximize,
            random_state=random_state + split_i,
            verbose=verbose,
        )
        result["split"] = split_i
        result["test_dates"] = (test_dates[0], test_dates[-1])
        all_results.append(result)

    cv_scores = [r["best_score"] for r in all_results]
    # Select best params by mean CV score
    best_idx = int(np.argmax(cv_scores)) if maximize else int(np.argmin(cv_scores))
    best = all_results[best_idx]

    return {
        "best_params": best["best_params"],
        "best_score": best["best_score"],
        "cv_scores": cv_scores,
        "cv_mean": float(np.mean(cv_scores)),
        "cv_std": float(np.std(cv_scores)),
        "per_split": all_results,
        "n_splits": n_splits,
    }


def convergence_plot_data(result: Dict) -> Dict[str, List]:
    """Extract convergence data for plotting (use with visualization module)."""
    return {
        "convergence": result.get("convergence", []),
        "n_evals": result.get("n_evals", 0),
        "best_score": result.get("best_score", 0),
    }


def _make_demo_data(n: int = 504, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    records = []
    for i, d in enumerate(dates):
        close = 100 + np.cumsum(rng.normal(0.05, 1.5, n))[i]
        records.append(
            {
                "date": d,
                "ticker": "DEMO",
                "open": close * 0.998,
                "high": close * 1.012,
                "low": close * 0.988,
                "close": close,
                "volume": float(rng.integers(1_000_000, 10_000_000)),
            }
        )
    return pd.DataFrame(records)


def main():
    """Demo: optimize a simple momentum strategy."""
    from quant_framework.strategies.qlib_factor_engine import compute_all_factors
    from quant_framework.strategies.factor_combiner import (
        equal_weighted_combine,
        generate_signals,
    )

    data = _make_demo_data(252, seed=7)

    def strategy_fn(df, params):
        factors = compute_all_factors(df)
        factor_cols = [
            c
            for c in factors.columns
            if c not in {"date", "ticker", "open", "high", "low", "close", "volume"}
        ]
        combined = equal_weighted_combine(factors, factor_cols)
        signals = generate_signals(
            combined,
            "combined_score",
            top_k=params.get("top_k", 10),
            method=params.get("method", "long_only"),
        )
        return signals

    def objective_fn(signals, prices):
        long_signals = (signals.get("signal", 0) == 1).sum()
        return float(long_signals)  # More signals = better (demo metric)

    params = [
        ParamSpec("top_k", "integer", 5, 30),
        ParamSpec("method", "categorical", choices=["long_only", "long_short"]),
    ]

    result = optimize_walk_forward(
        strategy_fn,
        objective_fn,
        data,
        params,
        n_splits=3,
        n_calls=20,
        verbose=True,
    )

    print(f"\nBest params: {result['best_params']}")
    print(f"CV scores: {[f'{s:.2f}' for s in result['cv_scores']]}")
    print(f"CV mean ± std: {result['cv_mean']:.2f} ± {result['cv_std']:.2f}")


if __name__ == "__main__":
    main()
