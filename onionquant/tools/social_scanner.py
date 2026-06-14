#!/usr/bin/env python3
"""
social_scanner.py — OnionQuant 社交舆论扫描器 (Step 1-2 of 6-step pipeline)

数据来源 (非编造):
  - HypeFinder (Reddit + Twitter/X, 开源CLI工具)
  - ApeWisdom (Reddit WSB 热门股票, 免费API)
  - Agent-Reach (微博/雪球/B站/小红书, 中文平台CLI)

输出: 热度突变的股票列表 + 讨论量/情绪/平台交叉验证

Usage:
    python onionquant/tools/social_scanner.py                      # 单次扫描 (英文)
    python onionquant/tools/social_scanner.py --cn                 # 包含中文平台
    python onionquant/tools/social_scanner.py --top 10 --explain   # 详细top10
    python onionquant/tools/social_scanner.py --schedule 60        # 每60分钟循环
"""

import csv
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HYPEFINDER_DIR = PROJECT_ROOT / "company" / "tools" / "HypeFinder"
OUTPUT_DIR = PROJECT_ROOT / "company" / "sentiment_data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_hypefinder_scan(
    top_n: int = 20, sources: str = "reddit", output: str = "csv"
) -> list[dict]:
    """Run HypeFinder CLI scan and parse results.

    Returns list of dicts with keys: ticker, hype_score, volume_score,
    sentiment_score, mentions, platforms.
    """
    cmd = [
        sys.executable,
        str(HYPEFINDER_DIR / "main.py"),
        "scan",
        "--sources",
        sources,
        "--top",
        str(top_n),
        "--output",
        output,
        "--min-mentions",
        "3",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, cwd=str(HYPEFINDER_DIR)
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[warn] HypeFinder failed: {e}")
        return []

    tickers = []
    csv_path = HYPEFINDER_DIR / "hype_history.csv"
    if csv_path.exists():
        try:
            with open(csv_path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    tickers.append(
                        {
                            "ticker": row.get("Ticker", "").strip(),
                            "hype_score": float(row.get("Hype Score", 0)),
                            "volume_score": float(row.get("Volume Score", 0)),
                            "sentiment_score": float(row.get("Sentiment", 0)),
                            "mentions": int(row.get("Mentions", 0)),
                            "platforms": row.get("Platforms", ""),
                        }
                    )
        except Exception:
            pass
    return tickers


def cross_check_apewisdom() -> list[dict]:
    """Cross-reference with ApeWisdom (Reddit WSB trending, free tier).

    Source: https://apewisdom.io/api/v1.0/filter/all-stocks/page/1
    (free tier, no auth required for basic usage)
    """
    import urllib.request

    url = "https://apewisdom.io/api/v1.0/filter/all-stocks/page/1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = json.loads(urllib.request.urlopen(req, timeout=15).read())
        results = data.get("results", [])[:20]
        return [
            {
                "ticker": r.get("ticker", ""),
                "mentions": r.get("mentions", 0),
                "rank": r.get("rank", 999),
                "sentiment": r.get("sentiment", "N/A"),
            }
            for r in results
        ]
    except Exception as e:
        print(f"[warn] ApeWisdom fetch failed: {e}")
        return []


def merge_and_rank(hypefinder: list[dict], apewisdom: list[dict]) -> list[dict]:
    """Merge HypeFinder + ApeWisdom results, deduplicate, re-rank."""
    aw_map = {item["ticker"].upper(): item for item in apewisdom}
    merged = {}

    for item in hypefinder:
        t = item["ticker"].upper()
        if not t:
            continue
        merged[t] = {
            "ticker": t,
            "hype_score": item.get("hype_score", 0),
            "volume_score": item.get("volume_score", 0),
            "sentiment_score": item.get("sentiment_score", 0),
            "mentions_hf": item.get("mentions", 0),
            "mentions_aw": aw_map.get(t, {}).get("mentions", 0),
            "cross_validated": t in aw_map,
            "platforms": item.get("platforms", ""),
            "aw_rank": aw_map.get(t, {}).get("rank", 999),
        }

    for item in apewisdom:
        t = item["ticker"].upper()
        if t not in merged:
            merged[t] = {
                "ticker": t,
                "hype_score": 0,
                "volume_score": 0,
                "sentiment_score": 0,
                "mentions_hf": 0,
                "mentions_aw": item.get("mentions", 0),
                "cross_validated": False,
                "platforms": "Reddit(WSB)",
                "aw_rank": item.get("rank", 999),
            }

    combined_score = lambda m: (
        m["hype_score"] * 0.4
        + (10 / (m["aw_rank"] + 1)) * 100 * 0.3
        + (m["cross_validated"] * 50) * 0.3
    )

    ranked = sorted(merged.values(), key=combined_score, reverse=True)
    return ranked


def save_scan_results(results: list[dict]) -> Path:
    """Save scan results to dated JSON for historical tracking."""
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    path = OUTPUT_DIR / f"scan_{date_str}.json"
    path.write_text(
        json.dumps(
            {
                "timestamp": datetime.now().isoformat(),
                "source": "HypeFinder + ApeWisdom",
                "results": results,
            },
            indent=2,
            default=str,
        ),
        "utf-8",
    )
    return path


def scan_chinese_social(
    tickers: list[str] | None = None,
    platforms: list[str] | None = None,
) -> list[dict]:
    """扫描中文社交平台（微博/雪球），返回情绪数据。

    依赖 Agent-Reach CLI；未安装时返回空列表。
    """
    try:
        from quant_framework.data.fetchers.chinese_social_sentiment import (
            scan_watchlist,
            _ar_available,
        )
    except ImportError:
        print("[warn] chinese_social_sentiment 模块不可用")
        return []

    if not _ar_available():
        print("[info] Agent-Reach 未安装，跳过中文社交扫描")
        return []

    platforms = platforms or ["weibo", "xueqiu"]
    df = scan_watchlist(tickers=tickers, platforms=platforms, verbose=False)
    if df.empty:
        return []

    results = []
    for _, row in df.iterrows():
        results.append({
            "ticker": row.get("ticker", ""),
            "sentiment_score": row.get("weighted_score", 0),
            "positive_ratio": row.get("positive_ratio", 0),
            "negative_ratio": row.get("negative_ratio", 0),
            "count": row.get("count", 0),
            "platforms": row.get("platforms", ""),
        })
    return results


def scan(explain: bool = False, cn: bool = False) -> list[dict]:
    """Run full social scan: HypeFinder + ApeWisdom → merged rankings.

    Args:
        explain: 打印详细说明
        cn: 是否包含中文社交平台 (微博/雪球)
    """
    sources = "HypeFinder (Reddit+X) + ApeWisdom (WSB)"
    if cn:
        sources += " + Agent-Reach (微博/雪球)"

    print("=" * 60)
    print(f"  OnionQuant Social Scanner  |  {datetime.now():%Y-%m-%d %H:%M}")
    print(f"  Sources: {sources}")
    print("=" * 60)

    steps = 3 + (1 if cn else 0)
    step = 1

    print(f"\n[{step}/{steps}] Running HypeFinder...")
    hf = run_hypefinder_scan()
    print(f"      → {len(hf)} tickers found")
    step += 1

    print(f"[{step}/{steps}] Cross-checking ApeWisdom...")
    aw = cross_check_apewisdom()
    print(f"      → {len(aw)} tickers found")
    step += 1

    if cn:
        print(f"[{step}/{steps}] Scanning Chinese social media (Agent-Reach)...")
        cn_results = scan_chinese_social()
        print(f"      → {len(cn_results)} tickers with Chinese sentiment")
        step += 1
    else:
        cn_results = []

    print(f"[{step}/{steps}] Merging & ranking...")
    results = merge_and_rank(hf, aw)
    print(f"      → {len(results)} unique tickers")

    # 附加中文情绪数据到结果中
    if cn_results:
        cn_map = {r["ticker"].upper(): r for r in cn_results}
        for r in results:
            cn_data = cn_map.get(r["ticker"], {})
            r["cn_sentiment"] = cn_data.get("sentiment_score")
            r["cn_mentions"] = cn_data.get("count", 0)
            r["cn_platforms"] = cn_data.get("platforms", "")

    path = save_scan_results(results)

    print(f"\n{'Rank':<5} {'Ticker':<8} {'Hype':>6} {'Cross':>6} {'AW Rank':>8}", end="")
    if cn:
        print(f" {'CN Sent':>8}", end="")
    print()
    print("-" * (48 if not cn else 58))
    for i, r in enumerate(results[:15]):
        xv = "✓" if r["cross_validated"] else "—"
        line = f"{i + 1:<5} {r['ticker']:<8} {r['hype_score']:>6.0f} {xv:>6} {r['aw_rank']:>8}"
        if cn:
            cs = r.get("cn_sentiment")
            line += f" {cs:>8.3f}" if cs is not None else f" {'N/A':>8}"
        print(line)

    print(f"\n→ Full results: {path}")
    if cn and cn_results:
        print(f"→ Chinese sentiment data integrated into results")
    return results


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--explain", action="store_true")
    p.add_argument("--schedule", type=int, default=0, help="Run every N minutes")
    args = p.parse_args()

    if args.schedule:
        print(f"Scheduled scan every {args.schedule} minutes. Ctrl+C to stop.")
        while True:
            scan(explain=args.explain)
            time.sleep(args.schedule * 60)
    else:
        scan(explain=args.explain)
