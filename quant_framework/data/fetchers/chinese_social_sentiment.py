"""中文社交平台舆情抓取 — Agent-Reach CLI 封装 → 情绪评分 → Parquet

支持平台: Weibo (微博), Xueqiu (雪球), Bilibili (B站), Xiaohongshu (小红书)

Agent-Reach (github.com/Panniantong/Agent-Reach) 是零 API 费用的中文平台
CLI 搜索工具。本模块封装其 CLI 调用，输出标准化情绪数据。

未安装 Agent-Reach 时回退到关键词占位数据（标记 source="fallback"）。
"""

import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from quant_framework.data.fetchers.sentiment_utils import (
    batch_score,
    aggregate_sentiments,
    has_chinese,
    score_chinese_text,
)

logger = logging.getLogger(__name__)
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "raw", "sentiment")

AGENT_REACH_BIN = shutil.which("agent-reach")

# Agent-Reach 支持的平台 → CLI 命令映射
PLATFORM_SEARCH = {
    "weibo": {
        "cmd": ["agent-reach", "search", "weibo"],
        "desc": "微博热搜/内容搜索",
        "cookie_needed": False,
    },
    "xueqiu": {
        "cmd": ["agent-reach", "search", "xueqiu"],
        "desc": "雪球股票讨论",
        "cookie_needed": True,
    },
    "bilibili": {
        "cmd": ["agent-reach", "search", "bilibili"],
        "desc": "B站视频搜索",
        "cookie_needed": False,
    },
    "xiaohongshu": {
        "cmd": ["agent-reach", "search", "xiaohongshu"],
        "desc": "小红书笔记搜索",
        "cookie_needed": True,
    },
}

# 默认搜索关键词映射（股票代码 → 中文平台常用搜索词）
DEFAULT_KEYWORDS = {
    "DXYZ": ["DXYZ SpaceX", "Starship 概念股", "SpaceX IPO"],
    "NVDA": ["英伟达", "NVIDIA", "AI芯片", "GPU"],
    "TSLA": ["特斯拉", "新能源", "电动车"],
    "AAPL": ["苹果", "iPhone", "果链"],
    "INTC": ["英特尔", "Intel", "芯片制造"],
    "MU": ["美光科技", "存储芯片", "HBM"],
    "WDC": ["西部数据", "存储硬盘"],
    "COHR": ["相干公司", "光模块", "CPO"],
    "LITE": ["Lumentum", "光通信"],
    "AVGO": ["博通", "ASIC", "定制芯片"],
    "RKLB": ["火箭实验室", "商业航天", "小型火箭"],
    "ASTS": ["AST SpaceMobile", "卫星通信", "太空互联网"],
    "LUNR": ["直觉机器", "月球着陆", "太空探索"],
    "RDW": ["红线太空", "太空制造"],
}


def _ar_available() -> bool:
    """检测 Agent-Reach CLI 是否可用。"""
    if AGENT_REACH_BIN:
        return True
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "show", "agent-reach"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
        return True
    except Exception:
        return False


def _run_ar_search(
    platform: str, query: str, max_results: int = 20, timeout: int = 60
) -> list[dict]:
    """调用 Agent-Reach CLI 搜索指定平台。

    Returns:
        list[dict]: 每项含 text, url, platform, timestamp
    """
    if not _ar_available():
        logger.debug("Agent-Reach 未安装，返回空结果")
        return []

    cfg = PLATFORM_SEARCH.get(platform)
    if not cfg:
        logger.warning("未知平台: %s", platform)
        return []

    cmd = cfg["cmd"] + [query, "--max-results", str(max_results), "--format", "json"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        if result.returncode != 0:
            logger.warning("Agent-Reach %s 搜索失败 (rc=%d): %s",
                           platform, result.returncode, result.stderr[:120])
            return []
        data = json.loads(result.stdout)
        items = data if isinstance(data, list) else data.get("results", [])
        return [
            {
                "text": item.get("title", item.get("text", item.get("content", ""))),
                "url": item.get("url", ""),
                "platform": platform,
                "timestamp": item.get("timestamp", datetime.now(timezone.utc).isoformat()),
            }
            for item in items
        ]
    except subprocess.TimeoutExpired:
        logger.warning("Agent-Reach %s 搜索超时 (query=%s)", platform, query)
        return []
    except json.JSONDecodeError:
        logger.warning("Agent-Reach %s JSON 解析失败", platform)
        return []
    except Exception as exc:
        logger.warning("Agent-Reach %s 异常: %s", platform, exc)
        return []


def fetch_platform_sentiment(
    ticker: str,
    platforms: Optional[list[str]] = None,
    max_per_query: int = 20,
    timeout: int = 90,
) -> pd.DataFrame:
    """抓取指定股票在中文社交平台上的舆情数据。

    Args:
        ticker: 股票代码 (如 DXYZ, NVDA, TSLA)
        platforms: 平台列表，默认 ["weibo", "xueqiu"]
        max_per_query: 每个查询的最大结果数
        timeout: 单次 CLI 调用超时秒数

    Returns:
        DataFrame，列: ticker, text, platform, url, positive, negative, neutral, timestamp
    """
    platforms = platforms or ["weibo", "xueqiu"]
    keywords = DEFAULT_KEYWORDS.get(ticker.upper(), [ticker])
    records = []

    for platform in platforms:
        for kw in keywords[:3]:  # 每个 ticker 最多搜 3 个关键词
            items = _run_ar_search(platform, kw, max_results=max_per_query, timeout=timeout)
            for item in items:
                scores = score_chinese_text(item["text"])
                records.append({
                    "ticker": ticker.upper(),
                    "text": item["text"],
                    "platform": item["platform"],
                    "url": item["url"],
                    "positive": scores["positive"],
                    "negative": scores["negative"],
                    "neutral": scores["neutral"],
                    "timestamp": item.get("timestamp", datetime.now(timezone.utc).isoformat()),
                })

    if not records and not _ar_available():
        logger.info("Agent-Reach 未安装，返回 fallback 数据 (ticker=%s)", ticker)
        return _fallback_data(ticker)

    return pd.DataFrame(records) if records else _fallback_data(ticker)


def _fallback_data(ticker: str) -> pd.DataFrame:
    """Agent-Reach 不可用时的占位数据。"""
    from quant_framework.data.fetchers.sentiment_utils import score_text

    fallback_texts = {
        "DXYZ": ["Destiny XYZ 太空概念股引热议", "Starship 概念股投资价值分析", "DXYZ SpaceX 关联公司讨论"],
        "NVDA": ["英伟达股价再创新高", "NVIDIA AI芯片需求旺盛", "GPU供不应求英伟达受益"],
        "TSLA": ["特斯拉交付量超预期", "新能源车市场竞争白热化", "FSD自动驾驶最新进展"],
    }
    texts = fallback_texts.get(ticker, [f"{ticker} 股票行情分析", f"{ticker} 最新消息讨论"])
    records = []
    for t in texts:
        scores = score_chinese_text(t)
        records.append({
            "ticker": ticker,
            "text": t,
            "platform": "fallback",
            "url": "",
            "positive": scores["positive"],
            "negative": scores["negative"],
            "neutral": scores["neutral"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    return pd.DataFrame(records)


def build_daily_index(
    df: pd.DataFrame, ticker: str, window_hours: int = 24
) -> pd.DataFrame:
    """将原始数据聚合成单日情绪指标（兼容现有 sentiment pipeline）。"""
    if df.empty:
        return pd.DataFrame([{
            "ticker": ticker,
            "positive_ratio": 0,
            "negative_ratio": 0,
            "neutral_ratio": 0,
            "weighted_score": 0.0,
            "count": 0,
            "date": pd.to_datetime(datetime.now(timezone.utc).date()),
        }])

    scores = df[["positive", "negative", "neutral"]].to_dict("records")
    agg = aggregate_sentiments(scores)
    agg["ticker"] = ticker
    agg["date"] = pd.to_datetime(datetime.now(timezone.utc).date())
    agg["platforms"] = ",".join(df["platform"].unique())
    return pd.DataFrame([agg])


def save_parquet(df: pd.DataFrame, name: str):
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, f"{name}_{datetime.now().strftime('%Y%m%d')}.parquet")
    df.to_parquet(path, index=False)
    logger.info("Written %s (%d rows)", path, len(df))


def scan_watchlist(
    tickers: Optional[list[str]] = None,
    platforms: Optional[list[str]] = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """批量扫描监控列表的中文舆情。

    Args:
        tickers: 股票列表，默认使用 DEFAULT_KEYWORDS 中定义的关键股票
        platforms: 平台列表，默认 ["weibo", "xueqiu"]
        verbose: 是否打印进度

    Returns:
        DataFrame: 每个 ticker 的情绪聚合指标
    """
    tickers = tickers or list(DEFAULT_KEYWORDS.keys())
    platforms = platforms or ["weibo", "xueqiu"]
    all_daily = []

    for ticker in tickers:
        if verbose:
            logger.info("扫描 %s 中文舆情...", ticker)
        raw = fetch_platform_sentiment(ticker, platforms=platforms)
        daily = build_daily_index(raw, ticker)
        all_daily.append(daily)

    combined = pd.concat(all_daily, ignore_index=True) if all_daily else pd.DataFrame()
    if not combined.empty:
        combined = combined.sort_values("weighted_score", ascending=False)
    return combined


def main():
    import argparse

    parser = argparse.ArgumentParser(description="中文社交平台舆情抓取 (Agent-Reach)")
    parser.add_argument("--tickers", nargs="+", help="股票代码列表")
    parser.add_argument("--platforms", nargs="+", default=["weibo", "xueqiu"],
                        choices=["weibo", "xueqiu", "bilibili", "xiaohongshu"])
    parser.add_argument("--output", default="chinese_social_sentiment")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not _ar_available():
        logger.warning("Agent-Reach CLI 未安装，使用 fallback 数据")
        logger.info("安装方法: pip install https://github.com/Panniantong/agent-reach/archive/main.zip")
        logger.info("然后: agent-reach install --env=auto && agent-reach doctor")

    tickers = args.tickers or list(DEFAULT_KEYWORDS.keys())
    result = scan_watchlist(tickers, platforms=args.platforms, verbose=True)

    if not result.empty:
        save_parquet(result, args.output)
        print(result.to_string(index=False))
    else:
        logger.warning("无结果产出")

    return 0


if __name__ == "__main__":
    sys.exit(main())
