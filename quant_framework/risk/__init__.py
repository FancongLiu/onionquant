"""Risk management modules — metrics, optimization, stress testing, attribution, covariance."""

from quant_framework.risk.covariance import (
    compare_estimators,
    cov_to_corr,
    estimate_covariance,
    exponentially_weighted,
    factor_model_cov,
    ledoit_wolf,
    oas,
    robust_mcd,
)
from quant_framework.risk.drawdown_control import (
    cppi,
    fixed_stop_loss,
    volatility_targeting,
)
from quant_framework.risk.industry_attribution import (
    analyze_risk_attribution,
    barra_risk_attribution,
    check_industry_exposure,
    risk_budget_decomposition,
)
from quant_framework.risk.industry_attribution import (
    report_markdown as industry_report,
)
from quant_framework.risk.performance_attribution import (
    brinson_attribution,
    contribution_summary,
    factor_regression,
    rolling_attribution,
)
from quant_framework.risk.performance_attribution import (
    report_markdown as attribution_report,
)
from quant_framework.risk.portfolio_optimizer import (
    bl_optimize,
    black_litterman,
    black_litterman_bayesian,
    black_litterman_rp,
    kelly_criterion,
    mean_variance_optimize,
    risk_parity,
)
from quant_framework.risk.risk_metrics import (
    cvar,
    max_drawdown,
    risk_metrics_summary,
    sharpe_ratio,
    var_historical,
)
from quant_framework.risk.stress_testing import (
    portfolio_stress_test,
    report_markdown,
    stress_correlation_matrix,
    var_backtest,
)
