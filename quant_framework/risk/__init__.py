"""Risk management modules — metrics, optimization, stress testing, attribution, covariance."""

from quant_framework.risk.risk_metrics import (
    var_historical, cvar, max_drawdown, sharpe_ratio, risk_metrics_summary,
)
from quant_framework.risk.portfolio_optimizer import (
    mean_variance_optimize, risk_parity, kelly_criterion,
    black_litterman, black_litterman_rp, black_litterman_bayesian, bl_optimize,
)
from quant_framework.risk.drawdown_control import (
    cppi, volatility_targeting, fixed_stop_loss,
)
from quant_framework.risk.stress_testing import (
    portfolio_stress_test, var_backtest, stress_correlation_matrix, report_markdown,
)
from quant_framework.risk.performance_attribution import (
    factor_regression, rolling_attribution, brinson_attribution,
    contribution_summary, report_markdown as attribution_report,
)
from quant_framework.risk.covariance import (
    estimate_covariance, ledoit_wolf, oas, exponentially_weighted,
    factor_model_cov, robust_mcd, cov_to_corr, compare_estimators,
)
from quant_framework.risk.industry_attribution import (
    check_industry_exposure, barra_risk_attribution, risk_budget_decomposition,
    analyze_risk_attribution, report_markdown as industry_report,
)
