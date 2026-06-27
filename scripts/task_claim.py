"""Task Claim Protocol — atomic mkdir-based mutex for cron sessions.

OS analogy:
  mkdir(.claim) = Test-and-Set instruction (atomic on all filesystems)
  .claim exists  = mutex held
  rmdir(.claim)  = mutex release
  TTL 15 min     = deadlock prevention (crash recovery)

Usage:
  python scripts/task_claim.py try inbox       # ACQUIRED | SKIPPED:<reason>
  python scripts/task_claim.py release inbox    # RELEASED
  python scripts/task_claim.py status           # lists all locks
"""

import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLAIMS_DIR = PROJECT_ROOT / "company" / "task_claims"
TTL_SECONDS = 900  # 15 minutes — deadlock prevention
VALID_TYPES = {"inbox", "iteration", "redteam", "hourly", "daily", "self_evolve"}


def _claim_dir(task_type: str) -> Path:
    return CLAIMS_DIR / task_type


def _lock_path(task_type: str) -> Path:
    return _claim_dir(task_type) / ".claim"


def _info_path(task_type: str) -> Path:
    return _lock_path(task_type) / "info.json"


def _stale_dir() -> Path:
    return CLAIMS_DIR / "_STALE_"


def _now_key() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write_info(task_type: str) -> None:
    info = {
        "session_key": _now_key(),
        "pid": os.getpid(),
        "task_type": task_type,
        "acquired_at": time.time(),
    }
    _info_path(task_type).write_text(json.dumps(info), encoding="utf-8")


def _read_info(task_type: str) -> dict | None:
    p = _info_path(task_type)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"acquired_at": 0}


def _recover_stale(task_type: str) -> bool:
    """If the existing lock is stale, move it to _STALE_ and return True."""
    lock = _lock_path(task_type)
    if not lock.exists():
        return True  # no lock at all

    info = _read_info(task_type)
    if info is None:
        # lock dir exists but no info.json — stale, reclaim
        _force_reclaim(task_type)
        return True

    age = time.time() - info.get("acquired_at", 0)
    if age > TTL_SECONDS:
        _force_reclaim(task_type)
        return True

    return False  # active lock held by another session


def _force_reclaim(task_type: str) -> None:
    """Move orphaned lock to _STALE_ for audit trail."""
    lock = _lock_path(task_type)
    stale_dir = _stale_dir()
    stale_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    dest = stale_dir / f"{task_type}_{ts}"
    lock.rename(dest)


def try_acquire(task_type: str) -> tuple[bool, str]:
    """Atomically claim a task. Returns (acquired, reason)."""
    if task_type not in VALID_TYPES:
        return False, f"invalid task type: {task_type}"

    claim_dir = _claim_dir(task_type)
    claim_dir.mkdir(parents=True, exist_ok=True)

    lock = _lock_path(task_type)

    # Step 1: attempt atomic mkdir
    try:
        lock.mkdir(exist_ok=False)
        _write_info(task_type)
        return True, "acquired"
    except FileExistsError:
        pass

    # Step 2: lock exists — check TTL
    if _recover_stale(task_type):
        # stale lock recovered — retry
        try:
            lock.mkdir(exist_ok=False)
            _write_info(task_type)
            return True, "acquired (recovered stale)"
        except FileExistsError:
            return False, "locked: race after recovery"

    # Step 3: active lock
    info = _read_info(task_type)
    holder = info.get("session_key", "unknown") if info else "unknown"
    age = time.time() - (info.get("acquired_at", 0) if info else 0)
    return False, f"locked by session {holder} ({age:.0f}s ago, ttl={TTL_SECONDS}s)"


def release(task_type: str) -> tuple[bool, str]:
    """Release a claimed task."""
    if task_type not in VALID_TYPES:
        return False, f"invalid task type: {task_type}"

    lock = _lock_path(task_type)
    if not lock.exists():
        return False, "not locked"

    # Remove info.json first, then rmdir
    info = _info_path(task_type)
    info.unlink(missing_ok=True)

    try:
        lock.rmdir()
        return True, "released"
    except OSError as e:
        return False, f"failed to release: {e}"


def status() -> str:
    """Return human-readable status of all locks."""
    lines = []
    for task_type in sorted(VALID_TYPES):
        lock = _lock_path(task_type)
        if not lock.exists():
            lines.append(f"[ ] {task_type}: free")
            continue
        info = _read_info(task_type)
        if info:
            age = time.time() - info.get("acquired_at", 0)
            status_flag = "STALE" if age > TTL_SECONDS else "ACTIVE"
            lines.append(
                f"[{'!' if status_flag == 'STALE' else 'X'}] {task_type}: "
                f"{status_flag} holder={info.get('session_key', '?')} "
                f"pid={info.get('pid', '?')} age={age:.0f}s"
            )
        else:
            lines.append(f"[?] {task_type}: locked but no info")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: task_claim.py <try|release|status> [task_type]")
        print(f"Valid types: {', '.join(sorted(VALID_TYPES))}")
        sys.exit(2)

    cmd = sys.argv[1]

    if cmd == "status":
        print(status())
        sys.exit(0)

    if cmd in ("try", "release"):
        if len(sys.argv) < 3:
            print(f"Missing task_type. Valid: {', '.join(sorted(VALID_TYPES))}")
            sys.exit(2)
        task_type = sys.argv[2]

        if cmd == "try":
            ok, msg = try_acquire(task_type)
            if ok:
                print(f"ACQUIRED:{task_type}:{msg}")
            else:
                print(f"SKIPPED:{task_type}:{msg}")
            sys.exit(0 if ok else 1)

        elif cmd == "release":
            ok, msg = release(task_type)
            print(f"{'RELEASED' if ok else 'FAILED'}:{task_type}:{msg}")
            sys.exit(0 if ok else 1)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(2)


if __name__ == "__main__":
    main()
