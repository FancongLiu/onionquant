#!/usr/bin/env python3
"""API Proxy middleware — rate limiting, audit logging, provider failover.

Inspired by thunderbolt's inference proxy and free-claude-code's BaseProvider pattern.
Wraps all external API calls (LLM, data vendors) with:
  - Rate limiting (token bucket algorithm)
  - Automatic retry with exponential backoff
  - Audit logging (every request/response logged)
  - Provider failover (primary → secondary → fallback)

Pure Python, zero new dependencies beyond stdlib.
"""

import time
import json
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass
from functools import wraps

logger = logging.getLogger(__name__)


# ── Token Bucket Rate Limiter ──────────────────────────────

class TokenBucket:
    """Token bucket rate limiter — allows bursts up to capacity, refills at steady rate."""

    def __init__(self, rate: float, capacity: int):
        """
        Args:
            rate: Tokens per second refill rate.
            capacity: Maximum tokens (burst capacity).
        """
        self.rate = rate
        self.capacity = float(capacity)
        self.tokens = self.capacity
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    def acquire(self, tokens: float = 1.0) -> Tuple[bool, float]:
        """Try to acquire tokens. Returns (allowed, wait_seconds)."""
        with self.lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, 0.0
            wait = (tokens - self.tokens) / self.rate
            return False, wait

    def wait_and_acquire(self, tokens: float = 1.0, timeout: float = 30.0) -> bool:
        """Block until tokens available or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            allowed, wait = self.acquire(tokens)
            if allowed:
                return True
            time.sleep(min(wait, 1.0))
        return False


# ── Rate Limit Config ──────────────────────────────────────

@dataclass
class RateConfig:
    """Per-provider rate limits."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst: int = 10
    retry_max: int = 3
    retry_base_delay: float = 1.0  # seconds
    retry_backoff: float = 2.0     # exponential factor
    timeout: float = 30.0


# Default rate limits per provider
DEFAULT_RATES = {
    "yfinance": RateConfig(requests_per_minute=120, burst=20),
    "alpha_vantage": RateConfig(requests_per_minute=5, requests_per_hour=500, burst=3),
    "anthropic": RateConfig(requests_per_minute=50, burst=10, retry_max=5),
    "openai": RateConfig(requests_per_minute=30, burst=10, retry_max=5),
    "polygon": RateConfig(requests_per_minute=300, burst=50),
    "default": RateConfig(),
}


# ── Audit Logger ───────────────────────────────────────────

@dataclass
class CallRecord:
    """Single API call audit record."""
    provider: str
    endpoint: str
    method: str
    request_id: str
    started_at: str
    duration_ms: float
    status: str           # success | retry | error | rate_limited
    attempt: int
    error_message: str = ""
    tokens_used: int = 0  # for LLM calls
    cost_estimate: float = 0.0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class AuditLog:
    """Append-only audit log for all API calls."""

    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path
        self.records: List[CallRecord] = []
        self.lock = threading.Lock()

    def record(self, call: CallRecord):
        with self.lock:
            self.records.append(call)
            if self.log_path:
                try:
                    self.log_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(call.to_dict(), ensure_ascii=False) + "\n")
                except Exception:
                    pass

    def summary(self, minutes: int = 60) -> dict:
        cutoff = time.time() - minutes * 60
        recent = []
        for r in self.records:
            try:
                # Parse ISO timestamp, strip microseconds if present
                ts = r.started_at.split(".")[0]
                t = time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%S"))
                if t > cutoff:
                    recent.append(r)
            except (ValueError, TypeError):
                recent.append(r)
        providers = {}
        for r in recent:
            if r.provider not in providers:
                providers[r.provider] = {"calls": 0, "errors": 0, "total_ms": 0}
            providers[r.provider]["calls"] += 1
            if r.status == "error":
                providers[r.provider]["errors"] += 1
            providers[r.provider]["total_ms"] += r.duration_ms
        return {
            "total_calls": len(recent),
            "error_rate": sum(1 for r in recent if r.status == "error") / max(len(recent), 1),
            "by_provider": providers,
        }


# ── Provider Registry ──────────────────────────────────────

class ProviderRegistry:
    """Registry of API providers with failover chains.

    Pattern from free-claude-code's BaseProvider transport contract.
    Each provider has a primary endpoint and optional failover endpoints.
    """

    def __init__(self):
        self.providers: Dict[str, dict] = {}

    def register(self, name: str, endpoints: List[str],
                 rate_config: Optional[RateConfig] = None,
                 headers: Optional[dict] = None):
        self.providers[name] = {
            "endpoints": endpoints,
            "current": 0,  # index into endpoints for round-robin
            "rate_config": rate_config or DEFAULT_RATES.get(name, DEFAULT_RATES["default"]),
            "headers": headers or {},
            "failures": 0,
            "last_failure": 0.0,
        }

    def get_endpoint(self, name: str) -> Optional[str]:
        p = self.providers.get(name)
        if not p or not p["endpoints"]:
            return None
        # Skip recently-failed endpoints (cool-down: 60s)
        if p["failures"] > 3 and time.monotonic() - p["last_failure"] < 60:
            p["current"] = (p["current"] + 1) % len(p["endpoints"])
        return p["endpoints"][p["current"]]

    def mark_failure(self, name: str):
        p = self.providers.get(name)
        if p:
            p["failures"] += 1
            p["last_failure"] = time.monotonic()
            # Rotate to next endpoint
            if len(p["endpoints"]) > 1:
                p["current"] = (p["current"] + 1) % len(p["endpoints"])

    def mark_success(self, name: str):
        p = self.providers.get(name)
        if p:
            p["failures"] = 0


# ── API Proxy ──────────────────────────────────────────────

class APIProxy:
    """Central API proxy with rate limiting, retry, audit, and failover.

    Usage:
        proxy = APIProxy(audit_path=Path("logs/api_audit.jsonl"))
        proxy.register("anthropic", ["https://api.anthropics.com"])

        @proxy.call("anthropic", "/v1/messages")
        def chat(messages, **kwargs):
            ...
    """

    def __init__(self, audit_path: Optional[Path] = None):
        self.registry = ProviderRegistry()
        self.audit = AuditLog(audit_path)
        self.buckets: Dict[str, TokenBucket] = {}
        logger.info("APIProxy initialized")

    def register(self, name: str, endpoints: List[str],
                 rate_config: Optional[RateConfig] = None,
                 headers: Optional[dict] = None):
        self.registry.register(name, endpoints, rate_config, headers)
        cfg = self.registry.providers[name]["rate_config"]
        # Token bucket: rate = RPM/60 tokens/sec, capacity = burst
        self.buckets[name] = TokenBucket(
            rate=cfg.requests_per_minute / 60.0,
            capacity=cfg.burst,
        )
        logger.info("Registered provider '%s' (%d endpoints, %d rpm)",
                     name, len(endpoints), cfg.requests_per_minute)

    def call(self, provider: str, endpoint: str = "", method: str = "POST"):
        """Decorator: wrap a function with rate limiting, retry, and audit.

        The decorated function receives the resolved endpoint URL as first argument.
        """
        cfg = self.registry.providers.get(provider, {}).get(
            "rate_config", DEFAULT_RATES["default"])
        bucket = self.buckets.get(provider)

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                base_url = self.registry.get_endpoint(provider)
                if not base_url:
                    raise RuntimeError(f"No endpoint for provider '{provider}'")

                url = f"{base_url}{endpoint}"
                start = time.time()
                last_error = None
                request_id = f"{provider}-{int(start * 1000)}"

                for attempt in range(cfg.retry_max + 1):
                    # Rate limit check
                    if bucket:
                        if not bucket.wait_and_acquire(timeout=cfg.timeout):
                            record = CallRecord(
                                provider=provider, endpoint=endpoint, method=method,
                                request_id=request_id,
                                started_at=datetime.fromtimestamp(start).isoformat(),
                                duration_ms=(time.time() - start) * 1000,
                                status="rate_limited", attempt=attempt + 1,
                            )
                            self.audit.record(record)
                            raise RuntimeError(f"Rate limit exceeded for '{provider}'")

                    try:
                        result = func(url, *args, **kwargs)
                        duration = (time.time() - start) * 1000
                        record = CallRecord(
                            provider=provider, endpoint=endpoint, method=method,
                            request_id=request_id,
                            started_at=datetime.fromtimestamp(start).isoformat(),
                            duration_ms=duration, status="success",
                            attempt=attempt + 1,
                        )
                        self.audit.record(record)
                        self.registry.mark_success(provider)
                        return result

                    except Exception as e:
                        last_error = e
                        logger.warning("%s attempt %d/%d: %s",
                                       provider, attempt + 1, cfg.retry_max + 1, e)
                        self.registry.mark_failure(provider)

                        if attempt < cfg.retry_max:
                            wait = cfg.retry_base_delay * (cfg.retry_backoff ** attempt)
                            time.sleep(wait)
                            # Rotate endpoint on retry
                            base_url = self.registry.get_endpoint(provider)

                duration = (time.time() - start) * 1000
                record = CallRecord(
                    provider=provider, endpoint=endpoint, method=method,
                    request_id=request_id,
                    started_at=datetime.fromtimestamp(start).isoformat(),
                    duration_ms=duration, status="error", attempt=cfg.retry_max + 1,
                    error_message=str(last_error),
                )
                self.audit.record(record)
                raise RuntimeError(f"All {cfg.retry_max + 1} attempts failed for "
                                   f"'{provider}{endpoint}': {last_error}")

            return wrapper
        return decorator


# ── Singleton ──────────────────────────────────────────────

_global_proxy: Optional[APIProxy] = None


def get_proxy(audit_path: Optional[Path] = None) -> APIProxy:
    """Get or create the global API proxy singleton."""
    global _global_proxy
    if _global_proxy is None:
        _global_proxy = APIProxy(audit_path or Path("company/logs/api_audit.jsonl"))
    return _global_proxy


# ── Demo ────────────────────────────────────────────────────

def main():
    import random
    import tempfile

    audit_file = Path(tempfile.gettempdir()) / "demo_api_audit.jsonl"
    proxy = APIProxy(audit_file)

    # Register providers
    proxy.register("demo_provider", ["https://api.example.com"],
                   rate_config=RateConfig(requests_per_minute=30, burst=5, retry_max=2))

    # Simulate API calls
    @proxy.call("demo_provider", "/v1/test")
    def demo_call(url: str, text: str = "") -> dict:
        # Simulate occasional failure
        if random.random() < 0.2:
            raise ConnectionError("simulated failure")
        return {"url": url, "text": text, "status": "ok"}

    for i in range(5):
        try:
            result = demo_call(text=f"test_{i}")
            print(f"  [{i}] success: {result['status']}")
        except RuntimeError as e:
            print(f"  [{i}] error: {e}")

    # Audit summary
    summary = proxy.audit.summary(minutes=5)
    print(f"\nAudit (5min): {summary['total_calls']} calls, "
          f"error rate: {summary['error_rate']:.2%}")

    # Cleanup
    audit_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
