"""
OnionQuant — Multi-Agent Quantitative Analysis System

A layered multi-agent system organized as a virtual company hierarchy.
CEO delegates to 15+ department agents for factor scanning, regime detection,
risk assessment, sentiment analysis, and market research.

Core packages:
  - agents: Agent definitions and manifest schema
  - api: FastAPI route handlers (quant, risk, dashboard, sentiment, wechat)
  - departments: Department agent implementations
  - tools: External data scanners and analysis pipelines
  - infrastructure: Database, knowledge graph, memory store, model routing
"""

__version__ = "0.1.0"
