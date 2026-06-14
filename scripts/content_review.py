#!/usr/bin/env python3
"""
OnionQuant Periodic Content Reviewer
Runs twice daily. Reviews homepage + README for professionalism issues.
Outputs findings to chairman_outbox/ for SSE push to frontend.

Checks:
  1. Broken links (404, connection refused)
  2. Missing files (images, CSS, JS referenced but not found)
  3. Unverified skill claims (tags that can't be backed by code)
  4. Missing metrics (no quantified results)
  5. Content freshness (stale references, old dates)
  6. Consistency (README vs homepage claims)

Usage:
  python scripts/content_review.py          # check + write outbox
  python scripts/content_review.py --quiet  # check only, no outbox
"""

import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTBOX_DIR = PROJECT_ROOT / "company" / "chairman_outbox"
BEIJING_TZ = timezone(timedelta(hours=8))

OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

# Files to check
HOMEPAGE = PROJECT_ROOT / "onionquant" / "homepage.html"
README = PROJECT_ROOT / "README.md"
CONTRIBUTING = PROJECT_ROOT / "CONTRIBUTING.md"


def now_ts():
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def extract_urls(text: str) -> list[str]:
    """Extract all URLs from text."""
    urls = re.findall(r'https?://[^\s<>"\')\]]+', text)
    return [u.rstrip(".,;:") for u in urls]


def extract_img_srcs(html: str) -> list[str]:
    """Extract image src paths from HTML."""
    return re.findall(r'src="([^"]+)"', html)


def check_broken_links() -> list[str]:
    """Check if any external links are broken."""
    from urllib.error import URLError
    from urllib.request import Request, urlopen

    findings = []
    urls_to_check = [
        "https://github.com/FancongLiu/onionquant",
        "https://onionoffice.xyz",
    ]
    for url in urls_to_check:
        try:
            req = Request(url, headers={"User-Agent": "OnionQuant-Reviewer/1.0"})
            urlopen(req, timeout=10)
        except URLError as e:
            findings.append(f"Broken link: {url} ({e})")
    if not findings:
        findings.append("All external links accessible")
    return findings


def check_missing_files() -> list[str]:
    """Check if referenced static files exist."""
    findings = []
    if not HOMEPAGE.exists():
        findings.append("CRITICAL: homepage.html not found!")
        return findings

    html = HOMEPAGE.read_text(encoding="utf-8")
    srcs = extract_img_srcs(html)
    for src in srcs:
        if src.startswith("http"):
            continue
        if src.startswith("/static/"):
            local = PROJECT_ROOT / "onionquant" / src.lstrip("/")
            if not local.exists():
                findings.append(f"Missing file: {src} (referenced in homepage)")
    return findings


def check_skill_claims() -> list[str]:
    """Check if skill tags are backed by actual code."""
    findings = []
    skill_to_patterns = {
        "LangChain": ["langchain", "from langchain"],
        "LangGraph": ["langgraph", "from langgraph"],
        "FastAPI": ["fastapi", "from fastapi"],
        "Docker": ["docker", "dockerfile", "Dockerfile"],
        "NetworkX": ["networkx", "from networkx"],
        "PostgreSQL": ["postgresql", "psycopg", "asyncpg"],
    }
    for skill, patterns in skill_to_patterns.items():
        found = False
        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", ".venv", "__pycache__", "node_modules")]
            for fname in files:
                if not fname.endswith((".py", ".toml", ".txt", ".md")):
                    continue
                try:
                    content = (Path(root) / fname).read_text(encoding="utf-8", errors="ignore").lower()
                    for p in patterns:
                        if p.lower() in content:
                            found = True
                            break
                except Exception:
                    pass
                if found:
                    break
            if found:
                break
        if not found:
            findings.append(f"Skill '{skill}' claimed but no code evidence found")
    return findings


def check_metrics() -> list[str]:
    """Check if README and homepage contain quantified results."""
    findings = []
    for name, path in [("README", README), ("Homepage", HOMEPAGE)]:
        if not path.exists():
            findings.append(f"MISSING: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        # Look for percentage improvements, cost reductions, etc.
        has_metric = bool(
            re.search(r"(\d+[\.,]?\d*\s*%|\d+x\s|¥\d+.*\d+|saved\s+\$)", text)
        )
        if not has_metric:
            findings.append(f"{name}: No quantified metrics (%, cost, time savings)")
        else:
            findings.append(f"{name}: Metrics found [OK]")
    return findings


def check_freshness() -> list[str]:
    """Check for stale content."""
    findings = []
    now = datetime.now()
    # Check if copyright year matches current
    if HOMEPAGE.exists():
        html = HOMEPAGE.read_text(encoding="utf-8")
        current_year = str(now.year)
        if current_year not in html:
            findings.append("Homepage: copyright year may be outdated")
    # Check timeline for future-dated entries
    if HOMEPAGE.exists():
        html = HOMEPAGE.read_text(encoding="utf-8")
        dates = re.findall(r"(\d{4}-\d{2})", html)
        for d in dates:
            try:
                dt = datetime.strptime(d, "%Y-%m")
                if dt > now:
                    findings.append(f"Homepage: future date found: {d}")
            except ValueError:
                pass
    return findings


def check_consistency() -> list[str]:
    """Check consistency between README and homepage."""
    findings = []
    hp_tech = set()
    rm_tech = set()

    if HOMEPAGE.exists():
        html = HOMEPAGE.read_text(encoding="utf-8")
        hp_tech = set(re.findall(r"Python|FastAPI|LangChain|LangGraph|DeepSeek|SSE|Docker", html))

    if README.exists():
        md = README.read_text(encoding="utf-8")
        rm_tech = set(re.findall(r"Python|FastAPI|LangChain|LangGraph|DeepSeek|SSE|Docker", md))

    if hp_tech and rm_tech:
        only_hp = hp_tech - rm_tech
        only_rm = rm_tech - hp_tech
        if only_hp:
            findings.append(f"Tech in homepage but not README: {only_hp}")
        if only_rm:
            findings.append(f"Tech in README but not homepage: {only_rm}")

    return findings


def write_outbox(findings: dict):
    """Write review findings to outbox."""
    body_parts = [f"## OnionQuant 内容审查报告\n**{now_ts()} CST**\n"]
    for section, items in findings.items():
        body_parts.append(f"\n### {section}")
        for item in items:
            icon = "OK" if "OK" in item or "accessible" in item.lower() else "WARN"
            body_parts.append(f"- {icon} {item}")

    body = "\n".join(body_parts)
    filename = f"REVIEW_{datetime.now(BEIJING_TZ).strftime('%Y%m%d_%H%M%S')}.md"
    filepath = OUTBOX_DIR / filename
    filepath.write_text(f"# 内容审查报告\n\n{body}", encoding="utf-8")
    print(f"[{now_ts()}] Review written to outbox: {filename}", flush=True)


def main():
    quiet = "--quiet" in sys.argv
    print(f"[{now_ts()}] Content Review — checking homepage + README...", flush=True)

    findings = {
        "External Links": check_broken_links(),
        "Static Files": check_missing_files(),
        "Skill Claims": check_skill_claims(),
        "Metrics": check_metrics(),
        "Freshness": check_freshness(),
        "Consistency": check_consistency(),
    }

    total_issues = sum(1 for items in findings.values() for i in items if "WARN" in i or "CRITICAL" in i)

    if total_issues > 0:
        print(f"[{now_ts()}] Found {total_issues} issues", flush=True)
    else:
        print(f"[{now_ts()}] All checks passed", flush=True)

    if not quiet:
        write_outbox(findings)
    else:
        for section, items in findings.items():
            print(f"\n{section}:")
            for item in items:
                print(f"  {item}")


if __name__ == "__main__":
    main()
