"""quant_framework.backtest — unified backtesting infrastructure."""

from quant_framework.backtest.analytics import (
    analytics_report_markdown,
    analyze_drawdown_duration,
    analyze_streaks,
    annual_returns_table,
    full_analytics,
    monthly_returns_table,
    profit_loss_ratio,
    rolling_metrics_df,
)
from quant_framework.backtest.harness import (
    compare_strategies,
    event_driven_backtest,
    signal_backtest,
    vectorized_backtest,
)
from quant_framework.backtest.visualization import (
    annual_returns,
    drawdown_plot,
    equity_curve,
    full_report,
    monthly_returns_heatmap,
    return_distribution,
    rolling_metrics,
)
