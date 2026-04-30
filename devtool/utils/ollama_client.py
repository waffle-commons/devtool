"""Ollama HTTP client — implements ILanguageModel and IEmbeddingModel.

This module is a PURE INFRASTRUCTURE ADAPTER. It handles:
  - HTTP transport to the local Ollama API
  - JSON-line streaming parsing
  - Connection error handling

All prompt engineering lives in devtool/prompts.py.
All orchestration lives in devtool/services/generation_service.py.
"""

import json
from typing import Generator, Iterator, Optional

import requests
from rich.console import Console

from ..config import Config
from ..interfaces import IEmbeddingModel, ILanguageModel

_err_console = Console(stderr=True)


# ── Exceptions ───────────────────────────────────────────────────────────────


class OllamaRequestError(Exception):
    """Raised when the Ollama API returns an error response."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body}")


# ── Network helpers (private) ────────────────────────────────────────────────


def _handle_request_exception(
    e: requests.exceptions.RequestException, url: str
) -> None:
    """Print a rich, actionable error message based on the exception type."""
    if isinstance(e, requests.exceptions.ConnectionError):
        _err_console.print(
            f"[bold red]✗ Connection Error:[/bold red] Could not reach Ollama at [cyan]{url}[/cyan]\n"
            "  → Is Ollama running? Try: [bold]ollama serve[/bold]"
        )
    elif isinstance(e, requests.exceptions.Timeout):
        _err_console.print(
            f"[bold red]✗ Timeout:[/bold red] Ollama at [cyan]{url}[/cyan] did not respond in time.\n"
            "  → The model may still be loading (cold start) or the diff is too large.\n"
            "  → Increase [bold]request_timeout[/bold] in your [cyan].devtool.toml[/cyan] (current default: 300s)."
        )
    elif isinstance(e, requests.exceptions.HTTPError):
        status_code = e.response.status_code if e.response is not None else "?"
        try:
            body = e.response.json()
            error_detail = body.get("error", e.response.text)
        except Exception:
            error_detail = e.response.text if e.response is not None else str(e)

        if status_code == 404:
            _err_console.print(
                f"[bold red]✗ HTTP 404 Model Not Found:[/bold red] {error_detail}\n"
                "  → Check the model name in your config. Try: [bold]ollama list[/bold]"
            )
        elif status_code == 500:
            _err_console.print(
                f"[bold red]✗ HTTP 500 Internal Server Error:[/bold red] {error_detail}\n"
                "  → Ollama encountered an internal error. Check `ollama serve` logs."
            )
        else:
            _err_console.print(
                f"[bold red]✗ HTTP {status_code}:[/bold red] {error_detail}"
            )
    else:
        _err_console.print(f"[bold red]✗ Request Error:[/bold red] {e}")


def _fetch_raw_lines(
    endpoint: str, model: str, payload: dict, timeout: int
) -> Generator[bytes, None, None]:
    """Base network layer for streaming raw bytes from local Ollama endpoint."""
    url = f"{endpoint.rstrip('/')}/api/generate"
    payload = {**payload, "model": model}
    try:
        with requests.post(url, json=payload, timeout=timeout, stream=True) as response:
            response.raise_for_status()
            yield from response.iter_lines()
    except requests.exceptions.RequestException as e:
        _handle_request_exception(e, url)


def _parse_stream(raw_lines: Generator[bytes, None, None]) -> Iterator[str]:
    """Parses JSON-line payloads cleanly into string tokens."""
    for line in raw_lines:
        if line:
            try:
                data = json.loads(line)
                if "response" in data:
                    yield data["response"]
            except json.JSONDecodeError:
                continue


# ── ILanguageModel implementation ────────────────────────────────────────────


class OllamaLanguageModel(ILanguageModel):
    """Ollama-backed language model for both streaming and synchronous generation.

    The *purpose* parameter (RFC 012) enables multi-model routing:
    pass ``"coding"``, ``"fast"``, ``"review"``, etc. and the model name
    will be resolved via :py:meth:`Config.resolve_model`.

    Performance tuning: num_ctx and num_predict are resolved per-purpose,
    allowing fast tasks (commit) to use small context windows while
    heavy tasks (review) get larger budgets.
    """

    def __init__(self, config: Config, *, purpose: str = "default"):
        self._endpoint = config.ollama_endpoint
        self._model = config.resolve_model(purpose)
        self._timeout = config.request_timeout
        self._num_ctx = config.resolve_num_ctx(purpose)
        self._num_predict = config.resolve_num_predict(purpose)
        self._keep_alive = config.keep_alive

    @property
    def model_name(self) -> str:
        """Currently resolved model name (useful for UI display)."""
        return self._model

    # -- ILanguageModel interface ------------------------------------------

    def generate(self, prompt: str, system: str) -> Optional[str]:
        payload = {
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "num_ctx": self._num_ctx,
                "num_predict": self._num_predict,
            },
            "keep_alive": self._keep_alive,
        }
        url = f"{self._endpoint.rstrip('/')}/api/generate"
        full_payload = {**payload, "model": self._model}
        try:
            response = requests.post(url, json=full_payload, timeout=self._timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
        except requests.exceptions.RequestException as e:
            _handle_request_exception(e, url)
            return None

    def stream(self, prompt: str, system: str) -> Iterator[str]:
        payload = {
            "prompt": prompt,
            "system": system,
            "stream": True,
            "options": {
                "num_ctx": self._num_ctx,
                "num_predict": self._num_predict,
            },
            "keep_alive": self._keep_alive,
        }
        raw = _fetch_raw_lines(self._endpoint, self._model, payload, self._timeout)
        yield from _parse_stream(raw)

    # -- Convenience: list models ------------------------------------------

    def list_models(self) -> Optional[list[dict]]:
        """Fetch the list of installed models from GET /api/tags."""
        url = f"{self._endpoint.rstrip('/')}/api/tags"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json().get("models", [])
        except requests.exceptions.RequestException as e:
            _handle_request_exception(e, url)
            return None


# ── IEmbeddingModel implementation ───────────────────────────────────────────


class OllamaEmbeddingModel(IEmbeddingModel):
    """Ollama-backed embedding model using /api/embeddings."""

    def __init__(self, config: Config):
        self._endpoint = config.ollama_endpoint
        self._model = config.embedding_model
        self._timeout = config.request_timeout
        self._keep_alive = config.keep_alive

    def embed(self, text: str) -> list[float]:
        url = f"{self._endpoint.rstrip('/')}/api/embeddings"
        payload = {
            "model": self._model,
            "prompt": text,
            "keep_alive": self._keep_alive,
        }
        try:
            response = requests.post(url, json=payload, timeout=self._timeout)
            response.raise_for_status()
            data: dict = response.json()
            embedding = data.get("embedding")
            if embedding is None:
                raise OllamaRequestError(
                    response.status_code,
                    "Response JSON missing 'embedding' key",
                )
            return embedding
        except requests.exceptions.RequestException as e:
            _handle_request_exception(e, url)
            raise


# ── Backward-compatible module-level functions ───────────────────────────────
# These thin wrappers keep existing callers working during the migration.
# New code should use GenerationService via the DI container.


def list_models(config: Config) -> Optional[list[dict]]:
    return OllamaLanguageModel(config).list_models()


def generate_commit_message(diff: str, config: Config) -> Optional[str]:
    from ..prompts import commit_prompt

    system, user = commit_prompt(diff)
    return OllamaLanguageModel(config, purpose="fast").generate(user, system)


def pre_review_code_stream(
    diff: str, config: Config, rag_context: Optional[str] = None,
    *, fix_mode: bool = False,
) -> Iterator[str]:
    from ..prompts import pre_review_prompt

    system, user = pre_review_prompt(diff, rag_context=rag_context, fix_mode=fix_mode)
    yield from OllamaLanguageModel(config, purpose="review").stream(user, system)


def sec_audit_stream(
    code: str, config: Config, rag_context: Optional[str] = None,
    *, fix_mode: bool = False,
) -> Iterator[str]:
    from ..prompts import sec_audit_prompt

    system, user = sec_audit_prompt(code, rag_context=rag_context, fix_mode=fix_mode)
    yield from OllamaLanguageModel(config, purpose="review").stream(user, system)


def docgen_stream(
    source_code: str,
    doc_type: str,
    language: str,
    config: Config,
    context_hint: str = "",
    existing_doc: Optional[str] = None,
) -> Iterator[str]:
    from ..prompts import docgen_prompt

    system, user = docgen_prompt(
        source_code, doc_type, language,
        context_hint=context_hint, existing_doc=existing_doc,
    )
    yield from OllamaLanguageModel(config, purpose="coding").stream(user, system)


def testgen_code_stream(
    source_code: str,
    language: str,
    framework: str,
    config: Config,
    existing_test_content: Optional[str] = None,
    rag_context: Optional[str] = None,
) -> Iterator[str]:
    from ..prompts import testgen_prompt

    system, user = testgen_prompt(
        source_code, language, framework,
        existing_test_content=existing_test_content,
        rag_context=rag_context,
    )
    yield from OllamaLanguageModel(config, purpose="coding").stream(user, system)


def summarize_file(content: str, config: Config) -> Optional[str]:
    from ..prompts import summarize_file_prompt

    system, user = summarize_file_prompt(content)
    return OllamaLanguageModel(config, purpose="fast").generate(user, system)


def repo_architect_stream(tree: str, summaries: str, config: Config) -> Iterator[str]:
    from ..prompts import repo_architect_prompt

    system, user = repo_architect_prompt(tree, summaries)
    yield from OllamaLanguageModel(config, purpose="default").stream(user, system)


def get_embedding(text: str, config: Config) -> list[float]:
    return OllamaEmbeddingModel(config).embed(text)


def stream_generate(prompt: str, system: str, config: Config) -> Iterator[str]:
    yield from OllamaLanguageModel(config).stream(prompt, system)
