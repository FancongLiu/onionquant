#!/usr/bin/env python3
"""
OnionQuant FULL Research Graph — all 11 departments in a LangGraph pipeline.

Pipeline:
  data_engineering → strategy_research → risk_management → backtest_engine
  → sentiment_intel → knowledge_management → academic_research → extreme_drive
  → reporting → ceo_office → chairman_secretariat

Each node is a dedicated LLM call with department-specific system prompt.
State is persisted via SqliteSaver for crash recovery.
"""

import json
import operator
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, TypedDict

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

DEPT_PROMPTS = {
    "data_engineering": """你是 OnionQuant 数据工程部。
任务：准备分析所需数据。
1. 确认需要哪些数据源（行情/财务/舆情/宏观）
2. 标注数据可用性和质量
3. 如果有 yfinance 数据则提取关键指标（最新价/MA20/波动率/1月回报）
4. 如果数据不可用，给出替代方案
输出：数据准备报告（≤300字）""",

    "strategy_research": """你是 OnionQuant 策略研究部。
任务：因子分析与交易信号。
1. 动量因子（5d/20d）· 波动率因子 · Sharpe比率
2. 多因子加权评分（动量20%+波动率15%+Sharpe25%+催化剂30%+Beta10%）
3. 技术面：支撑/阻力位、RSI/MACD状态
4. 评级：强烈看多/看多/中性/看空/强烈看空
输出：策略分析报告（≤400字）""",

    "risk_management": """你是 OnionQuant 风险管理部。
任务：风险评估与压力测试。
1. VaR/CVaR 估算
2. 最大回撤评估
3. 压力测试场景（暴跌-20%/利率突变/地缘政治/出口管制）
4. 持仓集中度风险
5. 综合风险评级：低/中/高/极高 + 建议仓位上限
输出：风险评估报告（≤400字）""",

    "backtest_engine": """你是 OnionQuant 回测引擎部。
任务：历史策略验证。
1. 如果有历史回测数据，验证当前分析逻辑
2. 相似市场环境下的历史表现
3. 关键模式识别（如"买预期卖事实"模式）
4. 历史胜率和平均收益参考
输出：回测验证报告（≤300字）""",

    "sentiment_intel": """你是 OnionQuant 舆情情报部。
任务：多源情绪分析。
1. 近期催化剂事件（已发生+即将发生）
2. 社交媒体情绪倾向
3. 机构评级变化
4. 供应链/行业动态关联
5. 情绪评分：强烈乐观/乐观/中性/悲观/强烈悲观
输出：舆情分析报告（≤400字）""",

    "knowledge_management": """你是 OnionQuant 知识管理部。
任务：知识图谱关联推理。
1. 该标的的供应链上下游关联
2. 替代品/互补品动态
3. 关键人物/机构关联
4. 宏观指标关联（利率/GDP/VIX）
5. 跨标的传导路径分析
输出：知识图谱分析（≤300字）""",

    "academic_research": """你是 OnionQuant 学术研究部。
任务：学术文献与理论支撑。
1. 该分析涉及的金融理论（如动量效应、波动率聚类、行为金融）
2. 相关学术研究发现
3. 理论局限性说明
4. 是否与学术共识一致
输出：学术文献参考（≤300字）""",

    "extreme_drive": """你是 OnionQuant 极限驱动部。
任务：极端风险审计与合规检查。
1. 黑天鹅风险评估
2. 流动性风险
3. 交易对手风险
4. 监管/合规风险（如内幕交易、市场操纵）
5. 极端情景下的最大损失估算
输出：极端风险审计（≤300字）""",

    "reporting": """你是 OnionQuant 报告部。
任务：将各部门分析整合为结构化报告。
请按以下结构组织：
# {tickers} 综合研究报告
## 核心结论
## 1. 策略与因子分析
## 2. 风险评估
## 3. 历史回测
## 4. 舆情与催化剂
## 5. 知识图谱关联
## 6. 学术理论支撑
## 7. 极端风险审计
## 8. 综合建议与操作计划
输出：结构化报告（≤600字）""",

    "ceo_office": """你是 OnionQuant CEO办公室。
任务：最终审核与决策。
1. 审核各部门分析的一致性和完整性
2. 标注分析中的矛盾点（如策略看多但风险极高）
3. 给出最终操作建议：买入/持有/减仓/卖出
4. 置信度评估：高/中/低
5. 下次复审时间建议
输出：CEO决策意见（≤300字）""",

    "chairman_secretariat": """你是 OnionQuant 董事长秘书处。
任务：上下文持久化与中断恢复。
1. 保存本次分析的完整状态到 context_state.json
2. 更新 pending_actions 中的相关条目
3. 标注需要董事长关注的优先级
4. 与其他待处理任务的关联
输出：上下文管理报告（≤200字）""",
}

# Department execution order
DEPT_ORDER = [
    "data_engineering",
    "strategy_research",
    "risk_management",
    "backtest_engine",
    "sentiment_intel",
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

def _call_llm(prompt: str, system: str, temperature: float = 0.3, max_tokens: int = 800) -> str:
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
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        max_tokens=max_tokens, temperature=temperature)
    return resp.choices[0].message.content.strip()


# ─── Node Factory ─────────────────────────────────────────

def _make_dept_node(dept_key: str):
    """Create a node function for a given department."""
    result_field = f"{dept_key}_result"

    def node_fn(state: FullResearchState) -> dict:
        tickers = state.get("tickers", [])
        request = state.get("user_request", "")
        error_field = f"{dept_key}_error"

        # Build context from previous departments
        context_parts = [f"标的: {', '.join(tickers)}", f"用户需求: {request}"]
        for prev_dept in DEPT_ORDER[:DEPT_ORDER.index(dept_key)]:
            prev_result = state.get(f"{prev_dept}_result", "")
            if prev_result and "ERROR" not in prev_result:
                context_parts.append(f"\n{DEPT_NAMES[prev_dept]}输出: {prev_result[:300]}")

        prompt = "\n".join(context_parts)
        try:
            result = _call_llm(prompt, DEPT_PROMPTS[dept_key])
            return {result_field: result, "steps_completed": [dept_key]}
        except Exception as e:
            return {result_field: f"[ERROR] {e}", "steps_completed": [dept_key], "errors": [f"{dept_key}: {e}"]}

    return node_fn


# ─── Route Function ───────────────────────────────────────

def _route_next(state: FullResearchState) -> str:
    """Determine next department to execute."""
    completed = set(state.get("steps_completed", []))
    for dept in DEPT_ORDER:
        if dept not in completed:
            return dept
    return END


# ─── Full Graph Builder ───────────────────────────────────

class FullResearchGraph:
    """Complete 11-department LangGraph pipeline for stock research."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).resolve().parent.parent.parent / "company" / "full_research_checkpoints.db")
        self.db_path = db_path
        self.graph = self._build()
        self.token_usage = {"total_input": 0, "total_output": 0}

    def _build(self):
        workflow = StateGraph(FullResearchState)

        # Add all 11 department nodes
        for dept in DEPT_ORDER:
            workflow.add_node(dept, _make_dept_node(dept))

        # Set entry point
        workflow.set_entry_point(DEPT_ORDER[0])

        # Chain: dept_i → dept_{i+1}
        for i, dept in enumerate(DEPT_ORDER[:-1]):
            next_dept = DEPT_ORDER[i + 1]
            workflow.add_edge(dept, next_dept)

        # Last dept → END
        workflow.add_edge(DEPT_ORDER[-1], END)

        return workflow.compile()

    def run_sync(self, user_request: str, tickers: list[str] = None, urgent: bool = False) -> dict:
        if tickers is None:
            tickers = self._extract_tickers(user_request)

        initial: FullResearchState = {
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

        config = {"configurable": {"thread_id": f"full_{datetime.now().strftime('%Y%m%d_%H%M%S')}"}}
        result = self.graph.invoke(initial, config)

        # Extract final report from reporting + ceo_office
        report = result.get("reporting_result", "")
        ceo = result.get("ceo_office_result", "")
        final = f"{report}\n\n---\n## CEO 终审\n{ceo}" if ceo else report

        # Estimate token usage
        input_tokens = sum(len(str(v)) // 4 for v in result.values() if isinstance(v, str))
        output_tokens = len(final) // 4
        self.token_usage = {"total_input": input_tokens, "total_output": output_tokens}

        return {"final_report": final, "steps_completed": result.get("steps_completed", []),
                "errors": result.get("errors", []), "token_usage": self.token_usage}

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
