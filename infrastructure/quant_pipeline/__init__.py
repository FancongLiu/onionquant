"""
quant_pipeline — OnionQuant 数据调度管线
Dagster pipeline for daily market data ingestion + factor computation + reporting.

作业:
  - daily_ingest_job    (每天 06:00 EST)  拉取美股日线数据 → TimescaleDB
  - weekly_factor_job   (每周六 08:00 EST) 计算因子 → 因子快照表
  - daily_report_job    (每天 09:00 EST)   生成市场摘要报告
"""

from dagster import Definitions, define_asset_job, AssetSelection, ScheduleDefinition

from quant_pipeline.assets import (
    market_data_ingest,
    factor_compute,
    data_quality_check,
    report_generate,
)

# ── 资产定义 ──
all_assets = [market_data_ingest, factor_compute, data_quality_check, report_generate]

# ── 作业 ──
daily_ingest_job = define_asset_job(
    name="daily_ingest_job",
    selection=AssetSelection.assets(market_data_ingest, data_quality_check),
)

weekly_factor_job = define_asset_job(
    name="weekly_factor_job",
    selection=AssetSelection.assets(factor_compute),
)

daily_report_job = define_asset_job(
    name="daily_report_job",
    selection=AssetSelection.assets(report_generate),
)

# ── 调度 ──
daily_ingest_schedule = ScheduleDefinition(
    name="daily_ingest_schedule",
    cron_schedule="0 6 * * 1-5",  # 工作日 EST 6:00 AM
    job=daily_ingest_job,
)

weekly_factor_schedule = ScheduleDefinition(
    name="weekly_factor_schedule",
    cron_schedule="0 8 * * 6",  # 周六 EST 8:00 AM
    job=weekly_factor_job,
)

daily_report_schedule = ScheduleDefinition(
    name="daily_report_schedule",
    cron_schedule="0 9 * * 1-5",  # 工作日 EST 9:00 AM (盘前)
    job=daily_report_job,
)

# ── Dagster Definitions ──
defs = Definitions(
    assets=all_assets,
    jobs=[daily_ingest_job, weekly_factor_job, daily_report_job],
    schedules=[daily_ingest_schedule, weekly_factor_schedule, daily_report_schedule],
)
