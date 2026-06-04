"""quant_framework.backtest — unified backtesting infrastructure."""
from quant_framework.backtest.harness import (
    vectorized_backtest, signal_backtest, event_driven_backtest, compare_strategies,
)
from quant_framework.backtest.visualization import (
    equity_curve, drawdown_plot, monthly_returns_heatmap,
    rolling_metrics, annual_returns, return_distribution, full_report,
)
from quant_framework.backtest.analytics import (
    analyze_streaks, analyze_drawdown_duration, monthly_returns_table,
    annual_returns_table, profit_loss_ratio, rolling_metrics_df,
    full_analytics, analytics_report_markdown,
)
