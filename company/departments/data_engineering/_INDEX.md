# 💾 数据工程部

> **状态**: done | **任务**: T858 | **完成**: 9 | **进行中**: 0 | **阻塞**: 0 | **更新**: 2026-05-17T13:00

## 部门职责
数据采集、清洗、存储、特征工程。为所有策略提供高质量数据基础设施。

## 天才Agent编制
- **首席数据架构师** — 数据仓库设计，Pipeline架构
- **Pipeline工程师** — ETL实现，数据质量管理
- **数据库管理员** — PostgreSQL/时序数据库运维
- **特征工程师** — 因子计算、特征存储

## 数据源方案
| 数据源 | 类型 | 频率 | 覆盖 | 接入难度 |
|--------|------|------|------|---------|
| Yahoo Finance | 行情+财务 | 日级 | 全球 | ⭐ |
| Alpha Vantage | 行情+指标 | 日/分 | 全球 | ⭐ |
| Polygon.io | 实时行情 | Tick | 美股 | ⭐⭐ |
| FRED | 宏观 | 日/月 | 美国 | ⭐ |
| SEC EDGAR | 财报XBRL | 季 | 美股 | ⭐⭐ |
| WRDS/CRSP | 学术数据库 | 日 | 美股 | ⭐⭐⭐ |

## 技术栈评估
| 组件 | 候选 | 推荐 |
|------|------|------|
| 存储 | PostgreSQL / Parquet / MongoDB | PostgreSQL + Parquet |
| 计算 | Pandas / Polars / Dask | Polars (快) + Dask (大) |
| 调度 | Airflow / Prefect / Dagster | Prefect |
| 特征存储 | Feast / 自研 | Feast |
| 数据质量 | Great Expectations / 自研 | Great Expectations |

## 当前任务
- [T835] E2E流水线一键运行 ✅ — scripts/run_pipeline.py
- [T840] 数据源质量基准测试 ✅ — benchmark.py
- [T815] 每日数据刷新cron ✅
- [T812] 真实市场数据拉取 ✅
- [T603] TimescaleDB+Dagster骨架 ✅
- [T014] 数据Pipeline技术栈选型 ✅

## 文件清单
- `_INDEX.md` — 本文件
- `data_knowledge.md` → 知识图谱 (待创建)
- `pipelines/` → Pipeline脚本 (待创建)
