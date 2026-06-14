#!/usr/bin/env python3
"""Unified logging configuration for quant_framework.

Replaces scattered print() calls with structured logging.
Usage:
    from quant_framework.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("message")
    logger.debug("detailed", extra={"data": value})
"""

import logging
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

# Default format: timestamp | module | level | message
CONSOLE_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s"
FILE_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-28s | %(filename)s:%(lineno)d | %(message)s"
DATE_FORMAT = "%m-%d %H:%M:%S"

_initialized = False

# Ring buffer for dashboard log viewer (T871)
_log_buffer: deque = deque(maxlen=200)


def setup_logging(
    level: int = logging.INFO,
    log_file: str | None = None,
    module_levels: dict | None = None,
) -> None:
    """Configure root logger for quant_framework.

    Args:
        level: Default log level (INFO for production, DEBUG for development).
        log_file: Optional path for file output (JSON Lines when .jsonl).
        module_levels: Per-module overrides, e.g. {"yfinance": logging.WARNING}.
    """
    global _initialized, _memory_handler
    if _initialized:
        return

    root = logging.getLogger("quant_framework")
    root.setLevel(logging.DEBUG)  # Capture everything, filter at handler level

    # Console handler
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(CONSOLE_FORMAT, DATE_FORMAT))
    root.addHandler(console)

    # File handler (optional)
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(path), encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT, DATE_FORMAT))
        root.addHandler(file_handler)

    # Module-level overrides
    if module_levels:
        for mod, lvl in module_levels.items():
            logging.getLogger(mod).setLevel(lvl)

    # Silence noisy third-party loggers by default
    for noisy in ["yfinance", "urllib3", "matplotlib", "PIL"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Attach memory handler for dashboard log viewer (T871)
    global _memory_handler
    if _memory_handler is None:
        _memory_handler = MemoryLogHandler()
        _memory_handler.setFormatter(logging.Formatter("%(message)s"))
        _memory_handler.setLevel(logging.DEBUG)
    root.addHandler(_memory_handler)
    # Also attach to root logger to capture all log hierarchy
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(_memory_handler)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Get a logger for the calling module.

    Usage: logger = get_logger(__name__)
    """
    if not _initialized:
        setup_logging()
    return logging.getLogger(name)


def reset_logging() -> None:
    """Reset logging state (for tests)."""
    global _initialized
    _initialized = False
    for h in logging.getLogger("quant_framework").handlers[:]:
        logging.getLogger("quant_framework").removeHandler(h)


class MemoryLogHandler(logging.Handler):
    """Handler that stores records in a ring buffer for dashboard viewing."""

    def __init__(self, capacity: int = 200):
        super().__init__()
        self.buffer = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        self.buffer.append(
            {
                "time": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "name": record.name,
                "msg": self.format(record),
            }
        )

    def get_records(self, level: str | None = None, limit: int = 50) -> list[dict]:
        records = list(self.buffer)
        if level:
            records = [r for r in records if r["level"] == level.upper()]
        return records[-limit:]


_memory_handler: MemoryLogHandler | None = None


def get_log_records(level: str | None = None, limit: int = 50) -> list[dict]:
    """Get recent log records from memory buffer (for dashboard API)."""
    global _memory_handler
    if _memory_handler is None:
        setup_logging()
    return _memory_handler.get_records(level, limit)
