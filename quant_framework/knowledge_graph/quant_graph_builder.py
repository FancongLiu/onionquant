"""Build the OnionQuant knowledge graph from project data sources.

Creates nodes for: Stocks, Factors, Departments, Tasks, Metrics
Creates edges for: supply chain, sector membership, factor exposure,
                   task assignments, metric relationships.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .neo4j_store import QuantGraphStore

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Sector mapping ───────────────────────────────────────────────

SECTOR_MAP = {
    "DXYZ": "Aerospace/SPAC",
    "MU": "Storage/DRAM",
    "AMD": "Semiconductor/AI",
    "AVGO": "Semiconductor/AI",
    "ANET": "Semiconductor/Networking",
    "NVDA": "Semiconductor/AI",
    "WDC": "Storage/HDD",
    "SNDK": "Storage/NAND",
    "STX": "Storage/HDD",
    "RKLB": "Aerospace/Launch",
    "LUNR": "Aerospace/Lunar",
    "RDW": "Aerospace/Infrastructure",
    "LITE": "Optical/Transceivers",
    "COHR": "Optical/Lasers",
    "BABA": "Ecommerce/China",
    "JD": "Ecommerce/China",
    "MRVL": "Semiconductor/CustomASIC",
    "INTC": "Semiconductor/Foundry",
}

FACTOR_LIST = [
    "momentum_21d",
    "momentum_63d",
    "reversal_5d",
    "volatility_21d",
    "volume_ratio",
    "turnover_5d",
    "size_log_mcap",
    "value_pe",
    "value_pb",
    "quality_roe",
    "growth_rev",
    "low_vol",
    "beta",
    "rsi_14",
    "macd_signal",
    "bb_position",
    "atr_14",
]

DEPARTMENTS = [
    "策略研究部",
    "风险管理部",
    "交易执行部",
    "数据工程部",
    "IT技术部",
    "舆情情报部",
    "回测引擎部",
    "开源研究院",
    "学术研究部",
    "CEO办公室",
    "极限驱动部",
    "持续进化部",
    "汇报展示部",
    "知识管理部",
    "秘书处",
]

# Quant tool stack (Phase 7) — maps tools → departments + scripts
QUANT_TOOLS = {
    "risk_threshold_engine": {
        "type": "Library",
        "category": "风险/状态",
        "pip": "risk-threshold-engine",
    },
    "statsmodels_MS": {"type": "Library", "category": "市场状态", "pip": "statsmodels"},
    "yfinance": {"type": "Library", "category": "数据/行情", "pip": "yfinance"},
    "bt_pmorissette": {"type": "Library", "category": "回测/事件驱动", "pip": "bt"},
    "empyrical": {"type": "Library", "category": "指标/绩效", "pip": "empyrical"},
    "networkx": {"type": "Library", "category": "知识图谱", "pip": "networkx"},
}
TOOL_SCRIPTS = {
    "decision_engine_v2": {
        "path": "scripts/decision_engine_v2.py",
        "description": "全量因子+决策矩阵",
    },
    "binary_catalyst_backtest": {
        "path": "scripts/binary_catalyst_backtest.py",
        "description": "二元事件回测+Monte Carlo",
    },
    "backtest_harness": {
        "path": "quant_framework/backtest/harness.py",
        "description": "统一回测框架(empyrical)",
    },
    "regime_detector": {
        "path": "quant_framework/strategies/regime_detector.py",
        "description": "MarkovSwitching市场状态",
    },
    "quant_graph_builder": {
        "path": "quant_framework/knowledge_graph/quant_graph_builder.py",
        "description": "知识图谱构建器",
    },
}
TOOL_DEPT_MAP = {
    "risk_threshold_engine": "风险管理部",
    "statsmodels_MS": "策略研究部",
    "yfinance": "数据工程部",
    "bt_pmorissette": "回测引擎部",
    "empyrical": "回测引擎部",
    "networkx": "知识管理部",
    "decision_engine_v2": "策略研究部",
    "binary_catalyst_backtest": "风险管理部",
    "backtest_harness": "回测引擎部",
    "regime_detector": "策略研究部",
    "quant_graph_builder": "知识管理部",
}


def build_quant_knowledge_graph(
    store: QuantGraphStore | None = None,
    tracker_path: Path | None = None,
    pipeline_reports_dir: Path | None = None,
) -> QuantGraphStore:
    """Build the full quant knowledge graph.

    Returns the store (creates one if not provided).
    """
    if store is None:
        store = QuantGraphStore()

    tracker_path = tracker_path or PROJECT_ROOT / "TASK_TRACKER.md"
    pipeline_reports_dir = pipeline_reports_dir or PROJECT_ROOT / "company" / "reports"

    # Phase 1: Stock nodes + sector relationships
    _build_stock_graph(store)

    # Phase 2: Factor nodes + stock-factor exposure edges
    _build_factor_graph(store)

    # Phase 3: Department nodes + task assignments
    _build_department_graph(store, tracker_path)

    # Phase 4: Supply chain edges (buyer/supplier)
    _build_supply_chain_edges(store)

    # Phase 5: Data-driven correlation edges
    build_correlation_edges(store, min_corr=0.4)

    # Phase 6: Export to HTML visualization
    export_graph_html(store)

    # Phase 7: Quant tool nodes + tool-department edges
    _build_tool_graph(store)

    logger.info(
        "Knowledge graph built: %s backend, %d stocks, %d factors, %d departments, %d tools",
        store.backend,
        len(SECTOR_MAP),
        len(FACTOR_LIST),
        len(DEPARTMENTS),
        len(QUANT_TOOLS),
    )
    return store


def _build_stock_graph(store: QuantGraphStore) -> None:
    for ticker, sector in SECTOR_MAP.items():
        store.add_node("Stock", {"id": ticker, "name": ticker, "sector": sector})
        # Sector node
        sector_id = f"sector_{sector.replace('/', '_')}"
        store.add_node("Sector", {"id": sector_id, "name": sector})
        store.add_relationship(ticker, sector_id, "BELONGS_TO")
    # Cross-sector edges
    ai_stocks = ["NVDA", "MU", "AMD", "AVGO", "SNDK", "WDC", "STX", "MRVL"]
    for i in range(len(ai_stocks)):
        for j in range(i + 1, len(ai_stocks)):
            store.add_relationship(
                ai_stocks[i], ai_stocks[j], "AI_HARDWARE_PEER", {"cluster": "ai_infra"}
            )


def _build_factor_graph(store: QuantGraphStore) -> None:
    for factor in FACTOR_LIST:
        # Parse factor category
        if "momentum" in factor:
            category = "动量因子"
        elif "reversal" in factor:
            category = "反转因子"
        elif (
            "volatility" in factor.lower()
            or "beta" in factor
            or "low_vol" in factor
            or "atr" in factor
        ):
            category = "波动因子"
        elif "volume" in factor or "turnover" in factor:
            category = "换手因子"
        elif "size" in factor:
            category = "规模因子"
        elif "value" in factor or "pe" in factor or "pb" in factor:
            category = "价值因子"
        elif "quality" in factor or "roe" in factor:
            category = "质量因子"
        elif "growth" in factor:
            category = "成长因子"
        elif "rsi" in factor:
            category = "技术指标"
        elif "macd" in factor:
            category = "技术指标"
        elif "bb_" in factor:
            category = "技术指标"
        else:
            category = "其他因子"

        store.add_node("Factor", {"id": factor, "name": factor, "category": category})
        # Category node
        cat_id = f"factor_category_{category}"
        store.add_node("FactorCategory", {"id": cat_id, "name": category})
        store.add_relationship(factor, cat_id, "IN_CATEGORY")

        # Stock-factor exposure: all stocks are exposed to all factors
        for ticker in SECTOR_MAP:
            store.add_relationship(ticker, factor, "EXPOSED_TO", {"type": "computed"})


def _build_department_graph(store: QuantGraphStore, tracker_path: Path) -> None:
    for dept in DEPARTMENTS:
        store.add_node("Department", {"id": f"dept_{dept}", "name": dept})

    # Extract tasks from TASK_TRACKER.md
    if tracker_path.exists():
        text = tracker_path.read_text(encoding="utf-8")
        tasks_found = 0
        for line in text.split("\n"):
            m = re.match(
                r"\|\s*(T\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(P\d)\s*\|\s*(.+?)\s*\|",
                line,
            )
            if m:
                task_id, name, dept, priority, status = (s.strip() for s in m.groups())
                store.add_node(
                    "Task",
                    {
                        "id": task_id,
                        "name": name,
                        "priority": priority,
                        "status": status,
                    },
                )
                store.add_relationship(task_id, f"dept_{dept}", "ASSIGNED_TO")
                store.add_relationship(task_id, f"priority_{priority}", "HAS_PRIORITY")
                tasks_found += 1
        logger.info("Extracted %d tasks from TASK_TRACKER.md", tasks_found)


def _build_tool_graph(store: QuantGraphStore) -> None:
    """Phase 7: Add quant tool/script nodes + connect to departments."""
    for tool_id, info in QUANT_TOOLS.items():
        store.add_node(
            "Tool",
            {
                "id": tool_id,
                "name": tool_id,
                "category": info["category"],
                "pip": info["pip"],
            },
        )
        dept = TOOL_DEPT_MAP.get(tool_id)
        if dept:
            store.add_relationship(tool_id, f"dept_{dept}", "USED_BY")
    for script_id, info in TOOL_SCRIPTS.items():
        store.add_node(
            "Script",
            {
                "id": script_id,
                "name": script_id,
                "path": info["path"],
                "description": info["description"],
            },
        )
        dept = TOOL_DEPT_MAP.get(script_id)
        if dept:
            store.add_relationship(script_id, f"dept_{dept}", "MAINTAINED_BY")
        # Connect scripts to libraries they use
        if script_id == "decision_engine_v2":
            for lib in [
                "risk_threshold_engine",
                "yfinance",
                "bt_pmorissette",
                "statsmodels_MS",
            ]:
                store.add_relationship(script_id, lib, "DEPENDS_ON")
        elif script_id == "binary_catalyst_backtest":
            for lib in ["bt_pmorissette", "yfinance", "empyrical"]:
                store.add_relationship(script_id, lib, "DEPENDS_ON")
        elif script_id == "backtest_harness":
            store.add_relationship(script_id, "empyrical", "DEPENDS_ON")
        elif script_id == "regime_detector":
            store.add_relationship(script_id, "statsmodels_MS", "DEPENDS_ON")
        elif script_id == "quant_graph_builder":
            store.add_relationship(script_id, "networkx", "DEPENDS_ON")


def build_correlation_edges(
    store: QuantGraphStore,
    price_data_path: Path | None = None,
    min_corr: float = 0.5,
) -> int:
    """Build stock→stock edges from price correlation data (data-driven).

    Reads the latest pipeline parquet, computes pairwise correlations,
    and adds CORRELATED_WITH edges for pairs above min_corr.
    Returns number of edges added.
    """
    import pandas as pd

    data_dir = PROJECT_ROOT / "quant_framework" / "data" / "raw"
    parquet_files = sorted(data_dir.glob("price_*.parquet"))
    if price_data_path:
        df = pd.read_parquet(price_data_path)
    elif parquet_files:
        df = pd.read_parquet(parquet_files[-1])
    else:
        logger.warning("No price data found for correlation edges")
        return 0

    # Pivot to dates × tickers
    pivot = df.pivot_table(index="date", columns="ticker", values="close")
    rets = pivot.pct_change().dropna(how="all")
    corr = rets.corr()

    edge_count = 0
    tickers = [t for t in SECTOR_MAP if t in corr.columns]
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            ti, tj = tickers[i], tickers[j]
            val = corr.loc[ti, tj]
            if abs(val) >= min_corr:
                store.add_relationship(
                    ti,
                    tj,
                    "CORRELATED_WITH",
                    {"correlation": round(float(val), 3), "source": "price_returns"},
                )
                edge_count += 1
    logger.info("Added %d correlation edges (min_corr=%.2f)", edge_count, min_corr)
    return edge_count


def export_graph_html(
    store: QuantGraphStore, output_path: Path | None = None
) -> Path:
    """Export the knowledge graph as an interactive vis.js HTML page.

    Returns path to the generated HTML file.
    """
    import json

    output_path = output_path or (
        PROJECT_ROOT / "company" / "reports" / "knowledge_graph_onionquant.html"
    )
    g = store.get_full_graph()

    nodes = []
    edges_list = []
    node_ids_seen = set()

    color_map = {
        "Stock": "#3b82f6",
        "Sector": "#f0b90b",
        "Factor": "#10b981",
        "FactorCategory": "#8b5cf6",
        "Department": "#ec4899",
        "Task": "#f59e0b",
        "Tool": "#06b6d4",
        "Script": "#14b8a6",
    }

    for nid, ndata in g.nodes(data=True):
        if nid in node_ids_seen:
            continue
        node_ids_seen.add(nid)
        label = ndata.get("label", "Unknown")
        nodes.append(
            {
                "id": nid,
                "label": ndata.get("name", nid),
                "group": label,
                "color": color_map.get(label, "#94a3b8"),
            }
        )

    for src, dst, edata in g.edges(data=True):
        rel = edata.get("rel_type", "RELATED_TO")
        edges_list.append(
            {
                "from": src,
                "to": dst,
                "label": rel,
                "arrows": "to",
            }
        )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><title>OnionQuant 知识图谱</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis/9.1.2/vis-network.min.js"></script>
<style>
  body {{ margin:0; background:#0a0e17; font-family:'Microsoft YaHei',sans-serif; }}
  #graph {{ width:100vw; height:100vh; }}
  .info {{ position:fixed; top:12px; left:16px; color:#f0b90b; font-size:0.85em; z-index:10; }}
</style>
</head>
<body>
<div class="info">🧅 OnionQuant 知识图谱 — {len(nodes)} 节点, {len(edges_list)} 边 — {store.backend} 后端</div>
<div id="graph"></div>
<script>
var nodes = new vis.DataSet({json.dumps(nodes, ensure_ascii=False)});
var edges = new vis.DataSet({json.dumps(edges_list, ensure_ascii=False)});
var container = document.getElementById('graph');
var data = {{ nodes: nodes, edges: edges }};
var options = {{
  physics: {{ solver:'forceAtlas2Based', forceAtlas2Based:{{ gravitationalConstant:-80, centralGravity:0.005 }} }},
  edges: {{ font:{{ size:9, color:'#94a3b8' }}, color:'#334155', arrows:{{ to:{{ scaleFactor:0.5 }} }} }},
  groups: {{ Stock:{{ shape:'dot', size:20 }}, Sector:{{ shape:'diamond', size:14 }}, Factor:{{ shape:'square', size:10 }} }},
}};
new vis.Network(container, data, options);
</script></body></html>"""

    output_path.write_text(html, encoding="utf-8")
    logger.info(
        "Knowledge graph HTML exported to %s (%d nodes, %d edges)",
        output_path,
        len(nodes),
        len(edges_list),
    )
    return output_path


def _build_supply_chain_edges(store: QuantGraphStore) -> None:
    edges: list[tuple[str, str, str, dict | None]] = [
        # GPU supply chain
        ("NVDA", "MU", "SUPPLIER_OF", {"component": "HBM"}),
        ("NVDA", "SNDK", "SUPPLIER_OF", {"component": "NAND"}),
        ("NVDA", "LITE", "SUPPLIER_OF", {"component": "optical_transceivers"}),
        ("NVDA", "COHR", "SUPPLIER_OF", {"component": "laser_components"}),
        ("NVDA", "ANET", "SUPPLIER_OF", {"component": "network_switches"}),
        # AVGO custom silicon
        ("AVGO", "MU", "SUPPLIER_OF", {"component": "HBM_for_XPU"}),
        ("AVGO", "NVDA", "COMPETITOR_OF", {"market": "AI_custom_silicon"}),
        ("AVGO", "ANET", "PARTNER_OF", {"market": "data_center_networking"}),
        # HBM supply chain
        ("MU", "AMD", "COMPETITOR_OF", {"market": "HBM"}),
        ("MU", "SNDK", "COMPETITOR_OF", {"market": "memory"}),
        ("WDC", "STX", "COMPETITOR_OF", {"market": "HDD_storage"}),
        ("SNDK", "STX", "COMPETITOR_OF", {"market": "enterprise_storage"}),
        # Aerospace
        ("RKLB", "LUNR", "COMPETITOR_OF", {"market": "space_launch"}),
        ("RKLB", "DXYZ", "RELATED_TO", {"via": "SpaceX_exposure"}),
        ("LUNR", "DXYZ", "RELATED_TO", {"via": "space_sector"}),
        ("RDW", "RKLB", "PARTNER_OF", {"market": "space_infrastructure"}),
        ("RDW", "LUNR", "PARTNER_OF", {"market": "space_infrastructure"}),
        # Optical
        ("LITE", "COHR", "COMPETITOR_OF", {"market": "optical_components"}),
        ("LITE", "AVGO", "SUPPLIER_OF", {"component": "optical_transceivers"}),
        # China tech
        ("BABA", "JD", "COMPETITOR_OF", {"market": "ecommerce_china"}),
        # AI hardware cluster
        ("NVDA", "AMD", "COMPETITOR_OF", {"market": "AI_GPU"}),
        ("ANET", "NVDA", "CUSTOMER_OF", {"relationship": "Spectrum-X_switches"}),
        # Storage cluster
        ("MU", "SNDK", "SUPPLIER_OF", {"market": "NAND_controller"}),
        ("WDC", "SNDK", "RELATED_TO", {"via": "spin_off_history"}),
        # MRVL custom ASIC ecosystem
        ("MRVL", "AVGO", "COMPETITOR_OF", {"market": "custom_ASIC"}),
        ("MRVL", "NVDA", "PARTNER_OF", {"via": "NVLink_Fusion_$2B"}),
        ("MRVL", "LITE", "RELATED_TO", {"via": "CelestialAI_CPO"}),
        ("MRVL", "COHR", "RELATED_TO", {"via": "optical_interconnect"}),
        ("MRVL", "ANET", "RELATED_TO", {"via": "data_center_networking"}),
    ]
    store.add_relationships_batch(edges)
