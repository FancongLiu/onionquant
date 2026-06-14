"""quant_framework.data — data fetching, pipeline, and quality monitoring."""

from quant_framework.data.data_quality import (
    QualityConfig,
    check_completeness,
    check_freshness,
    check_lookahead_bias,
    check_nan_ratio,
    check_outliers,
    quality_report_markdown,
    run_quality_checks,
)
