import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import autonomy_watchdog as watchdog


def _redirect_paths(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(watchdog, "PROJECT_ROOT", root)
    monkeypatch.setattr(watchdog, "RUNTIME_DIR", root / "company" / "runtime")
    monkeypatch.setattr(watchdog, "QUEUE_DIR", root / "company" / "evolution_queue")
    monkeypatch.setattr(watchdog, "HEARTBEAT_FILE", root / "company" / "runtime" / "agent_heartbeat.json")
    monkeypatch.setattr(watchdog, "STATUS_FILE", root / "company" / "runtime" / "autonomy_status.json")


def test_heartbeat_marks_agent_fresh(tmp_path, monkeypatch):
    _redirect_paths(monkeypatch, tmp_path)

    heartbeat = watchdog.write_heartbeat("test-session", note="alive")
    status = watchdog.inspect(ttl_seconds=3600)

    assert heartbeat["session_id"] == "test-session"
    assert heartbeat["note"] == "alive"
    assert status["heartbeat_stale"] is False
    assert status["pending_recovery_tasks"] == []


def test_stale_heartbeat_queues_one_recovery_task(tmp_path, monkeypatch):
    _redirect_paths(monkeypatch, tmp_path)

    queued = watchdog.queue_recovery_task("missing heartbeat", ttl_seconds=1)
    queued_again = watchdog.queue_recovery_task("missing heartbeat", ttl_seconds=1)
    status = watchdog.inspect(ttl_seconds=1)

    assert queued is not None
    assert queued.exists()
    assert queued_again is None
    assert len(status["pending_recovery_tasks"]) == 1
    assert "AUTO_EVOLVE_RECOVERY_" in status["pending_recovery_tasks"][0]
