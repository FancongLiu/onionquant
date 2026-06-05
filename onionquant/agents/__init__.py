#!/usr/bin/env python3
"""Agent definitions and manifest schema for multi-agent orchestration.

The manifest schema defines the contract between agents:
  - AgentManifest: an agent's identity, capabilities, dependencies, trigger conditions
  - ManifestRegistry: validates and resolves inter-agent wiring at startup

Based on LangGraph's StateGraph pattern with typed node contracts.
"""
