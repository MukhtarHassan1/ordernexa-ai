"""Ollama-only provider. AI can draft; deterministic business services authorize writes.

A successful /api/tags request does NOT establish that a model can generate.
`probe_inference` performs a deliberately small real generation and reports failure.
"""
import base64
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings

log = logging.getLogger(__name__)


@dataclass
class StructuredAIResult:
    data: BaseModel
    raw_content: str
    provider: str
    model: str
    usage: dict[str, Any]


class AIProviderError(RuntimeError):
    """Expected AI infrastructure/contract failure: never implies an order exists."""

    def __init__(self, code: str, detail: str, *, retryable: bool = True):
        self.code = code
        self.detail = detail
        self.retryable = retryable
        super().__init__(f"{code}: {detail}")


class AIProvider(ABC):
    @abstractmethod
    async def structured_completion(
        self, *, schema: type[BaseModel], system_prompt: str,
        user_prompt: str, images: list[bytes] | None = None,
    ) -> StructuredAIResult: ...

    @abstractmethod
    async def health(self) -> bool: ...


class OllamaProvider(AIProvider):
    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        # Preserve the legacy single-model setting unless explicit text/vision
        # overrides have been supplied. Models belong to the server at base_url:
        # the Docker Ollama registry is separate from Windows Ollama's registry.
        self.model = settings.ollama_model

    def selected_model(self, *, has_images: bool) -> str:
        override = settings.ollama_vision_model if has_images else settings.ollama_text_model
        return override.strip() or self.model

    async def _available_models(self) -> list[str] | None:
        """Read the configured server's registry, not the Docker Ollama registry.

        Called only after a 404 or explicitly by a diagnostic, so successful
        document extraction does not incur a second Ollama request.
        """
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(5.0, connect=3.0), trust_env=False
            ) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
                if not isinstance(models, list):
                    return None
                return sorted({
                    str(value).strip()
                    for entry in models if isinstance(entry, dict)
                    for value in (entry.get("name"), entry.get("model"))
                    if isinstance(value, str) and value.strip()
                })
        except (httpx.HTTPError, ValueError, TypeError):
            return None

    async def structured_completion(
        self, *, schema: type[BaseModel], system_prompt: str,
        user_prompt: str, images: list[bytes] | None = None,
    ) -> StructuredAIResult:
        if not user_prompt and not images:
            raise AIProviderError("EMPTY_INPUT", "Document contains no extractable content.", retryable=False)
        model = self.selected_model(has_images=bool(images))
        if not model:
            raise AIProviderError(
                "MODEL_NOT_CONFIGURED", "No Ollama model is configured for this document type.",
                retryable=False,
            )
        user_message: dict[str, Any] = {"role": "user", "content": user_prompt}
        if images:
            user_message["images"] = [base64.b64encode(item).decode("ascii") for item in images]
        payload = {
            "model": model,
            "stream": False,
            "format": schema.model_json_schema(),
            "messages": [{"role": "system", "content": system_prompt}, user_message],
            "options": {
                "temperature": 0,
                "num_ctx": settings.ollama_context_length,
            },
        }
        started = time.monotonic()
        timeout = httpx.Timeout(
            connect=settings.ollama_connect_timeout_seconds,
            read=settings.ollama_read_timeout_seconds,
            write=30.0, pool=10.0,
        )
        try:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                result = response.json()
        except httpx.TimeoutException as exc:
            log.warning("Ollama inference timeout model=%s elapsed=%.1fs", model, time.monotonic() - started)
            raise AIProviderError(
                "MODEL_TIMEOUT",
                f"Model {model!r} did not complete inference within "
                f"{settings.ollama_read_timeout_seconds:g}s. "
                "Verify cold-start time and memory on the configured Ollama host.",
            ) from exc
        except httpx.ConnectError as exc:
            raise AIProviderError(
                "OLLAMA_UNREACHABLE", "Configured Ollama server is unreachable. "
                "Verify OLLAMA_BASE_URL and whether Windows Ollama is running."
            ) from exc
        except httpx.HTTPStatusError as exc:
            # A Windows Ollama and a Docker Ollama have *different* model stores.
            # A generic 404 concealed an actionable missing-model configuration.
            if exc.response.status_code == 404:
                available = await self._available_models()
                if available is not None and model not in available:
                    options = ", ".join(available) if available else "(none)"
                    raise AIProviderError(
                        "MODEL_NOT_INSTALLED",
                        f"The configured Ollama server {self.base_url} does not have "
                        f"model {model!r}. Installed there: {options}. "
                        "Pull the model on THAT server, or update OLLAMA_TEXT_MODEL / "
                        "OLLAMA_VISION_MODEL. Models downloaded in Docker are "
                        "not automatically installed on Windows.",
                        retryable=False,
                    ) from exc
            raise AIProviderError(
                "OLLAMA_HTTP_ERROR",
                f"Ollama returned HTTP {exc.response.status_code} for model {model!r}. "
                "Check the configured Ollama endpoint and server logs.",
            ) from exc
        except (httpx.RequestError, ValueError) as exc:
            raise AIProviderError(
                "OLLAMA_TRANSPORT", "Ollama returned an invalid or incomplete response."
            ) from exc

        try:
            raw_content = result["message"]["content"]
            parsed = schema.model_validate_json(raw_content)
        except (KeyError, TypeError, ValidationError, ValueError) as exc:
            log.warning("Ollama schema validation failed model=%s", model)
            raise AIProviderError(
                "INVALID_AI_OUTPUT", "The model response did not meet the versioned extraction schema. "
                "The document must be reviewed; it cannot trigger an ERP write.", retryable=False,
            ) from exc

        return StructuredAIResult(
            data=parsed,
            raw_content=raw_content,
            provider="OLLAMA",
            model=model,
            usage={
                "prompt_eval_count": result.get("prompt_eval_count"),
                "eval_count": result.get("eval_count"),
                "total_duration": result.get("total_duration"),
                "elapsed_seconds": round(time.monotonic() - started, 3),
            },
        )

    async def health(self) -> bool:
        """HTTP availability only, NOT model readiness. Use probe_inference for that."""
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def probe_inference(self) -> dict[str, Any]:
        """Explicit diagnostic; never runs in a periodic /health check or per upload."""
        started = time.monotonic()
        model = settings.ollama_probe_model
        timeout = settings.ollama_probe_timeout_seconds
        payload = {
            "model": model, "prompt": "Say READY.", "stream": False,
            "keep_alive": "10m",
            "options": {"num_ctx": 512, "num_predict": 8, "temperature": 0},
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=5), trust_env=False) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                obj = response.json()
                if not obj.get("done") or not str(obj.get("response", "")).strip():
                    raise AIProviderError("EMPTY_GENERATION", "Probe completed without useful output.")
            return {
                "status": "READY", "model": model,
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "load_duration_ns": obj.get("load_duration"),
            }
        except AIProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise AIProviderError(
                "MODEL_RUNNER_TIMEOUT",
                f"The {model} probe failed to generate within {timeout:g}s. "
                "Check the Ollama runner and WSL resource configuration, not FastAPI routing.",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise AIProviderError("MODEL_HTTP_ERROR", f"Probe returned HTTP {exc.response.status_code}.") from exc
        except (httpx.RequestError, ValueError) as exc:
            raise AIProviderError("MODEL_PROBE_ERROR", "Probe request failed or its response was invalid.") from exc


def get_ai_provider() -> AIProvider:
    if settings.ai_provider.lower() == "ollama":
        return OllamaProvider()
    raise ValueError("OrderNexa local release supports AI_PROVIDER=ollama only.")
