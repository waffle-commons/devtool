"""LLM client abstraction — multi-provider support for Ollama and OpenAI-compatible APIs.

This module implements a Strategy Pattern with two concrete providers:
  1. OllamaProvider — for local Ollama instances and compatible servers
  2. OpenAIProvider — for OpenAI-compatible endpoints (PrivAiTe, Groq, vLLM, etc.)

Both providers implement ILanguageModel and IEmbeddingModel, allowing seamless
backend-swapping via configuration and dependency injection.

All prompt engineering lives in devtool/prompts.py.
All orchestration lives in devtool/services/generation_service.py.
"""

import json
from abc import ABC, abstractmethod
from typing import Generator, Iterator, Optional

import requests
from rich.console import Console

from ..config import Config
from ..interfaces import IEmbeddingModel, ILanguageModel

_err_console = Console(stderr=True)


# ── Exceptions ───────────────────────────────────────────────────────────────


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""

    pass


class OllamaRequestError(LLMProviderError):
    """Raised when the Ollama API returns an error response."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body}")


class OllamaEmbeddingError(LLMProviderError):
    """Raised when the embedding model is missing or fails during embedding.

    This exception wraps embedding-specific errors with a helpful suggestion
    to pull the missing model via `ollama pull`.
    """

    def __init__(self, model_name: str, original_error: str):
        self.model_name = model_name
        self.original_error = original_error
        message = (
            f"Embedding model '{model_name}' failed or is not available: {original_error}\n"
            f"  → Fix: Run `ollama pull {model_name}`"
        )
        super().__init__(message)


class OpenAIRequestError(LLMProviderError):
    """Raised when the OpenAI-compatible API returns an error response."""

    def __init__(self, status_code: int, body: str, endpoint: str):
        self.status_code = status_code
        self.body = body
        self.endpoint = endpoint
        super().__init__(
            f"OpenAI-compatible API at {endpoint} returned HTTP {status_code}: {body}"
        )


class OpenAIAuthenticationError(LLMProviderError):
    """Raised when authentication fails (missing or invalid API key)."""

    def __init__(self, endpoint: str):
        super().__init__(
            f"Authentication failed for {endpoint}. Check your API key in the config."
        )


# ── Provider Interface ───────────────────────────────────────────────────────


class ILLMProvider(ABC):
    """Abstract interface for LLM providers.

    A provider handles all protocol-specific details (HTTP headers, endpoint
    paths, request/response formats) while exposing a unified interface.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Currently resolved model name (useful for UI display)."""
        ...

    @abstractmethod
    def generate(self, prompt: str, system: str) -> Optional[str]:
        """Synchronous, non-streaming text generation. Returns full response or None."""
        ...

    @abstractmethod
    def stream(self, prompt: str, system: str) -> Iterator[str]:
        """Streaming text generation. Yields string chunks."""
        ...


class IEmbeddingProvider(ABC):
    """Abstract interface for embedding providers."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Return a vector embedding for *text*."""
        ...


# ── Ollama Provider ──────────────────────────────────────────────────────────


def _handle_request_exception(
    e: requests.exceptions.RequestException, url: str
) -> None:
    """Print a rich, actionable error message based on the exception type."""
    if isinstance(e, requests.exceptions.ConnectionError):
        _err_console.print(
            f"[bold red]✗ Connection Error:[/bold red] Could not reach LLM endpoint at [cyan]{url}[/cyan]\n"
            "  → Is the server running? Check your endpoint configuration."
        )
    elif isinstance(e, requests.exceptions.Timeout):
        _err_console.print(
            f"[bold red]✗ Timeout:[/bold red] LLM endpoint at [cyan]{url}[/cyan] did not respond in time.\n"
            "  → The model may still be loading (cold start) or the diff is too large.\n"
            "  → Increase [bold]request_timeout[/bold] in your [cyan].devtool.toml[/cyan]."
        )
    elif isinstance(e, requests.exceptions.HTTPError):
        status_code = e.response.status_code if e.response is not None else "?"
        try:
            body = e.response.json()
            error_detail = body.get("error", e.response.text)
        except Exception:
            error_detail = e.response.text if e.response is not None else str(e)

        if status_code == 401 or status_code == 403:
            _err_console.print(
                f"[bold red]✗ Authentication Error (HTTP {status_code}):[/bold red] {error_detail}\n"
                "  → Check your API key or authentication headers in the config."
            )
        elif status_code == 404:
            _err_console.print(
                f"[bold red]✗ HTTP 404 Not Found:[/bold red] {error_detail}\n"
                "  → Check the model name and endpoint in your config."
            )
        elif status_code == 500:
            _err_console.print(
                f"[bold red]✗ HTTP 500 Internal Server Error:[/bold red] {error_detail}\n"
                "  → The LLM server encountered an internal error. Check its logs."
            )
        else:
            _err_console.print(
                f"[bold red]✗ HTTP {status_code}:[/bold red] {error_detail}"
            )
    else:
        _err_console.print(f"[bold red]✗ Request Error:[/bold red] {e}")


def _fetch_raw_lines_ollama(
    endpoint: str, model: str, payload: dict, timeout: int
) -> Generator[bytes, None, None]:
    """Base network layer for streaming raw bytes from Ollama endpoint."""
    url = f"{endpoint.rstrip('/')}/api/generate"
    payload = {**payload, "model": model}
    try:
        with requests.post(url, json=payload, timeout=timeout, stream=True) as response:
            response.raise_for_status()
            yield from response.iter_lines()
    except requests.exceptions.RequestException as e:
        _handle_request_exception(e, url)


def _parse_stream_ollama(raw_lines: Generator[bytes, None, None]) -> Iterator[str]:
    """Parses JSON-line payloads from Ollama cleanly into string tokens."""
    for line in raw_lines:
        if line:
            try:
                data = json.loads(line)
                if "response" in data:
                    yield data["response"]
            except json.JSONDecodeError:
                continue


class OllamaProvider(ILLMProvider):
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
        raw = _fetch_raw_lines_ollama(
            self._endpoint, self._model, payload, self._timeout
        )
        yield from _parse_stream_ollama(raw)

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


class OllamaEmbeddingProvider(IEmbeddingProvider):
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
            # Extract error message from the exception
            if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                try:
                    error_body = e.response.json().get("error", e.response.text)
                except Exception:
                    error_body = e.response.text if e.response is not None else str(e)
            else:
                error_body = str(e)
            # Wrap with helpful model-specific suggestion
            raise OllamaEmbeddingError(self._model, error_body) from e


# ── OpenAI Provider ──────────────────────────────────────────────────────────


def _fetch_raw_lines_openai(
    endpoint: str,
    model: str,
    messages: list[dict],
    api_key: Optional[str],
    timeout: int,
) -> Generator[bytes, None, None]:
    """Base network layer for streaming raw bytes from OpenAI-compatible endpoint."""
    url = f"{endpoint.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    try:
        with requests.post(
            url, json=payload, headers=headers, timeout=timeout, stream=True
        ) as response:
            response.raise_for_status()
            yield from response.iter_lines()
    except requests.exceptions.RequestException as e:
        _handle_request_exception(e, url)


def _parse_stream_openai(raw_lines: Generator[bytes, None, None]) -> Iterator[str]:
    """Parses Server-Sent Event (SSE) from OpenAI-compatible API into tokens."""
    for line in raw_lines:
        if not line:
            continue
        # SSE format: "data: {json}"
        line_str = line.decode("utf8") if isinstance(line, bytes) else line
        if line_str.startswith("data: "):
            data_str = line_str[6:].strip()
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                # Extract token from choice.delta.content
                choices = data.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
            except json.JSONDecodeError:
                continue


class OpenAIProvider(ILLMProvider):
    """OpenAI-compatible language model (supports PrivAiTe, Groq, vLLM, etc.)."""

    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: Optional[str] = None,
        timeout: int = 300,
    ):
        """
        Args:
            endpoint: Base URL of the OpenAI-compatible API (e.g., http://localhost:8000)
            model: Model name/ID as recognized by the endpoint
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self._endpoint = endpoint
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    @property
    def model_name(self) -> str:
        """Currently resolved model name (useful for UI display)."""
        return self._model

    def generate(self, prompt: str, system: str) -> Optional[str]:
        url = f"{self._endpoint.rstrip('/')}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        try:
            response = requests.post(
                url, json=payload, headers=headers, timeout=self._timeout
            )
            response.raise_for_status()
            data = response.json()
            # Extract text from first choice
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            return None
        except requests.exceptions.RequestException as e:
            _handle_request_exception(e, url)
            return None

    def stream(self, prompt: str, system: str) -> Iterator[str]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        raw = _fetch_raw_lines_openai(
            self._endpoint, self._model, messages, self._api_key, self._timeout
        )
        yield from _parse_stream_openai(raw)


class OpenAIEmbeddingProvider(IEmbeddingProvider):
    """OpenAI-compatible embedding model."""

    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: Optional[str] = None,
        timeout: int = 300,
    ):
        self._endpoint = endpoint
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    def embed(self, text: str) -> list[float]:
        url = f"{self._endpoint.rstrip('/')}/v1/embeddings"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": self._model,
            "input": text,
        }
        try:
            response = requests.post(
                url, json=payload, headers=headers, timeout=self._timeout
            )
            response.raise_for_status()
            data = response.json()
            # Extract embedding from first data entry
            data_list = data.get("data", [])
            if data_list:
                return data_list[0].get("embedding", [])
            return []
        except requests.exceptions.RequestException as e:
            _handle_request_exception(e, url)
            raise


# ── Backward-compatible wrappers for ILanguageModel & IEmbeddingModel ────────


class OllamaLanguageModel(ILanguageModel):
    """Legacy wrapper for OllamaProvider implementing ILanguageModel.

    This class exists for backward compatibility. New code should use
    OllamaProvider (or OpenAIProvider) directly.
    """

    def __init__(self, config: Config, *, purpose: str = "default"):
        self._provider = OllamaProvider(config, purpose=purpose)

    @property
    def model_name(self) -> str:
        return self._provider.model_name

    def generate(self, prompt: str, system: str) -> Optional[str]:
        return self._provider.generate(prompt, system)

    def stream(self, prompt: str, system: str) -> Iterator[str]:
        return self._provider.stream(prompt, system)

    def list_models(self) -> Optional[list[dict]]:
        return self._provider.list_models()


class OllamaEmbeddingModel(IEmbeddingModel):
    """Legacy wrapper for OllamaEmbeddingProvider implementing IEmbeddingModel.

    This class exists for backward compatibility. New code should use
    OllamaEmbeddingProvider (or OpenAIEmbeddingProvider) directly.
    """

    def __init__(self, config: Config):
        self._provider = OllamaEmbeddingProvider(config)

    def embed(self, text: str) -> list[float]:
        return self._provider.embed(text)


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
    diff: str,
    config: Config,
    rag_context: Optional[str] = None,
    *,
    fix_mode: bool = False,
) -> Iterator[str]:
    from ..prompts import pre_review_prompt

    system, user = pre_review_prompt(diff, rag_context=rag_context, fix_mode=fix_mode)
    yield from OllamaLanguageModel(config, purpose="review").stream(user, system)


def sec_audit_stream(
    code: str,
    config: Config,
    rag_context: Optional[str] = None,
    *,
    fix_mode: bool = False,
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
        source_code,
        doc_type,
        language,
        context_hint=context_hint,
        existing_doc=existing_doc,
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
        source_code,
        language,
        framework,
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
