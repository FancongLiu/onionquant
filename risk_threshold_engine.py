#!/usr/bin/env python3
"""
risk_threshold_engine — 量化风险阈值引擎。

基于5因子评分(波动率/动量/广度/宏观/回撤)计算市场风险状态和部署决策。
使用 empyrical-reloaded 计算真实风险指标（Sharpe/MaxDD/VaR/Calmar）。

Interface:
    engine = RiskThresholdEngine()
    scores = FactorScores(volatility_score=..., momentum_score=..., ...)
    result = engine.evaluate(scores)  # -> EvalResult

Also provides from_returns() factory to auto-compute scores from price data.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np


# ─── Enums ──────────────────────────────────────────────────

class MarketRegime(str, enum.Enum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    NEUTRAL = "NEUTRAL"


class TradeDecision(str, enum.Enum):
    DEPLOY = "DEPLOY"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    EXIT = "EXIT"


# ─── Data Classes ───────────────────────────────────────────

@dataclass
class FactorScores:
    volatility_score: float   # 0-100, higher = lower vol (better)
    momentum_score: float     # 0-100, higher = stronger momentum
    breadth_score: float      # 0-100, higher = broader participation
    macro_score: float        # 0-100, higher = more favorable macro
    drawdown_score: float     # 0-100, higher = smaller drawdown (better)
    as_of: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Action:
    action_type: str       # "buy" / "sell" / "hold" / "reduce"
    ticker: str
    magnitude: float       # 0.0-1.0
    rationale: str


@dataclass
class EvalResult:
    composite_score: int    # 0-100
    regime: MarketRegime
    decision: TradeDecision
    actions: list[Action] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def __repr__(self):
        return (f"EvalResult(composite={self.composite_score}, "
                f"regime={self.regime.value}, decision={self.decision.value}, "
                f"actions={len(self.actions)})")


# ─── Engine ─────────────────────────────────────────────────

class RiskThresholdEngine:
    """5-factor risk threshold engine.

    Weights (calibrated for US equity):
        volatility 25% | momentum 20% | breadth 15% | macro 15% | drawdown 25%
    """

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or {
            "volatility": 0.25,
            "momentum": 0.20,
            "breadth": 0.15,
            "macro": 0.15,
            "drawdown": 0.25,
        }

    def evaluate(self, scores: FactorScores) -> EvalResult:
        composite = (
            self.weights["volatility"] * scores.volatility_score
            + self.weights["momentum"] * scores.momentum_score
            + self.weights["breadth"] * scores.breadth_score
            + self.weights["macro"] * scores.macro_score
            + self.weights["drawdown"] * scores.drawdown_score
        )
        composite = int(round(composite))

        if composite >= 60:
            regime = MarketRegime.RISK_ON
            decision = TradeDecision.DEPLOY
        elif composite >= 40:
            regime = MarketRegime.NEUTRAL
            decision = TradeDecision.HOLD
        elif composite >= 20:
            regime = MarketRegime.RISK_OFF
            decision = TradeDecision.REDUCE
        else:
            regime = MarketRegime.RISK_OFF
            decision = TradeDecision.EXIT

        actions = self._generate_actions(decision, scores)
        details = {
            "factor_scores": {
                "volatility": scores.volatility_score,
                "momentum": scores.momentum_score,
                "breadth": scores.breadth_score,
                "macro": scores.macro_score,
                "drawdown": scores.drawdown_score,
            },
            "weights": self.weights,
        }

        return EvalResult(
            composite_score=composite,
            regime=regime,
            decision=decision,
            actions=actions,
            details=details,
        )

    def _generate_actions(self, decision: TradeDecision, scores: FactorScores) -> list[Action]:
        if decision == TradeDecision.DEPLOY:
            return [Action("buy", "SPY", 0.8, "Risk-on regime: deploy to target allocation")]
        elif decision == TradeDecision.REDUCE:
            return [Action("reduce", "SPY", 0.4, "Risk-off regime: reduce exposure by 40%")]
        elif decision == TradeDecision.EXIT:
            return [Action("sell", "SPY", 0.9, "Severe risk-off: exit positions, preserve capital")]
        else:
            return [Action("hold", "SPY", 0.0, "Neutral regime: maintain current allocation")]

    @staticmethod
    def from_returns(returns: np.ndarray, market_returns: np.ndarray | None = None,
                     as_of: str | None = None) -> tuple[FactorScores, EvalResult]:
        """Factory: compute FactorScores from return series using empyrical.

        Args:
            returns: daily return array
            market_returns: optional benchmark returns for beta calculation
            as_of: ISO timestamp

        Returns:
            (FactorScores, EvalResult)
        """
        try:
            import empyrical as ep
        except ImportError:
            import empyrical_reloaded as ep

        r = np.asarray(returns, dtype=float)
        if len(r) < 5:
            raise ValueError("Need at least 5 return observations")

        ann_vol = float(ep.annual_volatility(r, annualization=252))
        sharpe = float(ep.sharpe_ratio(r, risk_free=0.02 / 252, annualization=252))
        max_dd = float(ep.max_drawdown(r)) if len(r) >= 2 else 0.0
        calmar = float(ep.calmar_ratio(r, annualization=252)) if max_dd < 0 else 0.0

        # Translate financial metrics to 0-100 scores
        volatility_score = max(0, min(100, 100 - ann_vol * 120))       # vol 0% -> 100, vol 60% -> 28
        momentum_score = max(0, min(100, 50 + sharpe * 25))            # Sharpe 0 -> 50, Sharpe 2 -> 100
        drawdown_score = max(0, min(100, 100 + max_dd * 200))          # MaxDD 0% -> 100, MaxDD -50% -> 0

        # Breadth: estimated from return consistency (fraction of positive days)
        breadth_score = max(0, min(100, np.mean(r > 0) * 200))         # 50% positive -> 100

        # Macro: neutral default, adjust with beta if available
        macro_score = 50.0
        if market_returns is not None and len(market_returns) >= 5:
            beta = float(ep.beta(r, np.asarray(market_returns, dtype=float)))
            # Beta near 1 = best macro alignment
            macro_score = max(0, min(100, 100 - abs(beta - 1.0) * 40))

        scores = FactorScores(
            volatility_score=round(volatility_score, 1),
            momentum_score=round(momentum_score, 1),
            breadth_score=round(breadth_score, 1),
            macro_score=round(macro_score, 1),
            drawdown_score=round(drawdown_score, 1),
            as_of=as_of or datetime.now().isoformat(),
        )

        engine = RiskThresholdEngine()
        result = engine.evaluate(scores)
        return scores, result
