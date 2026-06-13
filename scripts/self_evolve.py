#!/usr/bin/env python3
"""
OnionQuant Self-Evolution Cycle — IT/Tech Department Autonomous Research
Triggered every 6 hours by background_scheduler. Zero AI tokens for the trigger itself.

Cycle:
  1. OBSERVE: Scan GitHub Trending + own logs + error rates
  2. ANALYZE: Claude Code evaluates findings against current architecture
  3. PROPOSE: Write TECH_REPORT or ALERT to outbox
  4. EXECUTE: Low-risk improvements auto-applied
  5. REMEMBER: Update PROGRESS.md + distill learnings

Uses Claude Code persistent session for full context.
"""
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BEIJING_TZ = timezone(timedelta(hours=8))


def main():
    now = datetime.now(BEIJING_TZ)
    print(f"[{now.isoformat()}] Self-Evolution Cycle starting", flush=True)

    prompt = (
        "IT/Tech 部门自进化研究任务。请执行以下步骤：\n\n"
        "1. OBSERVE: 使用 WebSearch 搜索 'GitHub trending AI agent June 2026'，"
        "记录 3 个最相关的新项目/技术。检查 logs/ 目录最近的错误日志。\n"
        "2. ANALYZE: 这些新技术与 OnionQuant 当前架构匹配吗？有没有可以改进的？\n"
        "3. PROPOSE: 如果有发现，写 TECH_REPORT_*.md 到 chairman_outbox/。"
        "如果发现自身问题（错误率高、延迟大），写 ALERT_*.md。"
        "如果一切正常，写 SENTINEL_*.md 标注 'system nominal'。\n"
        "4. 更新 company/harness/PROGRESS.md：记录本次进化周期完成。\n"
        "5. 如果你发现了可复用的操作模式（5步以上），蒸馏为 skill 存入 "
        "company/departments/it_tech/discovered_skills/。\n\n"
        "直接执行所有步骤，不要只描述计划。完成后输出 DONE。"
    )

    prompt_file = PROJECT_ROOT / "company" / ".evolve_prompt.txt"
    prompt_file.write_text(prompt, encoding="utf-8")
    wsl_path = "/mnt/e/2026_AgentStudy/Python_code/company/.evolve_prompt.txt"

    try:
        result = subprocess.run(
            ["wsl", "-e", "bash", "-c",
             f'cd /mnt/e/2026_AgentStudy/Python_code && '
             f'claude -p "$(cat {wsl_path})" '
             f'--model deepseek-v4-pro --dangerously-skip-permissions 2>&1'],
            cwd=str(PROJECT_ROOT),
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=300,  # 5 min for research cycle
        )
        output = (result.stdout or "").strip()
        print(f"  Output: {output[:200]}...", flush=True)
        print(f"[{now.isoformat()}] Self-Evolution Cycle complete", flush=True)
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT: Evolution cycle exceeded 5 min", flush=True)
    except Exception as e:
        print(f"  ERROR: {e}", flush=True)
    finally:
        try:
            prompt_file.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()
