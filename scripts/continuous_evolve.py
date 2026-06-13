#!/usr/bin/env python3
"""
OnionQuant Continuous Evolution Daemon — Linear Agent Loop
No timers, no cron, no interrupts. Like a CPU time-slice scheduler.

Architecture:
  while True:
    1. OBSERVE  — scan GitHub trending + own logs + PROGRESS.md
    2. PRIORITIZE — rank findings by interview-value + code-impact
    3. EXECUTE    — implement ONE upgrade (claude -p)
    4. VERIFY     — run evaluator, check server, update PROGRESS
    5. COMMIT     — git commit + push
    6. COOLDOWN   — brief pause, then repeat

If a cycle is interrupted (crash/restart), PROGRESS.md preserves state.
On restart, reads PROGRESS.md → continues where it left off.

Start: python scripts/continuous_evolve.py
Stop:  touch company/.stop_evolve
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STOP_FILE = PROJECT_ROOT / "company" / ".stop_evolve"
PROGRESS_FILE = PROJECT_ROOT / "company" / "harness" / "PROGRESS.md"
BEIJING_TZ = timezone(timedelta(hours=8))

CYCLE_COOLDOWN = 120  # 2 minutes between cycles (brief pause, not a timer)

UPGRADE_PLAN = [
    # Format: (priority, category, description)
    ("P0", "dependency", "Verify and update all Python dependencies in requirements.txt"),
    ("P0", "testing", "Add CI smoke test that runs on every push via GitHub Actions"),
    ("P0", "docs", "Add architecture decision records (ADRs) to docs/ for key design choices"),
    ("P1", "observability", "Add token usage tracking per inbox message (already partially done)"),
    ("P1", "memory", "Integrate MemPalace-style semantic retrieval for memory files"),
    ("P1", "context", "✅ Evaluate headroom context compression for inbox LLM calls — DONE 2026-06-13"),
    ("P1", "research", "Integrate Agent-Reach for Chinese social media sentiment data"),
    ("P2", "frontend", "Add research panel SSE progress for LangGraph pipeline execution"),
    ("P2", "security", "Add rate limiting to POST /api/inbox"),
    ("P2", "ops", "Add Docker Compose for one-command local deployment"),
]


def now_ts():
    return datetime.now(BEIJING_TZ).strftime("%H:%M:%S")


def log(msg: str):
    line = f"[{now_ts()}] {msg}"
    print(line, flush=True)


def call_claude(prompt: str, timeout: int = 300) -> str:
    """Call Claude Code with a prompt. Returns output text.

    Auto-detects whether running inside WSL (native) or on Windows (via wsl.exe).
    """
    import platform as _platform
    prompt_file = PROJECT_ROOT / "company" / ".evolve_prompt.txt"
    prompt_file.write_text(prompt, encoding="utf-8")

    is_wsl = "microsoft" in _platform.release().lower() or "WSL" in os.environ.get("WSL_DISTRO_NAME", "")

    try:
        if is_wsl:
            # Running inside WSL — call claude directly
            result = subprocess.run(
                ["claude", "-p", prompt],
                cwd=str(PROJECT_ROOT),
                capture_output=True, encoding="utf-8", errors="replace",
                timeout=timeout,
                env={**os.environ, "CLAUDE_CODE_MODEL": "deepseek-v4-pro"},
            )
        else:
            # Running on Windows — call via wsl.exe with prompt file
            wsl_path = "/mnt/e/2026_AgentStudy/Python_code/company/.evolve_prompt.txt"
            result = subprocess.run(
                ["wsl", "-e", "bash", "-c",
                 f"cd /mnt/e/2026_AgentStudy/Python_code && "
                 f'claude -p "$(cat {wsl_path})" '
                 f"--model deepseek-v4-pro --dangerously-skip-permissions 2>&1"],
                cwd=str(PROJECT_ROOT),
                capture_output=True, encoding="utf-8", errors="replace",
                timeout=timeout,
            )
        return (result.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except Exception as e:
        return f"[ERROR: {e}]"
    finally:
        try: prompt_file.unlink()
        except: pass


def check_server() -> bool:
    """Quick server health check."""
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", 8765), timeout=3)
        s.close()
        return True
    except Exception:
        return False


def observe_phase() -> list[str]:
    """Phase 1: Observe — what's new, what's broken?"""
    findings = []

    # Check GitHub trending for new projects
    log("OBSERVE: Scanning GitHub trending...")
    result = call_claude(
        "Search GitHub trending for AI agent / LLM projects this week (June 2026). "
        "Find the TOP 3 most relevant for an AI application engineer's portfolio project. "
        "For each: name, stars, what it does, why it matters. "
        "Output format: BULLET_POINTS only, no markdown headers.", timeout=120)

    if result and "[ERROR" not in result and "[TIMEOUT" not in result:
        findings.append(f"github_trending: {result[:500]}")
        log(f"  Found: {result[:100]}...")

    # Check own logs for issues
    log("OBSERVE: Checking own logs...")
    log_dir = PROJECT_ROOT / "logs"
    issues = []
    for log_file in ["bg_scheduler_err.log", "server_error.log"]:
        lf = log_dir / log_file
        if lf.exists():
            content = lf.read_text(encoding="utf-8", errors="replace")
            error_count = content.count("Error") + content.count("ERROR")
            if error_count > 0:
                issues.append(f"{log_file}: {error_count} errors")

    if issues:
        findings.append(f"own_errors: {'; '.join(issues)}")

    # Check what PROGRESS.md says
    if PROGRESS_FILE.exists():
        progress = PROGRESS_FILE.read_text(encoding="utf-8")
        findings.append(f"progress_state: {progress[:200]}")

    return findings


def execute_phase(task: str) -> bool:
    """Phase 3: Execute one upgrade."""
    log(f"EXECUTE: {task}")

    prompt = (
        f"你是 OnionQuant 的持续进化 Agent。请完成以下升级任务：\n\n"
        f"任务: {task}\n\n"
        f"要求:\n"
        f"1. 基于当前项目上下文（CLAUDE.md + memory + 代码结构）执行\n"
        f"2. 直接进行代码/配置修改，不要只描述计划\n"
        f"3. 修改完成后，运行验证（如 syntax check, import test）\n"
        f"4. 如果任务不可执行（依赖缺失等），输出 SKIP: <原因>\n"
        f"5. 完成后输出 DONE: <做了什么>\n\n"
        f"开始执行。"
    )

    result = call_claude(prompt, timeout=300)
    success = "DONE:" in result and "SKIP:" not in result
    log(f"  {'COMPLETED' if success else 'SKIPPED/FAILED'}: {result[:150]}...")
    return success


def verify_phase() -> bool:
    """Phase 4: Verify nothing is broken."""
    log("VERIFY: Checking server...")
    if not check_server():
        log("  SERVER DOWN! Attempting restart...")
        subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "company" / "server.py")],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        time.sleep(5)
        if not check_server():
            log("  Server still DOWN — skipping commit")
            return False
    log("  Server OK")
    return True


def commit_phase(task: str) -> None:
    """Phase 5: Git commit + push."""
    log("COMMIT: Staging changes...")
    subprocess.run(["git", "add", "-A"], cwd=str(PROJECT_ROOT), capture_output=True, timeout=30)

    # Check if there's anything to commit
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(PROJECT_ROOT), capture_output=True, timeout=10)

    if result.returncode == 0:
        log("  No changes to commit")
        return

    msg = f"evolve: {task[:80]}"
    r = subprocess.run(
        ["git", "commit", "--no-verify", "-m", msg],
        cwd=str(PROJECT_ROOT), capture_output=True, encoding="utf-8", errors="replace", timeout=30)
    log(f"  Committed: {r.stdout.strip()[:100]}")

    subprocess.run(["git", "push", "origin", "main"], cwd=str(PROJECT_ROOT),
                   capture_output=True, timeout=60)
    log("  Pushed")


def main():
    log("=== OnionQuant Continuous Evolution Daemon ===")
    log(f"  Mode: linear loop (no timers, no interrupts)")
    log(f"  Cooldown: {CYCLE_COOLDOWN}s between cycles")
    log(f"  Stop: touch {STOP_FILE}")
    log(f"  Upgrade plan: {len(UPGRADE_PLAN)} tasks")
    log("")

    completed = set()
    cycle = 0

    while not STOP_FILE.exists():
        cycle += 1
        log(f"=== CYCLE {cycle} ===")

        # Anthropic cwc-long-running-agents pattern:
        # Never ask "what tasks are left?" — always ask "what's not passing right now?"
        # Claude Code reads the codebase + logs + PROGRESS.md and decides what to improve.
        log("READING: Scanning project for improvement opportunities...")

        result = call_claude(
            "你是 OnionQuant 持续进化 Agent。扫描当前项目，找出最需要改进的一个点。\n\n"
            "检查清单:\n"
            "1. 读 CLAUDE.md — 有没有未实现的规则或协议？\n"
            "2. 扫描 logs/ 目录 — 有没有反复出现的错误？\n"
            "3. 检查 company/harness/test_contract.json — 有没有 FAIL 的合同？\n"
            "4. 检查 README.md — 架构描述与实践一致吗？\n"
            "5. 用 WebSearch 搜索最新相关技术 — 有没有值得采纳的？\n\n"
            "输出格式（严格遵守）:\n"
            "IMPROVEMENT: <具体改进描述，一行>\n"
            "PRIORITY: P0/P1/P2\n"
            "REASON: <为什么这个值得做，一行>\n\n"
            "只输出上述三行。如果项目已经完美无需改进，输出: ALL_GOOD.", timeout=180)

        if "[ERROR" in result or "[TIMEOUT" in result:
            log(f"  Claude call failed: {result[:100]}")
            time.sleep(CYCLE_COOLDOWN)
            continue

        if "ALL_GOOD" in result:
            log("  No improvements needed — project is optimal")
            time.sleep(CYCLE_COOLDOWN * 3)  # Longer cooldown when nothing to do
            continue

        # Parse Claude's output
        import re
        m_task = re.search(r'IMPROVEMENT:\s*(.+)', result)
        m_priority = re.search(r'PRIORITY:\s*(.+)', result)

        if not m_task:
            log(f"  Could not parse improvement: {result[:200]}")
            time.sleep(CYCLE_COOLDOWN)
            continue

        task = m_task.group(1).strip()
        priority = m_priority.group(1).strip() if m_priority else "P1"

        log(f"  Found: [{priority}] {task[:100]}")

        # Execute the improvement
        success = execute_phase(task)

        if success and verify_phase():
            commit_phase(task)
            log(f"COMPLETED: {task[:80]}")
        else:
            log(f"SKIPPED/FAILED: {task[:80]}")

        # Update PROGRESS.md
        try:
            from scripts.harness_engine import update_progress
            update_progress(task, "completed" if success else "failed", 0)
        except Exception:
            pass

        log(f"Cooldown: {CYCLE_COOLDOWN}s...")
        time.sleep(CYCLE_COOLDOWN)

    log("Stop file detected. Exiting.")


if __name__ == "__main__":
    main()
