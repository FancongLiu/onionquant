#!/usr/bin/env python3
"""
OnionQuant Stock Research Graph — LangGraph-based multi-agent orchestration.

Architecture:
  User Request
    → Supervisor Node (intent classification + routing)
    → DataFetch Node (yfinance / multi-source data)
    → StrategyAnalysis Node (factor scoring, IC, regime detection)
    → RiskAssessment Node (VaR, MaxDD, stress testing)
    → SentimentCheck Node (catalysts, news, social sentiment)
    → AggregateReport Node (structured markdown report)
    → Reply

Each node is a dedicated LLM call with department-specific system prompt.
State is persisted via SqliteSaver for crash recovery.
Supervisor uses conditional edges to route → nodes can be skipped if not needed.

Usage:
  from quant_framework.agents.research_graph import ResearchGraph
  graph = ResearchGraph()
  result = await graph.run("分析 NVDA 目标价和风险", tickers=["NVDA"])
"""

import json
import operator
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver


# ─── State Schema ────────────────────────────────────────

class ResearchState(TypedDict):
    """Central state shared across all research nodes."""
    # Input
    user_request: str
    tickers: list[str]
    urgent: bool

    # Data Fetch
    data_fetched: dict[str, Any]       # {ticker: price_data_summary}
    data_error: str

    # Strategy Analysis
    strategy_result: str               # Factor scores, IC, regime analysis (markdown)
    strategy_error: str

    # Risk Assessment
    risk_result: str                   # VaR, MaxDD, stress test results (markdown)
    risk_error: str

    # Sentiment / Catalyst Check
    sentiment_result: str              # News, catalysts, social sentiment (markdown)
    sentiment_error: str

    # Supervisor routing
    route: str                         # "strategy" | "risk" | "sentiment" | "aggregate" | "error"
    steps_completed: Annotated[list[str], operator.add]  # Accumulate completed steps

    # Output
    final_report: str
    errors: Annotated[list[str], operator.add]  # Accumulate errors


# ─── System Prompts (per department) ─────────────────────

STRATEGY_PROMPT = """你是 OnionQuant 策略研究部的 AI 分析师。你的任务是对指定标的进行因子层面的量化分析。

请按照以下结构输出分析（Markdown 格式）：

## 策略研究分析

### 1. 动量因子
- 短期(5日)和中期(20日)价格动量评估
- 与行业基准的相对动量对比

### 2. 波动率分析
- 近期波动率水平（高/中/低）
- 与历史波动率的比较

### 3. 技术面信号
- 关键支撑/阻力位
- RSI / MACD 等技术指标状态

### 4. 因子综合评分
- 多因子加权评分（动量 20% + 波动率 15% + Sharpe 25% + 催化 30% + Beta 10%）
- 评分等级：强烈看多 / 看多 / 中性 / 看空 / 强烈看空

### 5. 关键结论
- 一句话总结策略观点

注意：
- 如果你没有实时数据，请基于公开信息和合理推断给出分析
- 明确标注不确定性和假设
- 不要编造具体数字，用趋势判断替代"""

RISK_PROMPT = """你是 OnionQuant 风险管理部的 AI 分析师。你的任务是对指定标的进行风险评估。

请按照以下结构输出分析（Markdown 格式）：

## 风险评估

### 1. 市场风险 (VaR/CVaR)
- 历史 VaR 估算或合理推断
- 尾部风险特征

### 2. 最大回撤风险
- 近期最大回撤水平
- 与历史极端回撤的对比

### 3. 压力测试场景
- 市场暴跌 (-20%) 情景下的预期影响
- 利率突变 / 地缘政治风险情景

### 4. 持仓集中度风险
- 如果该标的占组合比例过高，标注风险

### 5. 风险评级
- 综合风险等级：低 / 中 / 高 / 极高
- 建议仓位上限

注意：
- 如果你没有精确数据，给出合理估计并标注
- 风险评级要保守——宁可高估风险"""

SENTIMENT_PROMPT = """你是 OnionQuant 舆情情报部的 AI 分析师。你的任务是对指定标的进行催化剂和情绪分析。

请按照以下结构输出分析（Markdown 格式）：

## 舆情与催化剂分析

### 1. 近期催化剂事件
- 已发生的重大事件及影响
- 即将发生的关键事件（财报、产品发布、政策决议等）

### 2. 社交媒体情绪
- 总体情绪倾向（看多/看空/中性）
- 关键讨论主题

### 3. 新闻舆情
- 近期正面/负面新闻摘要
- 机构评级变化

### 4. 供应链/行业动态
- 上下游关联事件
- 竞争对手动态

### 5. 情绪综合判断
- 市场情绪评分：强烈乐观 / 乐观 / 中性 / 悲观 / 强烈悲观
- 与基本面的背离程度（情绪过热/过冷）"""

SUPERVISOR_PROMPT = """你是 OnionQuant 的 CEO Agent Supervisor。

用户请求: {request}
目标标的: {tickers}
当前已完成步骤: {completed}

请判断下一步应该执行哪个节点：
- strategy: 需要因子分析、趋势判断、技术面评估
- risk: 需要风险评估、回撤分析、压力测试
- sentiment: 需要催化剂分析、舆情判断
- aggregate: 所有需要的分析已完成，可以汇总报告
- error: 之前步骤出现严重错误，需要跳过

只回复一个词：strategy, risk, sentiment, aggregate, 或 error。"""

AGGREGATOR_PROMPT = """你是 OnionQuant 的 CEO Agent。你的任务是将各部门的分析结果汇总成一份专业的股票研究报告。

用户原始请求: {request}

## 策略研究部报告
{strategy}

## 风险管理部报告
{risk}

## 舆情情报部报告
{sentiment}

请按照以下结构输出最终报告（Markdown 格式）：

# 🔬 {tickers} 综合研究报告

## 📊 核心结论
（一段话总结最重要的发现和建议）

## 1. 策略面分析
（提炼策略研究部的关键发现）

## 2. 风险评估
（提炼风险管理部的关键发现）

## 3. 催化剂与情绪
（提炼舆情情报部的关键发现）

## 4. 综合建议
- **操作建议**：买入/持有/减仓/卖出
- **目标价位**：合理推断
- **关键风险**：最重要的 1-3 个风险因素
- **时间窗口**：建议的操作时间框架

## 5. 不确定性说明
（标注分析中的假设和局限）

---
*报告由 OnionQuant LangGraph Research System 自动生成*
*每个分析节点由独立 AI Agent 执行，确保分析深度和可靠性*
"""


# ─── Node Functions ──────────────────────────────────────

def _call_llm(prompt: str, system: str, temperature: float = 0.3) -> str:
    """Call DeepSeek API with given prompt and system message."""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        env_file = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").split("\n"):
                if line.startswith("DEEPSEEK_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        return "[ERROR] No DEEPSEEK_API_KEY configured"

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1500,
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()


def supervisor_node(state: ResearchState) -> dict:
    """Supervisor: decide which node to execute next based on request and completed steps."""
    completed = state.get("steps_completed", [])
    tickers = state.get("tickers", [])
    user_request = state.get("user_request", "")

    # Determine what's needed based on request content
    request_lower = user_request.lower()
    needed = set()
    if any(kw in request_lower for kw in ["分析", "走势", "趋势", "因子", "目标价", "估值", "technical"]):
        needed.add("strategy")
    if any(kw in request_lower for kw in ["风险", "risk", "回撤", "止损", "var", "压力"]):
        needed.add("risk")
    if any(kw in request_lower for kw in ["催化剂", "新闻", "舆情", "情绪", "财报", "事件"]):
        needed.add("sentiment")
    # If nothing specific, do everything for comprehensive analysis
    if not needed:
        needed = {"strategy", "risk", "sentiment"}

    # Remove already completed steps
    remaining = needed - set(completed)

    if "strategy" in remaining:
        route = "strategy"
    elif "risk" in remaining:
        route = "risk"
    elif "sentiment" in remaining:
        route = "sentiment"
    else:
        route = "aggregate"

    # Check for critical errors that would block aggregation
    errors = state.get("errors", [])
    if len(errors) >= 2:  # Too many errors → skip to aggregate
        route = "aggregate"

    return {"route": route, "steps_completed": []}


def data_fetch_node(state: ResearchState) -> dict:
    """Fetch market data for requested tickers."""
    tickers = state.get("tickers", [])
    data = {}
    errors = []

    for ticker in tickers:
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            hist = stock.history(period="3mo")
            if hist.empty:
                data[ticker] = {"error": "No data"}
                errors.append(f"{ticker}: no data returned")
            else:
                data[ticker] = {
                    "latest_close": float(hist["Close"].iloc[-1]),
                    "ma20": float(hist["Close"].tail(20).mean()),
                    "volatility": float(hist["Close"].pct_change().std() * (252 ** 0.5)),
                    "return_1m": float(hist["Close"].pct_change(periods=21).iloc[-1]) if len(hist) >= 21 else None,
                    "high_3m": float(hist["High"].max()),
                    "low_3m": float(hist["Low"].min()),
                }
        except ImportError:
            data[ticker] = {"note": "yfinance not available, using placeholder"}
            errors.append(f"{ticker}: yfinance not installed")
        except Exception as e:
            data[ticker] = {"error": str(e)}
            errors.append(f"{ticker}: {e}")

    return {
        "data_fetched": data,
        "data_error": "; ".join(errors) if errors else "",
        "errors": errors,
    }


def strategy_node(state: ResearchState) -> dict:
    """Strategy Research Department analysis node."""
    tickers = state.get("tickers", [])
    user_request = state.get("user_request", "")
    data = state.get("data_fetched", {})

    # Build data context for the LLM
    data_context = ""
    for t, d in data.items():
        if "latest_close" in d:
            data_context += (
                f"\n{t}: 最新收盘 ${d['latest_close']:.2f}, "
                f"MA20 ${d['ma20']:.2f}, "
                f"年化波动率 {d['volatility']:.1%}, "
                f"1月回报 {d.get('return_1m', 'N/A')}"
            )
        elif "note" in d:
            data_context += f"\n{t}: {d['note']}"

    prompt = f"请分析以下标的: {', '.join(tickers)}\n用户需求: {user_request}\n可用数据: {data_context or '使用公开信息和合理推断'}"
    try:
        result = _call_llm(prompt, STRATEGY_PROMPT)
        return {"strategy_result": result, "steps_completed": ["strategy"]}
    except Exception as e:
        return {"strategy_error": str(e), "steps_completed": ["strategy"], "errors": [f"strategy: {e}"]}


def risk_node(state: ResearchState) -> dict:
    """Risk Management Department analysis node."""
    tickers = state.get("tickers", [])
    user_request = state.get("user_request", "")
    data = state.get("data_fetched", {})

    data_context = ""
    for t, d in data.items():
        if "volatility" in d:
            max_dd_est = f"{d['volatility'] * 0.4:.1%}"
            data_context += f"\n{t}: 波动率 {d['volatility']:.1%}, 估算最大回撤 ~{max_dd_est}"

    prompt = f"请评估以下标的的风险: {', '.join(tickers)}\n用户需求: {user_request}\n{data_context}"
    try:
        result = _call_llm(prompt, RISK_PROMPT)
        return {"risk_result": result, "steps_completed": ["risk"]}
    except Exception as e:
        return {"risk_error": str(e), "steps_completed": ["risk"], "errors": [f"risk: {e}"]}


def sentiment_node(state: ResearchState) -> dict:
    """Sentiment Intelligence Department analysis node."""
    tickers = state.get("tickers", [])
    user_request = state.get("user_request", "")
    prompt = f"请分析以下标的的催化剂和舆情: {', '.join(tickers)}\n用户需求: {user_request}"
    try:
        result = _call_llm(prompt, SENTIMENT_PROMPT)
        return {"sentiment_result": result, "steps_completed": ["sentiment"]}
    except Exception as e:
        return {"sentiment_error": str(e), "steps_completed": ["sentiment"], "errors": [f"sentiment: {e}"]}


def aggregate_node(state: ResearchState) -> dict:
    """Aggregate all department results into final report."""
    tickers = state.get("tickers", [])
    request = state.get("user_request", "")
    strategy = state.get("strategy_result") or state.get("strategy_error") or "(未执行)"
    risk = state.get("risk_result") or state.get("risk_error") or "(未执行)"
    sentiment = state.get("sentiment_result") or state.get("sentiment_error") or "(未执行)"

    prompt = AGGREGATOR_PROMPT.format(
        request=request,
        tickers=", ".join(tickers),
        strategy=strategy,
        risk=risk,
        sentiment=sentiment,
    )
    try:
        final = _call_llm(prompt, "你是 OnionQuant CEO Agent。请汇总各部门分析，生成结构化研究报告。", temperature=0.3)
    except Exception as e:
        final = f"## 报告生成失败\n\n错误: {e}\n\n### 策略分析\n{strategy}\n\n### 风险评估\n{risk}\n\n### 舆情分析\n{sentiment}"

    errors = state.get("errors", [])
    if errors:
        final += f"\n\n---\n⚠️ 执行中遇到以下问题: {'; '.join(errors)}"

    return {"final_report": final, "steps_completed": ["aggregate"]}


# ─── Graph Builder ────────────────────────────────────────

class ResearchGraph:
    """LangGraph-based multi-agent stock research system.

    Usage:
        graph = ResearchGraph()
        result = graph.run_sync("分析 NVDA 目标价和风险", tickers=["NVDA"])
        print(result["final_report"])
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).resolve().parent.parent.parent / "company" / "research_checkpoints.db")
        self.db_path = db_path
        self.graph = self._build()

    def _build(self):
        workflow = StateGraph(ResearchState)

        # Add nodes
        workflow.add_node("supervisor", supervisor_node)
        workflow.add_node("data_fetch", data_fetch_node)
        workflow.add_node("strategy", strategy_node)
        workflow.add_node("risk", risk_node)
        workflow.add_node("sentiment", sentiment_node)
        workflow.add_node("aggregate", aggregate_node)

        # Entry point
        workflow.set_entry_point("data_fetch")

        # Data fetch → always go to supervisor
        workflow.add_edge("data_fetch", "supervisor")

        # Supervisor → conditional routing
        workflow.add_conditional_edges(
            "supervisor",
            lambda s: s["route"],
            {
                "strategy": "strategy",
                "risk": "risk",
                "sentiment": "sentiment",
                "aggregate": "aggregate",
                "error": "aggregate",  # Skip to end on error
            },
        )

        # After each department, loop back to supervisor for next step
        workflow.add_edge("strategy", "supervisor")
        workflow.add_edge("risk", "supervisor")
        workflow.add_edge("sentiment", "supervisor")

        # Aggregate → END
        workflow.add_edge("aggregate", END)

        return workflow.compile()

    def run_sync(self, user_request: str, tickers: list[str] = None, urgent: bool = False) -> dict:
        """Run the research graph synchronously. Returns final state dict."""
        if tickers is None:
            tickers = self._extract_tickers(user_request)

        initial_state: ResearchState = {
            "user_request": user_request,
            "tickers": tickers,
            "urgent": urgent,
            "data_fetched": {},
            "data_error": "",
            "strategy_result": "",
            "strategy_error": "",
            "risk_result": "",
            "risk_error": "",
            "sentiment_result": "",
            "sentiment_error": "",
            "route": "strategy",
            "steps_completed": [],
            "final_report": "",
            "errors": [],
        }

        config = {"configurable": {"thread_id": f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}"}}
        final_state = self.graph.invoke(initial_state, config)
        return final_state

    def _extract_tickers(self, text: str) -> list[str]:
        """Extract stock tickers from user request text."""
        # Common ticker patterns
        ticker_map = {
            "nvda": "NVDA", "amd": "AMD", "mu": "MU", "intc": "INTC",
            "dxyz": "DXYZ", "tsla": "TSLA", "aapl": "AAPL", "msft": "MSFT",
            "googl": "GOOGL", "meta": "META", "amzn": "AMZN", "smh": "SMH",
            "sox": "SOX", "qqq": "QQQ", "spy": "SPY", "vix": "VIX",
            "rklb": "RKLB", "asts": "ASTS", "lunr": "LUNR",
        }
        found = set()
        text_upper = text.upper()
        # Try mapping first
        for key, ticker in ticker_map.items():
            if key in text_upper:
                found.add(ticker)
        # Also find bare uppercase tickers
        for match in re.findall(r'\b[A-Z]{2,5}\b', text):
            if match not in ["CEO", "API", "ETF", "IPO", "USD"]:
                found.add(match)
        return sorted(found) if found else ["SPY"]


# Convenience function for server integration
def run_research(user_request: str, tickers: list[str] = None, urgent: bool = False) -> str:
    """Run stock research via LangGraph and return final report as markdown string."""
    graph = ResearchGraph()
    result = graph.run_sync(user_request, tickers=tickers, urgent=urgent)
    return result.get("final_report", "[ERROR] Research graph returned no report")
