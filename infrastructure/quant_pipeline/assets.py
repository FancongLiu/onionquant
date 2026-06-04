"""
assets.py — Dagster 资产定义
OnionQuant 数据管线的 4 个核心资产:

  1. market_data_ingest  — 拉取美股日线数据 → TimescaleDB
  2. factor_compute      — 计算因子 (Qlib 表达式引擎) → 因子快照表
  3. data_quality_check  — Great Expectations / 手搓数据质量检查
  4. report_generate     — 生成每日市场摘要 → company/reports/
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from dagster import asset, AssetExecutionContext, Config

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class IngestConfig(Config):
    """数据拉取配置."""
    tickers: list[str] = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM"]
    lookback_days: int = 5
    source: str = "yfinance"  # openbb | yfinance | polygon


class FactorConfig(Config):
    """因子计算配置."""
    use_alpha158: bool = True
    industry_neutralize: bool = True


# ── Asset 1: Market Data Ingest ──
@asset(
    description="拉取美股日线数据 → TimescaleDB us_stocks_daily 表",
    group_name="data_ingestion",
)
def market_data_ingest(context: AssetExecutionContext, config: IngestConfig) -> pd.DataFrame:
    """Fetch daily OHLCV data for configured tickers and store in TimescaleDB."""
    all_data = []
    end_date = datetime.now()
    start_date = end_date - timedelta(days=config.lookback_days)

    for ticker in config.tickers:
        try:
            df = _fetch_ticker_data(ticker, start_date.strftime("%Y-%m-%d"),
                                    end_date.strftime("%Y-%m-%d"), config.source)
            if df is not None and len(df) > 0:
                df["ticker"] = ticker
                all_data.append(df)
                context.log.info(f"  {ticker}: {len(df)} rows")
        except Exception as e:
            context.log.warning(f"  {ticker}: FAILED — {e}")

    if not all_data:
        context.log.warning("No data fetched for any ticker.")
        return pd.DataFrame()

    combined = pd.concat(all_data, ignore_index=True)
    context.add_output_metadata({
        "rows": len(combined),
        "tickers": len(all_data),
        "date_range": f"{combined['date'].min()} → {combined['date'].max()}",
    })

    # Write to TimescaleDB
    _write_to_timescaledb(combined, "us_stocks_daily", context)
    return combined


# ── Asset 2: Factor Compute ──
@asset(
    description="计算因子 (Qlib 表达式引擎) → factor_snapshots 表",
    group_name="factor_engine",
    deps=[market_data_ingest],
)
def factor_compute(context: AssetExecutionContext, config: FactorConfig) -> pd.DataFrame:
    """Compute factors from market data using Qlib expression engine."""
    # Read recent data from TimescaleDB (or CSV fallback)
    df = _read_from_timescaledb("us_stocks_daily", days=252)  # 1 year for factor calc
    if df is None or len(df) == 0:
        context.log.warning("No data in TimescaleDB; using CSV fallback...")
        return pd.DataFrame()

    context.log.info(f"Computing factors on {len(df)} rows across {df['ticker'].nunique()} tickers")

    from quant_framework.strategies.qlib_factor_engine import (
        compute_all_factors, neutralize_and_standardize,
    )

    factors = compute_all_factors(df)
    if config.industry_neutralize and "industry" in df.columns:
        factors = neutralize_and_standardize(factors, industry_col="industry")

    context.add_output_metadata({
        "factors": len([c for c in factors.columns if c not in ("ticker", "date")]),
        "rows": len(factors),
    })

    # Write factor snapshots to TimescaleDB (long format)
    _write_factors_to_timescaledb(factors, context)
    return factors


# ── Asset 3: Data Quality Check ──
@asset(
    description="数据质量检查 (完整性 / 异常值 / 缺失日期)",
    group_name="data_quality",
    deps=[market_data_ingest],
)
def data_quality_check(context: AssetExecutionContext) -> dict:
    """Run data quality checks on ingested market data."""
    df = _read_from_timescaledb("us_stocks_daily", days=10)
    if df is None or len(df) == 0:
        return {"status": "no_data", "checks": []}

    checks = []

    # Check 1: Null values
    null_pct = df[["open", "high", "low", "close", "volume"]].isna().mean() * 100
    for col, pct in null_pct.items():
        passed = pct < 1.0
        checks.append({
            "check": f"null_{col}",
            "passed": passed,
            "detail": f"{pct:.2f}% nulls (threshold: 1%)",
        })

    # Check 2: OHLC sanity (high >= low)
    ohlc_ok = (df["high"] >= df["low"]).mean() * 100
    checks.append({
        "check": "ohlc_sanity",
        "passed": ohlc_ok > 99.0,
        "detail": f"{ohlc_ok:.2f}% pass high>=low check",
    })

    # Check 3: Date continuity per ticker
    for ticker in df["ticker"].unique()[:5]:
        tdf = df[df["ticker"] == ticker].sort_values("date")
        if len(tdf) > 1:
            gaps = tdf["date"].diff().dt.days.max()
            checks.append({
                "check": f"date_gap_{ticker}",
                "passed": gaps <= 3,
                "detail": f"Max gap: {gaps} days",
            })

    failed = [c for c in checks if not c["passed"]]
    if failed:
        context.log.warning(f"Quality checks FAILED: {len(failed)}")
        for c in failed:
            context.log.warning(f"  - {c['check']}: {c['detail']}")
    else:
        context.log.info("All quality checks PASSED.")

    return {"status": "warning" if failed else "ok", "checks": checks}


# ── Asset 4: Report Generate ──
@asset(
    description="生成每日市场摘要 → company/reports/ 目录",
    group_name="reporting",
    deps=[factor_compute, data_quality_check],
)
def report_generate(context: AssetExecutionContext) -> str:
    """Generate daily market summary report."""
    df = _read_from_timescaledb("us_stocks_daily", days=5)
    if df is None or len(df) == 0:
        report = "# 每日市场摘要\n\n暂无数据。\n"
    else:
        report = _build_report(df)

    # Write to reports directory
    reports_dir = PROJECT_ROOT / "company" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"daily_{datetime.now().strftime('%Y%m%d')}.md"
    report_path.write_text(report, encoding="utf-8")

    context.add_output_metadata({"report": str(report_path), "size": len(report)})
    return report


# ── Helpers ──
def _fetch_ticker_data(ticker: str, start: str, end: str, source: str = "yfinance"):
    """Fetch data for a single ticker via yfinance_fetcher module."""
    from quant_framework.data.fetchers.yfinance_fetcher import fetch_single
    return fetch_single(ticker, start, end, source=source)


def _get_timescaledb_conn():
    """Get a connection to TimescaleDB."""
    import psycopg2
    return psycopg2.connect(
        host=os.environ.get("TIMESCALE_HOST", "localhost"),
        port=os.environ.get("TIMESCALE_PORT", "5432"),
        user=os.environ.get("TIMESCALE_USER", "quant"),
        password=os.environ["TIMESCALE_PASSWORD"],
        dbname=os.environ.get("TIMESCALE_DB", "market_data"),
    )


def _write_to_timescaledb(df: pd.DataFrame, table: str, context) -> None:
    """Write DataFrame to TimescaleDB. Upsert on (ticker, date)."""
    try:
        conn = _get_timescaledb_conn()
        cur = conn.cursor()
        from psycopg2.extras import execute_values

        cols = [c for c in df.columns if c in [
            "ticker", "date", "open", "high", "low", "close", "volume", "adj_close", "source"
        ]]
        rows = [tuple(row[c] for c in cols) for _, row in df.iterrows()]

        sql = f"""
            INSERT INTO {table} ({', '.join(cols)})
            VALUES %s
            ON CONFLICT (ticker, date) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                adj_close = EXCLUDED.adj_close,
                source = EXCLUDED.source
        """
        execute_values(cur, sql, rows)
        conn.commit()
        cur.close()
        conn.close()
        context.log.info(f"Wrote {len(rows)} rows to {table}")
    except Exception as e:
        context.log.warning(f"TimescaleDB write failed ({e}); data returned as DataFrame only")


def _read_from_timescaledb(table: str, days: int = 252) -> pd.DataFrame | None:
    """Read recent data from TimescaleDB. Returns None if unavailable."""
    try:
        conn = _get_timescaledb_conn()
        df = pd.read_sql_query(
            f"SELECT * FROM {table} WHERE date >= NOW() - INTERVAL '{days} days' ORDER BY date DESC",
            conn,
        )
        conn.close()
        return df
    except Exception:
        return None


def _write_factors_to_timescaledb(factors: pd.DataFrame, context) -> None:
    """Write factor values to factor_snapshots in long format."""
    try:
        conn = _get_timescaledb_conn()
        cur = conn.cursor()
        from psycopg2.extras import execute_values

        # Melt wide → long
        id_cols = ["ticker", "date"] if "date" in factors.columns else ["ticker"]
        factor_cols = [c for c in factors.columns if c not in id_cols and c != "industry"]
        long = factors.melt(id_vars=id_cols, value_vars=factor_cols,
                            var_name="factor_name", value_name="value")

        if "date" not in long.columns:
            long["date"] = datetime.now().strftime("%Y-%m-%d")

        rows = [(r["ticker"], r["date"], r["factor_name"], r["value"], None)
                for _, r in long.iterrows()]

        sql = """
            INSERT INTO factor_snapshots (ticker, date, factor_name, value, percentile)
            VALUES %s
            ON CONFLICT (ticker, date, factor_name) DO UPDATE SET
                value = EXCLUDED.value,
                percentile = EXCLUDED.percentile,
                computed_at = NOW()
        """
        execute_values(cur, sql, rows)
        conn.commit()
        cur.close()
        conn.close()
        context.log.info(f"Wrote {len(rows)} factor snapshots")
    except Exception as e:
        context.log.warning(f"Factor write failed ({e})")


def _build_report(df: pd.DataFrame) -> str:
    """Build a markdown market summary report."""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        "# 📊 每日市场摘要",
        f"**日期**: {today}",
        f"**覆盖标的**: {df['ticker'].nunique()} 只",
        "",
        "## 最近5日表现",
        "",
        "| Ticker | 最新价 | 5日涨跌% | 20日均价 | 距20MA% |",
        "|--------|--------|----------|----------|---------|",
    ]

    for ticker in sorted(df["ticker"].unique()):
        tdf = df[df["ticker"] == ticker].sort_values("date")
        if len(tdf) < 2:
            continue
        last = tdf.iloc[-1]
        first = tdf.iloc[0]
        chg = (last["close"] - first["close"]) / first["close"] * 100
        ma20 = tdf["close"].rolling(20).mean().iloc[-1] if len(tdf) >= 20 else tdf["close"].mean()
        dist = (last["close"] - ma20) / ma20 * 100
        lines.append(
            f"| {ticker:6s} | {last['close']:8.2f} | {chg:+7.2f}% | "
            f"{ma20:8.2f} | {dist:+7.2f}% |"
        )

    lines.append("")
    lines.append(f"*报告由 Dagster 自动生成 — {datetime.now().isoformat()}*")
    return "\n".join(lines)
