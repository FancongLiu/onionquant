#!/usr/bin/env python
"""
Token 审计 CLI — AI 自治理工具 (self-audit, not a chairman-facing panel)

用途: AI 自己跑 `python scripts/token_audit.py` 对账日志 logs/token_usage.jsonl，
      按 CLAUDE.md 策略(日耗 ¥8 上限 / 缓存命中 98% 目标 / headroom)自我检查。
      不挂 dashboard、不加 cron、不推微信。

口径说明 (重要):
  - 计费基线 = 代码实测的 DeepSeek API 口径 (DEEPSEEK_INPUT_PRICE / OUTPUT_PRICE /
    CACHE_HIT_INPUT_PRICE，见 inbox_processor.py 常量)。jsonl 里每条已有 cost_est，
    审计直接累加 cost_est，不重算，避免和写日志时的口径漂移。
  - CLAUDE.md 的 ¥5-8/天 & 120:1 价差 & 98-99% 命中是 *目标值*，审计用它作对照基准，
    报告里会标注"目标 vs 实测"。若两者不符，是 CLAUDE.md 口径与实测环境之差，非 bug。

数据来源: logs/token_usage.jsonl，每行一条 {_log_token_usage 写入}。
  字段: ts, source, input_tokens, output_tokens, cost_est, message_id,
        headroom?{used,free,headroom_pct,low_headroom},
        cache_hit_tokens?, cache_miss_tokens?

用法:
  python scripts/token_audit.py              # 默认: 近 24h 终端报告
  python scripts/token_audit.py --hours 72   # 指定窗口
  python scripts/token_audit.py --daily      # 按北京时间分日聚合
  python scripts/token_audit.py --json       # 机器可读 (供未来路由复用, 当前无消费者)
  退出码: 0=正常, 2=超预算或缓存命中率低于阈值 (便于脚本判定)

纯 stdlib 实现，零外部依赖，零 AI token。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── 常量 (与 inbox_processor.py 保持一致，但在此独立定义以免 import 整个 harness) ──
# 注: 若 inbox_processor.py 常量改了，这里要同步。刻意不 import 是为了审计脚本零依赖、
#     能在 harness 未初始化的纯 CLI 环境跑(例如 cron 容器、CI)。
DAILY_BUDGET_YUAN = 8.0        # CLAUDE.md 日耗目标上限 (aspirational)
CACHE_HIT_TARGET = 0.98        # CLAUDE.md 缓存命中目标 (aspirational)
CACHE_HIT_FLOOR = 0.90         # 命中率低于此值视为异常 (审计告警阈值)
SINGLE_CALL_COST_ALERT = 0.5   # 单条调用成本 ¥ 超此值标红 (约 ¥8 预算的 6%)

BEIJING_TZ = timezone(timedelta(hours=8))  # Asia/Shanghai

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOKEN_LOG = PROJECT_ROOT / "logs" / "token_usage.jsonl"


# ── 数据加载 ──────────────────────────────────────────────────────

def load_records(hours: int = 24) -> list[dict]:
    """解析 token_usage.jsonl，返回时间窗内的记录列表。hours=0 表示全部。"""
    if not TOKEN_LOG.exists():
        return []
    cutoff = datetime.now(BEIJING_TZ) - timedelta(hours=hours) if hours > 0 else None
    records: list[dict] = []
    for line in TOKEN_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if cutoff:
            try:
                ts = datetime.fromisoformat(rec["ts"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    continue
            except (KeyError, ValueError):
                pass  # 解析失败的 ts 不按时间过滤，保留(异常时审计能看到)
        records.append(rec)
    return records


# ── 审计维度 ──────────────────────────────────────────────────────

def audit_totals(records: list[dict]) -> dict:
    """总量汇总: 调用次数、input/output tokens、总成本、按 source 分布。"""
    if not records:
        return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0,
                "by_source": {}, "window_hours": 0}
    by_source: dict[str, dict] = {}
    total_in = total_out = 0
    total_cost = 0.0
    for r in records:
        src = r.get("source", "unknown")
        s = by_source.setdefault(src, {"calls": 0, "input": 0, "output": 0, "cost": 0.0})
        s["calls"] += 1
        s["input"] += r.get("input_tokens", 0)
        s["output"] += r.get("output_tokens", 0)
        s["cost"] += r.get("cost_est", 0.0)
        total_in += r.get("input_tokens", 0)
        total_out += r.get("output_tokens", 0)
        total_cost += r.get("cost_est", 0.0)
    return {"calls": len(records), "input_tokens": total_in,
            "output_tokens": total_out, "cost": round(total_cost, 6),
            "by_source": by_source}


def audit_cache_hit(records: list[dict]) -> dict:
    """缓存命中审计。仅统计报告了 cache_hit_tokens 的记录 (即 source=deepseek)。

    命中率 = Σcache_hit_tokens / Σinput_tokens (仅对有缓存维度的记录)。
    无缓存维度的记录(claude_code 子进程)不计入分母,避免拉低命中率造成误判。
    """
    with_cache = [r for r in records
                  if r.get("cache_hit_tokens") is not None
                  or r.get("cache_miss_tokens") is not None]
    if not with_cache:
        return {"has_cache_data": False, "hit_rate": None,
                "total_hit": 0, "total_miss": 0, "records_with_cache": 0,
                "note": "无缓存命中维度数据(可能全为 claude_code 子进程调用,不返回 usage)"}
    total_hit = sum(r.get("cache_hit_tokens", 0) or 0 for r in with_cache)
    total_miss = sum(r.get("cache_miss_tokens", 0) or 0 for r in with_cache)
    total_in = total_hit + total_miss
    hit_rate = (total_hit / total_in) if total_in > 0 else 0.0
    return {"has_cache_data": True, "hit_rate": round(hit_rate, 4),
            "total_hit": total_hit, "total_miss": total_miss,
            "records_with_cache": len(with_cache)}


def audit_daily_budget(records: list[dict]) -> dict:
    """按北京时间分日聚合成本,对照 ¥8/天 上限。"""
    by_day: dict[str, dict] = {}
    for r in records:
        try:
            ts = datetime.fromisoformat(r["ts"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc).astimezone(BEIJING_TZ)
            else:
                ts = ts.astimezone(BEIJING_TZ)
            day = ts.strftime("%Y-%m-%d")
        except (KeyError, ValueError):
            day = "unknown"
        d = by_day.setdefault(day, {"cost": 0.0, "calls": 0})
        d["cost"] += r.get("cost_est", 0.0)
        d["calls"] += 1
    for d in by_day.values():
        d["cost"] = round(d["cost"], 6)
        d["over_budget"] = d["cost"] > DAILY_BUDGET_YUAN
    return {"daily": by_day, "budget_yuan": DAILY_BUDGET_YUAN}


def audit_headroom(records: list[dict]) -> dict:
    """Context window headroom 审计: low_headroom 触发次数与比例。"""
    with_hr = [r for r in records if r.get("headroom")]
    if not with_hr:
        return {"has_headroom_data": False, "low_headroom_count": 0, "low_headroom_pct": 0.0}
    low = sum(1 for r in with_hr if r["headroom"].get("low_headroom"))
    pcts = [r["headroom"].get("headroom_pct", 1.0) for r in with_hr]
    avg_pct = sum(pcts) / len(pcts) if pcts else 0.0
    return {"has_headroom_data": True, "low_headroom_count": low,
            "total_with_headroom": len(with_hr),
            "low_headroom_pct": round(low / len(with_hr), 4),
            "avg_headroom_pct": round(avg_pct, 4)}


def audit_anomalies(records: list[dict]) -> list[dict]:
    """单条异常: 超高单次成本。返回异常记录摘要列表。"""
    anomalies = []
    for r in records:
        cost = r.get("cost_est", 0.0)
        if cost > SINGLE_CALL_COST_ALERT:
            anomalies.append({
                "ts": r.get("ts"), "source": r.get("source"),
                "cost": round(cost, 6), "message_id": r.get("message_id", ""),
                "reason": f"单次成本 ¥{cost:.4f} 超阈值 ¥{SINGLE_CALL_COST_ALERT}",
            })
    return anomalies


def run_audit(hours: int = 24) -> dict:
    """跑全维度审计,返回结构化结果。"""
    records = load_records(hours=hours)
    totals = audit_totals(records)
    totals["window_hours"] = hours if hours > 0 else "all"
    cache = audit_cache_hit(records)
    daily = audit_daily_budget(records)
    headroom = audit_headroom(records)
    anomalies = audit_anomalies(records)
    # 健康判定
    budget_ok = all(not d["over_budget"] for d in daily["daily"].values())
    cache_ok = (not cache["has_cache_data"]) or (cache["hit_rate"] >= CACHE_HIT_FLOOR)
    healthy = bool(records) and budget_ok and cache_ok and not anomalies
    return {
        "healthy": healthy,
        "record_count": len(records),
        "totals": totals,
        "cache_hit": cache,
        "daily_budget": daily,
        "headroom": headroom,
        "anomalies": anomalies,
    }


# ── 渲染 ──────────────────────────────────────────────────────────

def _fmt_yuan(v: float) -> str:
    return f"¥{v:.4f}" if v < 1 else f"¥{v:.2f}"


def render_markdown(audit: dict) -> str:
    """终端/Markdown 友好的审计报告。AI 自查读这个。"""
    lines = []
    t = audit["totals"]
    lines.append("# Token 审计报告 (AI self-audit)")
    lines.append(f"窗口: 近 {t['window_hours']} 小时 | 记录数: {audit['record_count']}")
    lines.append(f"健康度: {'✅ 正常' if audit['healthy'] else '⚠️ 有异常'}")
    lines.append("")
    lines.append("## 总量")
    lines.append(f"- 调用次数: {t['calls']}")
    lines.append(f"- input tokens: {t['input_tokens']:,} | output tokens: {t['output_tokens']:,}")
    lines.append(f"- 总成本: {_fmt_yuan(t['cost'])}")
    if t["by_source"]:
        lines.append("- 按 source:")
        for src, s in t["by_source"].items():
            lines.append(f"  - {src}: {s['calls']}次, in {s['input']:,} / out {s['output']:,}, {_fmt_yuan(s['cost'])}")
    lines.append("")
    lines.append("## 缓存命中 (对照目标 98%)")
    c = audit["cache_hit"]
    if c["has_cache_data"]:
        rate = c["hit_rate"] * 100
        flag = "✅" if rate >= CACHE_HIT_FLOOR * 100 else "⚠️"
        lines.append(f"- {flag} 命中率: {rate:.2f}% (命中 {c['total_hit']:,} / 未命中 {c['total_miss']:,})")
        lines.append(f"  - 告警阈值 {CACHE_HIT_FLOOR*100:.0f}% / 目标 {CACHE_HIT_TARGET*100:.0f}%")
    else:
        lines.append(f"- {c['note']}")
    lines.append("")
    lines.append("## 日耗 (对照上限 ¥" + f"{DAILY_BUDGET_YUAN:.0f}" + "/天)")
    daily = audit["daily_budget"]["daily"]
    if daily:
        for day, d in sorted(daily.items()):
            flag = "🔴超" if d["over_budget"] else "✅"
            lines.append(f"- {flag} {day}: {_fmt_yuan(d['cost'])} ({d['calls']}次)")
    else:
        lines.append("- (无数据)")
    lines.append("")
    lines.append("## Context headroom")
    h = audit["headroom"]
    if h["has_headroom_data"]:
        lines.append(f"- avg headroom: {h['avg_headroom_pct']*100:.1f}% | low_headroom 触发: {h['low_headroom_count']}/{h['total_with_headroom']} ({h['low_headroom_pct']*100:.1f}%)")
    else:
        lines.append("- (无 headroom 数据)")
    lines.append("")
    lines.append("## 异常")
    if audit["anomalies"]:
        for a in audit["anomalies"]:
            lines.append(f"- ⚠️ {a['ts']} [{a['source']}] {a['reason']} (msg={a['message_id']})")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("---")
    lines.append("口径: cost 累加 jsonl 内 cost_est (写日志时按 DeepSeek 实测价计)。")
    lines.append("CLAUDE.md 的 ¥5-8/天 & 98% 命中为 *目标值*,此处作对照基准,非实测环境断言。")
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Token 审计 CLI — AI 自治理工具")
    p.add_argument("--hours", type=int, default=24, help="审计时间窗(小时), 0=全部 (默认 24)")
    p.add_argument("--daily", action="store_true", help="按北京时间分日聚合成本")
    p.add_argument("--json", action="store_true", help="机器可读 JSON 输出")
    args = p.parse_args(argv)

    audit = run_audit(hours=args.hours)

    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_markdown(audit))
        if args.daily:
            print("\n# 按日明细 (北京时间)")
            for day, d in sorted(audit["daily_budget"]["daily"].items()):
                flag = "🔴超预算" if d["over_budget"] else "✅"
                print(f"  {flag} {day}: ¥{d['cost']:.4f} ({d['calls']}次)")

    # 退出码: 超预算 / 缓存命中率低 / 有异常 → 非零
    if not audit["healthy"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
