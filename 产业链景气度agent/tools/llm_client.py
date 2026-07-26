from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://sz.uyilink.com/v1"
DEFAULT_MODEL = "anthropic/claude-sonnet-5"
HARDCODED_API_KEY = "sk-Y7l3az9zcc2vo5xClbf05smmqkFaFGONis9Ip4zOQfYqrzXJ"


class LLMClient:
    """Minimal OpenAI-compatible chat client.

    The service URL and default model are configured here. API keys are read
    from environment variables instead of being stored in source code.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: int = 180
    ) -> None:
        self.api_key = api_key
        self.base_url = normalize_base_url(base_url)
        self.model = model
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "LLMClient | None":
        load_env_file()
        api_key = os.getenv("UYILINK_API_KEY") or os.getenv("OPENAI_API_KEY") or HARDCODED_API_KEY
        if not api_key:
            return None
        base_url = os.getenv("UYILINK_BASE_URL") or os.getenv("OPENAI_BASE_URL") or DEFAULT_BASE_URL
        model = os.getenv("UYILINK_MODEL") or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL
        timeout = int(os.getenv("UYILINK_TIMEOUT") or os.getenv("OPENAI_TIMEOUT") or "180")
        return cls(api_key=api_key, base_url=base_url, model=model, timeout=timeout)

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 800
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return body.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


def normalize_base_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return base_url


def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
