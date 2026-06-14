"""knowledge_graph.py — OnionQuant Neo4j 知识图谱引擎 (方案A: Neo4j + LangChain)

Usage:
    from infrastructure.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph()                     # 自动连接 (local Bos or AuraDB)
    kg.init_schema()                          # 首次创建约束+索引
    kg.ingest_pipeline_tickers(tickers, df)   # 摄入标的+因子关系
    kg.ingest_report(report_path)             # 摄入研究报告
    kg.query_stock_factors("NVDA")            # 查询某标的因子暴露
    kg.query_correlation_chain("MU", "NVDA")  # 查询关联路径
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from infrastructure.kg_schema import (
    CONSTRAINT_DDL,
    INDEX_DDL,
    INDUSTRY_TAXONOMY,
    NODE_EVENT,
    NODE_FACTOR,
    NODE_INDUSTRY,
    NODE_REPORT,
    NODE_RISK,
    NODE_STOCK,
    REL_CORRELATES,
    REL_HAS_FACTOR,
    REL_IN_INDUSTRY,
    REL_MENTIONED,
    REL_TRIGGERED,
    TICKER_INDUSTRY_MAP,
    EventNode,
    FactorNode,
    IndustryNode,
    ReportNode,
    RiskAlertNode,
    StockNode,
)


class KnowledgeGraph:
    """Neo4j 知识图谱 — 连接/摄入/查询 统一入口."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        self._driver = None
        self._uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self._user = user or os.getenv("NEO4J_USER", "neo4j")
        self._password = password or os.getenv("NEO4J_PASSWORD", "")

    @property
    def driver(self):
        if self._driver is None:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                self._uri, auth=(self._user, self._password)
            )
        return self._driver

    @property
    def connected(self) -> bool:
        try:
            self.driver.verify_connectivity()
            return True
        except Exception:
            return False

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    # ── Schema init ───────────────────────────────────────

    def init_schema(self):
        """首次运行时创建唯一约束和索引."""
        with self.driver.session() as session:
            for ddl in CONSTRAINT_DDL:
                try:
                    session.run(ddl)
                except Exception as e:
                    print(f"[KG] constraint skip: {e}")
            for ddl in INDEX_DDL:
                try:
                    session.run(ddl)
                except Exception as e:
                    print(f"[KG] index skip: {e}")
        print(
            f"[KG] Schema initialized: {len(CONSTRAINT_DDL)} constraints, {len(INDEX_DDL)} indexes"
        )

    # ── Node upsert helpers ───────────────────────────────

    def _merge_stock(self, session, stock: StockNode):
        session.run(
            f"MERGE (n:{NODE_STOCK} {{ticker: $ticker}}) "
            "SET n.name = $name, n.exchange = $exchange, n.sector = $sector, "
            "n.market_cap = $market_cap, n.price = $price",
            ticker=stock.uid,
            name=stock.name,
            exchange=stock.exchange,
            sector=stock.sector,
            market_cap=stock.market_cap,
            price=stock.price,
        )

    def _merge_industry(self, session, ind: IndustryNode):
        session.run(
            f"MERGE (n:{NODE_INDUSTRY} {{name: $name}}) "
            "SET n.sector = $sector, n.description = $description",
            name=ind.uid,
            sector=ind.sector,
            description=ind.description,
        )

    def _merge_factor(self, session, factor: FactorNode):
        session.run(
            f"MERGE (n:{NODE_FACTOR} {{name: $name}}) "
            "SET n.category = $category, n.description = $description, "
            "n.latest_ic = $latest_ic, n.ic_stable = $ic_stable",
            name=factor.uid,
            category=factor.category,
            description=factor.description,
            latest_ic=factor.latest_ic,
            ic_stable=factor.ic_stable,
        )

    def _merge_report(self, session, report: ReportNode):
        session.run(
            f"MERGE (n:{NODE_REPORT} {{path: $path}}) "
            "SET n.title = $title, n.report_type = $report_type, n.generated_at = $generated_at",
            path=report.uid,
            title=report.title or report.path,
            report_type=report.report_type,
            generated_at=report.generated_at,
        )

    def _merge_event(self, session, event: EventNode):
        session.run(
            f"MERGE (n:{NODE_EVENT} {{uid: $uid}}) "
            "SET n.name = $name, n.event_type = $event_type, "
            "n.date = $date, n.impact_score = $impact_score",
            uid=event.uid,
            name=event.name,
            event_type=event.event_type,
            date=event.date,
            impact_score=event.impact_score,
        )

    def _merge_risk_alert(self, session, alert: RiskAlertNode):
        session.run(
            f"MERGE (n:{NODE_RISK} {{uid: $uid}}) "
            "SET n.ticker = $ticker, n.alert_type = $alert_type, "
            "n.severity = $severity, n.message = $message, n.created_at = $created_at",
            uid=alert.uid,
            ticker=alert.ticker,
            alert_type=alert.alert_type,
            severity=alert.severity,
            message=alert.message,
            created_at=alert.created_at,
        )

    # ── Ingestion pipelines ───────────────────────────────

    def ingest_industries(self):
        """摄入行业分类."""
        with self.driver.session() as session:
            for key, name in INDUSTRY_TAXONOMY.items():
                self._merge_industry(session, IndustryNode(name=key, sector=name))
            print(f"[KG] Ingested {len(INDUSTRY_TAXONOMY)} industries")

    def ingest_pipeline_tickers(self, tickers: list, df: pd.DataFrame | None = None):
        """摄入流水线标的 + 行业关系 + 因子关系.

        Args:
            tickers: 标的列表
            df: 含 ticker/close 的价格数据 (可选, 用于设置 price)
        """
        latest_prices = {}
        if df is not None and "ticker" in df.columns and "close" in df.columns:
            latest_prices = df.groupby("ticker")["close"].last().to_dict()

        with self.driver.session() as session:
            for t in tickers:
                t = t.strip().upper()
                industry_key = TICKER_INDUSTRY_MAP.get(t, "")
                price = latest_prices.get(t, 0.0)

                stock = StockNode(ticker=t, sector=industry_key, price=price)
                self._merge_stock(session, stock)

                # Stock → Industry
                if industry_key:
                    INDUSTRY_TAXONOMY.get(industry_key, industry_key)
                    session.run(
                        f"MATCH (s:{NODE_STOCK} {{ticker: $ticker}}) "
                        f"MERGE (i:{NODE_INDUSTRY} {{name: $industry}}) "
                        f"MERGE (s)-[:{REL_IN_INDUSTRY}]->(i)",
                        ticker=t,
                        industry=industry_key,
                    )

            # Stock-Stock correlations (same industry)
            for i in range(len(tickers)):
                t1 = tickers[i].strip().upper()
                ind1 = TICKER_INDUSTRY_MAP.get(t1, "")
                for j in range(i + 1, len(tickers)):
                    t2 = tickers[j].strip().upper()
                    ind2 = TICKER_INDUSTRY_MAP.get(t2, "")
                    if ind1 == ind2 and ind1:
                        session.run(
                            f"MATCH (s1:{NODE_STOCK} {{ticker: $t1}}) "
                            f"MATCH (s2:{NODE_STOCK} {{ticker: $t2}}) "
                            f"MERGE (s1)-[:{REL_CORRELATES} {{connector: 'same_industry'}}]->(s2)",
                            t1=t1,
                            t2=t2,
                        )

        print(f"[KG] Ingested {len(tickers)} stocks + industry/correlation edges")

    def ingest_factors(self, factor_df: pd.DataFrame):
        """摄入因子节点 + Stock→Factor 关系 (含 IC 值).

        Args:
            factor_df: qlib_factor_engine 输出, 含 ticker + factor columns
        """
        if factor_df is None or factor_df.empty:
            print("[KG] No factor data to ingest")
            return

        exclude = {
            "ticker",
            "date",
            "close",
            "open",
            "high",
            "low",
            "volume",
            "industry",
        }
        factor_cols = [c for c in factor_df.columns if c not in exclude]

        if not factor_cols:
            return

        # Classify factors
        cat_map = {}
        for f in factor_cols:
            fl = f.lower()
            if any(k in fl for k in ("mom", "roc", "rsi")):
                cat_map[f] = "momentum"
            elif any(k in fl for k in ("rev", "mean_rev")):
                cat_map[f] = "reversal"
            elif any(k in fl for k in ("vol", "std", "atr", "bband")):
                cat_map[f] = "volatility"
            elif any(k in fl for k in ("turn", "volume_ratio", "dollar")):
                cat_map[f] = "volume"
            elif any(k in fl for k in ("size", "mcap", "ln_cap")):
                cat_map[f] = "size"
            elif any(
                k in fl
                for k in (
                    "pe",
                    "pb",
                    "roe",
                    "eps",
                    "bv",
                    "profit",
                    "margin",
                    "debt",
                    "yield",
                )
            ):
                cat_map[f] = "fundamental"
            else:
                cat_map[f] = "technical"

        # Compute per-factor mean IC (approximate: mean value sign correlation with close)
        if "close" in factor_df.columns:
            returns = factor_df.groupby("ticker")["close"].pct_change()
            factor_df_copy = factor_df.copy()
            factor_df_copy["_ret"] = returns

        with self.driver.session() as session:
            for fc in factor_cols:
                cat = cat_map.get(fc, "technical")
                # Approximate IC: Pearson r between factor value and forward return
                ic_val = 0.0
                try:
                    if (
                        "_ret" in factor_df_copy.columns
                        and fc in factor_df_copy.columns
                    ):
                        valid = factor_df_copy[[fc, "_ret"]].dropna()
                        if len(valid) > 10:
                            ic_val = valid[fc].corr(valid["_ret"])
                except Exception:
                    pass

                factor = FactorNode(
                    name=fc,
                    category=cat,
                    latest_ic=round(ic_val, 4),
                    ic_stable=abs(ic_val) >= 0.02,
                )
                self._merge_factor(session, factor)

            # Stock → Factor edges (with latest factor values)
            latest = factor_df.sort_values(
                "date" if "date" in factor_df.columns else factor_df.columns[0]
            )
            for t in latest["ticker"].unique():
                row = (
                    latest[latest["ticker"] == t].iloc[-1]
                    if len(latest[latest["ticker"] == t]) > 0
                    else None
                )
                if row is None:
                    continue
                for fc in factor_cols:
                    if fc in row.index and pd.notna(row[fc]):
                        session.run(
                            f"MATCH (s:{NODE_STOCK} {{ticker: $ticker}}) "
                            f"MERGE (f:{NODE_FACTOR} {{name: $factor}}) "
                            f"MERGE (s)-[:{REL_HAS_FACTOR} {{value: $value}}]->(f)",
                            ticker=t,
                            factor=fc,
                            value=float(row[fc]),
                        )

        print(f"[KG] Ingested {len(factor_cols)} factors with {cat_map} classification")

    def ingest_report(self, report_path: str, title: str = "", report_type: str = ""):
        """摄入研究报告 → 连接提到的标的关系."""
        path = Path(report_path)
        if not path.exists():
            print(f"[KG] Report not found: {report_path}")
            return

        content = path.read_text(encoding="utf-8")[:5000]
        # Extract tickers mentioned in report
        tickers_found = set()
        for t in TICKER_INDUSTRY_MAP:
            if t in content:
                tickers_found.add(t)

        rel_path = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        rtype = report_type or self._guess_report_type(rel_path)

        report = ReportNode(
            path=rel_path,
            title=title or path.stem,
            report_type=rtype,
            generated_at=datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            tickers_covered=list(tickers_found),
        )

        with self.driver.session() as session:
            self._merge_report(session, report)
            for t in tickers_found:
                session.run(
                    f"MATCH (r:{NODE_REPORT} {{path: $path}}) "
                    f"MATCH (s:{NODE_STOCK} {{ticker: $ticker}}) "
                    f"MERGE (s)-[:{REL_MENTIONED}]->(r)",
                    path=rel_path,
                    ticker=t,
                )
        print(f"[KG] Ingested report: {rel_path} ({len(tickers_found)} tickers)")

    def ingest_event(self, event: EventNode):
        """摄入催化剂事件."""
        with self.driver.session() as session:
            self._merge_event(session, event)
            for t in event.target_tickers:
                session.run(
                    f"MATCH (e:{NODE_EVENT} {{uid: $uid}}) "
                    f"MATCH (s:{NODE_STOCK} {{ticker: $ticker}}) "
                    f"MERGE (s)-[:{REL_TRIGGERED}]->(e)",
                    uid=event.uid,
                    ticker=t,
                )
        print(
            f"[KG] Ingested event: {event.name} ({len(event.target_tickers)} tickers)"
        )

    def ingest_risk_alert(self, alert: RiskAlertNode):
        """摄入风险告警."""
        alert.created_at = alert.created_at or datetime.now().isoformat()
        with self.driver.session() as session:
            self._merge_risk_alert(session, alert)
            session.run(
                f"MATCH (r:{NODE_RISK} {{uid: $uid}}) "
                f"MATCH (s:{NODE_STOCK} {{ticker: $ticker}}) "
                f"MERGE (s)-[:{REL_TRIGGERED}]->(r)",
                uid=alert.uid,
                ticker=alert.ticker,
            )

    # ── Queries ───────────────────────────────────────────

    def query_stock_factors(self, ticker: str, top_k: int = 10) -> list:
        """查询某标的关联的因子 (按 factor IC 排名)."""
        with self.driver.session() as session:
            result = session.run(
                f"MATCH (s:{NODE_STOCK} {{ticker: $ticker}})-[:{REL_HAS_FACTOR}]->(f:{NODE_FACTOR}) "
                "RETURN f.name AS factor, f.category AS category, f.latest_ic AS ic "
                "ORDER BY abs(f.latest_ic) DESC LIMIT $k",
                ticker=ticker.upper(),
                k=top_k,
            )
            return [r.data() for r in result]

    def query_correlation_chain(
        self, ticker_a: str, ticker_b: str, max_depth: int = 3
    ) -> list:
        """查询两标的最短关联路径."""
        with self.driver.session() as session:
            result = session.run(
                f"MATCH path = shortestPath((a:{NODE_STOCK} {{ticker: $a}})-[*..{max_depth}]-(b:{NODE_STOCK} {{ticker: $b}})) "
                "RETURN [n in nodes(path) | coalesce(n.ticker, n.name, n.uid)] AS chain, "
                "length(path) AS distance",
                a=ticker_a.upper(),
                b=ticker_b.upper(),
            )
            records = [r.data() for r in result]
            return records

    def query_industry_network(self, industry: str) -> dict:
        """查询某行业内所有标的及相互关系."""
        with self.driver.session() as session:
            result = session.run(
                f"MATCH (i:{NODE_INDUSTRY} {{name: $industry}})<-[:{REL_IN_INDUSTRY}]-(s:{NODE_STOCK}) "
                "OPTIONAL MATCH (s)-[r]->(f:{NODE_FACTOR}) "
                "RETURN s.ticker AS ticker, s.price AS price, "
                "collect(DISTINCT {{factor: f.name, ic: f.latest_ic}}) AS factors",
                industry=industry,
            )
            stocks = []
            for r in result:
                d = r.data()
                d["factor_count"] = len(
                    [x for x in d.get("factors", []) if x["factor"]]
                )
                stocks.append(d)
            return {"industry": industry, "stock_count": len(stocks), "stocks": stocks}

    def query_recent_events(self, days: int = 7) -> list:
        """查询近 N 天的催化剂事件."""
        with self.driver.session() as session:
            result = session.run(
                f"MATCH (e:{NODE_EVENT}) "
                "RETURN e.name AS name, e.date AS date, e.event_type AS type, e.impact_score AS score "
                "ORDER BY e.date DESC LIMIT 50",
            )
            return [r.data() for r in result]

    def query_graph_stats(self) -> dict:
        """返回图谱统计."""
        with self.driver.session() as session:
            stats = {}
            for label in [
                "Stock",
                "Factor",
                "Industry",
                "Report",
                "Event",
                "RiskAlert",
            ]:
                r = session.run(f"MATCH (n:{label}) RETURN count(n) AS c")
                stats[label.lower()] = r.single()["c"]
            r = session.run("MATCH ()-[r]->() RETURN count(r) AS c")
            stats["relationships"] = r.single()["c"]
            return stats

    # ── Helpers ───────────────────────────────────────────

    @staticmethod
    def _guess_report_type(path: str) -> str:
        if "stock_" in path:
            return "stock_research"
        if "daily" in path or "trade" in path:
            return "daily_trade"
        if "pipeline" in path:
            return "pipeline"
        if "system" in path or "eval" in path:
            return "system_eval"
        return "other"

    def clear_all(self):
        """⚠️ 清空图谱 — 仅开发/重置时使用."""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        print("[KG] All nodes/relationships deleted")


# ── Full ingestion pipeline ──────────────────────────────


def ingest_all(
    tickers: list,
    price_df: pd.DataFrame | None = None,
    factor_df: pd.DataFrame | None = None,
    reports_dir: str = "company/reports",
) -> dict:
    """一键摄入: 行业→标的→因子→报告→事件.

    返回图谱统计.
    """
    kg = KnowledgeGraph()
    if not kg.connected:
        print("[KG] Neo4j not reachable — check NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD")
        return {"error": "Neo4j not reachable"}

    kg.init_schema()
    kg.ingest_industries()
    kg.ingest_pipeline_tickers(tickers, price_df)

    if factor_df is not None and not factor_df.empty:
        kg.ingest_factors(factor_df)

    # Ingest all reports in reports_dir
    reports_path = PROJECT_ROOT / reports_dir
    if reports_path.exists():
        for f in sorted(reports_path.glob("*.md")):
            try:
                kg.ingest_report(str(f))
            except Exception as e:
                print(f"[KG] Report ingest failed {f.name}: {e}")

    # Add key events
    events = [
        EventNode(
            name="Starship V3 First Flight",
            event_type="launch",
            target_tickers=["DXYZ"],
            date="2026-05-19",
            impact_score=0.7,
        ),
        EventNode(
            name="NVDA Q1 FY27 Earnings",
            event_type="earnings",
            target_tickers=["NVDA", "MU", "LITE", "COHR", "AMD"],
            date="2026-05-20",
            impact_score=0.9,
        ),
        EventNode(
            name="LITE Nasdaq-100 Inclusion",
            event_type="catalyst",
            target_tickers=["LITE"],
            date="2026-05-18",
            impact_score=0.5,
        ),
    ]
    for ev in events:
        try:
            kg.ingest_event(ev)
        except Exception as e:
            print(f"[KG] Event ingest failed {ev.name}: {e}")

    stats = kg.query_graph_stats()
    kg.close()
    return stats


# ── CLI ──────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OnionQuant Knowledge Graph CLI")
    parser.add_argument(
        "action",
        choices=["init", "ingest", "stats", "query", "clear"],
        help="Action to perform",
    )
    parser.add_argument("--tickers", help="Comma-separated tickers for ingest")
    parser.add_argument("--query-ticker", help="Ticker for factor query")
    parser.add_argument("--query-a", help="Ticker A for chain query")
    parser.add_argument("--query-b", help="Ticker B for chain query")
    args = parser.parse_args()

    kg = KnowledgeGraph()

    if args.action == "init":
        kg.init_schema()
        kg.ingest_industries()
        print("[KG] Ready")

    elif args.action == "ingest" and args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
        kg.ingest_pipeline_tickers(tickers)
        print(f"[KG] Ingested {len(tickers)} tickers")

    elif args.action == "stats":
        if kg.connected:
            stats = kg.query_graph_stats()
            print(json.dumps(stats, indent=2))
        else:
            print("[KG] Not connected")

    elif args.action == "query" and args.query_ticker:
        factors = kg.query_stock_factors(args.query_ticker)
        print(json.dumps(factors, indent=2))

    elif args.action == "query" and args.query_a and args.query_b:
        chain = kg.query_correlation_chain(args.query_a, args.query_b)
        print(json.dumps(chain, indent=2))

    elif args.action == "clear":
        kg.clear_all()

    kg.close()
