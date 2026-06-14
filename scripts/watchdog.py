#!/usr/bin/env python3
"""
🧅 OnionQuant Watchdog — 服务守护 + 双 Tunnel 冗余
- 每 30 秒检测所有核心服务
- 挂了自动拉起
- 主 Tunnel 断线 → 启用备用 quick tunnel → 微信发备用 URL
- 开机自启，持续运行
"""

import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from scripts._subprocess_utils import Popen, run

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

BEIJING_TZ = timezone(timedelta(hours=8))
LOG_FILE = PROJECT_ROOT / "logs" / "watchdog.log"
VENV_PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")

# Service definitions
SERVICES = {
    "server": {
        "check": lambda: _check_port(8765),
        "start": lambda: _start_process(
            [VENV_PYTHON, str(PROJECT_ROOT / "company" / "server.py")]
        ),
        "name": "server.py :8765",
    },
    "auto_reply": {
        "check": lambda: _check_python_script("wechat_auto_reply"),
        "start": lambda: _start_process(
            [VENV_PYTHON, str(PROJECT_ROOT / "scripts" / "wechat_auto_reply.py")]
        ),
        "name": "wechat_auto_reply",
    },
    "cloudflared": {
        "check": lambda: _check_process_name("cloudflared"),
        "start": lambda: _start_cloudflared(),
        "name": "cloudflared tunnel",
    },
    "wsl_tmux": {
        "check": lambda: _check_wsl_tmux(),
        "start": lambda: _start_wsl_tmux(),
        "name": "WSL tmux ceo-24x7",
    },
    "bg_scheduler": {
        "check": lambda: _check_python_script("background_scheduler"),
        "start": lambda: _start_process(
            [VENV_PYTHON, str(PROJECT_ROOT / "scripts" / "background_scheduler.py")]
        ),
        "name": "background_scheduler",
    },
}

_BACKUP_TUNNEL_URL = None
_ALERTED_FAILURES = set()  # Don't spam WeChat for the same failure
_RECOVERED = set()  # Track what recovered

CLOUDFLARED_BIN = None  # Set on init
CLOUDFLARED_CONFIG = r"C:\Users\28462\.cloudflared\config.yml"


def _ts():
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _log(msg):
    line = f"[{_ts()}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _check_port(port: int) -> bool:
    """Check if something is listening on a port."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except Exception:
        return False


def _check_process_name(name: str) -> bool:
    """Check if a process name contains the given string."""
    try:
        result = run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                f"(Get-Process | Where-Object {{ $_.ProcessName -like '*{name}*' }} | Measure-Object).Count",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return int(result.stdout.strip() or "0") > 0
    except Exception:
        return False


def _check_python_script(script_name: str) -> bool:
    """Check if a Python script is running by inspecting command lines."""
    try:
        result = run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object {{ $_.CommandLine -like '*{script_name}*' }} | Measure-Object).Count",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return int(result.stdout.strip() or "0") > 0
    except Exception:
        return False


def _start_process(args: list) -> bool:
    """Start a background process and return True if successful."""
    try:
        Popen(
            args,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return True
    except Exception as e:
        _log(f"START FAILED {args}: {e}")
        return False


def _start_cloudflared() -> bool:
    """Start cloudflared named tunnel via bash."""
    global CLOUDFLARED_BIN
    if not CLOUDFLARED_BIN:
        # Find cloudflared
        for path in [
            r"C:\Users\28462\AppData\Local\Microsoft\WinGet\Packages\Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe\cloudflared.exe",
            "/c/Users/28462/AppData/Local/Microsoft/WinGet/Packages/Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe/cloudflared",
            "cloudflared",
        ]:
            try:
                result = run(
                    [path, "--version"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                )
                if result.returncode == 0:
                    CLOUDFLARED_BIN = path
                    break
            except Exception:
                continue
    if not CLOUDFLARED_BIN:
        _log("Cloudflared binary not found!")
        return False

    try:
        Popen(
            [
                CLOUDFLARED_BIN,
                "tunnel",
                "--config",
                CLOUDFLARED_CONFIG,
                "--protocol",
                "http2",
                "run",
                "onion-tunnel",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return True
    except Exception as e:
        _log(f"Cloudflared start failed: {e}")
        return False


def _check_wsl_tmux() -> bool:
    """Check if WSL tmux ceo-24x7 is running."""
    try:
        result = run(
            ["wsl", "-e", "bash", "-c", "tmux has-session -t ceo-24x7 2>&1"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _start_wsl_tmux() -> bool:
    """Start WSL tmux with Claude Code inbox relay."""
    try:
        Popen(
            [
                "wsl",
                "-e",
                "bash",
                "-c",
                "cd /mnt/e/2026_AgentStudy/Python_code && bash scripts/start_ceo_claude.sh",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
        )
        return True
    except Exception as e:
        _log(f"WSL tmux start failed: {e}")
        return False


# ─── Backup Tunnel ───


def start_backup_tunnel():
    """Start a quick trycloudflare tunnel as backup. Returns URL or None."""
    global CLOUDFLARED_BIN, _BACKUP_TUNNEL_URL
    if not CLOUDFLARED_BIN:
        return None
    try:
        proc = Popen(
            [CLOUDFLARED_BIN, "tunnel", "--url", "http://localhost:8765"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        # Parse the trycloudflare URL from output
        import re

        deadline = time.time() + 30
        while time.time() < deadline:
            line = proc.stderr.readline() if proc.stderr else ""
            if not line and proc.poll() is not None:
                break
            m = re.search(r"(https://[a-z0-9-]+\.trycloudflare\.com)", line)
            if m:
                url = m.group(1)
                _BACKUP_TUNNEL_URL = url
                _log(f"Backup tunnel: {url}")
                return url
            time.sleep(0.1)
        return None
    except Exception as e:
        _log(f"Backup tunnel failed: {e}")
        return None


# ─── WeChat Notification ───


def _send_wechat(text: str):
    """Send alert to WeChat. Returns True on success."""
    corp_id = os.getenv("WECHAT_CORP_ID", "")
    secret = os.getenv("WECHAT_SECRET", "")
    agent_id = os.getenv("WECHAT_AGENT_ID", "")
    if not all([corp_id, secret, agent_id]):
        return False
    try:
        r = requests.get(
            f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corp_id}&corpsecret={secret}",
            timeout=10,
        )
        token = r.json().get("access_token", "")
        if not token:
            return False
        body = {
            "touser": "@all",
            "msgtype": "text",
            "agentid": int(agent_id),
            "text": {"content": text[:2000]},
        }
        r = requests.post(
            f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
            json=body,
            timeout=10,
        )
        return r.json().get("errcode") == 0
    except Exception:
        return False


# ─── Domain Health Check ───


def check_domain() -> bool:
    """Check if onionoffice.xyz is reachable."""
    try:
        r = requests.get("https://onionoffice.xyz", timeout=10)
        return r.status_code in (200, 401, 403)  # Any of these means the tunnel works
    except Exception:
        return False


# ─── Main Watchdog Loop ───


def main():
    global CLOUDFLARED_BIN

    # Find cloudflared on startup
    for path in [
        r"C:\Users\28462\AppData\Local\Microsoft\WinGet\Packages\Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe\cloudflared.exe",
        "/c/Users/28462/AppData/Local/Microsoft/WinGet/Packages/Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe/cloudflared",
        "cloudflared",
    ]:
        try:
            result = run(
                [path, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if result.returncode == 0:
                CLOUDFLARED_BIN = path
                _log(f"Cloudflared: {path}")
                break
        except Exception:
            continue

    _log("Watchdog started — monitoring all services")
    _log(f"Cloudflared binary: {CLOUDFLARED_BIN}")

    # Initial startup: ensure everything is running
    for svc_name, svc in SERVICES.items():
        if not svc["check"]():
            _log(f"STARTING {svc['name']} (was down)")
            svc["start"]()
            time.sleep(1)

    # Start backup tunnel
    _log("Starting backup tunnel...")
    start_backup_tunnel()

    _send_wechat(
        "🟢 OnionQuant Watchdog 已启动\n\n主域名: https://onionoffice.xyz\n状态: 监控中..."
    )

    last_domain_check = 0
    last_status_push = 0

    while True:
        try:
            now = time.time()

            # Check all services
            for svc_name, svc in SERVICES.items():
                if not svc["check"]():
                    _log(f"RESTARTING {svc['name']}")
                    svc["start"]()

                    if svc_name not in _ALERTED_FAILURES:
                        _ALERTED_FAILURES.add(svc_name)
                        _send_wechat(f"⚠️ {svc['name']} 已断线，正在自动重启...")

                    if svc_name in _RECOVERED:
                        _RECOVERED.remove(svc_name)
                else:
                    if svc_name in _ALERTED_FAILURES:
                        _ALERTED_FAILURES.remove(svc_name)
                        _RECOVERED.add(svc_name)
                        _log(f"RECOVERED {svc['name']}")
                        _send_wechat(f"✅ {svc['name']} 已恢复")

            # Periodic domain health check (every 5 min)
            if now - last_domain_check > 300:
                last_domain_check = now
                if check_domain():
                    if "domain" in _ALERTED_FAILURES:
                        _ALERTED_FAILURES.remove("domain")
                        _send_wechat("✅ onionoffice.xyz 已恢复")
                else:
                    if "domain" not in _ALERTED_FAILURES:
                        _ALERTED_FAILURES.add("domain")
                        # Send backup URL if available
                        backup_msg = "🔴 onionoffice.xyz 不可达！"
                        if _BACKUP_TUNNEL_URL:
                            backup_msg += f"\n\n备用地址: {_BACKUP_TUNNEL_URL}"
                        else:
                            # Try to start backup now
                            new_backup = start_backup_tunnel()
                            if new_backup:
                                backup_msg += f"\n\n备用地址: {new_backup}"
                        _send_wechat(backup_msg)

            # Hourly status push
            if now - last_status_push > 3600:
                last_status_push = now
                ok = sum(1 for s in SERVICES.values() if s["check"]())
                total = len(SERVICES)
                domain_ok = "✅" if check_domain() else "🔴"
                _send_wechat(
                    f"📊 系统状态 ({_ts()})\n\n服务: {ok}/{total} 在线\n域名: {domain_ok}\n备用: {_BACKUP_TUNNEL_URL or '无'}"
                )

            time.sleep(30)

        except KeyboardInterrupt:
            _log("Watchdog stopped")
            break
        except Exception as e:
            _log(f"Watchdog error: {e}")
            time.sleep(30)


if __name__ == "__main__":
    main()
