#!/usr/bin/env python3
"""update_knowledge_graph.py — Auto-update department knowledge graph.

Reads department manifest YAMLs and codebase module imports to
regenerate the interactive knowledge graph (NetworkX + PyVis).

Usage:
    python scripts/update_knowledge_graph.py              # full rebuild
    python scripts/update_knowledge_graph.py --no-stocks  # departments + tech only
"""

import argparse
import json
import sys
from pathlib import Path

import networkx as nx
from pyvis.network import Network

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = PROJECT_ROOT / "company" / "reports" / "knowledge_graph_onionquant.html"


def scan_departments() -> dict:
    """Scan company/agents/manifests/ for department YAMLs."""
    dept_info = {}
    manifest_dir = PROJECT_ROOT / "company" / "agents" / "manifests"
    if not manifest_dir.exists():
        return _default_departments()
    for yf in manifest_dir.glob("*.yaml"):
        try:
            import yaml
            data = yaml.safe_load(yf.read_text(encoding="utf-8"))
            name = data.get("name", yf.stem)
            dept_info[yf.stem] = {
                "name": name,
                "description": data.get("description", ""),
            }
        except Exception:
            continue
    return dept_info or _default_departments()


def _default_departments() -> dict:
    return {
        "ceo_office": {"name": "CEO办公室"},
        "extreme_drive": {"name": "极限驱动部"},
        "strategy_research": {"name": "策略研究部"},
        "risk_management": {"name": "风险管理部"},
        "data_engineering": {"name": "数据工程部"},
        "it_tech": {"name": "IT技术部"},
        "backtest_engine": {"name": "回测引擎部"},
        "trading_execution": {"name": "交易执行部"},
        "sentiment_intel": {"name": "舆情情报部"},
        "academic_research": {"name": "学术研究部"},
        "open_source_research": {"name": "开源研究院"},
        "continuous_evolution": {"name": "持续进化部"},
        "knowledge_management": {"name": "知识管理部"},
        "secretariat": {"name": "秘书处"},
        "reporting": {"name": "汇报展示部"},
        "infra_ops": {"name": "基础设施部"},
    }


def scan_tech_stack() -> list:
    """Detect tech stack from project imports and requirements."""
    techs = set()
    req_path = PROJECT_ROOT / "requirements.txt"
    if req_path.exists():
        for line in req_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                pkg = line.split("==")[0].split(">=")[0].split("<")[0].strip()
                if pkg and len(pkg) > 2:
                    techs.add(pkg)
    # Manual additions from CLAUDE.md
    techs.update(["Python3.12", "FastAPI", "SSE", "Docker", "TimescaleDB",
                  "Dagster", "WeChat-SDK", "LedoitWolf", "NetworkX", "PyVis"])
    return sorted(techs)


def scan_stocks() -> list:
    """Read watchlist from TASK_TRACKER.md PIPELINE_TICKERS."""
    tracker = PROJECT_ROOT / "TASK_TRACKER.md"
    if not tracker.exists():
        return ["DXYZ", "INTC", "MU", "AMD", "NVDA"]
    import re
    text = tracker.read_text(encoding="utf-8")
    m = re.search(r"PIPELINE_TICKERS\s*\|\s*(.+?)\s*\|", text)
    if m:
        return [t.strip().upper() for t in m.group(1).split(",") if t.strip()]
    return ["DXYZ", "INTC", "MU", "AMD", "NVDA"]


def build_graph(dept_info: dict, techs: list, stocks: list) -> nx.DiGraph:
    G = nx.DiGraph()

    for did, info in dept_info.items():
        G.add_node(did, label=info["name"], title=info["name"], group="department", size=40)

    for t in techs:
        G.add_node(t, label=t, title=t, group="tech", size=20)

    for s in stocks:
        G.add_node(s, label=s, title=f"Stock: {s}", group="stock", size=25)

    # Edges: tech → departments
    tech_dept_map = {
        "yfinance": ["data_engineering", "sentiment_intel", "trading_execution", "strategy_research"],
        "OpenBB": ["data_engineering"],
        "Qlib": ["strategy_research"],
        "Riskfolio-Lib": ["risk_management", "trading_execution"],
        "empyrical": ["backtest_engine", "risk_management"],
        "Alphalens": ["strategy_research"],
        "Backtrader": ["backtest_engine"],
        "FastAPI": ["it_tech"],
        "Dagster": ["data_engineering"],
        "PRAW": ["sentiment_intel"],
        "FinBERT": ["sentiment_intel"],
        "NetworkX": ["it_tech", "knowledge_management"],
        "PyVis": ["it_tech", "knowledge_management"],
    }
    for tech, depts in tech_dept_map.items():
        if tech in G:
            for d in depts:
                if d in G:
                    G.add_edge(d, tech)

    # Stock → research departments
    for s in stocks:
        if s in G:
            for d in ["strategy_research", "sentiment_intel", "risk_management"]:
                if d in G:
                    G.add_edge(d, s)
            G.add_edge("ceo_office", s)

    # Inter-department
    G.add_edge("continuous_evolution", "strategy_research")
    G.add_edge("continuous_evolution", "risk_management")
    G.add_edge("continuous_evolution", "sentiment_intel")
    G.add_edge("knowledge_management", "ceo_office")

    return G


def render_html(G: nx.DiGraph, out_path: Path):
    net = Network(height="800px", width="100%", directed=True, notebook=False, bgcolor="#0a0e17")
    net.from_nx(G)

    colors = {"department": "#3b82f6", "tech": "#10b981", "stock": "#f0b90b"}
    for node in net.nodes:
        group = node.get("group", "")
        node["color"] = colors.get(group, "#94a3b8")
        if group == "department":
            node["shape"] = "box"
        elif group == "stock":
            node["shape"] = "triangle"

    net.options = {
        "nodes": {"font": {"size": 14, "color": "#e2e8f0"}, "borderWidth": 2},
        "edges": {"color": {"color": "#475569", "opacity": 0.6},
                  "arrows": {"to": {"enabled": True, "scaleFactor": 0.5}}},
        "physics": {"barnesHut": {"gravitationalConstant": -3000, "centralGravity": 0.3, "springLength": 180}},
        "interaction": {"hover": True, "tooltipDelay": 100, "navigationButtons": True},
    }
    net.save_graph(str(out_path))


def main():
    parser = argparse.ArgumentParser(description="Update knowledge graph")
    parser.add_argument("--no-stocks", action="store_true")
    args = parser.parse_args()

    depts = scan_departments()
    techs = scan_tech_stack()
    stocks = [] if args.no_stocks else scan_stocks()

    print(f"Building knowledge graph: {len(depts)} depts, {len(techs)} techs, {len(stocks)} stocks")
    G = build_graph(depts, techs, stocks)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    render_html(G, OUT_PATH)
    print(f"Done: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges → {OUT_PATH}")


if __name__ == "__main__":
    main()
