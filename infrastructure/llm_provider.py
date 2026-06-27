"""Shared OpenAI-compatible LLM provider configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_BASE_URL = "https://ergouzi.life/v1"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_WIRE_API = "responses"
LEGACY_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
LEGACY_DEEPSEEK_MODEL = "deepseek-chat"


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    api_key: str
    base_url: str
    model: str
    wire_api: str
    is_fallback: bool = False


def _read_dotenv() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _env(name: str, dotenv_values: dict[str, str]) -> str:
    return os.getenv(name) or dotenv_values.get(name, "")


def get_llm_config(*, allow_deepseek_fallback: bool = True) -> LLMConfig | None:
    values = _read_dotenv()
    primary_key = _env("ONIONQUANT_LLM_API_KEY", values) or _env("OPENAI_API_KEY", values)
    if primary_key:
        return LLMConfig(
            provider=_env("ONIONQUANT_LLM_PROVIDER", values) or "ergouzi",
            api_key=primary_key,
            base_url=_env("ONIONQUANT_LLM_BASE_URL", values)
            or _env("OPENAI_BASE_URL", values)
            or DEFAULT_BASE_URL,
            model=_env("ONIONQUANT_LLM_MODEL", values)
            or _env("OPENAI_MODEL", values)
            or DEFAULT_MODEL,
            wire_api=(
                _env("ONIONQUANT_LLM_WIRE_API", values)
                or _env("OPENAI_WIRE_API", values)
                or DEFAULT_WIRE_API
            ).lower(),
        )

    if allow_deepseek_fallback:
        deepseek_key = _env("DEEPSEEK_API_KEY", values)
        if deepseek_key:
            return LLMConfig(
                provider="deepseek",
                api_key=deepseek_key,
                base_url=LEGACY_DEEPSEEK_BASE_URL,
                model=LEGACY_DEEPSEEK_MODEL,
                wire_api="chat",
                is_fallback=True,
            )

    return None


def extract_response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return str(text).strip()
    output = getattr(response, "output", None) or []
    chunks: list[str] = []
    for item in output:
        content = getattr(item, "content", None) or []
        for block in content:
            block_text = getattr(block, "text", None)
            if block_text:
                chunks.append(str(block_text))
    return "".join(chunks).strip()


def call_llm(
    prompt: str,
    system: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 800,
    timeout: float | None = None,
) -> tuple[str, Any | None, LLMConfig]:
    config = get_llm_config()
    if not config:
        raise RuntimeError(
            "No LLM provider configured. Set ONIONQUANT_LLM_API_KEY or OPENAI_API_KEY."
        )

    from openai import OpenAI

    client_kwargs: dict[str, Any] = {
        "api_key": config.api_key,
        "base_url": config.base_url,
    }
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    client = OpenAI(**client_kwargs)

    if config.wire_api == "responses":
        response = client.responses.create(
            model=config.model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        return extract_response_text(response), getattr(response, "usage", None), config

    response = client.chat.completions.create(
        model=config.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip(), getattr(response, "usage", None), config
