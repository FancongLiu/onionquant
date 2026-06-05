#!/usr/bin/env python3
"""
OnionQuant Auto-Healing Health Monitor
Runs every 12 hours. Checks website health and auto-recovers if down.

Recovery steps:
  1. Kill zombie processes on port 8765
  2. Recover critical files from git if deleted (server.py, routes/*.py)
  3. Restart server
  4. Verify and log

Usage:
  python scripts/health_monitor.py          # one-shot check+recover
  python scripts/health_monitor.py --dry-run  # check only, no recovery
"""

import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")
BEIJING_TZ = timezone(timedelta(hours=8))

# Files that must exist for the server to run
CRITICAL_FILES = [
    "company/server.py",
    "company/__init__.py",
    "company/routes/__init__.py",
    "company/routes/shared.py",
    "company/routes/dashboard.py",
    "company/routes/quant.py",
    "company/routes/risk.py",
    "company/routes/sentiment.py",
    "company/routes/wechat.py",
    "company/agents/__init__.py",
]

# Parent commit to recover from (before auto-commit deletions)
RECOVERY_REF = "6e4c400"


def now_ts():
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str):
    line = f"[{now_ts()}] {msg}"
    print(line, flush=True)
    log_file = PROJECT_ROOT / "logs" / "health_monitor.log"
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def check_server() -> bool:
    """Check if the server is responding on port 8765."""
    import socket

    try:
        with socket.create_connection(("127.0.0.1", 8765), timeout=5):
            return True
    except Exception:
        return False


def kill_zombie_port():
    """Kill any zombie processes on port 8765."""
    log("Killing zombie processes on port 8765...")
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "$p = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | "
                "Select-Object -ExpandProperty OwningProcess; "
                "if ($p) { Stop-Process -Id $p -Force; Write-Host 'Killed PID:' $p } "
                "else { Write-Host 'No process on port 8765' }",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except Exception as e:
        log(f"Kill failed (non-critical): {e}")


def recover_critical_files() -> list[str]:
    """Recover any missing critical files from git history."""
    recovered = []
    for filepath in CRITICAL_FILES:
        full_path = PROJECT_ROOT / filepath
        if full_path.exists():
            continue
        log(f"Recovering missing file: {filepath}")
        try:
            result = subprocess.run(
                ["git", "show", f"{RECOVERY_REF}:{filepath}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(PROJECT_ROOT),
                timeout=10,
            )
            if result.returncode == 0:
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(result.stdout, encoding="utf-8")
                recovered.append(filepath)
                log(f"  [RECOVERED] {filepath} ({len(result.stdout.splitlines())} lines)")
            else:
                log(f"  ERR: Failed to recover {filepath}: {result.stderr.strip()}")
        except Exception as e:
            log(f"  ERR: Error recovering {filepath}: {e}")
    return recovered


def check_critical_files() -> list[str]:
    """Return list of critical files that exist."""
    missing = []
    for fp in CRITICAL_FILES:
        if not (PROJECT_ROOT / fp).exists():
            missing.append(fp)
    return missing


def start_server():
    """Start the server as a background process."""
    log("Starting server...")
    try:
        subprocess.Popen(
            [VENV_PYTHON, str(PROJECT_ROOT / "company" / "server.py")],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return True
    except Exception as e:
        log(f"Failed to start server: {e}")
        return False


def verify_server(attempts: int = 6, delay: float = 3.0) -> bool:
    """Wait for server to come up, retrying."""
    for i in range(attempts):
        if check_server():
            return True
        time.sleep(delay)
    return False


def send_alert(message: str):
    """Try to send WeChat alert. Non-critical — silently skip if not configured."""
    try:
        import requests

        env_file = PROJECT_ROOT / ".env"
        corp_id = secret = agent_id = ""
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").split("\n"):
                if line.startswith("WECHAT_CORP_ID="):
                    corp_id = line.split("=", 1)[1].strip()
                elif line.startswith("WECHAT_SECRET="):
                    secret = line.split("=", 1)[1].strip()
                elif line.startswith("WECHAT_AGENT_ID="):
                    agent_id = line.split("=", 1)[1].strip()
        if not all([corp_id, secret, agent_id]):
            return
        r = requests.get(
            f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corp_id}&corpsecret={secret}",
            timeout=10,
        )
        token = r.json().get("access_token", "")
        if not token:
            return
        requests.post(
            f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
            json={"touser": "@all", "msgtype": "text", "agentid": int(agent_id), "text": {"content": message[:2000]}},
            timeout=10,
        )
    except Exception:
        pass


def main():
    dry_run = "--dry-run" in sys.argv

    log(f"=== Health Monitor {'(DRY RUN)' if dry_run else ''} ===")

    # Step 1: Check
    if check_server():
        log("OK: Server is healthy — nothing to do")
        return

    log("ERR: Server is DOWN — starting auto-recovery...")

    if dry_run:
        missing = check_critical_files()
        if missing:
            log(f"DRY RUN: Would recover {len(missing)} files: {missing}")
        log("DRY RUN: Would restart server")
        return

    # Step 2: Kill zombies
    kill_zombie_port()
    time.sleep(1)

    # Step 3: Recover missing files
    recovered = recover_critical_files()
    if recovered:
        send_alert(
            f"🔧 OnionQuant Health Monitor: 发现 {len(recovered)} 个文件丢失，已从 git 恢复\n"
            + "\n".join(recovered[:5])
            + ("\n..." if len(recovered) > 5 else "")
            + "\n正在重启服务器..."
        )

    # Step 4: Start server
    if not start_server():
        log("ERR: Failed to start server")
        send_alert("🔴 OnionQuant 服务器启动失败，需要手动检查！")
        return

    # Step 5: Verify
    if verify_server():
        log("✓ Server recovered successfully")
        send_alert(f"✅ OnionQuant 自动修复完成\n服务器已恢复\n{now_ts()}")
    else:
        log("ERR: Server started but not responding")
        send_alert("⚠️ OnionQuant 服务器已启动但无响应，可能启动缓慢，watchdog 会继续监控")


if __name__ == "__main__":
    main()
