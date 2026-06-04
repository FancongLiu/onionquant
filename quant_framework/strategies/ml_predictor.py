#!/usr/bin/env python3
"""ML return prediction — sklearn-based factor → forward return models.

Uses established sklearn estimators (Ridge, RandomForest, XGBoost) to predict
forward returns from factor values. Time-series aware cross-validation
(no lookahead bias). Feature importance for factor evaluation."""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class PredictorConfig:
    model: str = "ridge"  # "ridge" | "rf" | "xgb"
    alpha: float = 1.0  # Ridge regularization
    n_estimators: int = 100
    max_depth: int = 5
    test_size: float = 0.2
    n_splits: int = 5  # time-series CV splits
    random_state: int = 42


def _get_model(config: PredictorConfig):
    """Get sklearn estimator from config."""
    if config.model == "ridge":
        from sklearn.linear_model import Ridge

        return Ridge(alpha=config.alpha, random_state=config.random_state)

    elif config.model == "rf":
        from sklearn.ensemble import RandomForestRegressor

        return RandomForestRegressor(
            n_estimators=config.n_estimators,
            max_depth=config.max_depth,
            random_state=config.random_state,
            n_jobs=-1,
        )

    elif config.model == "xgb":
        try:
            from xgboost import XGBRegressor

            return XGBRegressor(
                n_estimators=config.n_estimators,
                max_depth=config.max_depth,
                learning_rate=0.05,
                random_state=config.random_state,
                verbosity=0,
            )
        except ImportError:
            from sklearn.ensemble import RandomForestRegressor

            return RandomForestRegressor(
                n_estimators=config.n_estimators,
                max_depth=config.max_depth,
                random_state=config.random_state,
                n_jobs=-1,
            )

    else:
        from sklearn.linear_model import Ridge

        return Ridge(alpha=config.alpha)


def prepare_data(
    factor_df: pd.DataFrame,
    factor_cols: List[str],
    forward_returns: pd.Series,
) -> Tuple[np.ndarray, np.ndarray, pd.Index]:
    """Prepare X (factors) and y (forward returns) for ML training.

    Returns (X, y, index) where X and y are aligned and NaN-free.
    """
    X = factor_df[factor_cols].copy()
    y = forward_returns.copy()

    aligned = pd.concat([X, y.rename("_target")], axis=1).dropna()
    if aligned.empty:
        return np.array([]), np.array([]), pd.Index([])

    X_clean = aligned[factor_cols]
    y_clean = aligned["_target"]

    return X_clean.values, y_clean.values, X_clean.index


def time_series_split(
    n_samples: int,
    n_splits: int = 5,
    test_size: float = 0.2,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Time-series aware train/test split (no lookahead bias).

    Each split: train = [0, t], test = [t+1, t+test_size].
    Walk-forward expanding window.
    """
    splits = []
    test_len = max(int(n_samples * test_size / n_splits), 5)
    train_start = int(n_samples * 0.3)  # start with 30% for first train

    for i in range(n_splits):
        test_end = n_samples - (n_splits - 1 - i) * test_len
        train_end = test_end - test_len
        if train_end <= train_start:
            continue
        splits.append(
            (
                np.arange(0, train_end),
                np.arange(train_end, test_end),
            )
        )

    return splits


def train_predict(
    X: np.ndarray,
    y: np.ndarray,
    config: Optional[PredictorConfig] = None,
) -> Dict:
    """Train an ML model to predict forward returns from factors.

    Returns dict with model, metrics, feature_importance.
    """
    if config is None:
        config = PredictorConfig()

    if len(X) < 50 or X.shape[1] == 0:
        return {"error": "Insufficient data (need 50+ observations)"}

    model = _get_model(config)

    # Train on full data
    model.fit(X, y)
    y_pred = model.predict(X)

    # Metrics
    from sklearn.metrics import r2_score, mean_squared_error

    r2 = float(r2_score(y, y_pred))
    mse = float(mean_squared_error(y, y_pred))
    ic = float(pd.Series(y_pred).corr(pd.Series(y), method="spearman"))

    # Feature importance
    importance = _feature_importance(model, config, X.shape[1])

    return {
        "model": model,
        "config": config.model,
        "r2": round(r2, 6),
        "mse": round(mse, 8),
        "ic": round(ic, 4),
        "rmse": round(float(np.sqrt(mse)), 6),
        "feature_importance": importance,
        "n_samples": len(X),
        "n_features": X.shape[1],
    }


def _feature_importance(model, config: PredictorConfig, n_features: int) -> np.ndarray:
    """Extract feature importance from model."""
    if hasattr(model, "coef_"):
        return np.abs(model.coef_)
    elif hasattr(model, "feature_importances_"):
        return model.feature_importances_
    else:
        return np.ones(n_features) / n_features


def cross_validate(
    X: np.ndarray,
    y: np.ndarray,
    factor_cols: List[str],
    config: Optional[PredictorConfig] = None,
) -> pd.DataFrame:
    """Time-series cross-validation for ML factor model.

    Returns DataFrame with per-fold metrics.
    """
    if config is None:
        config = PredictorConfig()

    folds = time_series_split(len(X), config.n_splits, config.test_size)
    if not folds:
        return pd.DataFrame()

    rows = []
    for fold_idx, (train_idx, test_idx) in enumerate(folds):
        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        if len(X_train) < 30 or len(X_test) < 5:
            continue

        model = _get_model(config)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        from sklearn.metrics import r2_score

        r2 = float(r2_score(y_test, y_pred))
        ic = float(pd.Series(y_pred).corr(pd.Series(y_test), method="spearman"))
        mse = float(np.mean((y_test - y_pred) ** 2))

        # Top features by importance
        imp = _feature_importance(model, config, X.shape[1])
        top_idx = np.argsort(imp)[-3:][::-1]
        top_features = [
            factor_cols[i] if i < len(factor_cols) else f"f{i}" for i in top_idx
        ]

        rows.append(
            {
                "fold": fold_idx + 1,
                "train_n": len(train_idx),
                "test_n": len(test_idx),
                "r2": round(r2, 6),
                "ic": round(ic, 4),
                "mse": round(mse, 8),
                "top_features": ", ".join(top_features),
            }
        )

    return pd.DataFrame(rows)


def predict_returns(
    factor_df: pd.DataFrame,
    factor_cols: List[str],
    config: Optional[PredictorConfig] = None,
    cross_validated: bool = True,
) -> Dict:
    """Full ML prediction pipeline: prepare → train → CV → predict.

    Returns dict with predictions, metrics, cv_results, importance_df.
    """
    if config is None:
        config = PredictorConfig()

    # Prepare data — use forward returns from factor_df if available
    if "forward_return" in factor_df.columns:
        forward_returns = factor_df["forward_return"]
    else:
        # Create proxy: next period close return (for demo/testing)
        forward_returns = factor_df.groupby("ticker")["close"].transform(
            lambda x: x.pct_change(21).shift(-21)
        )

    valid_cols = [c for c in factor_cols if c in factor_df.columns]
    X, y, idx = prepare_data(factor_df, valid_cols, forward_returns)

    if len(X) < 50:
        return {"error": "Insufficient data after cleaning"}

    # Train
    result = train_predict(X, y, config)

    if "error" in result:
        return result

    # CV
    cv_df = pd.DataFrame()
    if cross_validated and len(X) > 100:
        cv_df = cross_validate(X, y, valid_cols, config)

    # Build importance DataFrame
    imp = result["feature_importance"]
    if len(imp) == len(valid_cols):
        imp_df = pd.DataFrame(
            {
                "factor": valid_cols,
                "importance": imp,
            }
        ).sort_values("importance", ascending=False)
    else:
        imp_df = pd.DataFrame()

    # Predictions as Series
    y_pred = result["model"].predict(X)
    predictions = pd.Series(y_pred, index=idx, name="ml_prediction")

    return {
        "predictions": predictions,
        "model": result["model"],
        "r2": result["r2"],
        "ic": result["ic"],
        "rmse": result["rmse"],
        "n_samples": result["n_samples"],
        "n_features": result["n_features"],
        "feature_importance": imp_df,
        "cv_results": cv_df,
        "method": config.model,
    }


def evaluate_prediction(
    predictions: pd.Series,
    actual_returns: pd.Series,
    n_quantiles: int = 5,
) -> Dict:
    """Evaluate ML predictions: IC, quantile spread, hit rate."""
    aligned = pd.DataFrame(
        {
            "pred": predictions,
            "actual": actual_returns,
        }
    ).dropna()

    if len(aligned) < n_quantiles * 10:
        return {"error": "Insufficient data for evaluation"}

    ic = float(aligned["pred"].corr(aligned["actual"], method="spearman"))
    hit = float(
        (
            (aligned["pred"] > 0) & (aligned["actual"] > 0)
            | (aligned["pred"] < 0) & (aligned["actual"] < 0)
        ).mean()
    )

    aligned["quantile"] = pd.qcut(aligned["pred"], n_quantiles, labels=False)
    top = aligned[aligned["quantile"] == n_quantiles - 1]["actual"].mean()
    bottom = aligned[aligned["quantile"] == 0]["actual"].mean()
    spread = float(top - bottom)

    return {
        "ic": round(ic, 6),
        "hit_rate": round(hit, 4),
        "quantile_spread": round(spread, 6),
        "long_short_spread_annual": round(spread * 252, 6),
        "top_quantile_return": round(float(top), 6),
        "bottom_quantile_return": round(float(bottom), 6),
        "n": len(aligned),
    }


def report_markdown(result: Dict, eval_result: Optional[Dict] = None) -> str:
    """Generate markdown ML prediction report."""
    lines = [
        "# ML Return Prediction Report",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**Model**: {result.get('method', 'unknown')}  ",
        f"**R^2**: {result.get('r2', 0):.4f}  ",
        f"**IC**: {result.get('ic', 0):.4f}  ",
        f"**RMSE**: {result.get('rmse', 0):.4f}  ",
        f"**N**: {result.get('n_samples', 0)} | **Features**: {result.get('n_features', 0)}  ",
        "",
    ]

    if eval_result and "error" not in eval_result:
        lines += [
            "## Prediction Evaluation",
            "",
            f"**Quantile Spread**: {eval_result['quantile_spread']:.4%}  ",
            f"**Annual L/S Spread**: {eval_result['long_short_spread_annual']:.2%}  ",
            f"**Hit Rate**: {eval_result['hit_rate']:.2%}  ",
            f"**Top Q Return**: {eval_result['top_quantile_return']:.4%}  ",
            f"**Bottom Q Return**: {eval_result['bottom_quantile_return']:.4%}  ",
            "",
        ]

    imp_df = result.get("feature_importance")
    if imp_df is not None and not imp_df.empty:
        lines += [
            "## Feature Importance",
            "",
            "| Factor | Importance |",
            "|--------|-----------|",
        ]
        for _, row in imp_df.head(10).iterrows():
            lines.append(f"| {row['factor']} | {row['importance']:.6f} |")
        lines.append("")

    cv_df = result.get("cv_results")
    if cv_df is not None and not cv_df.empty:
        lines += [
            "## Cross-Validation",
            "",
            f"**Mean CV R^2**: {cv_df['r2'].mean():.4f}  ",
            f"**Mean CV IC**: {cv_df['ic'].mean():.4f}  ",
            f"**Folds**: {len(cv_df)}  ",
            "",
        ]

    lines.append("*Auto-generated by ml_predictor.py*")
    return "\n".join(lines)


# ── Demo ────────────────────────────────────────────────────


def _make_demo_data(
    n: int = 252, n_factors: int = 8, n_tickers: int = 10, seed: int = 42
) -> Tuple[pd.DataFrame, List[str]]:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    tickers = [f"T{i}" for i in range(n_tickers)]

    rows = []
    for date in dates:
        for ticker in tickers:
            rows.append({"date": date, "ticker": ticker})
    df = pd.DataFrame(rows)

    # Factors with varying signal
    true_betas = [0.01, 0.02, 0.03, -0.01, 0.015, -0.02, 0.005, 0.008]
    factor_cols = []
    for i, beta in enumerate(true_betas):
        col = f"factor_{i}"
        factor_cols.append(col)
        df[col] = rng.normal(0, 1, len(df))

    # Forward returns: linear combination of factors + noise
    noise = rng.normal(0, 0.015, len(df))
    df["forward_return"] = (
        sum(df[f"factor_{i}"] * true_betas[i] for i in range(n_factors)) + noise
    )
    df["close"] = 100.0

    return df, factor_cols


def main():
    df, factor_cols = _make_demo_data(252, 8, 10, seed=7)

    # Ridge
    cfg = PredictorConfig(model="ridge", alpha=1.0)
    result = predict_returns(df, factor_cols, cfg)
    eval_ = evaluate_prediction(result["predictions"], df["forward_return"])
    print(report_markdown(result, eval_))

    # Compare models
    print("## Model Comparison\n")
    print("| Model | R^2 | IC | CV R^2 | CV IC |")
    print("|-------|-----|-----|-------|-------|")
    for model_name in ["ridge", "rf"]:
        cfg2 = PredictorConfig(model=model_name)
        r2 = predict_returns(df, factor_cols, cfg2)
        cv_mean_r2 = r2["cv_results"]["r2"].mean() if not r2["cv_results"].empty else 0
        cv_mean_ic = r2["cv_results"]["ic"].mean() if not r2["cv_results"].empty else 0
        print(
            f"| {model_name} | {r2['r2']:.4f} | {r2['ic']:.4f} | "
            f"{cv_mean_r2:.4f} | {cv_mean_ic:.4f} |"
        )

    # Feature importance
    if not result["feature_importance"].empty:
        print(
            f"\nTop 3 features: "
            f"{result['feature_importance'].head(3)['factor'].tolist()}"
        )


if __name__ == "__main__":
    main()
