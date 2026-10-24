"""Ollama LLM and embedding integration for Pinni supervisor and agents.

Follows the bounded supervisor pattern:
1. Typed decisions with JSON schema enforced via Ollama's `format` parameter.
2. Structured categorization, translation checking and explanation generation.
3. Fallback when Ollama or a specific model is offline.
"""
import json
import time
from typing import Any, Callable, Dict, List, Optional
import httpx

from .config import Settings, default_settings


class LLMUnavailable(RuntimeError):
    pass


class OllamaLLM:
    """Client for Ollama models (e.g. Qwen 3.5 quantized, nomic-embed-text)."""

    def __init__(self, settings: Optional[Settings] = None):
        self.s = settings or default_settings
        self.model = self.s.llm_model
        self.embed_model = self.s.embed_model
        self._status: Optional[Dict[str, Any]] = None
        self._status_ts = 0.0

    def status(self, refresh: bool = False) -> Dict[str, Any]:
        if not self.s.llm_enabled:
            return {
                "available": False,
                "reason": "disabled by PINNI_LLM_ENABLED=0",
                "model": self.model,
            }
        if not refresh and self._status and (time.time() - self._status_ts < 20):
            return self._status

        try:
            r = httpx.get(f"{self.s.ollama_url}/api/tags", timeout=3.0)
            names = [m.get("name", "") for m in r.json().get("models", [])]
            ok = any(
                n == self.model
                or n.split(":")[0] == self.model
                or n == f"{self.model}:latest"
                for n in names
            )
            emb = any(
                n.split(":")[0] == self.embed_model.split(":")[0] for n in names
            )
            st = {
                "available": ok,
                "model": self.model,
                "installed": names,
                "embed_model_ready": emb,
                "reason": None
                if ok
                else f"model '{self.model}' not found in Ollama tags",
            }
        except Exception as e:
            st = {
                "available": False,
                "model": self.model,
                "embed_model_ready": False,
                "reason": f"Ollama not reachable at {self.s.ollama_url} ({type(e).__name__})",
            }
        self._status, self._status_ts = st, time.time()
        return st

    @property
    def available(self) -> bool:
        return self.status()["available"]

    def chat(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]] = None,
        think: Optional[bool] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
        temperature: float = 0.1,
        max_tokens: int = 800,
    ) -> Dict[str, Any]:
        """Invoke chat completion on Ollama.

        When `schema` is passed, schema-constrained decoding is enforced.
        """
        if not self.available:
            raise LLMUnavailable(self.status()["reason"])

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if think is not None:
            body["think"] = think
        if schema is not None:
            body["format"] = schema

        content: List[str] = []
        thinking: List[str] = []
        t_in, t_out = 0, 0
        t0 = time.perf_counter()

        try:
            with httpx.stream(
                "POST",
                f"{self.s.ollama_url}/api/chat",
                json=body,
                timeout=60.0,
            ) as r:
                if r.status_code != 200:
                    raw_err = r.read().decode("utf-8", errors="replace")
                    raise LLMUnavailable(f"Ollama HTTP {r.status_code}: {raw_err[:200]}")
                for line in r.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    msg = chunk.get("message") or {}
                    if msg.get("thinking"):
                        thinking.append(msg["thinking"])
                        if on_thinking:
                            on_thinking(msg["thinking"])
                    if msg.get("content"):
                        content.append(msg["content"])
                    if chunk.get("done"):
                        t_in = chunk.get("prompt_eval_count", 0)
                        t_out = chunk.get("eval_count", 0)
        except httpx.HTTPError as e:
            self._status = None
            raise LLMUnavailable(f"{type(e).__name__}: {e}") from e

        text = "".join(content).strip()
        out: Dict[str, Any] = {
            "content": text,
            "data": None,
            "thinking": "".join(thinking).strip(),
            "tokens_in": t_in,
            "tokens_out": t_out,
            "ms": (time.perf_counter() - t0) * 1000,
        }
        if schema is not None and text:
            try:
                out["data"] = json.loads(text)
            except json.JSONDecodeError as err:
                raise ValueError(f"Failed to parse model output as JSON: {text}") from err
        return out

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Compute dense vector embeddings using Ollama."""
        body = {
            "model": self.embed_model,
            "input": texts,
            "truncate": True,
        }
        r = httpx.post(f"{self.s.ollama_url}/api/embed", json=body, timeout=60.0)
        r.raise_for_status()
        return r.json().get("embeddings", [])
