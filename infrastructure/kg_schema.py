"""kg_schema.py — OnionQuant 知识图谱数据模型 (Neo4j)

Node types: Stock, Factor, Industry, Report, Event, Agent, RiskAlert
Relationship types: CORRELATES_WITH, HAS_FACTOR, IN_INDUSTRY, MENTIONED_IN,
                    TRIGGERED_BY, EXECUTED_BY, DEPENDS_ON, SUPPLIES_TO
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# ── Node labels ──────────────────────────────────────────

NODE_STOCK = "Stock"
NODE_FACTOR = "Factor"
NODE_INDUSTRY = "Industry"
NODE_REPORT = "Report"
NODE_EVENT = "Event"
NODE_AGENT = "Agent"
NODE_RISK = "RiskAlert"

# ── Relationship types ───────────────────────────────────

REL_CORRELATES = "CORRELATES_WITH"     # (Stock)-[:CORRELATES_WITH {rho, window}]->(Stock)
REL_HAS_FACTOR = "HAS_FACTOR"          # (Stock)-[:HAS_FACTOR {ic, date}]->(Factor)
REL_IN_INDUSTRY = "IN_INDUSTRY"         # (Stock)-[:IN_INDUSTRY]->(Industry)
REL_MENTIONED = "MENTIONED_IN"          # (Stock)-[:MENTIONED_IN {sentiment}]->(Report)
REL_TRIGGERED = "TRIGGERED_BY"          # (Event)-[:TRIGGERED_BY]->(Report)
REL_EXECUTED = "EXECUTED_BY"            # (Report)-[:EXECUTED_BY]->(Agent)
REL_DEPENDS = "DEPENDS_ON"              # (Factor)-[:DEPENDS_ON]->(Factor)
REL_SUPPLIES = "SUPPLIES_TO"            # (Stock)-[:SUPPLIES_TO {relationship}]->(Industry)

ALL_NODE_LABELS = [NODE_STOCK, NODE_FACTOR, NODE_INDUSTRY, NODE_REPORT,
                   NODE_EVENT, NODE_AGENT, NODE_RISK]


@dataclass
class StockNode:
    ticker: str
    name: str = ""
    exchange: str = ""
    sector: str = ""
    market_cap: float = 0.0
    price: float = 0.0

    @property
    def uid(self) -> str:
        return self.ticker.upper()


@dataclass
class FactorNode:
    name: str
    category: str = ""          # momentum, reversal, volatility, volume, fundamental
    description: str = ""
    latest_ic: float = 0.0       # latest cross-sectional IC
    ic_stable: bool = True

    @property
    def uid(self) -> str:
        return self.name


@dataclass
class IndustryNode:
    name: str
    sector: str = ""
    description: str = ""

    @property
    def uid(self) -> str:
        return self.name


@dataclass
class ReportNode:
    path: str
    title: str = ""
    report_type: str = ""       # stock_research, daily_trade, pipeline, system_eval
    generated_at: str = ""      # ISO timestamp
    tickers_covered: list = field(default_factory=list)

    @property
    def uid(self) -> str:
        return self.path


@dataclass
class EventNode:
    name: str
    event_type: str = ""        # earnings, launch, macro, regulatory, catalyst
    target_tickers: list = field(default_factory=list)
    date: str = ""              # YYYY-MM-DD
    impact_score: float = 0.0   # -1.0 to 1.0

    @property
    def uid(self) -> str:
        return f"{self.date}_{self.name}"


@dataclass
class AgentNode:
    name: str
    department: str = ""
    role: str = ""
    status: str = "active"

    @property
    def uid(self) -> str:
        return self.name


@dataclass
class RiskAlertNode:
    ticker: str
    alert_type: str = ""        # premium, dilution, overbought, concentration, earnings
    severity: str = "warning"   # info, warning, critical
    message: str = ""
    created_at: str = ""

    @property
    def uid(self) -> str:
        return f"{self.ticker}_{self.alert_type}_{self.created_at}"


# ── Cypher constraint DDL ────────────────────────────────

CONSTRAINT_DDL = [
    f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{NODE_STOCK}) REQUIRE n.ticker IS UNIQUE",
    f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{NODE_FACTOR}) REQUIRE n.name IS UNIQUE",
    f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{NODE_INDUSTRY}) REQUIRE n.name IS UNIQUE",
    f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{NODE_REPORT}) REQUIRE n.path IS UNIQUE",
    f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{NODE_EVENT}) REQUIRE n.uid IS UNIQUE",
    f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{NODE_AGENT}) REQUIRE n.name IS UNIQUE",
]

# ── Index DDL ────────────────────────────────────────────

INDEX_DDL = [
    f"CREATE INDEX IF NOT EXISTS FOR (n:{NODE_STOCK}) ON n.sector",
    f"CREATE INDEX IF NOT EXISTS FOR (n:{NODE_FACTOR}) ON n.category",
    f"CREATE INDEX IF NOT EXISTS FOR (n:{NODE_EVENT}) ON n.date",
    f"CREATE INDEX IF NOT EXISTS FOR (n:{NODE_RISK}) ON n.ticker",
    f"CREATE INDEX IF NOT EXISTS FOR (n:{NODE_REPORT}) ON n.report_type",
]

# ── Industry taxonomy ────────────────────────────────────

INDUSTRY_TAXONOMY = {
    "AI_CHIPS": "AI/Semiconductor",
    "STORAGE": "Storage/HDD/NAND",
    "SPACE": "Aerospace/Space",
    "OPTICAL": "Optical Modules/CPO",
    "FINTECH": "FinTech/Payments",
    "E_COMMERCE": "E-Commerce/Cloud",
    "AEROSPACE_DEFENSE": "Aerospace/Defense",
    "TELECOM": "Telecom/5G",
    "FUND": "Investment Fund/CEF",
}

TICKER_INDUSTRY_MAP = {
    "DXYZ": "FUND", "NVDA": "AI_CHIPS", "AMD": "AI_CHIPS",
    "MU": "STORAGE", "WDC": "STORAGE", "SNDK": "STORAGE",
    "STX": "STORAGE", "SMCI": "AI_CHIPS",
    "RKLB": "SPACE", "LUNR": "SPACE",
    "LITE": "OPTICAL", "COHR": "OPTICAL",
    "BABA": "E_COMMERCE", "JD": "E_COMMERCE",
    "GE": "AEROSPACE_DEFENSE", "NOK": "TELECOM",
}
