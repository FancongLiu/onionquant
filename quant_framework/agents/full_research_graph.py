#!/usr/bin/env python3
"""
OnionQuant FULL Research Graph — all 11 departments in a LangGraph pipeline.

Pipeline:
  data_engineering
    ├── strategy_research ──┐
    ├── risk_management ────┤  (parallel)
    └── sentiment_intel ────┘
            ↓
  backtest_engine → knowledge_management → academic_research
  → extreme_drive → reporting → ceo_office → chairman_secretariat

Each node is a dedicated LLM call with department-specific system prompt.
State is persisted via SqliteSaver for crash recovery.
"""

import json
import operator
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph


class FullResearchState(TypedDict):
    """State shared across all 11 department nodes."""
    user_request: str
    tickers: list[str]
    urgent: bool

    # Per-department outputs
    data_engineering_result: str
    strategy_research_result: str
    risk_management_result: str
    backtest_engine_result: str
    sentiment_intel_result: str
    knowledge_management_result: str
    academic_research_result: str
    extreme_drive_result: str
    reporting_result: str
    ceo_office_result: str
    chairman_secretariat_result: str

    # Progress tracking
    route: str
    steps_completed: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
    skipped: list[str]

    # Final output
    final_report: str


# ─── Department System Prompts ───────────────────────────

# Common anti-hallucination suffix appended to data-dependent departments
_NO_FABRICATE = (
    "\n\n⚠ 你没有实时数据访问权限。无法确认的数字标注'需API接入'或使用范围估计"
    "（如'约3-5%'），禁止编造精确价格/MA/波动率/日期。直接输出分析，不打招呼。"
)

DEPT_PROMPTS = {
    "data_engineering": """你是 OnionQuant 数据工程部。
任务：准备分析所需数据。
1. 确认需要的数据源类型（行情/财务/舆情/宏观）
2. 标注各类数据的可用性和质量等级
3. 给出数据获取方案（API/爬虫/人工），标注优先级
4. 数据缺口及替代方案
直接输出结构化报告，用数字编号，每条≤2行。≤300字。"""
    + _NO_FABRICATE,

    "strategy_research": """你是 OnionQuant 策略研究部。
任务：因子分析与交易信号。
1. 动量因子评估（5d/20d方向与强度）
2. 波动率因子（当前波动率vs历史区间）
3. Sharpe比率估算（风险调整后收益）
4. 多因子加权评分（动量20%+波动率15%+Sharpe25%+催化剂30%+Beta10%）
5. 技术面态势（趋势方向、超买超卖、关键位置）
6. 最终评级：强烈看多/看多/中性/看空/强烈看空
直接输出，每项≤3行。≤400字。"""
    + _NO_FABRICATE,

    "risk_management": """你是 OnionQuant 风险管理部。
任务：风险评估与压力测试。
1. VaR/CVaR 范围估计（用范围而非精确值）
2. 最大回撤历史参考
3. 压力测试场景（暴跌/利率/地缘政治/行业特定）
4. 持仓集中度风险
5. 综合评级：低/中/高/极高 + 建议仓位上限
直接输出，不打招呼，每项≤3行。≤400字。""",

    "backtest_engine": """你是 OnionQuant 回测引擎部。
任务：历史策略验证。
1. 当前周期位置判断（类比历史相似周期）
2. 相似市场环境下的历史收益/回撤参考
3. 关键行为模式识别（如"买预期卖事实"）
4. 历史胜率参考区间 + 置信度
直接输出，只给方向性判断不用精确数字。≤300字。""",

    "sentiment_intel": """你是 OnionQuant 舆情情报部。
任务：多源情绪分析。
1. 近期催化剂（已发生+即将发生，标注大致时间如"近期/Q2"）
2. 社交媒体/散户情绪倾向
3. 机构评级方向变化
4. 供应链/行业动态关键信号
5. 综合情绪评分：强烈乐观/乐观/中性/悲观/强烈悲观
直接输出，不编造精确日期或具体推文内容。≤400字。""",

    "knowledge_management": """你是 OnionQuant 知识管理部。
任务：知识图谱关联推理。
1. 供应链上下游关键节点
2. 替代品/互补品竞争态势
3. 关键机构关联（股东/评级/合作伙伴）
4. 宏观指标敏感度（利率/GDP/VIX方向性影响）
5. 跨标的传导路径（谁影响这个标的、谁被它影响）
直接输出，每项1-2行要点。≤300字。""",

    "academic_research": """你是 OnionQuant 学术研究部。
任务：学术理论支撑（极简格式）。
列出3-5条相关金融理论，每条格式：
- **理论名**：适用性（1句）+ 局限性（1句）
最后给一行结论：与学术共识一致/部分一致/存疑。
直接输出，不铺垫不总结。≤300字。""",

    "extreme_drive": """你是 OnionQuant 极限驱动部。
任务：极端风险审计。
1. 黑天鹅风险（≥2个被市场忽略的极端情景）
2. 流动性风险（极端行情下能否退出）
3. 交易对手/供应链中断风险
4. 监管/合规雷点
5. 最坏情景损失估算（范围）
直接输出，不打招呼，每项2-3行。≤300字。""",

    "reporting": """你是 OnionQuant 报告部。
任务：整合各部门分析为结构化报告。
格式（严格遵守）：
# {tickers} 综合研究报告
## 核心结论（2-3句）
## 1. 策略与因子（3-5行要点）
## 2. 风险（3-5行要点）
## 3. 回测验证（2-3行要点）
## 4. 舆情与催化剂（3-5行要点）
## 5. 知识图谱（2-3行要点）
## 6. 学术支撑（1-2行）
## 7. 极端风险（2-3行）
## 8. 综合建议（含仓位、止损、时间窗口）
直接输出报告正文，精炼不啰嗦。≤600字。""",

    "ceo_office": """你是 OnionQuant CEO办公室。
任务：最终审核与决策。
1. 审核各部门分析一致性，标注矛盾点
2. 最终操作建议：买入/持有/减仓/卖出 + 仓位建议
3. 置信度：高/中/低 + 理由
4. 下次复审时间窗口
直接输出决策，不重复已有分析。≤300字。""",

    "chairman_secretariat": """你是 OnionQuant 董事长秘书处。
任务：上下文管理。
1. 本次分析关键结论（≤2句）
2. pending_actions 更新项（具体可执行的动作）
3. 需董事长关注的优先级 + 理由
直接输出，纯行动导向不啰嗦。≤200字。""",
}

# Per-department max_tokens (tighter caps to enforce prompt word limits)
DEPT_MAX_TOKENS = {
    "data_engineering": 500,
    "strategy_research": 600,
    "risk_management": 600,
    "backtest_engine": 450,
    "sentiment_intel": 600,
    "knowledge_management": 500,
    "academic_research": 400,
    "extreme_drive": 500,
    "reporting": 800,
    "ceo_office": 500,
    "chairman_secretariat": 350,
}

# Department execution order (reflects parallel topology: de[0] → de[1:4] parallel → de[4:] sequential)
DEPT_ORDER = [
    "data_engineering",
    "strategy_research",
    "risk_management",
    "sentiment_intel",
    "backtest_engine",
    "knowledge_management",
    "academic_research",
    "extreme_drive",
    "reporting",
    "ceo_office",
    "chairman_secretariat",
]

# Human-readable names
DEPT_NAMES = {
    "data_engineering": "数据工程部",
    "strategy_research": "策略研究部",
    "risk_management": "风险管理部",
    "backtest_engine": "回测引擎部",
    "sentiment_intel": "舆情情报部",
    "knowledge_management": "知识管理部",
    "academic_research": "学术研究部",
    "extreme_drive": "极限驱动部",
    "reporting": "报告部",
    "ceo_office": "CEO办公室",
    "chairman_secretariat": "董事长秘书处",
}


# ─── LLM Call ────────────────────────────────────────────

def _call_llm(prompt: str, system: str, temperature: float = 0.3, max_tokens: int = 800,
              max_retries: int = 2, timeout: float = 60.0) -> str:
    """Call DeepSeek LLM with retry on transient failures. Max 2 retries, exponential backoff."""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        env_file = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").split("\n"):
                if line.startswith("DEEPSEEK_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        return "[ERROR] No DEEPSEEK_API_KEY"

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=timeout)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                max_tokens=max_tokens, temperature=temperature)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt  # 1s, 2s backoff
                time.sleep(wait)
    raise last_error


# ─── Node Factory ─────────────────────────────────────────

def _make_dept_node(dept_key: str):
    """Create a node function for a given department with error recovery.

    Node failures are recorded in state.errors but never crash the pipeline.
    Downstream nodes receive 'upstream failed' context so they can adapt.
    LLM calls get up to 2 retries with exponential backoff before giving up.
    """
    result_field = f"{dept_key}_result"

    def node_fn(state: FullResearchState) -> dict:
        tickers = state.get("tickers", [])
        request = state.get("user_request", "")
        existing_errors = state.get("errors", [])

        # Build context from all completed departments (dynamic — handles parallel topology)
        context_parts = [f"标的: {', '.join(tickers)}", f"用户需求: {request}"]
        skipped_deps = []
        for d in DEPT_ORDER:
            if d == dept_key:
                continue
            prev_result = state.get(f"{d}_result", "")
            if not prev_result:
                continue
            if "ERROR" in prev_result or "[SKIPPED]" in prev_result:
                skipped_deps.append(DEPT_NAMES.get(d, d))
                continue
            context_parts.append(f"\n{DEPT_NAMES[d]}输出: {prev_result[:300]}")

        if skipped_deps:
            context_parts.insert(1, f"⚠ 上游部门分析失败/跳过: {', '.join(skipped_deps)}。请在缺失信息的情况下独立完成分析。")

        prompt = "\n".join(context_parts)
        max_tok = DEPT_MAX_TOKENS.get(dept_key, 600)
        try:
            result = _call_llm(prompt, DEPT_PROMPTS[dept_key], max_tokens=max_tok)
            return {result_field: result, "steps_completed": [dept_key]}
        except Exception as e:
            skip_msg = f"[SKIPPED] {dept_key}: {e} (retried 2x, pipeline continues)"
            return {result_field: skip_msg, "steps_completed": [dept_key], "errors": [f"{dept_key}: {e}"],
                    "skipped": [dept_key]}

    return node_fn


# ─── Full Graph Builder ───────────────────────────────────

class FullResearchGraph:
    """Complete 11-department LangGraph pipeline for stock research."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).resolve().parent.parent.parent / "company" / "full_research_checkpoints.db")
        self.db_path = db_path
        self._db_conn = sqlite3.connect(db_path, check_same_thread=False)
        self.checkpointer = SqliteSaver(self._db_conn)
        self.graph = self._build()
        self.token_usage = {"total_input": 0, "total_output": 0}

    def _build(self):
        workflow = StateGraph(FullResearchState)

        # Add all 11 department nodes
        for dept in DEPT_ORDER:
            workflow.add_node(dept, _make_dept_node(dept))

        # Set entry point
        workflow.set_entry_point("data_engineering")

        # Fan-out: data_engineering → 3 parallel depts
        workflow.add_edge("data_engineering", "strategy_research")
        workflow.add_edge("data_engineering", "risk_management")
        workflow.add_edge("data_engineering", "sentiment_intel")

        # Fan-in: all 3 converge at backtest_engine
        workflow.add_edge("strategy_research", "backtest_engine")
        workflow.add_edge("risk_management", "backtest_engine")
        workflow.add_edge("sentiment_intel", "backtest_engine")

        # Sequential chain: backtest_engine → ... → chairman_secretariat → END
        sequential = ["backtest_engine", "knowledge_management", "academic_research",
                      "extreme_drive", "reporting", "ceo_office", "chairman_secretariat"]
        for i, dept in enumerate(sequential[:-1]):
            workflow.add_edge(dept, sequential[i + 1])
        workflow.add_edge("chairman_secretariat", END)

        return workflow.compile(checkpointer=self.checkpointer)

    def run_sync(self, user_request: str, tickers: list[str] = None, urgent: bool = False,
                 resume: bool = False) -> dict:
        if tickers is None:
            tickers = self._extract_tickers(user_request)

        # Deterministic thread_id per ticker set — enables checkpoint resume across restarts
        ticker_key = "_".join(sorted(tickers)) if tickers else "SPY"
        thread_id = f"full_{ticker_key}"

        # Check for existing checkpoint
        existing_state = None
        if resume:
            existing_state = self._load_checkpoint(thread_id)

        if existing_state and existing_state.get("steps_completed"):
            # Resume from checkpoint — skip already-completed nodes
            initial = existing_state
        else:
            initial = {
                "user_request": user_request, "tickers": tickers, "urgent": urgent,
                "route": DEPT_ORDER[0], "steps_completed": [], "errors": [], "skipped": [],
                "final_report": "",
                **{f"{d}_result": "" for d in DEPT_ORDER},
                "data_engineering_result": "", "strategy_research_result": "",
                "risk_management_result": "", "backtest_engine_result": "",
                "sentiment_intel_result": "", "knowledge_management_result": "",
                "academic_research_result": "", "extreme_drive_result": "",
                "reporting_result": "", "ceo_office_result": "", "chairman_secretariat_result": "",
            }

        config = {"configurable": {"thread_id": thread_id}}
        result = self.graph.invoke(initial, config)

        # Extract final report from reporting + ceo_office
        report = result.get("reporting_result", "")
        ceo = result.get("ceo_office_result", "")
        final = f"{report}\n\n---\n## CEO 终审\n{ceo}" if ceo else report

        # Estimate token usage
        input_tokens = sum(len(str(v)) // 4 for v in result.values() if isinstance(v, str))
        output_tokens = len(final) // 4
        self.token_usage = {"total_input": input_tokens, "total_output": output_tokens}

        dept_outputs = {f"{d}_result": result.get(f"{d}_result", "") for d in DEPT_ORDER}
        return {"final_report": final, "steps_completed": result.get("steps_completed", []),
                "errors": result.get("errors", []), "token_usage": self.token_usage,
                "skipped": result.get("skipped", []), **dept_outputs}

    def _load_checkpoint(self, thread_id: str) -> dict | None:
        """Load most recent checkpoint state for a given thread_id. Returns None if no checkpoint exists."""
        try:
            config = {"configurable": {"thread_id": thread_id}}
            state = self.graph.get_state(config)
            if state and state.values:
                return {**state.values}
        except Exception:
            pass
        return None

    def _extract_tickers(self, text: str) -> list[str]:
        ticker_map = {
            "nvda": "NVDA", "amd": "AMD", "mu": "MU", "intc": "INTC", "dxyz": "DXYZ",
            "tsla": "TSLA", "aapl": "AAPL", "msft": "MSFT", "googl": "GOOGL",
            "meta": "META", "amzn": "AMZN", "smh": "SMH", "sox": "SOX",
            "qqq": "QQQ", "spy": "SPY", "vix": "VIX",
        }
        found = set()
        for key, ticker in ticker_map.items():
            if key in text.lower():
                found.add(ticker)
        for match in re.findall(r'\b[A-Z]{2,5}\b', text):
            if match not in ("CEO", "API", "ETF", "IPO", "USD"):
                found.add(match)
        return sorted(found) if found else ["SPY"]


def run_full_research(user_request: str, tickers: list[str] = None, urgent: bool = False) -> str:
    graph = FullResearchGraph()
    result = graph.run_sync(user_request, tickers=tickers, urgent=urgent)
    return result.get("final_report", "[ERROR]")
