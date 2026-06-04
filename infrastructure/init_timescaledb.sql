-- init_timescaledb.sql — TimescaleDB 初始化
-- 创建 Hypertable 用于市场行情数据存储

-- 启用 TimescaleDB 扩展
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ── 美股日线行情表 ──
CREATE TABLE IF NOT EXISTS us_stocks_daily (
    ticker      VARCHAR(10)     NOT NULL,
    date        DATE            NOT NULL,
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    volume      BIGINT,
    adj_close   DOUBLE PRECISION,
    source      VARCHAR(20)     DEFAULT 'openbb',  -- openbb / yfinance / polygon
    ingested_at TIMESTAMPTZ     DEFAULT NOW(),
    PRIMARY KEY (ticker, date)
);

-- 转换为 Hypertable (TimescaleDB 核心 — 按日期自动分区)
SELECT create_hypertable('us_stocks_daily', 'date', if_not_exists => TRUE);

-- 创建常用索引
CREATE INDEX IF NOT EXISTS idx_us_daily_ticker ON us_stocks_daily (ticker);
CREATE INDEX IF NOT EXISTS idx_us_daily_date   ON us_stocks_daily (date DESC);

-- ── 美股分钟线行情表 ──
CREATE TABLE IF NOT EXISTS us_stocks_minute (
    ticker      VARCHAR(10)     NOT NULL,
    datetime    TIMESTAMPTZ     NOT NULL,
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    volume      BIGINT,
    source      VARCHAR(20)     DEFAULT 'openbb',
    ingested_at TIMESTAMPTZ     DEFAULT NOW(),
    PRIMARY KEY (ticker, datetime)
);

SELECT create_hypertable('us_stocks_minute', 'datetime',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE);

-- ── 因子快照表 ──
CREATE TABLE IF NOT EXISTS factor_snapshots (
    ticker      VARCHAR(10)     NOT NULL,
    date        DATE            NOT NULL,
    factor_name VARCHAR(50)     NOT NULL,
    value       DOUBLE PRECISION,
    percentile  DOUBLE PRECISION,
    computed_at TIMESTAMPTZ     DEFAULT NOW(),
    PRIMARY KEY (ticker, date, factor_name)
);

SELECT create_hypertable('factor_snapshots', 'date', if_not_exists => TRUE);

-- ── 回测结果表 ──
CREATE TABLE IF NOT EXISTS backtest_results (
    run_id      VARCHAR(64)     PRIMARY KEY,
    strategy    VARCHAR(50)     NOT NULL,
    start_date  DATE,
    end_date    DATE,
    sharpe      DOUBLE PRECISION,
    max_dd      DOUBLE PRECISION,
    annual_ret  DOUBLE PRECISION,
    win_rate    DOUBLE PRECISION,
    params      JSONB,
    created_at  TIMESTAMPTZ     DEFAULT NOW()
);

-- ── 数据质量日志 ──
CREATE TABLE IF NOT EXISTS data_quality_log (
    check_id    SERIAL          PRIMARY KEY,
    table_name  VARCHAR(50),
    check_name  VARCHAR(100),
    passed      BOOLEAN,
    details     JSONB,
    checked_at  TIMESTAMPTZ     DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_quality_table ON data_quality_log (table_name);
CREATE INDEX IF NOT EXISTS idx_quality_time   ON data_quality_log (checked_at DESC);
