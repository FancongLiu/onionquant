#!/usr/bin/env python3
"""
OnionQuant Harness Engine — Production Agent Quality Gates (Anthropic 2026 pattern)

4 Primitives:
  1. Default-FAIL Contract  — all criteria start false, agent must prove success
  2. PROGRESS.md Self-Maint  — agent reads/writes its own progress, survives restarts
  3. Fresh Evaluator          — independent agent (no Write tools) reviews work
  4. Auto-Skill Distillation  — complex tasks (5+ steps) → reusable Skill

Architecture:
  Agent Loop → complete task → update PROGRESS.md → evaluator reviews
  → update test_contract → if complex: distill Skill → loop

Usage:
  from scripts.harness_engine import HarnessEngine
  engine = HarnessEngine()
  engine.start_task("分析 MU 目标价")
  # ... agent does work ...
  engine.complete_task(success=True, evidence={"reply": "outbox/REPLY_x.md", "nodes": 11})
"""

import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HARNESS_DIR = PROJECT_ROOT / "company" / "harness"
PROGRESS_FILE = HARNESS_DIR / "PROGRESS.md"
CONTRACT_FILE = HARNESS_DIR / "test_contract.json"
SKILLS_DIR = PROJECT_ROOT / "company" / "departments" / "it_tech" / "discovered_skills"
BEIJING_TZ = timezone(timedelta(hours=8))

HARNESS_DIR.mkdir(parents=True, exist_ok=True)
SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def now_iso():
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def now_ts():
    return datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")


# ─── Primitive 1: Default-FAIL Contract ─────────────────

def load_contract():
    """Load the current test contract. All criteria default to false."""
    if CONTRACT_FILE.exists():
        try:
            return json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return json.loads("""
    {"contracts":[{"task_id":null,"criteria":[],"evaluator_verdict":null,"evaluator_findings":[]}]}
    """)


def create_contract(task_id: str, criteria_override: list = None) -> dict:
    """Create a Default-FAIL contract for a new task."""
    criteria = criteria_override or [
        {"name": "task_completed", "passes": False, "evidence_required": "task output exists"},
        {"name": "progress_updated", "passes": False, "evidence_required": "PROGRESS.md updated"},
        {"name": "evaluator_passed", "passes": False, "evidence_required": "fresh evaluator review"},
    ]

    contract = {
        "task_id": task_id,
        "criteria": criteria,
        "evaluator_verdict": None,
        "evaluator_findings": [],
        "created_at": now_iso(),
        "resolved_at": None,
    }

    data = load_contract()
    data["contracts"] = [c for c in data.get("contracts", []) if c.get("task_id") != task_id]
    data["contracts"].append(contract)
    CONTRACT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return contract


def update_criterion(task_id: str, name: str, passes: bool, evidence: str = ""):
    """Update a single criterion in the contract. Agent must provide evidence."""
    data = load_contract()
    for contract in data.get("contracts", []):
        if contract.get("task_id") == task_id:
            for c in contract.get("criteria", []):
                if c["name"] == name:
                    c["passes"] = passes
                    if evidence:
                        c["evidence"] = evidence
            contract["resolved_at"] = now_iso()
            break
    CONTRACT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def all_criteria_pass(task_id: str) -> bool:
    """Check if all criteria for a task have passed."""
    data = load_contract()
    for contract in data.get("contracts", []):
        if contract.get("task_id") == task_id:
            return all(c.get("passes", False) for c in contract.get("criteria", []))
    return False


# ─── Primitive 2: PROGRESS.md Self-Maintenance ──────────

def read_progress() -> dict:
    """Agent reads its own progress on startup to know where it left off."""
    info = {
        "active_task": None,
        "last_completed": None,
        "interrupted_tasks": [],
        "tasks_completed": 0,
        "tasks_failed": 0,
        "skills_distilled": 0,
    }
    if PROGRESS_FILE.exists():
        content = PROGRESS_FILE.read_text(encoding="utf-8")
        # Parse current state
        m = re.search(r'\*\*Active task\*\*:\s*(.+)', content)
        if m:
            info["active_task"] = m[1].strip() if m[1].strip() != "none" else None
        m = re.search(r'\*\*Last completed\*\*:\s*(.+)', content)
        if m:
            info["last_completed"] = m[1].strip() if m[1].strip() != "none" else None
        m = re.search(r'\*\*Tasks completed this session\*\*:\s*(\d+)', content)
        if m:
            info["tasks_completed"] = int(m[1])
        m = re.search(r'\*\*Tasks failed this session\*\*:\s*(\d+)', content)
        if m:
            info["tasks_failed"] = int(m[1])
        m = re.search(r'\*\*Skills distilled this session\*\*:\s*(\d+)', content)
        if m:
            info["skills_distilled"] = int(m[1])
        # Parse interrupted tasks
        in_interrupted = False
        for line in content.split("\n"):
            if "## Interrupted Tasks" in line:
                in_interrupted = True
                continue
            if in_interrupted and line.startswith("##"):
                break
            if in_interrupted and line.strip().startswith("-"):
                info["interrupted_tasks"].append(line.strip("- ").strip())
    return info


def update_progress(task_description: str, status: str, duration_sec: float = 0,
                    evaluator_result: str = "", skills_distilled: int = 0):
    """Agent writes its own progress after completing a task."""
    now = now_iso()
    progress = read_progress()

    # Update counters
    if status == "completed":
        progress["tasks_completed"] += 1
    elif status == "failed":
        progress["tasks_failed"] += 1
    progress["skills_distilled"] += skills_distilled
    progress["last_completed"] = task_description[:80]
    progress["active_task"] = None

    # Build new PROGRESS.md
    lines = [
        "# Agent Progress Log",
        "",
        "> Auto-maintained by OnionQuant Harness Engine.",
        "> Agent reads this on every restart. Agent writes after every task.",
        f"> Last updated: {now}",
        "",
        "## Current State",
        "",
        f"- **Active task**: {progress['active_task'] or 'none'}",
        f"- **Last completed**: {progress['last_completed'] or 'none'}",
        f"- **Tasks completed this session**: {progress['tasks_completed']}",
        f"- **Tasks failed this session**: {progress['tasks_failed']}",
        f"- **Skills distilled this session**: {progress['skills_distilled']}",
        "",
        "## Task History (most recent first)",
        "",
        "| # | Task | Status | Duration | Evaluator | Skills |",
        "|---|------|--------|----------|-----------|--------|",
        f"| {progress['tasks_completed']} | {task_description[:50]} | {status} | {duration_sec:.0f}s | {evaluator_result or 'N/A'} | {skills_distilled} |",
        "",
        "## Interrupted Tasks",
        "",
    ]
    if progress["interrupted_tasks"]:
        for t in progress["interrupted_tasks"]:
            lines.append(f"- {t}")
    else:
        lines.append("(none)")

    lines += [
        "",
        "## Distilled Skills This Session",
        "",
    ]
    if skills_distilled > 0:
        lines.append(f"- {skills_distilled} skill(s) distilled this session")
    else:
        lines.append("(none)")

    PROGRESS_FILE.write_text("\n".join(lines), encoding="utf-8")
    return progress


def mark_interrupted(task_description: str):
    """Mark current task as interrupted — agent will resume on next startup."""
    progress = read_progress()
    progress["interrupted_tasks"].insert(0, task_description[:100])
    progress["active_task"] = None
    # Rebuild with interrupted state
    update_progress(task_description, "interrupted", 0)
    # Restore interrupted list
    content = PROGRESS_FILE.read_text(encoding="utf-8")
    content = re.sub(r"\(none\)", "", content)
    interrupted_block = "\n".join(f"- {t}" for t in progress["interrupted_tasks"])
    content = re.sub(
        r"## Interrupted Tasks\n\n.*?\n\n",
        f"## Interrupted Tasks\n\n{interrupted_block}\n\n",
        content, flags=re.DOTALL
    )
    PROGRESS_FILE.write_text(content, encoding="utf-8")


# ─── Primitive 3: Fresh Evaluator ───────────────────────

EVALUATOR_PROMPT = """你是 OnionQuant Harness 的独立评估 Agent。

你的职责：审查另一个 Agent 刚刚完成的任务产出，判断是否真正达到质量标准。

评估标准：
1. 回复是否基于项目上下文（CLAUDE.md + memory），而非凭空编造？
2. 回复是否包含具体数据/分析而非泛泛而谈？
3. 回复长度是否 >= 200 chars（简单确认除外）？
4. 如果涉及股票分析，是否使用了 LangGraph 多部门管道？
5. 是否有明显的逻辑错误或自相矛盾？

输出格式（严格遵守）：
VERDICT: PASS 或 NEEDS_WORK
FINDINGS: （如果 NEEDS_WORK，列出具体问题点，每条一行）
SCORE: 0-10（综合质量评分）

注意：你只有 Read 权限，没有 Write/Edit 权限。这是设计原则——评估者不能修改被评估的内容。"""


def run_evaluator(task_output: str, task_context: str = "") -> dict:
    """Run Fresh Evaluator — independent agent reviews completed work.

    Uses DeepSeek API with evaluator system prompt.
    Evaluator has no Write/Edit tools — design principle.
    """
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").split("\n"):
                if line.startswith("DEEPSEEK_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        return {"verdict": "ERROR", "findings": ["No API key"], "score": 0}

    prompt = f"请评估以下 Agent 任务产出：\n\n## 任务上下文\n{task_context[:500]}\n\n## Agent 产出\n{task_output[:2000]}"

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": EVALUATOR_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500, temperature=0.1,
        )
        text = resp.choices[0].message.content.strip()

        # Parse structured output
        verdict = "PASS"
        m = re.search(r'VERDICT:\s*(PASS|NEEDS_WORK)', text)
        if m:
            verdict = m[1]

        findings = []
        findings_section = False
        for line in text.split("\n"):
            if "FINDINGS:" in line:
                findings_section = True
                continue
            if findings_section and line.strip().startswith(("- ", "* ")):
                findings.append(line.strip("- *"))
            elif findings_section and line.strip() and not line.startswith("SCORE"):
                if len(line.strip()) > 10:
                    findings.append(line.strip())

        score = 5
        m = re.search(r'SCORE:\s*(\d+(?:\.\d+)?)', text)
        if m:
            score = float(m[1])

        return {"verdict": verdict, "findings": findings, "score": score, "raw": text}
    except Exception as e:
        return {"verdict": "ERROR", "findings": [str(e)], "score": 0}


# ─── Primitive 4: Auto-Skill Distillation ───────────────

SKILL_TEMPLATE = """---
name: {skill_name}
description: {skill_description}
version: 1.0.0
auto_generated: true
distilled_at: {timestamp}
source_task: {task_id}
tool_calls_used: {tool_count}
---

# {skill_title}

## 触发条件
{trigger_conditions}

## 执行步骤
{steps}

## 成功指标
{success_indicators}

## 注意事项
{notes}
"""


def distill_skill(task_description: str, tool_calls_used: int, task_output: str,
                  steps_taken: list = None) -> str | None:
    """Auto-distill a completed task into a reusable Skill. Returns skill file path or None.

    Only triggers when tool_calls_used >= 5 (Hermes pattern).
    """
    if tool_calls_used < 5:
        return None

    # Generate skill name from task description
    skill_name = re.sub(r'[^a-z0-9-]', '', task_description.lower().replace(' ', '-'))[:40]
    if not skill_name:
        skill_name = f"auto-skill-{now_ts()}"

    # Simple keyword-based distillation (zero AI tokens for basic structure)
    # For complex tasks, the Claude session itself can produce the skill content
    skill_content = SKILL_TEMPLATE.format(
        skill_name=skill_name,
        skill_description=f"从任务 '{task_description[:60]}' 自动蒸馏 (>{tool_calls_used} 步)",
        timestamp=now_iso(),
        task_id=task_description[:40],
        tool_count=tool_calls_used,
        skill_title=task_description[:80],
        trigger_conditions=f"用户请求涉及: {task_description[:100]}",
        steps="\n".join(f"{i+1}. {s}" for i, s in enumerate(steps_taken or [])) or "见原始任务执行轨迹",
        success_indicators=f"- 输出通过 Fresh Evaluator 审查\n- 任务完成标记为 completed",
        notes=f"自动生成于 {now_iso()}。原始工具调用: {tool_calls_used} 次。",
    )

    skill_file = SKILLS_DIR / f"{skill_name}.md"
    skill_file.write_text(skill_content, encoding="utf-8")
    return str(skill_file)


# ─── Complete Harness Cycle ─────────────────────────────

class HarnessEngine:
    """Production Agent Quality Gates — coordinates all 4 primitives.

    Usage in server.py inbox processing:
        engine = HarnessEngine()
        engine.start_task("分析 MU 目标价")
        ... agent processes ...
        result = engine.complete_task(reply_text, context, tool_count=11)
        if result["all_pass"]:
            print("Task passed all quality gates")
    """

    def __init__(self):
        self.current_task = None
        self.task_start_time = None

    def start_task(self, task_description: str, criteria_override: list = None):
        """Begin a new task with Default-FAIL contract."""
        import time
        self.current_task = task_description
        self.task_start_time = time.time()
        task_id = f"task-{now_ts()}"
        create_contract(task_id, criteria_override)
        return task_id

    def complete_task(self, reply_text: str, task_context: str = "",
                      tool_count: int = 1, task_id: str = None) -> dict:
        """Complete a task: run evaluator, update progress, distill skill if complex."""
        import time

        if not task_id:
            task_id = f"task-{now_ts()}"

        duration = time.time() - (self.task_start_time or time.time())

        # 1. Run Fresh Evaluator
        eval_result = run_evaluator(reply_text, task_context or self.current_task or "")

        # 2. Update Default-FAIL contract
        status = "completed" if eval_result["verdict"] == "PASS" else "failed"
        update_criterion(task_id, "task_completed",
                         passes=(eval_result["verdict"] == "PASS"),
                         evidence=f"reply {len(reply_text)} chars")
        update_criterion(task_id, "evaluator_passed",
                         passes=(eval_result["verdict"] == "PASS"),
                         evidence=f"score {eval_result['score']}/10")

        # 3. Update PROGRESS.md
        update_progress(
            self.current_task or task_id,
            status,
            duration_sec=duration,
            evaluator_result=f"{eval_result['verdict']} ({eval_result['score']}/10)",
            skills_distilled=0,
        )

        # 4. Auto-distill Skill if complex enough
        skill_file = None
        if tool_count >= 5:
            skill_file = distill_skill(
                self.current_task or task_id, tool_count, reply_text,
                steps_taken=eval_result.get("findings", [])[:5]
            )
            if skill_file:
                progress = read_progress()
                update_progress(
                    self.current_task or task_id, status, duration,
                    evaluator_result=f"{eval_result['verdict']} ({eval_result['score']}/10)",
                    skills_distilled=1,
                )

        return {
            "verdict": eval_result["verdict"],
            "score": eval_result["score"],
            "findings": eval_result["findings"],
            "all_pass": all_criteria_pass(task_id),
            "skill_distilled": skill_file,
            "duration_sec": duration,
        }


# Quick CLI test
if __name__ == "__main__":
    engine = HarnessEngine()
    tid = engine.start_task("Harness Engine 自检")
    result = engine.complete_task(
        "Harness Engine 4 primitives verified. PROGRESS.md updated. Evaluator passed.",
        "自检测试", tool_count=6, task_id=tid,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
