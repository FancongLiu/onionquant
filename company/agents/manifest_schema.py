#!/usr/bin/env python3
"""Agent manifest schema — financial-services pattern: YAML-defined agents.

Each department agent has a manifest declaring its role, skills, tool permissions,
worker agents, and steering examples. Manifests are self-describing, auditable,
and separate from execution code.

Pattern from: anthropics/financial-services agent.yaml + steering-examples.json
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path
import yaml


@dataclass
class WorkerAgent:
    name: str
    role: str = ""
    permissions: str = "read"  # read | write | approve
    skills: List[str] = field(default_factory=list)


@dataclass
class SkillRef:
    name: str
    path: str = ""  # relative path to skill .md file
    description: str = ""


@dataclass
class AgentManifest:
    """Self-describing agent definition, following financial-services pattern."""

    name: str  # unique agent identifier
    display_name: str = ""  # human-readable name
    department: str = ""  # owning department (matches directory)
    role: str = ""  # one-line role description
    version: str = "1.0.0"
    status: str = "active"  # active | draft | deprecated

    system_prompt: str = ""  # Core system prompt (Markdown)
    skills: List[SkillRef] = field(default_factory=list)
    workers: List[WorkerAgent] = field(default_factory=list)
    steering_examples: List[str] = field(default_factory=list)

    # Permission model: allow | deny | ask
    tool_permissions: Dict[str, str] = field(default_factory=dict)
    bash_permission: str = "ask"  # allow | deny | ask
    write_permission: str = "allow"  # allow | deny | ask
    api_permission: str = "ask"  # allow | deny | ask

    # Operational
    schedule: Optional[str] = None  # cron expression for autonomous runs
    max_retries: int = 3
    timeout_seconds: int = 300
    requires_approval: List[str] = field(
        default_factory=list
    )  # actions needing chairman

    # Memory & context
    context_budget_tokens: int = 4000
    memory_categories: List[str] = field(
        default_factory=list
    )  # relevant memory categories

    # Metadata
    created_at: str = ""
    updated_at: str = ""
    description: str = ""  # longer description

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dataclass_fields__.items():
            val = getattr(self, k)
            if (
                isinstance(val, list)
                and val
                and isinstance(val[0], (WorkerAgent, SkillRef))
            ):
                d[k] = [x.__dict__ if hasattr(x, "__dict__") else x for x in val]
            elif isinstance(val, list):
                d[k] = val
            elif isinstance(val, dict):
                d[k] = val
            else:
                d[k] = val
        return d

    def to_yaml(self) -> str:
        return yaml.dump(
            self.to_dict(),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )

    @classmethod
    def from_yaml(cls, path: Path) -> "AgentManifest":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        # Parse nested objects
        workers = []
        for w in data.pop("workers", []):
            workers.append(WorkerAgent(**w))
        skills = []
        for s in data.pop("skills", []):
            skills.append(SkillRef(**s))
        return cls(workers=workers, skills=skills, **data)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentManifest":
        workers = [WorkerAgent(**w) for w in data.pop("workers", [])]
        skills = [SkillRef(**s) for s in data.pop("skills", [])]
        return cls(workers=workers, skills=skills, **data)


# ── Manifest Registry ──────────────────────────────────────


class ManifestRegistry:
    """Load and validate all agent manifests from a directory."""

    def __init__(self, manifests_dir: Path):
        self.dir = Path(manifests_dir)
        self.manifests: Dict[str, AgentManifest] = {}
        self._load()

    def _load(self):
        for yaml_file in sorted(self.dir.glob("*.yaml")):
            try:
                m = AgentManifest.from_yaml(yaml_file)
                self.manifests[m.name] = m
            except Exception as e:
                print(f"[WARN] Failed to load {yaml_file}: {e}")

    def get(self, name: str) -> Optional[AgentManifest]:
        return self.manifests.get(name)

    def list_active(self) -> List[AgentManifest]:
        return [m for m in self.manifests.values() if m.status == "active"]

    def by_department(self, dept: str) -> List[AgentManifest]:
        return [m for m in self.manifests.values() if m.department == dept]

    def validate_all(self) -> Dict[str, List[str]]:
        """Validate all manifests, return {name: [errors]}."""
        errors = {}
        for name, m in self.manifests.items():
            errs = []
            if not m.name:
                errs.append("missing name")
            if not m.role:
                errs.append("missing role")
            if not m.system_prompt:
                errs.append("missing system_prompt")
            if m.department and not m.department.startswith("_"):
                # Verify department exists
                dept_path = Path("company/departments") / m.department
                if not dept_path.exists():
                    errs.append(f"department '{m.department}' not found")
            if errs:
                errors[name] = errs
        return errors

    def stats(self) -> dict:
        active = self.list_active()
        return {
            "total": len(self.manifests),
            "active": len(active),
            "departments": len(set(m.department for m in active)),
            "total_workers": sum(len(m.workers) for m in active),
            "total_skills": sum(len(m.skills) for m in active),
        }


# ── Demo ────────────────────────────────────────────────────


def main():
    import tempfile

    d = Path(tempfile.gettempdir()) / "demo_manifests"
    d.mkdir(exist_ok=True)

    # Write demo manifest
    demo = AgentManifest(
        name="demo_agent",
        display_name="Demo Agent",
        department="ceo_office",
        role="Demonstrate the manifest pattern",
        system_prompt="You are a demo agent. Be helpful and concise.",
        skills=[SkillRef(name="factor_analysis", path="skills/factor_analysis.md")],
        workers=[WorkerAgent(name="analyst", role="Data Analyst", permissions="read")],
        steering_examples=["Analyze AAPL factors", "Report portfolio risk"],
        tool_permissions={"bash": "deny", "web_search": "allow"},
        created_at="2026-05-17",
    )

    yaml_path = d / "demo_agent.yaml"
    yaml_path.write_text(demo.to_yaml(), encoding="utf-8")

    # Load back
    registry = ManifestRegistry(d)
    print(f"Loaded: {registry.stats()}")
    loaded = registry.get("demo_agent")
    print(f"  {loaded.name}: {loaded.role}")
    print(f"  Workers: {[w.name for w in loaded.workers]}")
    print(f"  Skills: {[s.name for s in loaded.skills]}")
    errors = registry.validate_all()
    print(f"  Validation errors: {errors}")

    # Cleanup
    yaml_path.unlink()
    d.rmdir()


if __name__ == "__main__":
    main()
