#!/usr/bin/env python3
"""
connectivity_guardian.py — 连通守护部 · 全链路健康检查

监控 7 条关键通道，发现断裂自动修复，不可修复则告警。
设计目标: WSL cron 每小时调用一次，也可手动触发。
"""

import io
import json
import os
import subprocess
import sys

# Fix Windows GBK encoding for emoji output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTBOX_DIR = PROJECT_ROOT / "company" / "chairman_outbox"
INBOX_DIR = PROJECT_ROOT / "company" / "chairman_inbox"
PROCESSED_DIR = INBOX_DIR / "processed"

ALERT_FILE = (
    OUTBOX_DIR / f"ALERT_connectivity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
)

CHECKS = {}
ALERTS = []


def check(name, severity="🟡"):
    """Decorator to register and run a health check."""

    def decorator(fn):
        CHECKS[name] = (fn, severity)
        return fn

    return decorator


# ─── Check 1: tmux session ───────────────────────────


@check("WSL tmux 会话", severity="🔴")
def check_tmux():
    try:
        r = subprocess.run(
            ["tmux", "has-session", "-t", "onionquant"], capture_output=True, timeout=10
        )
        if r.returncode != 0:
            return False, "onionquant 会话不存在"

        # Check if claude process is running inside tmux
        r2 = subprocess.run(
            ["bash", "-c", "ps aux | grep -c '[c]laude'"],
            capture_output=True,
            timeout=10,
        )
        count = int(r2.stdout.decode().strip() or "0")
        if count == 0:
            return False, "tmux 会话存在但 claude 进程不在"

        return True, f"alive ({count} claude processes)"
    except FileNotFoundError:
        return False, "tmux 命令不可用（不在 WSL 环境中）"
    except Exception as e:
        return False, str(e)[:100]


# ─── Check 2: Hermes (WeChat) ────────────────────────


@check("Hermes 微信网关", severity="🔴")
def check_hermes():
    try:
        req = urllib.request.Request("http://localhost:8645/health")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "ok":
                return True, f"platform={data.get('platform', '?')}"
            return False, f"status={data.get('status', '?')}"
    except urllib.error.URLError:
        return False, "端口 8645 无法连接"
    except Exception as e:
        return False, str(e)[:100]


# ─── Check 3: Dashboard ──────────────────────────────


@check("Dashboard 前端", severity="🔴")
def check_dashboard():
    try:
        req = urllib.request.Request("http://localhost:8765/api/status")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return (
                True,
                f"depts={data.get('departments', '?')} inbox={data.get('inbox_pending', '?')}",
            )
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return True, "running (auth required)"
        return False, f"HTTP {e.code}"
    except urllib.error.URLError:
        return False, "端口 8765 无法连接"
    except Exception as e:
        return False, str(e)[:100]


# ─── Check 4: Inbox/outbox flow ──────────────────────


@check("Inbox→Outbox 消息流", severity="🔴")
def check_message_flow():
    # Check for stale .processing lock files
    stale_locks = []
    cutoff = time.time() - 1800  # 30 minutes
    for lock_dir in [PROCESSED_DIR, INBOX_DIR]:
        for lock in lock_dir.glob("*.processing"):
            try:
                if lock.stat().st_mtime < cutoff:
                    stale_locks.append(str(lock.name))
            except OSError:
                pass

    # Check inbox pending
    pending = [
        f
        for f in INBOX_DIR.glob("MSG_*.md")
        if f.name != "README.md"
        and not (PROCESSED_DIR / f"{f.name}.processing").exists()
    ]

    status_parts = []
    if stale_locks:
        status_parts.append(f"{len(stale_locks)} 孤儿锁")
        ALERTS.append(
            (
                "孤儿锁文件",
                f"发现 {len(stale_locks)} 个超过30分钟的.processing锁: {', '.join(stale_locks[:5])}",
            )
        )

    if pending:
        oldest = min(f.stat().st_mtime for f in pending)
        age_min = (time.time() - oldest) / 60
        status_parts.append(f"{len(pending)} 待处理 (最旧 {age_min:.0f}min)")

    if not status_parts:
        return True, "通畅 (无待处理/孤儿锁)"

    return False, "; ".join(status_parts)


# ─── Check 5: Cross-filesystem ───────────────────────


@check("WSL↔Windows 文件桥接", severity="🔴")
def check_cross_fs():
    test_file = PROJECT_ROOT / "company" / ".connectivity_test"
    try:
        test_file.write_text(datetime.now().isoformat())
        content = test_file.read_text()
        test_file.unlink()
        return True, "/mnt/e/ 读写正常"
    except Exception as e:
        return False, f"跨文件系统访问失败: {str(e)[:80]}"


# ─── Check 6: DeepSeek API ───────────────────────────


@check("DeepSeek API", severity="🟡")
def check_deepseek_api():
    # Primary check: if Claude CLI is running, API is almost certainly working
    # (Claude CLI depends on it for every response)
    try:
        r = subprocess.run(
            ["bash", "-c", "ps aux | grep -c '[c]laude'"],
            capture_output=True,
            timeout=10,
        )
        claude_count = int(r.stdout.decode().strip() or "0")
        if claude_count > 0:
            return True, "Claude CLI 运行中 (API 可用)"
    except Exception:
        pass

    # Secondary: DNS + TCP reachability
    import socket

    try:
        ips = socket.getaddrinfo("api.deepseek.com", 443, proto=socket.IPPROTO_TCP)
        if not ips:
            return False, "DNS 解析失败"
        ip = ips[0][4][0]
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex((ip, 443))
        sock.close()
        if result == 0:
            return True, f"TCP {ip}:443 可达"
        return False, f"TCP {ip}:443 不可达"
    except socket.gaierror:
        return False, "DNS 解析失败"
    except Exception as e:
        return False, str(e)[:100]


# ─── Check 7: Cloudflared tunnels ────────────────────


@check("Cloudflared 隧道", severity="🟡")
def check_tunnels():
    try:
        r = subprocess.run(
            ["bash", "-c", "pgrep -a cloudflared 2>/dev/null"],
            capture_output=True,
            timeout=10,
        )
        output = r.stdout.decode().strip()
        if output:
            lines = output.split("\n")
            return True, f"{len(lines)} 隧道运行中"
        return False, "cloudflared 进程不存在"
    except FileNotFoundError:
        return None, "不在 WSL，跳过"  # neutral
    except Exception as e:
        return None, str(e)[:80]


# ─── Recovery actions ────────────────────────────────


def recover_stale_locks():
    """Auto-clean stale lock files."""
    cleaned = 0
    cutoff = time.time() - 1800
    for lock_dir in [PROCESSED_DIR, INBOX_DIR]:
        for lock in lock_dir.glob("*.processing"):
            try:
                if lock.stat().st_mtime < cutoff:
                    lock.unlink()
                    cleaned += 1
            except OSError:
                pass
    return cleaned


def restart_hermes():
    """Attempt to restart Hermes."""
    try:
        subprocess.run(["pkill", "-f", "hermes gateway"], timeout=5)
        time.sleep(2)
        subprocess.run(
            [
                "rm",
                "-f",
                os.path.expanduser("~/.hermes/gateway.lock"),
                os.path.expanduser("~/.hermes/gateway.pid"),
            ],
            timeout=5,
        )
        subprocess.Popen(
            ["nohup", "hermes", "gateway", "run", "--replace"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3)
        # Verify
        req = urllib.request.Request("http://localhost:8645/health")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("status") == "ok"
    except Exception:
        return False


# ─── Main ────────────────────────────────────────────


def run_all_checks():
    results = {}
    for name, (fn, severity) in CHECKS.items():
        try:
            ok, detail = fn()
            if ok is None:
                results[name] = {"status": "skip", "detail": detail}
            elif ok:
                results[name] = {"status": "ok", "detail": detail}
            else:
                results[name] = {
                    "status": "fail",
                    "severity": severity,
                    "detail": detail,
                }
        except Exception as e:
            results[name] = {"status": "error", "detail": str(e)[:100]}

    return results


def generate_report(results):
    fails = [k for k, v in results.items() if v["status"] == "fail"]
    oks = [k for k, v in results.items() if v["status"] == "ok"]

    lines = [
        f"# 🔗 连通守护报告 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} CST",
        "",
        "| 通道 | 状态 | 详情 |",
        "|------|------|------|",
    ]
    for name, v in results.items():
        icon = {"ok": "🟢", "fail": "🔴", "skip": "⚪", "error": "🟡"}[v["status"]]
        lines.append(f"| {icon} {name} | {v['status']} | {v['detail']} |")

    lines.append("")

    if fails:
        lines.append("## 🔴 断裂通道")
        for name in fails:
            v = results[name]
            lines.append(f"- **{v['severity']} {name}**: {v['detail']}")
        lines.append("")
    else:
        lines.append("## ✅ 全通道畅通")
        lines.append("")

    # Auto-recovery
    lines.append("## 🔧 自动修复")
    cleaned = recover_stale_locks()
    if cleaned:
        lines.append(f"- 清理 {cleaned} 个孤儿 .processing 锁文件")
    else:
        lines.append("- 无需修复操作")

    lines.append("")

    if ALERTS:
        lines.append("## ⚠️ 需关注")
        for title, detail in ALERTS:
            lines.append(f"- **{title}**: {detail}")
        lines.append("")

    return "\n".join(lines)


def main():
    global ALERTS
    ALERTS = []

    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        results = run_all_checks()
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    results = run_all_checks()
    report = generate_report(results)

    fails = [k for k, v in results.items() if v["status"] == "fail"]
    critical_fails = [k for k in fails if results[k]["severity"] == "🔴"]

    # Always print to stdout
    print(report)

    # Write to outbox if there are critical failures
    if critical_fails:
        ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
        ALERT_FILE.write_text(report, encoding="utf-8")
        print(f"\n🚨 关键通道断裂，告警已写入 {ALERT_FILE.name}")

    # Try Hermes restart if it's down
    hermes_result = results.get("Hermes 微信网关", {})
    if hermes_result.get("status") == "fail":
        print("🔄 尝试重启 Hermes...")
        if restart_hermes():
            print("✅ Hermes 重启成功")
        else:
            print("❌ Hermes 重启失败，需要手动干预")


if __name__ == "__main__":
    main()
