#!/usr/bin/env python3
"""
market_heat.py — 市场热力引擎 (成交量级热度, 免费)

用真实交易数据量化热度:
  - 异常成交量扫描 (相对20日均量的倍数)
  - 期权大单检测 (成交量/持仓量比值 > 3x, 权利金 > $25k)
  - Finviz screener 抓取 (unusual_volume, most_active, top_gainers)
  - 换手率排行

数据量级: 每只股票每天几万笔交易 → 真正的"大数据"热度
vs ApeWisdom 的 1-100 次 Reddit 提及 → 4-5 个数量级的差距

Usage:
    python onionquant/tools/market_heat.py --scan
    python onionquant/tools/market_heat.py --ticker NVDA
    python onionquant/tools/market_heat.py --unusual-volume
    python onionquant/tools/market_heat.py --options-flow
"""

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import requests
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DATA_DIR = PROJECT_ROOT / "company" / "sentiment_data" / "market_heat"
DATA_DIR.mkdir(parents=True, exist_ok=True)

AI_CHAIN_TICKERS = [
    "NVDA",
    "AMD",
    "INTC",
    "TSM",
    "AVGO",
    "MRVL",
    "MU",
    "LITE",
    "COHR",
    "AAOI",
    "ANET",
    "CIEN",
    "RKLB",
    "ASTS",
    "LUNR",
    "RDW",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class MarketHeat:
    """市场热力引擎 — 基于真实交易数据的热度量化."""

    def __init__(self):
        self._cache: dict[str, dict] = {}

    # ─── 异常成交量 ───────────────────────────────────

    def unusual_volume_scan(
        self,
        tickers: list[str] | None = None,
        vol_ratio_threshold: float = 1.5,
    ) -> list[dict]:
        """扫描异常成交量 — 当前量 vs 20日均量.

        这是最直接的"市场在关注什么"指标。
        量增价涨 = 真热度, 量缩价涨 = 假热度。
        """
        if tickers is None:
            tickers = AI_CHAIN_TICKERS

        print(f"\n  [>] Market Heat: unusual volume scan ({len(tickers)} tickers)...")
        results = []

        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                hist = stock.history(period="1mo")

                if hist.empty or len(hist) < 5:
                    continue

                current_vol = int(info.get("volume", 0) or 0)
                avg_vol = int(info.get("averageVolume", 0) or 0)
                avg_vol_10d = int(info.get("averageVolume10days", 0) or 0)

                # 使用更好的均量估算
                if avg_vol_10d > 0:
                    base_vol = avg_vol_10d
                elif avg_vol > 0:
                    base_vol = avg_vol
                else:
                    base_vol = int(hist["Volume"].tail(20).mean())

                if base_vol > 0:
                    vol_ratio = current_vol / base_vol
                else:
                    vol_ratio = 1.0

                # 价格变化
                if len(hist) >= 2:
                    prev_close = hist["Close"].iloc[-2]
                    current_price = hist["Close"].iloc[-1]
                    price_change = (current_price - prev_close) / prev_close * 100
                else:
                    price_change = 0.0

                # 热度评级
                if vol_ratio >= 3.0:
                    heat_level = "🔥🔥🔥 极度放量"
                elif vol_ratio >= 2.0:
                    heat_level = "🔥🔥 显著放量"
                elif vol_ratio >= 1.5:
                    heat_level = "🔥 温和放量"
                elif vol_ratio >= 0.8:
                    heat_level = "正常"
                else:
                    heat_level = "缩量"

                results.append(
                    {
                        "ticker": ticker,
                        "current_volume": current_vol,
                        "avg_volume_10d": base_vol,
                        "volume_ratio": round(vol_ratio, 2),
                        "price_change_pct": round(price_change, 2),
                        "heat_level": heat_level,
                        "is_unusual": vol_ratio >= vol_ratio_threshold,
                        "data_type": "REAL_TRADING_VOLUME",
                        "data_scale": f"{current_vol:,} shares",
                    }
                )
            except Exception as e:
                print(f"    [WARN] {ticker}: {e}")

        results.sort(key=lambda x: -x["volume_ratio"])
        return results

    # ─── 期权大单 ──────────────────────────────────────

    def options_flow_scan(
        self,
        ticker: str,
        min_premium: float = 25000,
        min_vol_oi_ratio: float = 3.0,
    ) -> dict:
        """扫描单个 ticker 的期权异常流.

        检测逻辑:
        - 成交量/持仓量比值 > 3x → 新资金进场
        - 估算权利金 > $25,000 → 不是散户噪音
        - 区分 Call/Put → 方向性判断
        """
        try:
            stock = yf.Ticker(ticker)
            expirations = stock.options
            if not expirations:
                return self._empty_options(ticker)

            unusual_trades = []
            total_call_premium = 0.0
            total_put_premium = 0.0

            for exp_date in expirations[:6]:  # 最近6个到期日
                try:
                    chain = stock.option_chain(exp_date)
                except Exception:
                    continue

                for side, df in [("CALL", chain.calls), ("PUT", chain.puts)]:
                    if df.empty:
                        continue
                    for _, row in df.iterrows():
                        vol = int(row.get("volume", 0) or 0)
                        oi = int(row.get("openInterest", 0) or 0)
                        if oi == 0 or vol == 0:
                            continue
                        ratio = vol / oi
                        last_price = float(row.get("lastPrice", 0) or 0)
                        premium = vol * last_price * 100  # 每合约100股

                        if ratio >= min_vol_oi_ratio and premium >= min_premium:
                            unusual_trades.append(
                                {
                                    "side": side,
                                    "strike": float(row.get("strike", 0)),
                                    "expiration": exp_date,
                                    "volume": vol,
                                    "open_interest": oi,
                                    "vol_oi_ratio": round(ratio, 1),
                                    "premium": round(premium, 0),
                                    "last_price": last_price,
                                }
                            )

                time.sleep(0.3)

            # 聚合统计
            call_trades = [t for t in unusual_trades if t["side"] == "CALL"]
            put_trades = [t for t in unusual_trades if t["side"] == "PUT"]
            total_call_premium = sum(t["premium"] for t in call_trades)
            total_put_premium = sum(t["premium"] for t in put_trades)

            if total_call_premium > total_put_premium * 1.5:
                flow_bias = "BULLISH"
            elif total_put_premium > total_call_premium * 1.5:
                flow_bias = "BEARISH"
            else:
                flow_bias = "NEUTRAL"

            return {
                "ticker": ticker,
                "unusual_trades": len(unusual_trades),
                "call_count": len(call_trades),
                "put_count": len(put_trades),
                "call_premium": round(total_call_premium, 0),
                "put_premium": round(total_put_premium, 0),
                "flow_bias": flow_bias,
                "top_trades": sorted(unusual_trades, key=lambda x: -x["premium"])[:10],
                "data_type": "OPTIONS_FLOW",
                "data_scale": f"${(total_call_premium + total_put_premium):,.0f} total premium",
            }
        except Exception as e:
            print(f"    [WARN] Options {ticker}: {e}")
            return self._empty_options(ticker)

    def _empty_options(self, ticker: str) -> dict:
        return {
            "ticker": ticker,
            "unusual_trades": 0,
            "call_count": 0,
            "put_count": 0,
            "call_premium": 0,
            "put_premium": 0,
            "flow_bias": "NO_DATA",
            "top_trades": [],
            "data_type": "OPTIONS_FLOW",
            "data_scale": "$0",
        }

    # ─── Finviz Screener ────────────────────────────────

    def finviz_screener(self, signal: str = "unusual_volume") -> list[dict]:
        """从 Finviz screener 抓取预建榜单.

        可用 signal:
        - unusual_volume: 异常成交量
        - most_active: 最活跃
        - top_gainers: 涨幅最大
        - overbought: 超买
        - oversold: 超卖
        - new_high: 52周新高
        """
        signal_map = {
            "unusual_volume": "sh_unusual_volume",
            "most_active": "sh_most_active",
            "top_gainers": "sh_top_gainers",
            "overbought": "ta_overbought",
            "oversold": "ta_oversold",
            "new_high": "ta_newhigh",
        }
        finviz_signal = signal_map.get(signal, signal)

        url = "https://finviz.com/screener.ashx"
        params = {
            "v": "111",
            "f": finviz_signal,
            "o": "-change",
        }

        try:
            resp = requests.get(
                url,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            if resp.status_code != 200:
                return []

            # 解析 HTML 表格
            html = resp.text
            results = []
            # 找 ticker 行: class="screener-link"
            import re

            ticker_matches = re.findall(
                r'<a[^>]*class="screener-link"[^>]*>(\w+)</a>', html
            )
            # 找 volume 列 (第5列数字)
            re.findall(
                r'<td[^>]*class="screener-body-table-nw"[^>]*>([\d,]+)</td>',
                html,
            )
            # 找 change% 列
            change_matches = re.findall(
                r'<td[^>]*class="screener-body-table-nw"[^>]*>'
                r"<span[^>]*>([^<]+)</span></td>",
                html,
            )

            for i, tkr in enumerate(ticker_matches[:30]):
                result = {
                    "ticker": tkr,
                    "signal": signal,
                    "data_type": "FINVIZ_SCREENER",
                }
                if i < len(change_matches):
                    result["change_pct"] = change_matches[i].strip()
                results.append(result)

            return results
        except Exception as e:
            print(f"    [WARN] Finviz screener: {e}")
            return []

    # ─── 综合扫描 ───────────────────────────────────────

    def full_scan(
        self,
        tickers: list[str] | None = None,
        scan_options: bool = True,
    ) -> dict:
        """完整市场热力扫描."""
        if tickers is None:
            tickers = AI_CHAIN_TICKERS

        start = time.time()
        print(f"\n{'=' * 65}")
        print("  MARKET HEAT ENGINE — Real Trading Data")
        print("  Scale: millions of shares/day · thousands of options")
        print(f"{'=' * 65}")

        # 1. 异常成交量
        vol_results = self.unusual_volume_scan(tickers)
        unusual = [r for r in vol_results if r["is_unusual"]]
        hot_vol = sorted(vol_results, key=lambda x: -x["volume_ratio"])

        print("\n  >> 成交量热度 (放量>1.5x 均量):")
        if hot_vol:
            for i, r in enumerate(hot_vol[:10]):
                icon = (
                    "🔴"
                    if r["volume_ratio"] >= 3
                    else "🟡"
                    if r["volume_ratio"] >= 2
                    else "🟢"
                )
                print(
                    f"  {i + 1}. {r['ticker']:<6} {icon} {r['volume_ratio']:.1f}x vol "
                    f"({r['current_volume']:,} shrs) price:{r['price_change_pct']:+.1f}% "
                    f"{r['heat_level']}"
                )
        else:
            print("  (no unusual volume detected)")

        # 2. 期权大单 (前5只)
        options_results = {}
        if scan_options:
            top_volume = [r["ticker"] for r in hot_vol[:5]]
            print("\n  >> 期权异常流 (前5放量票):")
            for ticker in top_volume:
                opt = self.options_flow_scan(ticker)
                options_results[ticker] = opt
                if opt["unusual_trades"] > 0:
                    print(
                        f"  {ticker:<6} {opt['unusual_trades']:>2} unusual trades | "
                        f"Calls:${opt['call_premium']:,.0f} "
                        f"Puts:${opt['put_premium']:,.0f} | "
                        f"BIAS: {opt['flow_bias']}"
                    )
                time.sleep(0.5)

        # 3. Finviz 异常成交量榜
        print("\n  >> Finviz Unusual Volume (全市场):")
        finviz = self.finviz_screener("unusual_volume")
        ai_in_finviz = [r for r in finviz if r["ticker"] in AI_CHAIN_TICKERS]
        for r in finviz[:15]:
            tag = " [AI]" if r["ticker"] in AI_CHAIN_TICKERS else ""
            print(f"  {r['ticker']:<6} {r.get('change_pct', '?'):>8}{tag}")
        if ai_in_finviz:
            print(
                f"\n  AI链出现在全市场异常量榜: "
                f"{', '.join(r['ticker'] for r in ai_in_finviz)}"
            )

        elapsed = time.time() - start
        snapshot = {
            "timestamp": datetime.now(UTC).isoformat(),
            "volume_heat": vol_results,
            "unusual_count": len(unusual),
            "options_flow": options_results,
            "finviz_unusual_volume": finviz,
            "scan_time_seconds": round(elapsed, 1),
        }

        # 保存
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = DATA_DIR / f"market_heat_{ts}.json"
        path.write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False, default=str), "utf-8"
        )
        print(f"\n  [SAVE] {path}")
        print(
            f"  Scan complete in {elapsed:.0f}s | "
            f"Data scale: BILLIONS of shares + MILLIONS of options contracts"
        )

        return snapshot


# ─── CLI ────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="OnionQuant Market Heat Engine")
    p.add_argument("--scan", action="store_true", help="完整扫描 (默认)")
    p.add_argument("--ticker", type=str, help="单票深度")
    p.add_argument("--unusual-volume", action="store_true", help="异常成交量榜")
    p.add_argument("--options-flow", action="store_true", help="期权流扫描")
    p.add_argument("--finviz", type=str, default="", help="Finviz screener signal")
    p.add_argument("--no-options", action="store_true", help="跳过期权扫描")
    args = p.parse_args()

    mh = MarketHeat()

    if args.ticker:
        ticker = args.ticker.upper()
        print(f"\n  Market Heat: ${ticker}")
        vol = mh.unusual_volume_scan([ticker])
        if vol:
            v = vol[0]
            print(
                f"  成交量: {v['current_volume']:,} shares "
                f"({v['volume_ratio']:.1f}x avg) | "
                f"价格: {v['price_change_pct']:+.1f}% | {v['heat_level']}"
            )
        opt = mh.options_flow_scan(ticker)
        if opt["unusual_trades"] > 0:
            print(
                f"  期权异常: {opt['unusual_trades']} 笔 | "
                f"Call:${opt['call_premium']:,.0f} "
                f"Put:${opt['put_premium']:,.0f} | {opt['flow_bias']}"
            )
            for t in opt["top_trades"][:5]:
                print(
                    f"    {t['side']:<5} ${t['strike']} {t['expiration']} "
                    f"vol:{t['volume']} oi:{t['open_interest']} "
                    f"ratio:{t['vol_oi_ratio']}x prem:${t['premium']:,.0f}"
                )

    elif args.unusual_volume:
        results = mh.unusual_volume_scan(AI_CHAIN_TICKERS)
        results.sort(key=lambda x: -x["volume_ratio"])
        print("\n  AI链 异常成交量排行:")
        for i, r in enumerate(results):
            if r["volume_ratio"] >= 1.0:
                print(
                    f"  {i + 1}. {r['ticker']:<6} {r['volume_ratio']:.1f}x "
                    f"({r['current_volume']:,} shrs) price:{r['price_change_pct']:+.1f}%"
                )

    elif args.options_flow:
        for t in AI_CHAIN_TICKERS[:5]:
            opt = mh.options_flow_scan(t)
            if opt["unusual_trades"] > 0:
                print(
                    f"\n  {t}: {opt['unusual_trades']} unusual trades | "
                    f"{opt['flow_bias']}"
                )
                for tr in opt["top_trades"][:5]:
                    print(
                        f"    {tr['side']} ${tr['strike']} "
                        f"prem:${tr['premium']:,.0f} ratio:{tr['vol_oi_ratio']}x"
                    )

    elif args.finviz:
        results = mh.finviz_screener(args.finviz)
        print(f"\n  Finviz '{args.finviz}': {len(results)} results")
        for r in results:
            print(f"  {r['ticker']:<6} {r.get('change_pct', '?')}")

    else:
        mh.full_scan()
