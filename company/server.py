#!/usr/bin/env python3
"""
OnionQuant — Chairman Dashboard Server
FastAPI + SSE + watchdog file monitoring + WeChat notifications

Route modules extracted to company/routes/ (T914):
  routes/quant.py     — factors, signals, backtest, optimization, strategies
  routes/risk.py      — risk limit checks, alerts
  routes/dashboard.py — data health, logs, snapshot, wechat
"""
import asyncio
import base64
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CTX_STATE_PATH = PROJECT_ROOT / "company" / "departments" / "execution" / "context_state.json"
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

# Fix Windows GBK encoding for emoji output
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="OnionQuant Dashboard")

# ─── Auth ─────────────────────────────────────────────

# Fully public — no auth ever
PUBLIC_PATHS = {
    "/", "/api/wechat/callback", "/wecom/callback",
}

# Read-only for GET (no password to view), POST/DELETE/PUT still need auth
READ_ONLY_PATHS = {
    "/office", "/monitor", "/quant", "/factors", "/trade", "/research",
    "/api/research/dxyz", "/api/research/hynix", "/api/research/overview",
    "/api/research/catalysts", "/api/sentiment/dxyz", "/api/sentiment/watchlist",
    "/api/risk/limits", "/api/quant/factors", "/api/quant/signals",
    "/api/quant/ic_trend", "/api/quant/risk", "/api/quant/recommendations",
    "/api/quant/market", "/api/backtest/equity", "/api/dashboard/snapshot",
    "/api/tasks", "/api/task-tracker/summary", "/api/milestones",
    "/api/logs", "/api/data/health", "/api/wechat/status",
    "/api/paper/portfolio", "/api/paper/history", "/api/research/reports",
}

_AUTH_USER = os.getenv("DASHBOARD_USERNAME", "admin")
_AUTH_PASS = os.getenv("DASHBOARD_PASSWORD") or secrets.token_urlsafe(16)
if not os.getenv("DASHBOARD_PASSWORD"):
    print(f"[AUTH] No DASHBOARD_PASSWORD set — using random: {_AUTH_PASS}")


def _check_auth(request: Request) -> bool:
    token = request.query_params.get("token", "")
    if token and token == _AUTH_PASS:
        return True

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        user, pwd = decoded.split(":", 1)
        return secrets.compare_digest(user, _AUTH_USER) and secrets.compare_digest(pwd, _AUTH_PASS)
    except Exception:
        return False


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Fully public paths — no auth ever
    if path in PUBLIC_PATHS or path.startswith("/api/wechat") or path.startswith("/static/"):
        request.state.authenticated = False
        return await call_next(request)

    # Check if authenticated
    is_auth = _check_auth(request)
    request.state.authenticated = is_auth

    # Read-only: GET allowed without auth, mutations need auth
    if path in READ_ONLY_PATHS or any(
        path.startswith(p) for p in ["/api/research/reports/", "/api/inbox/file/",
                                      "/api/outbox/file/", "/api/quant/strategies/",
                                      "/api/backtest/", "/api/factor/", "/api/strategy/",
                                      "/api/research/", "/api/sentiment/"]
    ):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)
        if not is_auth:
            return Response(content="Unauthorized — POST/PUT/DELETE require authentication",
                           status_code=401)

    # All other paths (API mutations, etc.) require full auth
    if not is_auth:
        return Response(
            content="Unauthorized",
            status_code=401,
            headers={"WWW-Authenticate": "Basic realm=\"OnionQuant Dashboard\""},
        )

    return await call_next(request)


# ─── Shared state imports ────────────────────────────

from company.routes.shared import (
    INBOX_DIR, PROCESSED_DIR, OUTBOX_DIR,
    subscribers, notify_all,
    wechat_status, WECHAT_CONFIGURED, WECHAT_CORP_ID,
    WECHAT_SECRET, WECHAT_AGENT_ID,
)

# ─── Include route modules ───────────────────────────

from company.routes.quant import router as quant_router
from company.routes.risk import router as risk_router
from company.routes.dashboard import router as dashboard_router
from company.routes.sentiment import router as sentiment_router
from company.routes.wechat import router as wechat_router

app.include_router(quant_router)
app.include_router(risk_router)
app.include_router(dashboard_router)
app.include_router(sentiment_router)
app.include_router(wechat_router)

# ─── Core API Routes ─────────────────────────────────

@app.get("/api/status")
async def get_status():
    dept_dirs = [d for d in (PROJECT_ROOT / "company" / "departments").iterdir() if d.is_dir()]
    inbox_files = [f for f in INBOX_DIR.glob("*.md") if f.name != "README.md"]
    processed_files = list(PROCESSED_DIR.glob("*.md"))
    py_files = list((PROJECT_ROOT / "quant_framework").rglob("*.py"))

    return {
        "departments": len(dept_dirs),
        "inbox_pending": len(inbox_files),
        "inbox_processed": len(processed_files),
        "python_files": len(py_files),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/departments")
async def get_departments():
    import re
    depts = []
    dept_base = PROJECT_ROOT / "company" / "departments"
    for d in sorted(dept_base.iterdir()):
        if not d.is_dir():
            continue
        idx_file = d / "_INDEX.md"
        if not idx_file.exists():
            continue

        dept_id = d.name
        name = dept_id
        status = "waiting"
        task = ""
        done = 0
        in_progress = 0
        blocked = 0
        updated = ""

        first_line = ""
        try:
            with open(idx_file, encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line.startswith("# "):
                    name = first_line[2:].strip()
                for _ in range(5):
                    line = f.readline()
                    if not line:
                        break
                    m = re.search(r'\*\*状态\*\*:\s*(\w+)', line)
                    if m:
                        status = m.group(1)
                    m = re.search(r'\*\*任务\*\*:\s*(\S+)', line)
                    if m:
                        task = m.group(1)
                    m = re.search(r'\*\*完成\*\*:\s*(\d+)', line)
                    if m:
                        done = int(m.group(1))
                    m = re.search(r'\*\*进行中\*\*:\s*(\d+)', line)
                    if m:
                        in_progress = int(m.group(1))
                    m = re.search(r'\*\*阻塞\*\*:\s*(\d+)', line)
                    if m:
                        blocked = int(m.group(1))
                    m = re.search(r'\*\*更新\*\*:\s*(\S+)', line)
                    if m:
                        updated = m.group(1)
        except Exception:
            pass

        depts.append({
            "id": dept_id,
            "name": name,
            "status": status,
            "task": task,
            "done": done,
            "in_progress": in_progress,
            "blocked": blocked,
            "updated": updated,
        })

    return {"departments": depts, "count": len(depts)}


@app.post("/api/inbox")
async def post_inbox(request: Request):
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "empty text"}, status_code=400)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"MSG_{timestamp}.md"
    filepath = INBOX_DIR / filename

    content = f"# 董事长来信\n\n**时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{text}\n"
    filepath.write_text(content, encoding="utf-8")

    await notify_all("inbox_new", {"file": filename, "preview": text[:100]})

    return {"ok": True, "file": filename}


def _parse_msg_metadata(filename: str, text: str | None = None) -> dict:
    """Extract timestamp + subject from message filename and content."""
    import re
    meta = {"file": filename}

    # Parse timestamp from filename: MSG_20260518_103615.md
    m = re.match(r"MSG_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", filename)
    if m:
        meta["timestamp"] = f"{m[1]}-{m[2]}-{m[3]} {m[4]}:{m[5]}:{m[6]}"
        meta["ts_iso"] = f"{m[1]}-{m[2]}-{m[3]}T{m[4]}:{m[5]}:{m[6]}"

    # Extract subject from content
    if text:
        lines = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith("#")]
        # Find the subject: first meaningful line after headers
        subject = ""
        for line in lines:
            if len(line) > 5 and not line.startswith("**"):
                subject = line[:80]
                break
        if not subject:
            subject = text.split("\n")[0].replace("# ", "")[:80] if text else "(empty)"
        meta["subject"] = subject
        meta["preview"] = text[:300]
    else:
        meta["subject"] = filename
        meta["preview"] = "(no content)"

    return meta


@app.get("/api/inbox/history")
async def inbox_history(hours: int = 0):
    """List inbox/outbox messages. hours=2 filters to last 2 hours only."""
    from datetime import timedelta
    cutoff = None
    if hours > 0:
        cutoff = datetime.now() - timedelta(hours=hours)

    def _after_cutoff(ts_iso: str) -> bool:
        if cutoff is None:
            return True
        if not ts_iso:
            return False
        try:
            dt = datetime.fromisoformat(ts_iso)
            return dt >= cutoff
        except Exception:
            return False

    processed = []
    for f in sorted(PROCESSED_DIR.glob("MSG_*.md"), reverse=True):
        text = f.read_text(encoding="utf-8")[:500]
        meta = _parse_msg_metadata(f.name, text)
        if not _after_cutoff(meta.get("ts_iso", "")):
            continue
        meta["size"] = f.stat().st_size
        meta["status"] = "processed"
        processed.append(meta)

    pending = []
    for f in INBOX_DIR.glob("MSG_*.md"):
        if f.name.endswith(".processing") or f.name.endswith(".done"):
            continue
        text = f.read_text(encoding="utf-8")[:500]
        meta = _parse_msg_metadata(f.name, text)
        if not _after_cutoff(meta.get("ts_iso", "")):
            continue
        meta["size"] = f.stat().st_size
        meta["status"] = "pending"
        pending.append(meta)

    # Also include outbox messages in the bulletin
    outbox_msgs = []
    outbox_files = sorted(OUTBOX_DIR.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)[:80]
    for f in outbox_files:
        text = f.read_text(encoding="utf-8")[:500]
        out_meta = _parse_outbox_message(f.name, text)
        ts = out_meta.get("timestamp", "")
        if not _after_cutoff(ts.replace(" ", "T")):
            continue
        out_meta["size"] = f.stat().st_size
        out_meta["status"] = "outbox"
        out_meta["subject"] = out_meta.get("title", f.name)
        out_meta["preview"] = text[:300]
        out_meta["file"] = f.name
        outbox_msgs.append(out_meta)

    return {
        "pending": pending,
        "processed": processed[:50],
        "outbox": outbox_msgs,
        "total": len(pending) + len(processed) + len(outbox_msgs),
    }


@app.get("/api/inbox/file/{filename:path}")
async def inbox_read_file(filename: str):
    """Read a specific inbox or processed message by filename."""
    for base_dir in [INBOX_DIR, PROCESSED_DIR]:
        fp = base_dir / filename
        if fp.exists() and fp.suffix == ".md":
            text = fp.read_text(encoding="utf-8")
            return {"ok": True, "file": filename, "content": text, "size": len(text)}
    return JSONResponse({"ok": False, "error": "not found"}, status_code=404)

@app.post("/api/inbox/delete/{filename:path}")
async def inbox_delete_file(filename: str):
    """Delete (move to processed) an inbox message. Chairman-requested feature."""
    fp = INBOX_DIR / filename
    if not fp.exists() or fp.suffix != ".md":
        return JSONResponse({"ok": False, "error": "not found or not .md"}, status_code=404)
    try:
        dest = PROCESSED_DIR / filename
        fp.rename(dest)
        return {"ok": True, "file": filename, "action": "moved to processed"}
    except OSError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/outbox/delete/{filename:path}")
async def outbox_delete_file(filename: str):
    """Delete (move to processed) an outbox message."""
    fp = OUTBOX_DIR / filename
    if not fp.exists() or fp.suffix != ".md":
        return JSONResponse({"ok": False, "error": "not found or not .md"}, status_code=404)
    try:
        dest = PROCESSED_DIR / ("ARCHIVED_" + filename)
        fp.rename(dest)
        return {"ok": True, "file": filename, "action": "archived"}
    except OSError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/outbox/file/{filename:path}")
async def outbox_read_file(filename: str):
    """Read a specific outbox message by filename."""
    for base_dir in [OUTBOX_DIR, OUTBOX_DIR.parent / "chairman_outbox" / "processed"]:
        fp = base_dir / filename
        if fp.exists() and fp.suffix == ".md":
            text = fp.read_text(encoding="utf-8")
            return {"ok": True, "file": filename, "content": text, "size": len(text)}
    return JSONResponse({"ok": False, "error": "not found"}, status_code=404)


# ─── Outbox ──────────────────────────────────────────

# All outbox file prefixes Claude CLI writes
_OUTBOX_PREFIXES = ["ASK_", "NOTIFY_", "RESP_", "BRIEF_", "ALERT_", "RESEARCH_",
                     "SUMMARY_", "SENTINEL_", "INFO_", "TEST_"]

_OUTBOX_TYPE_MAP = {
    "ASK_": ("❓ 请示", "🔴"),
    "NOTIFY_": ("📢 通知", "🟡"),
    "RESP_": ("💬 回复", "🟢"),
    "BRIEF_": ("📋 简报", "🟢"),
    "ALERT_": ("🚨 预警", "🔴"),
    "RESEARCH_": ("🔬 研报", "🟡"),
    "SUMMARY_": ("📊 总结", "🟢"),
    "SENTINEL_": ("🛡️ 哨兵", "🟡"),
    "INFO_": ("ℹ️ 信息", "🟢"),
    "TEST_": ("🧪 测试", "⚪"),
}

@app.get("/api/outbox")
async def outbox_messages():
    messages = []
    for prefix in _OUTBOX_PREFIXES:
        label, priority = _OUTBOX_TYPE_MAP.get(prefix, ("📄", "⚪"))
        for f in sorted(OUTBOX_DIR.glob(f"{prefix}*.md"), reverse=True):
            text = f.read_text(encoding="utf-8")
            msg = _parse_outbox_message(f.name, text)
            msg["type"] = label
            msg["priority"] = priority
            messages.append(msg)
    # Sort by file modification time, newest first
    messages.sort(key=lambda m: m.get("file", ""), reverse=True)
    return {"messages": messages, "count": len(messages)}


@app.get("/api/outbox/count")
async def outbox_count():
    total = sum(1 for p in _OUTBOX_PREFIXES for _ in OUTBOX_DIR.glob(f"{p}*.md"))
    ask_count = sum(1 for _ in OUTBOX_DIR.glob("ASK_*.md"))
    alert_count = sum(1 for _ in OUTBOX_DIR.glob("ALERT_*.md"))
    return {"unread": ask_count, "alerts": alert_count, "total": total}


@app.post("/api/outbox")
async def post_outbox(request: Request):
    body = await request.json()
    title = body.get("title", "无标题").strip()
    text = body.get("text", "").strip()
    priority = body.get("priority", "中")
    msg_type = body.get("type", "其他")
    task_id = body.get("task_id", "")
    suggestion = body.get("suggestion", "")

    if not text:
        return JSONResponse({"ok": False, "error": "empty text"}, status_code=400)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ASK_{timestamp}.md"
    filepath = OUTBOX_DIR / filename

    priority_icon = {"高": "🔴", "中": "🟡", "低": "🟢"}.get(priority, "🟡")
    content = f"""# [{msg_type}] {title}
**优先级**：{priority_icon} {priority}
**类型**：{msg_type}
**阻塞任务ID**：{task_id}

## 需要你决定
{text}

## 我的建议
{suggestion}

---
**时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    filepath.write_text(content, encoding="utf-8")

    await notify_all("outbox_new", {
        "file": filename, "title": title, "priority": priority,
        "type": msg_type, "task_id": task_id, "preview": text[:200],
        "body": text,
    })

    return {"ok": True, "file": filename}


@app.post("/api/outbox/respond")
async def outbox_respond(request: Request):
    body = await request.json()
    outbox_file = body.get("file", "").strip()
    action = body.get("action", "defer")
    note = body.get("note", "").strip()

    if not outbox_file:
        return JSONResponse({"ok": False, "error": "missing file"}, status_code=400)

    outbox_path = OUTBOX_DIR / outbox_file
    if not outbox_path.exists():
        return JSONResponse({"ok": False, "error": "file not found"}, status_code=404)

    original = outbox_path.read_text(encoding="utf-8")

    action_label = {"approve": "✅ 已批准", "reject": "❌ 已拒绝", "defer": "⏳ 稍后处理"}.get(action, action)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    resp_filename = f"RESP_{timestamp}.md"
    resp_content = f"""# 董事长回复: {action_label}

**原始问题**：{outbox_file}
**决定**：{action_label}
**附加说明**：{note if note else '(无)'}

## 原始消息
{original[:1000]}
"""
    (INBOX_DIR / resp_filename).write_text(resp_content, encoding="utf-8")

    processed_name = f"RESOLVED_{timestamp}_{outbox_file}"
    outbox_path.rename(PROCESSED_DIR / processed_name)

    await notify_all("outbox_responded", {
        "file": outbox_file, "action": action, "response_file": resp_filename,
    })

    return {"ok": True, "action": action, "response_file": resp_filename}


@app.post("/api/outbox/delete/{filename:path}")
async def outbox_delete_file(filename: str):
    fp = OUTBOX_DIR / filename
    if not fp.exists() or fp.suffix != ".md":
        # Also check processed dir
        fp2 = OUTBOX_DIR.parent / "chairman_outbox" / "processed" / filename
        if fp2.exists() and fp2.suffix == ".md":
            fp2.unlink()
            return {"ok": True, "file": filename, "action": "deleted from processed"}
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    try:
        fp.unlink()
        return {"ok": True, "file": filename, "action": "deleted"}
    except OSError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/market/snapshot")
async def market_snapshot():
    """Return portfolio prices from context_state.json."""
    try:
        ctx = json.loads(CTX_STATE_PATH.read_text(encoding="utf-8"))
        pos = ctx.get("key_context", {}).get("chairman_position", "")
        # Extract MU price: looks for MU$XXX or MU~$XXX
        mu_price = ""
        intc_price = ""
        import re
        m_mu = re.search(r'MU[~$]+([\d.]+)', pos)
        if m_mu:
            mu_price = "$" + m_mu.group(1)
        m_intc = re.search(r'INTC[~$]+([\d.]+)', pos)
        if m_intc:
            intc_price = "$" + m_intc.group(1)
        # SOX from key_context
        sox_info = ctx.get("key_context", {}).get("macro", "")
        m_sox = re.search(r'SOX\+?([\d.]+)%', sox_info)
        sox_disp = ("SOX +" + m_sox.group(1) + "% YTD") if m_sox else "--"
        return {
            "ok": True,
            "mu": mu_price or "--",
            "intc": intc_price or "--",
            "sox": sox_disp,
            "updated": ctx.get("last_updated", ""),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _parse_outbox_message(filename: str, text: str) -> dict:
    lines = text.split("\n")
    title = filename
    priority = "中"
    msg_type = "其他"
    task_id = ""

    for line in lines[:10]:
        if line.startswith("# ") and "]" in line:
            rest = line[2:]
            if rest.startswith("["):
                bracket_end = rest.find("]")
                if bracket_end > 0:
                    msg_type = rest[1:bracket_end]
                    title = rest[bracket_end + 1:].strip()
        # Fallback: plain # Title without [TYPE] prefix (e.g. RESP files)
        if title == filename and line.startswith("# "):
            plain = line[2:].strip()
            if plain and len(plain) > 3:
                title = plain[:80]
        if "**类型**" in line:
            msg_type = line.split("**类型**：")[-1].strip() if "**类型**：" in line else msg_type
        if "**优先级**" in line:
            if "高" in line:
                priority = "高"
            elif "低" in line:
                priority = "低"
        if "**阻塞任务ID**" in line:
            task_id = line.split("**阻塞任务ID**：")[-1].strip() if "**阻塞任务ID**：" in line else ""

    # Extract timestamp from **时间**： line or filename
    timestamp = ""
    for line in lines[:20]:
        m = re.match(r"\*\*时间\*\*[：:]\s*(.+)", line)
        if m:
            timestamp = m.group(1).strip()
            break
    if not timestamp:
        # Fallback: parse from filename RESP_20260518_103615.md
        m = re.match(r".*_(\d{8})_(\d{6})\.md$", filename)
        if m:
            d, t = m.groups()
            timestamp = f"{d[:4]}-{d[4:6]}-{d[6:8]} {t[:2]}:{t[2:4]}:{t[4:6]}"

    # Build ts_iso for filtering
    ts_iso = ""
    if timestamp:
        try:
            from datetime import datetime
            dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            ts_iso = dt.isoformat()
        except ValueError:
            pass
    # Fallback: use file modification time when content timestamp is unparseable
    if not ts_iso:
        try:
            from datetime import datetime, timezone, timedelta
            fp = OUTBOX_DIR / filename
            if fp.exists():
                mtime = fp.stat().st_mtime
                from datetime import datetime, timezone, timedelta
                dt = datetime.fromtimestamp(mtime)
                ts_iso = dt.isoformat()
                if not timestamp:
                    tz_cn = timezone(timedelta(hours=8))
                    timestamp = datetime.fromtimestamp(mtime, tz=tz_cn).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    # Extract subject (first meaningful content line as subject)
    subject = title
    if not subject or subject == filename:
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("**") and len(stripped) > 3:
                subject = stripped[:80]
                break

    return {
        "file": filename, "title": title, "subject": subject,
        "priority": priority, "type": msg_type, "task_id": task_id,
        "preview": text[:200],
        "body": text,
        "size": len(text),
        "timestamp": timestamp,
        "ts_iso": ts_iso,
    }


# ─── Tasks ───────────────────────────────────────────

@app.get("/api/tasks")
async def api_tasks():
    tracker_path = PROJECT_ROOT / "TASK_TRACKER.md"
    if not tracker_path.exists():
        return {"completed": 0, "in_progress": 0, "updated": ""}

    import re
    text = tracker_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    completed = 0
    in_progress = 0
    for line in lines:
        if "✅" in line and "|" in line:
            completed += 1
        if "🔵" in line and "|" in line:
            in_progress += 1

    m_comp = re.search(r'\|\s*✅\s*已完成\s*\|\s*(\d+)\s*\|', text)
    if m_comp:
        completed = int(m_comp.group(1))

    m_prog = re.search(r'\|\s*🔵\s*进行中\s*\|\s*(\d+)\s*\|', text)
    if m_prog:
        in_progress = int(m_prog.group(1))

    updated = datetime.fromtimestamp(tracker_path.stat().st_mtime).isoformat()

    return {
        "completed": completed,
        "in_progress": in_progress,
        "updated": updated,
    }


@app.get("/api/task-tracker/summary")
async def api_task_tracker_summary():
    """Detailed task summary for the chairman office right panel."""
    tracker_path = PROJECT_ROOT / "TASK_TRACKER.md"
    if not tracker_path.exists():
        return {"tasks": [], "summary": {"total": 0, "done": 0, "sprint25_pending": 0}}

    import re
    text = tracker_path.read_text(encoding="utf-8")

    # Parse summary table
    summary = {"total": 0, "done": 0, "sprint25_pending": 0}
    m_done = re.search(r'\|\s*✅\s*已完成\s*\|\s*(\d+)\s*\|', text)
    if m_done:
        summary["done"] = int(m_done.group(1))
    m_s25 = re.search(r'\|\s*🟡\s*Sprint 25.*?\|\s*(\d+)\s*\(', text)
    if m_s25:
        summary["sprint25_pending"] = int(m_s25.group(1))

    # Parse Sprint 25 tasks from task table
    tasks = []
    in_sprint25 = False
    for line in text.split("\n"):
        if "Sprint 25" in line or "T105" in line:
            in_sprint25 = True
        if in_sprint25 and line.startswith("| T105"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                tasks.append({
                    "id": parts[0] if len(parts) > 0 else "",
                    "content": parts[1] if len(parts) > 1 else "",
                    "progress": "0%",
                    "sprint": "Sprint 25",
                })
        if in_sprint25 and line.strip() == "":
            in_sprint25 = False

    summary["total"] = summary["done"] + summary["sprint25_pending"] + 50  # rough estimate

    return {"tasks": tasks, "summary": summary, "updated": datetime.fromtimestamp(tracker_path.stat().st_mtime).isoformat()}


@app.get("/api/milestones")
async def api_milestones():
    """Extract milestones from TASK_TRACKER.md context_state.json, and outbox reports."""
    import re
    milestones = []

    # 1. From context_state.json
    ctx_path = PROJECT_ROOT / "company" / "departments" / "execution" / "context_state.json"
    if ctx_path.exists():
        try:
            import json
            ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
            for action in ctx.get("pending_actions", [])[:15]:
                # Extract date-like patterns or key events
                milestones.append({
                    "date": ctx.get("last_updated", "")[:10],
                    "text": action[:120],
                    "source": "context_state",
                })
        except Exception:
            pass

    # 2. From outbox alert files
    outbox_dir = PROJECT_ROOT / "company" / "chairman_outbox"
    if outbox_dir.exists():
        for f in sorted(outbox_dir.glob("ALERT_*.md"), reverse=True)[:5]:
            milestones.append({
                "date": f.stem.split("_")[-2] if "_" in f.stem else "",
                "text": f"红队审查: {f.stem}",
                "source": "outbox",
            })

    # 3. Key hardcoded dates from TASK_TRACKER header
    tracker_path = PROJECT_ROOT / "TASK_TRACKER.md"
    if tracker_path.exists():
        header = tracker_path.read_text(encoding="utf-8").split("\n")[2] if tracker_path.exists() else ""
        # Extract dates like "5/20", "5/21", "6/12"
        for m in re.finditer(r'(\d+/\d+)[:\s]*([^·,\n]{3,40})', header):
            date_str = f"2026-{m.group(1).replace('/', '-')}"
            milestones.append({
                "date": date_str,
                "text": m.group(2).strip()[:80],
                "source": "header",
            })

    # Sort by date
    milestones.sort(key=lambda x: x.get("date", ""), reverse=True)

    return {"milestones": milestones[:30]}


# ─── WeChat Watcher Thread ───────────────────────────

def _wechat_watcher_thread():
    """Background thread: watches outbox and pushes to WeChat."""
    import requests
    WECOM_API = "https://qyapi.weixin.qq.com/cgi-bin"
    wechat_status["connected"] = True if WECHAT_CONFIGURED else False

    if not WECHAT_CONFIGURED:
        return

    notified_files = set()
    while True:
        try:
            ask_files = sorted(OUTBOX_DIR.glob("ASK_*.md"))

            if ask_files:
                token_resp = requests.get(
                    f"{WECOM_API}/gettoken?corpid={WECHAT_CORP_ID}&corpsecret={WECHAT_SECRET}",
                    timeout=10,
                ).json()
                if token_resp.get("errcode") != 0:
                    wechat_status["last_error"] = f"Token: {token_resp}"
                    time.sleep(30)
                    continue

                token = token_resp["access_token"]

                for f in ask_files:
                    if f.name in notified_files:
                        continue
                    text = f.read_text(encoding="utf-8")[:500]
                    body = {
                        "touser": "@all",
                        "msgtype": "text",
                        "agentid": int(WECHAT_AGENT_ID),
                        "text": {"content": f"[OnionQuant Outbox]\n{text}"},
                    }
                    resp = requests.post(
                        f"{WECOM_API}/message/send?access_token={token}",
                        json=body, timeout=10,
                    ).json()

                    if resp.get("errcode") == 0:
                        notified_files.add(f.name)
                        wechat_status["last_push"] = datetime.now().isoformat()
                        wechat_status["push_count"] += 1
                        try:
                            loop.call_soon_threadsafe(
                                asyncio.ensure_future,
                                notify_all("wechat_push", {
                                    "file": f.name,
                                    "success": True,
                                    "timestamp": wechat_status["last_push"],
                                }),
                            )
                        except Exception:
                            pass
                    else:
                        wechat_status["push_errors"] += 1
            time.sleep(5)
        except Exception as e:
            wechat_status["last_error"] = str(e)[:200]
            wechat_status["push_errors"] += 1
            time.sleep(5)


def _factor_alert_thread():
    """Background: periodically checks factor decay and pushes critical alerts via SSE."""
    global loop
    time.sleep(30)

    while True:
        try:
            from quant_framework.strategies.factor_decay import check_decay_alerts
            from quant_framework.strategies.factor_combiner import _cs_ic_series
            from scripts.run_pipeline import step1_fetch, step2_factors

            from company.routes.shared import QUANT_TICKERS
            tickers = QUANT_TICKERS[:15]
            df = step1_fetch(tickers, "2025-01-01")
            factors = step2_factors(df)
            factor_cols = [c for c in factors.columns if c not in ("ticker", "date", "close")]

            ic_df = _cs_ic_series(factors, factor_cols)
            if not ic_df.empty:
                alerts = check_decay_alerts(ic_df, factor_df=factors, factor_cols=factor_cols[:12])
                critical = [a for a in alerts if a.severity == "critical"]
                if critical and loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        notify_all("factor_alert", {
                            "type": "factor_decay",
                            "critical": len(critical),
                            "warnings": sum(1 for a in alerts if a.severity == "warning"),
                            "alerts": [{"factor": a.factor, "severity": a.severity,
                                        "type": a.alert_type, "detail": a.detail}
                                       for a in alerts[:10]],
                        }), loop,
                    )
        except Exception as e:
            logger.warning(f"Factor alert thread error: {e}")
        time.sleep(300)


_wechat_thread: threading.Thread | None = None

# ─── Paper Trading ────────────────────────────────────

@app.get("/api/paper/portfolio")
async def api_paper_portfolio():
    """Virtual paper trading portfolio snapshot."""
    try:
        from quant_framework.execution.paper_tracker import PaperPortfolio
        pf = PaperPortfolio()
        return pf.get_summary()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/paper/history")
async def api_paper_history():
    """Daily performance history."""
    try:
        from quant_framework.execution.paper_tracker import HISTORY_FILE
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return []
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/paper/trade")
async def api_paper_trade(request: Request):
    """Execute a virtual trade."""
    try:
        from quant_framework.execution.paper_tracker import PaperPortfolio
        body = await request.json()
        pf = PaperPortfolio()
        result = pf.execute_trade(
            ticker=body["ticker"],
            action=body["action"],
            shares=int(body["shares"]),
            reason=body.get("reason", "manual"),
        )
        return result
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/paper/alpaca")
async def api_alpaca_account():
    """Alpaca paper trading account summary."""
    try:
        from quant_framework.execution.broker_bridge import BrokerBridge
        bridge = BrokerBridge()
        positions = bridge.get_positions()
        account = bridge.get_account_summary()
        return {
            "account": account,
            "positions": [{"symbol": p.symbol, "qty": p.qty,
                           "market_value": p.market_value,
                           "unrealized_pl": p.unrealized_pl} for p in positions],
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/market/snapshot")
async def api_market_snapshot():
    """Compact market snapshot for sidebar — MU, INTC, SOX."""
    from datetime import datetime, timezone, timedelta
    tz_cn = timezone(timedelta(hours=8))
    result = {"ok": True, "updated": datetime.now(tz_cn).strftime("%H:%M:%S")}
    try:
        import yfinance as yf
        for sym, key in [("MU", "mu"), ("INTC", "intc"), ("SOX", "sox")]:
            try:
                tk = yf.Ticker(sym)
                info = tk.info or {}
                px = info.get("currentPrice") or info.get("regularMarketPrice") or 0
                prev = info.get("regularMarketPreviousClose") or info.get("previousClose") or px
                chg = ((px - prev) / prev * 100) if prev else 0
                sign = "+" if chg >= 0 else ""
                result[key] = f"${px:,.2f} {sign}{chg:.1f}%"
            except Exception:
                result[key] = "--"
    except Exception as e:
        result["error"] = str(e)
    return result


# ─── SSE ─────────────────────────────────────────────

@app.get("/sse")
async def sse_endpoint():
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    subscribers.append(queue)
    try:
        async def event_generator():
            yield {"event": "connected", "data": json.dumps({"msg": "SSE connected"})}
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield msg
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": json.dumps({"ts": datetime.now().isoformat()})}
        return EventSourceResponse(event_generator())
    finally:
        if queue in subscribers:
            subscribers.remove(queue)


# ─── Static Files ────────────────────────────────────

def _inject_auth(html: str, request: Request, inject_token: bool = True) -> str:
    """Inject auth token or read-only marker into HTML pages."""
    if request.state.authenticated and inject_token:
        # Authenticated: inject real token
        html = html.replace(
            '<script>',
            '<script>window.DASHBOARD_TOKEN=' + json.dumps(_AUTH_PASS)
            + ';window.READ_ONLY=false;</script>\n<script>',
            1,
        )
    else:
        # Unauthenticated / read-only: no token, mark read-only
        html = html.replace(
            '<script>',
            '<script>window.READ_ONLY=true;</script>\n<script>',
            1,
        )
    return html


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Personal homepage (public) or Chairman Office (authenticated)"""
    if request.state.authenticated:
        office = PROJECT_ROOT / "company" / "chairman_office.html"
        if office.exists():
            html = office.read_text(encoding="utf-8")
            return HTMLResponse(_inject_auth(html, request))
        return HTMLResponse("<h1>Chairman Office not found.</h1>")

    # Public visitor → personal homepage
    homepage = PROJECT_ROOT / "company" / "homepage.html"
    if homepage.exists():
        return HTMLResponse(homepage.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>OnionQuant</h1><p>AI Engineer & Quant Developer</p>")


@app.get("/monitor", response_class=HTMLResponse)
async def monitor_page(request: Request):
    """System Monitor — task tracking, milestones, org status"""
    dashboard = PROJECT_ROOT / "company" / "chairman_dashboard.html"
    if dashboard.exists():
        html = dashboard.read_text(encoding="utf-8")
        html = html.replace(
            '<script src="/static/js/dashboard.js"></script>',
            '<script>window.DASHBOARD_TOKEN=' + json.dumps(_AUTH_PASS)
            + ';window.READ_ONLY=' + json.dumps(not request.state.authenticated)
            + ';</script>\n<script src="/static/js/dashboard.js"></script>',
        ) if request.state.authenticated else html.replace(
            '<script src="/static/js/dashboard.js"></script>',
            '<script>window.READ_ONLY=true;</script>\n<script src="/static/js/dashboard.js"></script>',
        )
        return HTMLResponse(html)
    return HTMLResponse("<h1>System Monitor not found.</h1>")


@app.get("/quant", response_class=HTMLResponse)
async def quant_page(request: Request):
    quant_dash = PROJECT_ROOT / "company" / "quant_dashboard.html"
    if quant_dash.exists():
        return HTMLResponse(quant_dash.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Quant Dashboard not found.</h1>")


@app.get("/factors", response_class=HTMLResponse)
async def factor_monitor_page(request: Request):
    monitor = PROJECT_ROOT / "company" / "factor_monitor.html"
    if monitor.exists():
        html = monitor.read_text(encoding="utf-8")
        return HTMLResponse(_inject_auth(html, request, inject_token=False))
    return HTMLResponse("<h1>Factor Monitor not found.</h1>")


@app.get("/office", response_class=HTMLResponse)
async def chairman_office_page(request: Request):
    office = PROJECT_ROOT / "company" / "chairman_office.html"
    if office.exists():
        html = office.read_text(encoding="utf-8")
        return HTMLResponse(_inject_auth(html, request))
    return HTMLResponse("<h1>Chairman Office not found.</h1>")


# ─── Research Panel ─────────────────────────────────────

@app.get("/trade", response_class=HTMLResponse)
async def trade_dashboard_page(request: Request):
    trade = PROJECT_ROOT / "company" / "trade_dashboard.html"
    if trade.exists():
        html = trade.read_text(encoding="utf-8")
        return HTMLResponse(_inject_auth(html, request))
    return HTMLResponse("<h1>Trading Desk not found.</h1>")


@app.get("/research", response_class=HTMLResponse)
async def research_panel_page(request: Request):
    panel = PROJECT_ROOT / "company" / "research_panel.html"
    if panel.exists():
        return HTMLResponse(panel.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Research Panel not found.</h1>")


@app.get("/api/research/dxyz")
async def api_research_dxyz():
    """DXYZ live research data."""
    try:
        import yfinance as yf
        tk = yf.Ticker("DXYZ")
        info = tk.info or {}
        hist = tk.history(period="5d")
        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose") or price
        change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0
        return {
            "ticker": "DXYZ",
            "price": round(price, 2),
            "change_pct": round(change_pct, 2),
            "nav_premium": 138,
            "rsi": 96.4,
            "risks": [
                {"label": "RSI 96 极端超买", "severity": "critical"},
                {"label": "NAV 溢价 138%", "severity": "critical"},
                {"label": "$10亿 ATM 稀释", "severity": "warning"},
                {"label": "SpaceX IPO=利空落地", "severity": "info"},
            ],
            "catalysts": [
                {"title": "SpaceX 秘密提交 IPO ($1.75T)", "time": "5/13-15", "desc": "SEC 注册已提交，史上最大 IPO，夏季上市"},
                {"title": "Starship V3 首飞 (5/19 18:30 EDT)", "time": "明天", "desc": "全新星舰+Raptor3引擎+Pad2首次使用，7月来首次"},
                {"title": "DXYZ 增持 Anthropic $1亿", "time": "近日", "desc": "via Magnitude ANC III，AI 持仓增至 32%+"},
                {"title": "IPO 招股书\"最快下周公布\"", "time": "本周随时", "desc": "5/15 起传，若公开 → DXYZ 短期脉冲"},
            ],
            "summary": "三重催化叠加: SpaceX秘密IPO+Starship V3明天首飞+招股书传闻。RSI 96极端超买,NAV溢价138%风险高。关键窗口:5/19发射结果→±30%波动。",
            "verdict": "持有观察 — Starship发射后决定去留。涨幅>20%考虑减仓20-30%",
            "verdict_class": "verdict-neutral",
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/research/hynix")
async def api_research_hynix():
    """SK Hynix tracking data."""
    try:
        import yfinance as yf
        tk = yf.Ticker("000660.KS")
        info = tk.info or {}
        price = info.get("currentPrice") or 1835000
        prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose") or price
        change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0
        return {
            "ticker": "000660.KR",
            "name": "SK Hynix",
            "price": price,
            "change_pct": round(change_pct, 2),
            "hbm_share": 60,
            "op_margin": 72,
            "summary": "HBM全球市占~60%, NVIDIA HBM4订单占~70%。Q1营收₩52.5T(+3x YoY),营业利润率72%。2026全年HBM已售罄。韩股新高,分析师PT ₩188-300万。",
            "verdict": "买入 — HBM双寡头格局稳固，NVIDIA HBM4 70%份额锁定",
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/research/overview")
async def api_research_overview():
    """Research watchlist overview."""
    tickers = ["DXYZ", "NVDA", "MU", "SNDK", "STX", "WDC", "RKLB", "LUNR", "RDW", "LITE", "COHR", "AVGO", "BABA", "JD"]
    stocks = []
    for t in tickers:
        try:
            import yfinance as yf
            tk = yf.Ticker(t)
            info = tk.info or {}
            price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
            prev = info.get("regularMarketPreviousClose") or info.get("previousClose") or price
            chg = ((price - prev) / prev * 100) if prev else 0
            stocks.append({"ticker": t, "price": round(price, 2), "change_pct": round(chg, 1), "signal": "—"})
        except Exception:
            stocks.append({"ticker": t, "price": 0, "change_pct": 0, "signal": "N/A"})
    return {
        "stocks": stocks,
        "focus_note": "DXYZ P0全仓跟踪 | NVDA 5/20财报 | 存储(MU/SNDK/STX/WDC) | 航天(RKLB/LUNR/RDW) | 光模块(LITE/COHR)",
    }


@app.get("/api/research/catalysts")
async def api_research_catalysts():
    """Upcoming catalyst calendar."""
    return {
        "events": [
            {"date": "5/18", "priority": "p1", "title": "LITE Nasdaq-100 正式纳入", "tickers": ["LITE"]},
            {"date": "5/19", "priority": "p0", "title": "Starship V3 首飞 (18:30 EDT)", "tickers": ["DXYZ"]},
            {"date": "5/20", "priority": "p0", "title": "NVDA Q1 FY27 财报 (盘后)", "tickers": ["NVDA", "MU", "LITE", "COHR", "AVGO"]},
            {"date": "6/?", "priority": "p0", "title": "SpaceX IPO 招股书公开 (预期)", "tickers": ["DXYZ"]},
            {"date": "6/?", "priority": "p1", "title": "Neutron 首飞 (RKLB)", "tickers": ["RKLB"]},
            {"date": "H2 2026", "priority": "p1", "title": "COHR 6.4T SiPh CPO 发布", "tickers": ["COHR", "LITE"]},
        ],
    }


static_dir = PROJECT_ROOT / "company" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ─── Watchdog ────────────────────────────────────────

def start_watchdog():
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class ChangeHandler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.is_directory:
                    return
                rel = os.path.relpath(event.src_path, PROJECT_ROOT)
                asyncio.run_coroutine_threadsafe(
                    notify_all("file_change", {"path": rel}),
                    loop,
                )

            def on_created(self, event):
                if event.is_directory:
                    return
                rel = os.path.relpath(event.src_path, PROJECT_ROOT)
                asyncio.run_coroutine_threadsafe(
                    notify_all("file_created", {"path": rel}),
                    loop,
                )

        observer = Observer()
        watch_dirs = [
            str(PROJECT_ROOT / "company" / "chairman_inbox"),
            str(PROJECT_ROOT / "company" / "chairman_outbox"),
            str(PROJECT_ROOT / "company" / "reports"),
            str(PROJECT_ROOT / "TASK_TRACKER.md"),
            str(PROJECT_ROOT / "company" / "departments"),
        ]
        for wd in watch_dirs:
            p = Path(wd)
            if p.is_file():
                observer.schedule(ChangeHandler(), str(p.parent), recursive=False)
            elif p.is_dir():
                observer.schedule(ChangeHandler(), str(p), recursive=False)

        observer.start()
        print(f"👁️  Watchdog monitoring {len(watch_dirs)} paths")
        return observer
    except ImportError:
        print("⚠️  watchdog not installed, auto-reload disabled")
        return None


# ─── Main ────────────────────────────────────────────

loop = None

if __name__ == "__main__":
    import uvicorn

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    observer = start_watchdog()

    if WECHAT_CONFIGURED:
        _wechat_thread = threading.Thread(target=_wechat_watcher_thread, daemon=True)
        _wechat_thread.start()
        wc_status = "enabled"
    else:
        wc_status = "disabled (missing credentials)"

    # Factor decay SSE alert thread (T940)
    _factor_thread = threading.Thread(target=_factor_alert_thread, daemon=True)
    _factor_thread.start()
    print("  📊 Factor alerts   → enabled (SSE push)")

    print("=" * 50)
    print("  🧅 OnionQuant Dashboard Server")
    print("  🌐 http://localhost:8765")
    try:
        import json
        ctx = json.loads(Path("company/departments/execution/context_state.json").read_text(encoding="utf-8"))
        tunnel = ctx.get("key_context", {}).get("tunnel_url", "")
        if tunnel:
            print(f"  🌍 {tunnel}")
    except Exception:
        pass
    print("  📬 POST /api/inbox  → 写入信箱")
    print("  📡 GET  /sse        → 实时推送")
    print("  📊 GET  /factors    → 因子监控")
    print(f"  💬 WeChat          → {wc_status}")
    print("=" * 50)

    try:
        uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
    finally:
        if observer:
            observer.stop()
            observer.join()
        print("👋 Server stopped")
