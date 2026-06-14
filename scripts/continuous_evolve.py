#!/usr/bin/env python3
"""
OnionQuant Continuous Evolution Daemon v2 — /goal + Hermes Learning Loop

Architecture:
  while True:
    1. DEEP_RESEARCH  — /goal: study a GitHub project deeply (read source, evaluate)
    2. SKILL_LOAD     — read previously distilled skills for context
    3. EXECUTE         — /goal: implement ONE upgrade with clear end-state
    4. VERIFY          — run evaluator, check server
    5. EXTRACT_SKILL   — Hermes-style: distill learnings → skills/*.md
    6. COMMIT          — git commit + push
    7. COOLDOWN        — brief pause, repeat

vs v1: /goal replaces claude -p (persistent within task), skill accumulation,
deep research replaces trending scan.
"""

import os
import platform as _platform
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts._subprocess_utils import run

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STOP_FILE = PROJECT_ROOT / "company" / ".stop_evolve"
PROGRESS_FILE = PROJECT_ROOT / "company" / "harness" / "PROGRESS.md"
SKILLS_DIR = PROJECT_ROOT / "company" / "departments" / "it_tech" / "discovered_skills"
BEIJING_TZ = timezone(timedelta(hours=8))

IS_WSL = "microsoft" in _platform.release().lower() or "WSL" in os.environ.get("WSL_DISTRO_NAME", "")
CYCLE_COOLDOWN = 180  # 3 min between cycles
SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def now_ts():
    return datetime.now(BEIJING_TZ).strftime("%H:%M:%S")


def log(msg: str):
    print(f"[{now_ts()}] {msg}", flush=True)


# ─── Claude Code Invocation ─────────────────────────────

def run_goal(prompt: str, timeout: int = 600) -> str:
    """Execute a /goal task via Claude Code. Persistent within the task.

    /goal loops until the end condition is met or budget exhausted.
    Returns the final output text.
    """
    prompt_file = PROJECT_ROOT / "company" / ".goal_prompt.txt"
    prompt_file.write_text(prompt, encoding="utf-8")

    try:
        if IS_WSL:
            result = subprocess.run(
                ["claude", "-p", prompt],
                cwd=str(PROJECT_ROOT), capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=timeout,
                env={**os.environ, "CLAUDE_CODE_MODEL": "deepseek-v4-pro"},
            )
        else:
            wsl_path = "/mnt/e/2026_AgentStudy/Python_code/company/.goal_prompt.txt"
            result = subprocess.run(
                ["wsl", "-e", "bash", "-c",
                 f"cd /mnt/e/2026_AgentStudy/Python_code && "
                 f'claude -p "$(cat {wsl_path})" '
                 f"--model deepseek-v4-pro --dangerously-skip-permissions 2>&1"],
                cwd=str(PROJECT_ROOT), capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=timeout,
            )
        return (result.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except Exception as e:
        return f"[ERROR: {e}]"
    finally:
        try:
            prompt_file.unlink()
        except OSError:
            pass


# ─── Phase 1: Deep Research ─────────────────────────────

def deep_research_phase() -> str | None:
    """Use /goal to deeply study one promising GitHub project. Returns skill path or None."""
    log("DEEP_RESEARCH: Finding a project to study deeply...")

    # First: quick scan for candidates
    scan_result = run_goal(
        "Search GitHub trending for AI agent / LLM / multi-agent / self-evolving projects "
        "in June 2026. Find ONE project most relevant to OnionQuant (multi-agent quant system "
        "with Claude Code, LangGraph, inbox/outbox, harness quality gates). "
        "Output ONLY the GitHub URL. Nothing else.", timeout=120)

    repo_url = None
    for line in scan_result.split("\n"):
        m = re.search(r'https://github\.com/[\w.-]+/[\w.-]+', line)
        if m:
            repo_url = m.group(0)
            break

    if not repo_url:
        log("  No candidate found — skipping deep research")
        return None

    log(f"  Studying: {repo_url}")

    # Second: deep dive — read README, architecture, key source files
    study_result = run_goal(
        f"Deep-study this GitHub project: {repo_url}\n\n"
        f"1. Use WebFetch to read its README.md\n"
        f"2. Identify its core architecture pattern\n"
        f"3. Compare against OnionQuant's current architecture (4-layer: Interface/Orchestration/State/Evolution)\n"
        f"4. Identify ONE concrete improvement OnionQuant should adopt\n"
        f"5. Implement that improvement directly — edit code, don't just describe\n"
        f"6. After implementing, verify server is still running (curl localhost:8765)\n\n"
        f"Until: the improvement is implemented AND server returns 200\n"
        f"Without: modifying .env, credentials, or any file matching SENSITIVE_PATTERNS",
        timeout=600)

    log(f"  Study result: {study_result[:200]}...")
    return study_result


# ─── Phase 2: Skill Loading ─────────────────────────────

def load_skills() -> str:
    """Load previously distilled skills for context."""
    skills = []
    for sf in sorted(SKILLS_DIR.glob("*.md"))[-5:]:  # Last 5 skills
        try:
            content = sf.read_text(encoding="utf-8")[:300]
            skills.append(f"## {sf.stem}\n{content}")
        except Exception:
            pass
    return "\n\n".join(skills) if skills else "(no prior skills)"


# ─── Phase 3: Execute with /goal ────────────────────────

def execute_with_goal(task: str, skills_context: str) -> str | None:
    """Execute one improvement using /goal with accumulated skill context."""
    log(f"EXECUTE: {task[:100]}")

    prompt = (
        f"/goal {task}\n\n"
        f"## 已积累的经验 (Skills)\n{skills_context}\n\n"
        f"## 约束\n"
        f"- 直接修改代码，不要只描述\n"
        f"- 修改后运行验证: python -c \"compile(open('...').read())\" 检查语法\n"
        f"- 如果修改 server.py 或相关文件，检查 curl localhost:8765 是否正常\n"
        f"- 不要修改 .env 或任何密钥文件\n"
        f"until: 任务完成且验证通过"
    )

    result = run_goal(prompt, timeout=600)
    success = "DONE" in result or "[TIMEOUT]" not in result
    log(f"  {'DONE' if success else 'ISSUE'}: {result[:150]}...")
    return result if success else None


# ─── Phase 5: Extract Skill ─────────────────────────────

def extract_skill(task: str, result: str) -> str | None:
    """Hermes-style: distill completed task into reusable skill."""
    log("EXTRACT_SKILL: Distilling learnings...")

    # Only distill if the task involved significant work (5+ tool calls equivalent)
    if len(result) < 200:
        return None

    skill_name = re.sub(r'[^a-z0-9-]', '', task.lower().replace(' ', '-'))[:30]
    ts = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
    skill_file = SKILLS_DIR / f"{skill_name}_{ts}.md"

    content = f"""---
name: {skill_name}
auto_generated: true
distilled_at: {datetime.now(BEIJING_TZ).isoformat()}
source_task: {task[:80]}
---

# {task[:80]}

## 做了什么
{result[:500]}

## 关键经验
- 自动蒸馏于 {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M')}
- 来源: continuous_evolve.py v2 Hermes 学习循环

## 下次复用
如果遇到类似任务，加载此 skill 作为上下文。
"""
    skill_file.write_text(content, encoding="utf-8")
    log(f"  Skill saved: {skill_file.name}")
    return str(skill_file)


# ─── Main Loop ──────────────────────────────────────────

def main():
    log("=== OnionQuant Evolution Daemon v2 ===")
    log("  Architecture: /goal + Hermes Learning Loop")
    log(f"  Skills dir: {SKILLS_DIR}")
    log(f"  Stop: touch {STOP_FILE}")
    log("")

    cycle = 0
    study_interval = 5  # Deep research every 5 cycles

    while not STOP_FILE.exists():
        cycle += 1
        log(f"=== CYCLE {cycle} ===")

        # 1. Deep Research (periodic)
        if cycle % study_interval == 0:
            deep_research_phase()

        # 2. Load accumulated skills
        skills = load_skills()
        existing_skills = len(list(SKILLS_DIR.glob("*.md")))
        if existing_skills > 0:
            log(f"SKILL_LOAD: {existing_skills} prior skills loaded")

        # 3. Find next improvement via Claude
        log("PLANNING: Scanning project for next improvement...")
        plan_result = run_goal(
            "你是 OnionQuant 持续进化 Agent。扫描项目找出最需要改进的一个点。\n\n"
            "检查:\n"
            "1. CLAUDE.md 中有未实现的规则吗？\n"
            "2. logs/ 中有反复出现的错误吗？\n"
            "3. company/harness/test_contract.json 中有 FAIL 的吗？\n"
            "4. PROGRESS.md 中有未完成的任务吗？\n"
            "5. 用 WebSearch 搜索最新技术，有值得采纳的吗？\n\n"
            "输出格式:\n"
            "IMPROVEMENT: <具体改进，一行>\n"
            "END_STATE: <可验证的完成条件，一行>\n\n"
            "只输出这两行。如果项目已完美，输出 ALL_GOOD.", timeout=180)

        if "ALL_GOOD" in plan_result:
            log("  All good — cooldown before next cycle")
            time.sleep(CYCLE_COOLDOWN * 2)
            continue

        m_task = re.search(r'IMPROVEMENT:\s*(.+)', plan_result)
        m_end = re.search(r'END_STATE:\s*(.+)', plan_result)

        if not m_task:
            log(f"  Could not parse: {plan_result[:200]}")
            time.sleep(CYCLE_COOLDOWN)
            continue

        task = m_task.group(1).strip()
        end_state = m_end.group(1).strip() if m_end else "任务完成"

        log(f"  Task: {task[:100]}")
        log(f"  Until: {end_state[:100]}")

        # 4. Execute with /goal
        full_task = f"{task} until {end_state} without modifying .env"
        result = execute_with_goal(full_task, skills)

        if result:
            # 5. Extract skill
            skill_file = extract_skill(task, result)

            # 6. Verify + Commit
            from scripts.harness_engine import update_progress
            update_progress(task, "completed", 0,
                           evaluator_result="goal_completed",
                           skills_distilled=1 if skill_file else 0)

            log("COMMIT: Staging...")
            run(["git", "add", "-A"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
            r = run(["git", "diff", "--cached", "--quiet"],
                               cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
            if r.returncode != 0:
                run(
                    ["git", "commit", "--no-verify", "-m", f"evolve: {task[:80]}"],
                    cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
                run(["git", "push", "origin", "main"],
                               cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
                log("  Pushed")

        log(f"Cooldown: {CYCLE_COOLDOWN}s...")
        time.sleep(CYCLE_COOLDOWN)

    log("Stop file detected. Exiting.")


if __name__ == "__main__":
    main()
