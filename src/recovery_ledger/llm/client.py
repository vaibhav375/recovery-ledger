"""The one interface every LLM-touching component in this project calls
through — persona simulation, reply-intent parsing, message drafting,
negotiation dialogue (spec section 8.5). Nothing under `kernel/` may import
this module (enforced by `tests/test_kernel_no_llm_imports.py`); everything
else in the agent loop is allowed to, but always through this interface, so
the backend can change without touching call sites.

Backend: local, open-source, no subscription (explicit project decision,
2026-08-23 — see ENGINEERING_LOG.md). `OllamaClient` talks to a local Ollama
server; default model is `qwen2.5:3b`, chosen empirically, not by
assumption — see the engineering log for the actual latency/quality
comparison against qwen2.5:7b and qwen3:4b on this project's real hardware.

`MockLLMClient` is not a placeholder to delete later — it's what keeps
`make demo` working on a clean clone with no Ollama installed and no model
pulled. Judges without a local LLM set up still get a fully running demo;
they just don't get LLM-generated dialogue in it.
"""

from __future__ import annotations

from typing import Protocol

import requests

DEFAULT_OLLAMA_MODEL = "qwen2.5:3b"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"


class LLMClient(Protocol):
    def complete(self, prompt: str, *, system: str | None = None, temperature: float = 0.7) -> str: ...


class OllamaUnavailableError(RuntimeError):
    """Raised when the configured Ollama server or model isn't reachable.
    Callers that need a guaranteed-working fallback should catch this and
    fall back to MockLLMClient, rather than let the whole run crash on a
    missing local service."""


class OllamaClient:
    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_MODEL,
        host: str = DEFAULT_OLLAMA_HOST,
        *,
        timeout_seconds: float = 60.0,
    ):
        self.model = model
        self.host = host
        self.timeout_seconds = timeout_seconds

    def complete(self, prompt: str, *, system: str | None = None, temperature: float = 0.7) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaUnavailableError(
                f"Ollama at {self.host} (model={self.model!r}) is unreachable: {exc}"
            ) from exc

        data = response.json()
        return data["message"]["content"]

    def is_available(self) -> bool:
        try:
            requests.get(f"{self.host}/api/version", timeout=2.0).raise_for_status()
            return True
        except requests.RequestException:
            return False


class MockLLMClient:
    """Deterministic, offline, no network calls. Returns a fixed response
    per call unless a `responses` mapping keyed by a substring of the
    prompt is supplied, in which case the first matching entry is used."""

    def __init__(self, default_response: str = "[mock LLM response]", responses: dict[str, str] | None = None):
        self.default_response = default_response
        self.responses = responses or {}
        self.calls: list[dict] = []

    def complete(self, prompt: str, *, system: str | None = None, temperature: float = 0.7) -> str:
        self.calls.append({"prompt": prompt, "system": system, "temperature": temperature})
        for key, value in self.responses.items():
            if key in prompt:
                return value
        return self.default_response


def build_default_client() -> LLMClient:
    """Ollama if it's actually reachable right now, MockLLMClient otherwise.
    Checked once at call time, not cached — a client built before Ollama
    starts (or after it stops) should still make the right choice."""
    ollama = OllamaClient()
    if ollama.is_available():
        return ollama
    return MockLLMClient()
