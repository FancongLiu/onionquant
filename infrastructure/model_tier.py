#!/usr/bin/env python3
"""Dual model tier configuration — cost-optimized LLM routing.

Pattern from TradingAgents' dual LLM layer:
  - Quick-thinking model: cheap, fast (<500ms) — routine tasks
  - Deep-thinking model: expensive, high-quality (>2s) — strategic decisions

Routes tasks to appropriate tier based on: task type, complexity, urgency, cost budget.

Pure config + routing — no new dependencies.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
from pathlib import Path
import yaml


class Tier(Enum):
    QUICK = "quick"    # Cheap, fast model — routine
    DEEP = "deep"      # Expensive, capable model — strategic
    LOCAL = "local"    # Free, local model — when offline/privacy needed


@dataclass
class ModelSpec:
    """A specific model configuration."""
    provider: str                       # anthropic, openai, openrouter, ollama
    model_id: str                       # e.g., claude-haiku-4-5, gpt-4o-mini
    tier: Tier = Tier.QUICK
    cost_per_1k_input: float = 0.0      # USD
    cost_per_1k_output: float = 0.0
    max_tokens: int = 4096
    supports_thinking: bool = False     # extended thinking / reasoning
    supports_structured_output: bool = False
    timeout_seconds: float = 30.0
    notes: str = ""


@dataclass
class TierConfig:
    """Which tier to use for which task category."""
    tier: Tier
    model: str = ""                     # model name key
    max_tokens: int = 4096
    temperature: float = 0.0
    retry_count: int = 3


@dataclass
class TaskRouting:
    """Task → tier mapping with rationale."""
    task_category: str                  # e.g., factor_analysis, regime_detection
    tier: Tier
    rationale: str = ""
    examples: List[str] = field(default_factory=list)
    budget_tokens: int = 2000
    timeout_seconds: float = 60.0


# ── Default Quant Trading Tier Config ──────────────────────

DEFAULT_MODELS = {
    "claude-haiku-4-5": ModelSpec(
        provider="anthropic", model_id="claude-haiku-4-5-20251001",
        tier=Tier.QUICK,
        cost_per_1k_input=0.0008, cost_per_1k_output=0.004,
        supports_structured_output=True, timeout_seconds=15.0,
        notes="Fast, cheap — ideal for routine factor scanning and standard reports",
    ),
    "claude-sonnet-4-6": ModelSpec(
        provider="anthropic", model_id="claude-sonnet-4-6-20250514",
        tier=Tier.DEEP,
        cost_per_1k_input=0.003, cost_per_1k_output=0.015,
        supports_thinking=True, supports_structured_output=True,
        timeout_seconds=60.0, notes="Deep reasoning — strategic decisions, regime analysis",
    ),
    "gpt-4o-mini": ModelSpec(
        provider="openai", model_id="gpt-4o-mini",
        tier=Tier.QUICK,
        cost_per_1k_input=0.00015, cost_per_1k_output=0.0006,
        supports_structured_output=True, timeout_seconds=20.0,
        notes="Cheapest option — high-volume simple tasks",
    ),
    "ollama-qwen": ModelSpec(
        provider="ollama", model_id="qwen2.5:14b",
        tier=Tier.LOCAL,
        cost_per_1k_input=0.0, cost_per_1k_output=0.0,
        timeout_seconds=120.0, notes="Free local model — offline, private, no rate limits",
    ),
}

# Task → tier routing table (from TradingAgents pattern)
DEFAULT_ROUTING = [
    TaskRouting(
        task_category="factor_scanning",
        tier=Tier.QUICK,
        rationale="High-volume, routine — 500+ factors scanned daily. Cost-sensitive.",
        examples=["Scan all momentum factors", "Compute daily IC for 50 factors"],
        budget_tokens=1000,
    ),
    TaskRouting(
        task_category="factor_analysis",
        tier=Tier.QUICK,
        rationale="Routine factor evaluation — descriptive stats, basic IC analysis.",
        examples=["Evaluate factor_3 performance", "Report top-10 factors by IC IR"],
        budget_tokens=2000,
    ),
    TaskRouting(
        task_category="regime_detection",
        tier=Tier.DEEP,
        rationale="Market regime changes are high-stakes — requires deep reasoning about macro conditions, correlations, volatility patterns.",
        examples=["Detect regime shift from bull to bear", "Analyze correlation breakdown"],
        budget_tokens=3000,
    ),
    TaskRouting(
        task_category="strategy_decision",
        tier=Tier.DEEP,
        rationale="Portfolio allocation decisions impact real capital. Needs thorough analysis and confidence calibration.",
        examples=["Allocate sector weights", "Approve new factor for production"],
        budget_tokens=4000,
    ),
    TaskRouting(
        task_category="risk_assessment",
        tier=Tier.QUICK,
        rationale="Daily risk monitoring is routine — VaR/CVaR computation, limit checks. Deep model only when limits breach.",
        examples=["Daily VaR report", "Position limit check"],
        budget_tokens=1500,
    ),
    TaskRouting(
        task_category="crisis_analysis",
        tier=Tier.DEEP,
        rationale="Crisis situations demand maximum reasoning — factor models may break, correlations spike, liquidity vanishes.",
        examples=["Assess portfolio impact of flash crash", "Emergency risk scenario analysis"],
        budget_tokens=6000, timeout_seconds=120.0,
    ),
    TaskRouting(
        task_category="chairman_summary",
        tier=Tier.DEEP,
        rationale="Chairman-facing output must be insightful, well-structured, and accurate.",
        examples=["Daily market briefing", "Portfolio performance summary"],
        budget_tokens=4000,
    ),
    TaskRouting(
        task_category="data_cleaning",
        tier=Tier.QUICK,
        rationale="Routine data quality checks — NaN detection, outlier flagging, freshness check.",
        examples=["Check data completeness", "Flag stale data sources"],
        budget_tokens=1000,
    ),
    TaskRouting(
        task_category="code_generation",
        tier=Tier.DEEP,
        rationale="Production quant code requires correctness guarantees. Deep model for generation, quick model for review.",
        examples=["Implement new factor", "Write backtest for strategy"],
        budget_tokens=8000,
    ),
    TaskRouting(
        task_category="offline_batch",
        tier=Tier.LOCAL,
        rationale="Offline or privacy-sensitive batch processing — use free local model.",
        examples=["Batch factor description generation", "Overnight report summarization"],
        budget_tokens=2000, timeout_seconds=300.0,
    ),
]


# ── Tier Router ────────────────────────────────────────────

class TierRouter:
    """Route tasks to appropriate model tier based on task category.

    Usage:
        router = TierRouter()
        config = router.route("regime_detection")
        # config.tier = Tier.DEEP, config.model = "claude-sonnet-4-6"
    """

    def __init__(self,
                 models: Optional[Dict[str, ModelSpec]] = None,
                 routing: Optional[List[TaskRouting]] = None):
        self.models = models or DEFAULT_MODELS
        self.routing: Dict[str, TaskRouting] = {}
        for r in (routing or DEFAULT_ROUTING):
            self.routing[r.task_category] = r

    def route(self, task_category: str) -> Optional[TierConfig]:
        """Get tier config for a task category."""
        rt = self.routing.get(task_category)
        if rt is None:
            # Fallback: unknown tasks → deep model (safety first)
            rt = TaskRouting(task_category=task_category, tier=Tier.DEEP,
                           rationale="Unknown task — defaulting to deep for safety",
                           budget_tokens=2000)

        # Select cheapest model in tier
        candidates = [(name, spec) for name, spec in self.models.items()
                      if spec.tier == rt.tier]
        if not candidates:
            # Fallback to any available model in tier
            candidates = [(name, spec) for name, spec in self.models.items()]

        if not candidates:
            return None

        # Cheapest first
        candidates.sort(key=lambda x: x[1].cost_per_1k_input + x[1].cost_per_1k_output)
        name, spec = candidates[0]

        return TierConfig(
            tier=rt.tier,
            model=name,
            max_tokens=rt.budget_tokens,
            temperature=0.0 if rt.tier != Tier.LOCAL else 0.3,
        )

    def estimate_cost(self, task_category: str, input_tokens: int = 1000,
                      output_tokens: int = 500) -> float:
        """Estimate USD cost for a task."""
        config = self.route(task_category)
        if config is None:
            return 0.0
        spec = self.models.get(config.model)
        if spec is None:
            return 0.0
        return (input_tokens / 1000 * spec.cost_per_1k_input +
                output_tokens / 1000 * spec.cost_per_1k_output)

    def routing_table(self) -> str:
        """Markdown routing table for documentation."""
        lines = ["| Task Category | Tier | Model | Budget (tokens) | Rationale |",
                 "|--------------|------|-------|-----------------|-----------|"]
        for cat, rt in sorted(self.routing.items()):
            config = self.route(cat)
            model = config.model if config else "N/A"
            lines.append(f"| {cat} | {rt.tier.value} | {model} | {rt.budget_tokens} | {rt.rationale[:60]}... |")
        return "\n".join(lines)

    def daily_cost_estimate(self, task_volumes: Dict[str, int]) -> dict:
        """Estimate daily LLM cost based on task volumes.

        Args:
            task_volumes: {task_category: calls_per_day}
        Returns:
            {total_usd, per_tier: {tier: usd}, per_task: {category: usd}}
        """
        total = 0.0
        per_tier = {}
        per_task = {}
        for cat, calls in task_volumes.items():
            cost = self.estimate_cost(cat) * calls
            per_task[cat] = round(cost, 6)
            total += cost
            tier = self.routing.get(cat, TaskRouting(task_category=cat, tier=Tier.DEEP)).tier
            per_tier[tier.value] = per_tier.get(tier.value, 0.0) + cost
        return {
            "total_usd": round(total, 4),
            "per_tier": {k: round(v, 4) for k, v in per_tier.items()},
            "per_task": per_task,
        }


# ── Save/Load Config ───────────────────────────────────────

def save_config(path: Path) -> None:
    """Save current model+tier config as YAML."""
    config = {
        "models": {name: {
            "provider": s.provider, "model_id": s.model_id,
            "tier": s.tier.value,
            "cost_per_1k_input": s.cost_per_1k_input,
            "cost_per_1k_output": s.cost_per_1k_output,
            "max_tokens": s.max_tokens,
            "supports_thinking": s.supports_thinking,
            "supports_structured_output": s.supports_structured_output,
            "timeout_seconds": s.timeout_seconds,
            "notes": s.notes,
        } for name, s in DEFAULT_MODELS.items()},
        "routing": [{
            "task_category": r.task_category, "tier": r.tier.value,
            "rationale": r.rationale, "budget_tokens": r.budget_tokens,
            "timeout_seconds": r.timeout_seconds,
        } for r in DEFAULT_ROUTING],
    }
    path.write_text(yaml.dump(config, default_flow_style=False,
                              allow_unicode=True, sort_keys=False, width=120),
                    encoding="utf-8")


def load_config(path: Path) -> TierRouter:
    """Load model+tier config from YAML."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    models = {}
    for name, spec in data.get("models", {}).items():
        spec["tier"] = Tier(spec["tier"])
        models[name] = ModelSpec(**spec)
    routing = []
    for r in data.get("routing", []):
        r["tier"] = Tier(r["tier"])
        routing.append(TaskRouting(**r))
    return TierRouter(models=models, routing=routing)


# ── Demo ────────────────────────────────────────────────────

def main():
    router = TierRouter()

    print("## Model Tier Routing Table\n")
    for cat in ["factor_scanning", "regime_detection", "strategy_decision",
                "crisis_analysis", "chairman_summary", "data_cleaning"]:
        config = router.route(cat)
        cost = router.estimate_cost(cat)
        print(f"  {cat:25s} → {config.tier.value:5s} | {config.model:20s} | ~${cost:.6f}/call")

    # Daily cost estimate
    volumes = {
        "factor_scanning": 50,
        "factor_analysis": 20,
        "regime_detection": 4,
        "strategy_decision": 2,
        "risk_assessment": 10,
        "crisis_analysis": 0.1,
        "chairman_summary": 2,
        "data_cleaning": 10,
        "code_generation": 0.5,
        "offline_batch": 5,
    }
    daily = router.daily_cost_estimate(volumes)
    print(f"\n## Daily Cost Estimate: ${daily['total_usd']:.4f}")
    for tier, cost in daily["per_tier"].items():
        print(f"  {tier}: ${cost:.4f}")


if __name__ == "__main__":
    main()
