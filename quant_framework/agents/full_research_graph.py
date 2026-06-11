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

import asyncio
import json
import operator
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, TypedDict

import numpy as np
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

try:
    from stigmergy import StigmergyScheduler, TaskSpec, DispatchResult
    _STIGMERGY_AVAILABLE = True
except ImportError:
    _STIGMERGY_AVAILABLE = False


def _merge_dicts(left: dict, right: dict) -> dict:
    """Reducer for merging confidence_scores dict from parallel nodes."""
    merged = {**left}
    merged.update(right)
    return merged


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

    # Per-department confidence scores (0.0-10.0, parsed from LLM output)
    # Uses dict merge reducer so parallel nodes (strategy/risk/sentiment) can update concurrently
    confidence_scores: Annotated[dict[str, float], _merge_dicts]

    # Progress tracking
    route: str
    steps_completed: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
    skipped: Annotated[list[str], operator.add]

    # Irrelevant departments pre-classified by keyword heuristics (zero-token)
    irrelevant_depts: list[str]

    # Real market data (populated by data_engineering via yfinance/empyrical/risk_threshold_engine)
    market_data: dict[str, Any]
    risk_metrics: dict[str, Any]

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
任务：基于已获取的实时行情数据，完成数据准备分析。
提示中已包含 yfinance 实时行情数据，直接基于这些数据做分析。
1. 评估数据质量和完整性（有多少天数据、是否有缺口）
2. 判断当前价格处于什么区间（vs MA20，MA50）
3. 近期趋势方向（1月/3月涨跌幅）
4. 数据缺口（如缺少财务数据、舆情数据），建议补充方案
直接输出，每条≤2行。≤300字。""",

    "strategy_research": """你是 OnionQuant 策略研究部。
任务：因子分析与交易信号。提示中已包含实时行情和风险指标，直接使用。
1. 动量因子评估（基于实际1月/3月收益判断方向与强度）
2. 波动率因子（基于实际年化波动率判断风险水平）
3. Sharpe比率评估（基于实际Sharpe值判断风险调整后收益质量）
4. 多因子加权评分（动量20%+波动率15%+Sharpe25%+催化剂30%+Beta10%）
5. 技术面态势（MA20/MA50位置关系、超买超卖、关键价格位）
6. 最终评级：强烈看多/看多/中性/看空/强烈看空
直接输出，每项≤3行。≤400字。""",

    "risk_management": """你是 OnionQuant 风险管理部。
任务：风险评估与压力测试。提示中已包含 empyrical 计算的真实风险指标和 RTE 评分。
1. VaR/CVaR / 最大回撤（基于实际数据解读）
2. 风险调整收益评估（Sharpe/Calmar 实际值）
3. 压力测试场景（暴跌/利率/地缘政治/行业特定）
4. 仓位建议（基于 RTE 市场状态和综合评分）
5. 综合评级：低/中/高/极高 + 建议仓位上限
直接输出，每项≤3行。≤400字。""",

    "backtest_engine": """你是 OnionQuant 回测引擎部。极简模式。
1. 当前周期类比（1句）
2. 关键行为模式（1句，如"买预期卖事实"）
3. 历史胜率方向（偏多/偏空/不确定）
直接输出，不用精确数字。≤150字。""",

    "sentiment_intel": """你是 OnionQuant 舆情情报部。
任务：多源情绪分析。
1. 近期催化剂（已发生+即将发生，标注大致时间如"近期/Q2"）
2. 社交媒体/散户情绪倾向
3. 机构评级方向变化
4. 供应链/行业动态关键信号
5. 综合情绪评分：强烈乐观/乐观/中性/悲观/强烈悲观
直接输出，不编造精确日期或具体推文内容。≤400字。""",

    "knowledge_management": """你是 OnionQuant 知识管理部。极简模式。
1. 关键供应链/竞争节点（1句）
2. 宏观敏感度方向（利率/GDP/VIX，1句）
3. 跨标的传导（1句）
直接输出要点，不展开。≤150字。""",

    "academic_research": """你是 OnionQuant 学术研究部。极简模式。
列出2-3条最相关金融理论，每条≤1行。
结尾一行结论：与学术共识一致/存疑。
≤150字。""",

    "extreme_drive": """你是 OnionQuant 极限驱动部。极简模式。
1. 黑天鹅风险（1-2个被忽略的极端情景，各1句）
2. 流动性/监管风险（1句）
3. 最坏损失范围（1个区间）
≤150字。""",

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

    "chairman_secretariat": """你是 OnionQuant 董事长秘书处。极简模式。
1. 关键结论（1句）
2. 需董事长行动项（1-2条）
≤100字。""",
}

# Per-department max_tokens (tighter caps to enforce prompt word limits)
DEPT_MAX_TOKENS = {
    # Critical departments — full analysis
    "data_engineering": 500,
    "strategy_research": 600,
    "risk_management": 600,
    "sentiment_intel": 600,
    "reporting": 800,
    "ceo_office": 500,
    # Non-critical departments — reduced caps (~40% savings, P3-11)
    "backtest_engine": 250,
    "knowledge_management": 300,
    "academic_research": 250,
    "extreme_drive": 300,
    "chairman_secretariat": 200,
}

# Confidence scoring instruction appended to every department prompt
_CONFIDENCE_INSTRUCTION = (
    "\n\n最后一行必须输出置信度评分：`[置信度: X.X/10]`。"
    "评判标准：数据质量(0-3分)+信号强度(0-3分)+推理链稳健性(0-4分)。"
)

# Regex to parse confidence score from LLM output
_CONFIDENCE_RE = re.compile(r'置信度[：:]\s*(-?\d+(?:\.\d+)?)\s*/\s*10')


def _parse_confidence(text: str) -> tuple[str, float | None]:
    """Extract confidence score from department output.

    Returns (cleaned_text, score). score is a float 0-10 or None if unparseable.
    The confidence line is stripped from cleaned_text.
    """
    if not text:
        return text, None
    m = list(_CONFIDENCE_RE.finditer(text))
    if not m:
        return text, None
    last_match = m[-1]
    try:
        score = float(last_match.group(1))
        score = max(0.0, min(10.0, score))
    except (ValueError, IndexError):
        return text, None
    # Strip the confidence line(s) from output
    cleaned = _CONFIDENCE_RE.sub("", text)
    # Remove trailing blank lines
    cleaned = cleaned.rstrip()
    return cleaned, score


def _classify_irrelevant_departments(user_request: str, tickers: list[str]) -> list[str]:
    """Zero-token keyword classifier: determine which departments are irrelevant.

    Saves 10-20% LLM tokens by skipping departments that add no value for the query type.
    Never skips core departments: data_engineering, reporting, ceo_office, chairman_secretariat.
    """
    text = user_request.lower()
    has_tickers = bool(tickers) and tickers != ["SPY"]

    # Query type signals
    is_macro_only = any(kw in text for kw in (
        "宏观", "macro", "fed", "美联储", "利率", "加息", "降息",
        "gdp", "通胀", "cpi", "ppi", "经济", "recession", "衰退",
        "非农", "失业率", "货币政策"
    )) and not has_tickers

    is_quick = any(kw in text for kw in (
        "快速", "简要", "quick", "brief", "简单", "一句话", "极简"
    ))

    is_event = any(kw in text for kw in (
        "财报", "earnings", "发射", "launch", "ipo", "并购",
        "merger", "罢工", "strike", "分红", "dividend", "拆股", "split"
    ))

    is_pure_technical = any(kw in text for kw in (
        "技术面", "technical", "ma", "macd", "rsi", "布林", "bollinger"
    )) and not any(kw in text for kw in ("舆情", "sentiment", "情绪", "新闻", "news"))

    irrelevant = set()

    # Academic research: financial theories rarely actionable for real-time/event queries
    if is_quick or is_event or is_macro_only:
        irrelevant.add("academic_research")

    # Knowledge management: supply chain / macro sensitivity — heavy for quick queries
    if is_quick:
        irrelevant.add("knowledge_management")

    # Extreme drive: black swan analysis — heavy for quick queries
    if is_quick:
        irrelevant.add("extreme_drive")

    # Backtest engine: needs historical price data — skip for macro-only
    if is_macro_only:
        irrelevant.add("backtest_engine")
        irrelevant.add("strategy_research")
        irrelevant.add("risk_management")

    # Sentiment intel: skip for pure technical queries (user wants charts, not news)
    if is_pure_technical and not is_event:
        irrelevant.add("sentiment_intel")

    # Never skip these core departments
    for essential in ("data_engineering", "reporting", "ceo_office", "chairman_secretariat"):
        irrelevant.discard(essential)

    return sorted(irrelevant)


# Non-critical departments parallelized via StigmergyScheduler (P3-14)
_STIGMERGY_BATCH_DEPTS = ["knowledge_management", "academic_research", "extreme_drive"]

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


# ─── Real Market Data Tools ─────────────────────────────

def _fetch_market_data(tickers: list[str]) -> dict[str, dict]:
    """Fetch real market data via yfinance for each ticker.

    Returns dict keyed by ticker with price, returns, and volatility stats.
    Gracefully skips tickers that fail — never blocks the pipeline.
    """
    try:
        import yfinance as yf
    except ImportError:
        return {"_error": "yfinance not installed"}

    results = {}
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker.upper())
            hist = stock.history(period="6mo")
            if hist.empty:
                results[ticker] = {"error": f"no data for {ticker}"}
                continue
            closes = hist["Close"].values.astype(float)
            log_returns = np.diff(np.log(np.maximum(closes, 1e-10)))
            n = len(closes)
            results[ticker] = {
                "ticker": ticker.upper(),
                "latest_price": round(float(closes[-1]), 2),
                "ma20": round(float(np.mean(closes[-20:])), 2) if n >= 20 else None,
                "ma50": round(float(np.mean(closes[-50:])), 2) if n >= 50 else None,
                "volatility_ann_pct": round(float(np.std(log_returns) * np.sqrt(252)) * 100, 1),
                "return_1m_pct": round(float((closes[-1] / closes[-21] - 1) * 100), 2) if n >= 21 else None,
                "return_3m_pct": round(float((closes[-1] / closes[-63] - 1) * 100), 2) if n >= 63 else None,
                "return_ytd_pct": round(float((closes[-1] / closes[0] - 1) * 100), 2),
                "n_days": n,
                "max_dd_pct": round(float(np.min(closes / np.maximum.accumulate(closes) - 1)) * 100, 2),
            }
        except Exception as e:
            results[ticker] = {"error": str(e)[:200]}
    return results


def _compute_risk_metrics(market_data: dict[str, dict]) -> dict[str, dict]:
    """Compute risk metrics from fetched market data using empyrical + risk_threshold_engine.

    Returns dict keyed by ticker with Sharpe, VaR, Calmar, factor scores, and regime.
    """
    try:
        import empyrical as ep
    except ImportError:
        import empyrical_reloaded as ep

    from risk_threshold_engine import RiskThresholdEngine

    results = {}
    for ticker, data in market_data.items():
        if "error" in data:
            results[ticker] = data
            continue
        try:
            # We need actual prices to compute returns — fetch again or reconstruct
            # Use yfinance for a quick re-fetch to get full price series for metrics
            import yfinance as yf
            stock = yf.Ticker(ticker.upper())
            hist = stock.history(period="6mo")
            if hist.empty:
                results[ticker] = {"error": f"no hist data for metrics"}
                continue
            closes = hist["Close"].values.astype(float)
            returns = np.diff(np.log(np.maximum(closes, 1e-10)))

            if len(returns) < 5:
                results[ticker] = {"error": f"insufficient data ({len(returns)} days)"}
                continue

            sharpe = float(ep.sharpe_ratio(returns, risk_free=0.02 / 252, annualization=252))
            max_dd = float(ep.max_drawdown(returns))
            calmar = float(ep.calmar_ratio(returns, annualization=252)) if max_dd < 0 else 0.0
            var_95 = float(ep.value_at_risk(returns, cutoff=0.05))
            ann_vol = float(ep.annual_volatility(returns, annualization=252))

            # Risk threshold engine
            engine = RiskThresholdEngine()
            scores, rte_result = RiskThresholdEngine.from_returns(returns)

            results[ticker] = {
                "sharpe": round(sharpe, 3),
                "max_dd_pct": round(max_dd * 100, 2),
                "calmar": round(calmar, 3),
                "var_95_pct": round(var_95 * 100, 2),
                "ann_vol_pct": round(ann_vol * 100, 1),
                "rte_composite": rte_result.composite_score,
                "rte_regime": rte_result.regime.value,
                "rte_decision": rte_result.decision.value,
                "factor_scores": {
                    "volatility": scores.volatility_score,
                    "momentum": scores.momentum_score,
                    "breadth": scores.breadth_score,
                    "macro": scores.macro_score,
                    "drawdown": scores.drawdown_score,
                },
            }
        except Exception as e:
            results[ticker] = {"error": f"risk metrics failed: {e}"}
    return results


def _format_market_data_for_prompt(market_data: dict[str, dict]) -> str:
    """Format market data dict as a compact text block for LLM prompt injection."""
    if not market_data:
        return "（无实时市场数据）"
    lines = []
    for ticker, data in market_data.items():
        if "error" in data:
            lines.append(f"  {ticker}: 数据获取失败 ({data['error']})")
        else:
            parts = [f"  {ticker}: 最新价${data.get('latest_price','N/A')}"]
            if data.get("return_1m_pct") is not None:
                parts.append(f"1月收益{data['return_1m_pct']:+.1f}%")
            if data.get("return_3m_pct") is not None:
                parts.append(f"3月收益{data['return_3m_pct']:+.1f}%")
            parts.append(f"年化波动{data.get('volatility_ann_pct','N/A')}%")
            parts.append(f"最大回撤{data.get('max_dd_pct','N/A')}%")
            lines.append("，".join(parts))
    return "\n".join(lines)


def _format_risk_for_prompt(risk_metrics: dict[str, dict]) -> str:
    """Format risk metrics dict as a compact text block for LLM prompt injection."""
    if not risk_metrics:
        return "（无风险评估数据）"
    lines = []
    for ticker, data in risk_metrics.items():
        if "error" in data:
            lines.append(f"  {ticker}: 风险评估失败 ({data['error']})")
        else:
            lines.append(
                f"  {ticker}: Sharpe={data.get('sharpe','N/A')}, "
                f"MaxDD={data.get('max_dd_pct','N/A')}%, "
                f"VaR95={data.get('var_95_pct','N/A')}%, "
                f"Calmar={data.get('calmar','N/A')}, "
                f"波动率={data.get('ann_vol_pct','N/A')}%, "
                f"RTE评分={data.get('rte_composite','N/A')}, "
                f"市场状态={data.get('rte_regime','N/A')}"
            )
    return "\n".join(lines) if lines else "（无风险评估数据）"


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


# ─── Stigmergy Parallel Batch Node ───────────────────────

def _make_stigmergy_batch_node(progress_callback=None):
    """Run knowledge_management + academic_research + extreme_drive in parallel
    using StigmergyScheduler pressure-field-based dispatch.

    Replaces the previous sequential chain (KM→AR→ED) with auto-parallelized
    execution. Each department receives the same upstream context and runs
    independently — no cross-department dependencies within the batch.
    """
    def node_fn(state: FullResearchState) -> dict:
        if progress_callback:
            progress_callback("start", "stigmergy_batch", "Stigmergy 并行批处理 (3部门)")

        tickers = state.get("tickers", [])
        request = state.get("user_request", "")
        irrelevant = state.get("irrelevant_depts", [])

        # Build shared upstream context for all 3 batch departments
        context_parts = [f"标的: {', '.join(tickers)}", f"用户需求: {request}"]
        skipped_deps = []
        for d in DEPT_ORDER:
            prev_result = state.get(f"{d}_result", "")
            if not prev_result:
                continue
            if "ERROR" in prev_result or "[SKIPPED]" in prev_result:
                skipped_deps.append(DEPT_NAMES.get(d, d))
                continue
            context_parts.append(f"\n{DEPT_NAMES[d]}输出: {prev_result[:300]}")
        if skipped_deps:
            context_parts.insert(1, f"⚠ 上游部门分析失败/跳过: {', '.join(skipped_deps)}。请在缺失信息的情况下独立完成分析。")
        shared_context = "\n".join(context_parts)

        results: dict[str, dict] = {}

        async def dispatch(agent_id: str, task):
            dept_key = task.id
            if dept_key in irrelevant:
                results[dept_key] = {"output": f"[SKIPPED] {dept_key}: 智能跳过", "score": None}
                return DispatchResult(success=True, output=results[dept_key]["output"])

            if progress_callback:
                progress_callback("start", dept_key, DEPT_NAMES.get(dept_key, dept_key))

            system = DEPT_PROMPTS[dept_key] + _CONFIDENCE_INSTRUCTION
            max_tok = DEPT_MAX_TOKENS.get(dept_key, 300)

            loop = asyncio.get_running_loop()
            try:
                llm_result = await loop.run_in_executor(
                    None, _call_llm, shared_context, system, 0.3, max_tok)
                cleaned, score = _parse_confidence(llm_result)
                results[dept_key] = {"output": cleaned, "score": score}
                if progress_callback:
                    progress_callback("complete", dept_key, DEPT_NAMES.get(dept_key, dept_key),
                                      {"score": score, "summary": cleaned[:120]})
                return DispatchResult(success=True, output=cleaned)
            except Exception as e:
                if progress_callback:
                    progress_callback("error", dept_key, DEPT_NAMES.get(dept_key, dept_key),
                                      {"error": str(e)[:150]})
                results[dept_key] = {"output": f"[ERROR] {dept_key}: {e}", "score": None}
                return DispatchResult(success=False, error=str(e))

        if not _STIGMERGY_AVAILABLE:
            # Fallback: sequential execution if stigmergy not installed
            if progress_callback:
                progress_callback("start", "stigmergy_batch", "Stigmergy 不可用，回退顺序执行")
            for dept in _STIGMERGY_BATCH_DEPTS:
                node = _make_dept_node(dept, progress_callback)
                updates = node(state)
                state = {**state, **updates}
                result_key = f"{dept}_result"
                score = updates.get("confidence_scores", {}).get(dept)
                results[dept] = {"output": updates.get(result_key, ""), "score": score}
        else:
            scheduler = StigmergyScheduler(
                tick_interval=0.01,
                wake_threshold=0.3,
            )
            scheduler.set_dispatcher(dispatch)

            async def _run():
                for dept in _STIGMERGY_BATCH_DEPTS:
                    if dept in irrelevant:
                        continue
                    await scheduler.add_task(TaskSpec(
                        id=dept,
                        description=DEPT_NAMES.get(dept, dept),
                        agent_id=dept,
                        priority=0.5,
                        dependencies=[],
                    ))
                if scheduler._tasks:
                    await scheduler.run()

            asyncio.run(_run())

        # Build return dict
        updates: dict = {"steps_completed": [], "skipped": [], "errors": []}
        conf_updates: dict[str, float] = {}
        for dept in _STIGMERGY_BATCH_DEPTS:
            updates["steps_completed"].append(dept)
            if dept in irrelevant:
                updates[f"{dept}_result"] = f"[SKIPPED] {dept}: 智能跳过 — 与当前查询类型不相关"
                updates["skipped"].append(dept)
            elif dept in results:
                updates[f"{dept}_result"] = results[dept]["output"]
                score = results[dept].get("score")
                if score is not None:
                    conf_updates[dept] = score
            else:
                updates[f"{dept}_result"] = f"[ERROR] {dept}: 执行失败"
                updates["errors"].append(f"{dept}: execution failed")
                updates["skipped"].append(dept)

        if conf_updates:
            updates["confidence_scores"] = conf_updates

        if progress_callback:
            completed = len([d for d in _STIGMERGY_BATCH_DEPTS if d not in irrelevant and d in results])
            progress_callback("complete", "stigmergy_batch", "Stigmergy 并行批处理",
                              {"batch_completed": completed, "total_batch": 3})

        return updates

    return node_fn


# ─── Node Factory ─────────────────────────────────────────

def _make_dept_node(dept_key: str, progress_callback=None):
    """Create a node function for a given department with error recovery.

    Node failures are recorded in state.errors but never crash the pipeline.
    Downstream nodes receive 'upstream failed' context so they can adapt.
    LLM calls get up to 2 retries with exponential backoff before giving up.
    """
    result_field = f"{dept_key}_result"

    def node_fn(state: FullResearchState) -> dict:
        # Pre-classified irrelevant → skip LLM call entirely (zero token cost)
        if dept_key in state.get("irrelevant_depts", []):
            skip_msg = f"[SKIPPED] {dept_key}: 智能跳过 — 与当前查询类型不相关"
            if progress_callback:
                progress_callback("skip", dept_key, DEPT_NAMES.get(dept_key, dept_key),
                                  {"reason": "智能跳过：与查询类型不相关"})
            return {result_field: skip_msg, "steps_completed": [dept_key], "skipped": [dept_key]}
        if progress_callback:
            progress_callback("start", dept_key, DEPT_NAMES.get(dept_key, dept_key))
        tickers = state.get("tickers", [])
        request = state.get("user_request", "")
        market_data = state.get("market_data", {})
        risk_metrics = state.get("risk_metrics", {})

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

        # Inject real market data for data-dependent departments
        if dept_key in ("strategy_research", "sentiment_intel") and market_data:
            context_parts.append(f"\n📊 实时行情数据（yfinance）:\n{_format_market_data_for_prompt(market_data)}")
        if dept_key == "risk_management" and risk_metrics:
            context_parts.append(f"\n📉 风险评估数据（empyrical + risk_threshold_engine）:\n{_format_risk_for_prompt(risk_metrics)}")
        if dept_key == "risk_management" and not risk_metrics and market_data:
            context_parts.append(f"\n📊 行情数据:\n{_format_market_data_for_prompt(market_data)}")
        if dept_key == "backtest_engine" and market_data:
            context_parts.append(f"\n📊 行情参考:\n{_format_market_data_for_prompt(market_data)}")

        # Inject confidence scores for ceo_office aggregation
        if dept_key == "ceo_office":
            conf = state.get("confidence_scores", {})
            if conf:
                conf_lines = [f"  {DEPT_NAMES.get(d, d)}: {conf[d]:.2f}/10"
                              for d in DEPT_ORDER[:-2] if d in conf]  # exclude ceo_office + chairman
                if conf_lines:
                    context_parts.append(f"\n🎯 各部门置信度:\n" + "\n".join(conf_lines))
                    valid_scores = [conf[d] for d in DEPT_ORDER[:-2] if d in conf]
                    if valid_scores:
                        avg = sum(valid_scores) / len(valid_scores)
                        context_parts.append(f"综合平均置信度: {avg:.2f}/10")

        prompt = "\n".join(context_parts)
        max_tok = DEPT_MAX_TOKENS.get(dept_key, 600)
        system = DEPT_PROMPTS[dept_key] + _CONFIDENCE_INSTRUCTION
        try:
            result = _call_llm(prompt, system, max_tokens=max_tok)
            cleaned, score = _parse_confidence(result)
            if progress_callback:
                progress_callback("complete", dept_key, DEPT_NAMES.get(dept_key, dept_key),
                                  {"score": score, "summary": cleaned[:120]})
            updates: dict = {result_field: cleaned, "steps_completed": [dept_key]}
            if score is not None:
                updates["confidence_scores"] = {dept_key: score}
            return updates
        except Exception as e:
            if progress_callback:
                progress_callback("error", dept_key, DEPT_NAMES.get(dept_key, dept_key),
                                  {"error": str(e)[:150]})
            skip_msg = f"[SKIPPED] {dept_key}: {e} (retried 2x, pipeline continues)"
            return {result_field: skip_msg, "steps_completed": [dept_key], "errors": [f"{dept_key}: {e}"],
                    "skipped": [dept_key]}

    return node_fn


def _make_data_engineering_node(progress_callback=None):
    """Specialized data_engineering node: fetches real market data via yfinance
    and computes risk metrics via empyrical + risk_threshold_engine before LLM analysis."""
    result_field = "data_engineering_result"

    def node_fn(state: FullResearchState) -> dict:
        if progress_callback:
            progress_callback("start", "data_engineering", "数据工程部 (fetching yfinance...)")
        tickers = state.get("tickers", [])
        request = state.get("user_request", "")

        # Step 1: Fetch real market data via yfinance
        market_data = _fetch_market_data(tickers)

        # Step 2: Compute risk metrics via empyrical + risk_threshold_engine
        risk_metrics = {}
        risk_engine_error = None
        try:
            risk_metrics = _compute_risk_metrics(market_data)
        except Exception as e:
            risk_engine_error = str(e)[:200]

        # Step 3: Build prompt with real data
        context_parts = [
            f"标的: {', '.join(tickers)}",
            f"用户需求: {request}",
            f"\n📊 实时行情数据（yfinance）:\n{_format_market_data_for_prompt(market_data)}",
        ]
        if risk_metrics:
            context_parts.append(f"\n📉 风险指标（empyrical + risk_threshold_engine）:\n{_format_risk_for_prompt(risk_metrics)}")
        if risk_engine_error:
            context_parts.append(f"\n⚠ 风险引擎部分失败: {risk_engine_error}")

        prompt = "\n".join(context_parts)
        max_tok = DEPT_MAX_TOKENS.get("data_engineering", 500)
        system = DEPT_PROMPTS["data_engineering"] + _CONFIDENCE_INSTRUCTION

        try:
            result = _call_llm(prompt, system, max_tokens=max_tok)
            cleaned, score = _parse_confidence(result)
            if progress_callback:
                progress_callback("complete", "data_engineering", "数据工程部",
                                  {"score": score, "tickers_loaded": len(market_data),
                                   "risk_tickers": len(risk_metrics)})
            resp = {
                result_field: cleaned,
                "steps_completed": ["data_engineering"],
                "market_data": market_data,
                "risk_metrics": risk_metrics,
            }
            if score is not None:
                resp["confidence_scores"] = {"data_engineering": score}
            return resp
        except Exception as e:
            if progress_callback:
                progress_callback("error", "data_engineering", "数据工程部",
                                  {"error": str(e)[:150], "tickers_loaded": len(market_data)})
            skip_msg = f"[SKIPPED] data_engineering: {e} (retried 2x)"
            return {
                result_field: skip_msg,
                "steps_completed": ["data_engineering"],
                "errors": [f"data_engineering: {e}"],
                "skipped": ["data_engineering"],
                "market_data": market_data,
                "risk_metrics": risk_metrics,
            }

    return node_fn


# ─── Full Graph Builder ───────────────────────────────────

class FullResearchGraph:
    """Complete 11-department LangGraph pipeline for stock research."""

    def __init__(self, db_path: str = None, progress_callback=None, reports_dir: str = None):
        if db_path is None:
            db_path = str(Path(__file__).resolve().parent.parent.parent / "company" / "full_research_checkpoints.db")
        self.db_path = db_path
        self._db_conn = sqlite3.connect(db_path, check_same_thread=False)
        self.checkpointer = SqliteSaver(self._db_conn)
        self.progress_callback = progress_callback
        self.reports_dir = Path(reports_dir) if reports_dir else None
        self.graph = self._build()
        self.token_usage = {"total_input": 0, "total_output": 0}
        self._cache_ttl_minutes = 30

    def _build(self):
        workflow = StateGraph(FullResearchState)

        # Add all 11 department nodes (data_engineering uses specialized node with real tools)
        workflow.add_node("data_engineering", _make_data_engineering_node(self.progress_callback))
        for dept in DEPT_ORDER[1:]:
            workflow.add_node(dept, _make_dept_node(dept, self.progress_callback))

        # Stigmergy-powered parallel batch node (P3-14):
        # knowledge_management + academic_research + extreme_drive run in parallel
        workflow.add_node("stigmergy_batch", _make_stigmergy_batch_node(self.progress_callback))

        # Set entry point
        workflow.set_entry_point("data_engineering")

        # Fan-out: data_engineering → 3 parallel depts (strategy, risk, sentiment)
        workflow.add_edge("data_engineering", "strategy_research")
        workflow.add_edge("data_engineering", "risk_management")
        workflow.add_edge("data_engineering", "sentiment_intel")

        # Fan-in: all 3 converge at backtest_engine
        workflow.add_edge("strategy_research", "backtest_engine")
        workflow.add_edge("risk_management", "backtest_engine")
        workflow.add_edge("sentiment_intel", "backtest_engine")

        # Stigmergy batch: backtest_engine → 3 non-critical depts in parallel → reporting
        workflow.add_edge("backtest_engine", "stigmergy_batch")
        workflow.add_edge("stigmergy_batch", "reporting")
        # Final chain: reporting → ceo_office → chairman_secretariat → END
        workflow.add_edge("reporting", "ceo_office")
        workflow.add_edge("ceo_office", "chairman_secretariat")
        workflow.add_edge("chairman_secretariat", END)

        return workflow.compile(checkpointer=self.checkpointer)

    def _check_result_cache(self, ticker_key: str) -> dict | None:
        """Return cached result dict if same ticker was researched < 30 min ago. None on miss."""
        if not self.reports_dir:
            return None
        try:
            candidates = sorted(
                self.reports_dir.glob(f"lg_*_{ticker_key}.json"),
                key=lambda p: p.stat().st_mtime, reverse=True)
            if not candidates:
                return None
            latest = json.loads(candidates[0].read_text(encoding="utf-8"))
            ts_str = latest.get("timestamp", "")
            if not ts_str:
                return None
            ts = datetime.fromisoformat(ts_str)
            age = (datetime.now() - ts).total_seconds() / 60
            if age > self._cache_ttl_minutes:
                return None
            # Reconstruct result dict in same shape as run_sync() return
            dept_outputs = {f"{d}_result": latest.get(f"{d}_result", "") for d in DEPT_ORDER}
            return {
                "final_report": latest.get("final_report", ""),
                "steps_completed": latest.get("steps_completed", []),
                "errors": latest.get("errors", []),
                "token_usage": latest.get("token_usage", {}),
                "skipped": latest.get("skipped", []),
                "confidence_scores": latest.get("confidence_scores", {}),
                "from_cache": True,
                **dept_outputs,
            }
        except Exception:
            return None

    def run_sync(self, user_request: str, tickers: list[str] = None, urgent: bool = False,
                 resume: bool = False) -> dict:
        if tickers is None:
            tickers = self._extract_tickers(user_request)

        # Deterministic thread_id per ticker set — enables checkpoint resume across restarts
        ticker_key = "_".join(sorted(tickers)) if tickers else "SPY"
        thread_id = f"full_{ticker_key}"

        # ── Cache check: same ticker within 30 min → return cached ──
        if not resume:
            cached = self._check_result_cache(ticker_key)
            if cached:
                return cached

        # Classify irrelevant departments (zero-token heuristic)
        irrelevant = _classify_irrelevant_departments(user_request, tickers)

        # Check for existing checkpoint
        existing_state = None
        if resume:
            existing_state = self._load_checkpoint(thread_id)

        if existing_state and existing_state.get("steps_completed"):
            # Resume from checkpoint — skip already-completed nodes
            initial = existing_state
            # Preserve original irrelevant classification
            if "irrelevant_depts" not in initial:
                initial["irrelevant_depts"] = irrelevant
        else:
            initial = {
                "user_request": user_request, "tickers": tickers, "urgent": urgent,
                "route": DEPT_ORDER[0], "steps_completed": [], "errors": [], "skipped": [],
                "irrelevant_depts": irrelevant,
                "final_report": "", "market_data": {}, "risk_metrics": {},
                "confidence_scores": {},
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
                "skipped": result.get("skipped", []),
                "confidence_scores": result.get("confidence_scores", {}),
                **dept_outputs}

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


def run_full_research(user_request: str, tickers: list[str] = None, urgent: bool = False,
                     progress_callback=None, reports_dir: str = None) -> str:
    graph = FullResearchGraph(progress_callback=progress_callback, reports_dir=reports_dir)
    result = graph.run_sync(user_request, tickers=tickers, urgent=urgent)
    return result.get("final_report", "[ERROR]")
