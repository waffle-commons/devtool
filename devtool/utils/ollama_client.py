"""Ollama HTTP client — implements ILanguageModel and IEmbeddingModel.

All prompt-engineering (system prompts) has been moved to service classes.
This module is now a pure infrastructure adapter.
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
    """

    def __init__(self, config: Config, *, purpose: str = "default"):
        self._endpoint = config.ollama_endpoint
        self._model = config.resolve_model(purpose)
        self._timeout = config.request_timeout
        self._num_ctx = config.num_ctx

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
            "options": {"num_ctx": self._num_ctx},
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
            "options": {"num_ctx": self._num_ctx},
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

    def embed(self, text: str) -> list[float]:
        url = f"{self._endpoint.rstrip('/')}/api/embeddings"
        payload = {"model": self._model, "prompt": text}
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
# New code should use the class-based API via the DI container.


def list_models(config: Config) -> Optional[list[dict]]:
    return OllamaLanguageModel(config).list_models()


def generate_commit_message(diff: str, config: Config) -> Optional[str]:
    system_prompt = (
        "You are an expert developer. Read the following `git diff` and write a single "
        "commit message following the Conventional Commits specification. Use present tense. "
        "Do not add any markdown formatting, explanations, or extra text. Only output the commit message."
    )
    return OllamaLanguageModel(config, purpose="fast").generate(diff, system_prompt)


# ── Fix-mode prompt suffix (RFC 011) ─────────────────────────────────────────

_FIX_MODE_SUFFIX = (
    "\n\nIMPORTANT — AUTO-FIX MODE: In addition to your review, for every issue you identify "
    "that can be fixed programmatically, output a structured patch block using EXACTLY this format:\n\n"
    "<<<< SEARCH file:path/to/file.py\n"
    "original code that needs to change (copy it EXACTLY)\n"
    "==== REPLACE\n"
    "the corrected code\n"
    ">>>>\n\n"
    "You may output multiple patch blocks. The file path MUST be relative to the project root. "
    "The SEARCH section must match the existing code EXACTLY (including whitespace). "
    "Place all patch blocks AFTER your review commentary."
)


def pre_review_code_stream(
    diff: str, config: Config, rag_context: Optional[str] = None,
    *, fix_mode: bool = False,
) -> Iterator[str]:
    system_prompt = (
        "You are a strict Senior Developer specializing in PHP and C#. "
        "Review the following git diff. Identify SOLID principle violations, "
        "high cyclomatic complexity, and code smells. Provide your feedback in a "
        "structured Markdown format with actionable refactoring suggestions. "
        "Be concise and prioritize maintainability."
    )
    prompt_body = diff
    if rag_context:
        system_prompt += (
            "\n\nYou are also provided with [REPOSITORY CONTEXT] containing related classes, "
            "interfaces, and modules from the same codebase. Use this context to understand "
            "the broader architecture and detect violations that span across files — such as "
            "broken contracts, misused abstractions, or coupling issues invisible from the diff alone."
        )
        prompt_body += f"\n\n[REPOSITORY CONTEXT]\n{rag_context}"
    if fix_mode:
        system_prompt += _FIX_MODE_SUFFIX
    yield from OllamaLanguageModel(config, purpose="review").stream(prompt_body, system_prompt)


def sec_audit_stream(
    code: str, config: Config, rag_context: Optional[str] = None,
    *, fix_mode: bool = False,
) -> Iterator[str]:
    system_prompt = (
        "You are a strict DevSecOps Security Auditor specializing in PHP, C#, and general web development. "
        "Analyze the provided code for security vulnerabilities. "
        "Focus heavily on the OWASP Top 10: SQL Injection, Cross-Site Scripting (XSS), "
        "Insecure Direct Object References (IDOR), hardcoded secrets/passwords, and unsafe deserialization. "
        "IMPORTANT: Completely ignore any line of code that has the comment "
        "`// devtool-ignore-sec` or `# devtool-ignore-sec` appended to it. "
        "If vulnerabilities are found, format EVERY finding strictly as: "
        "[Severity (Critical/High/Medium/Low)] - [File/Line] - [Description] - [Remediation]. "
        "Output one finding per line. Do not add any prose or markdown headers. "
        "CRITICAL INSTRUCTION: If absolutely no vulnerabilities are found, "
        "your entire output MUST be exactly the string NO_VULNERABILITIES_FOUND and nothing else."
    )
    prompt_body = code
    if fix_mode:
        system_prompt += _FIX_MODE_SUFFIX
    if rag_context:
        system_prompt += (
            "\n\nYou are also provided with [CROSS-FILE CONTEXT] showing how the audited code "
            "is used elsewhere in the repository. Use this to detect source-to-sink vulnerabilities "
            "where a seemingly safe function receives unvalidated user input from a caller in another file."
        )
        prompt_body += f"\n\n[CROSS-FILE CONTEXT]\n{rag_context}"
    yield from OllamaLanguageModel(config, purpose="review").stream(prompt_body, system_prompt)


# Diátaxis documentation type → system prompt mapping
_DIATAXIS_PROMPTS: dict[str, str] = {
    "tutorial": (
        "You are a technical writer using the Diátaxis documentation framework. "
        "Create a 'Tutorial' document for the provided {language} source code. "
        "Focus on LEARNING by DOING. Guide the reader step-by-step through a practical implementation. "
        "Do not explain deep theory — keep it action-oriented and beginner-friendly. "
        "Output strict, clean Markdown compatible with Obsidian and MkDocs. "
        "Use ## headings, fenced code blocks with language tags, and clear numbered steps."
    ),
    "howto": (
        "You are a technical writer using the Diátaxis documentation framework. "
        "Create a 'How-to Guide' for the provided {language} source code. "
        "Focus on achieving a SPECIFIC GOAL. Provide practical, problem-solving steps. "
        "Assume the reader already understands the domain basics. "
        "Output strict, clean Markdown compatible with Obsidian and MkDocs. "
        "Use ## headings, fenced code blocks with language tags, and concise numbered steps."
    ),
    "reference": (
        "You are a technical writer using the Diátaxis documentation framework. "
        "Create a 'Reference' document for the provided {language} source code. "
        "Focus on INFORMATION. Document every public class, method, parameter, return type, "
        "and exception in a structured, austere, and accurate format. "
        "Use tables where appropriate. Output strict, clean Markdown compatible with Obsidian and MkDocs."
    ),
    "explanation": (
        "You are a technical writer using the Diátaxis documentation framework. "
        "Create an 'Explanation' document for the provided {language} source code. "
        "Focus on UNDERSTANDING. Discuss the architectural choices, underlying concepts, "
        "design patterns, and the reasoning behind key decisions. "
        "Do not focus on step-by-step instructions. "
        "Output strict, clean Markdown compatible with Obsidian and MkDocs. "
        "Use ## headings and narrative prose."
    ),
}


def docgen_stream(
    source_code: str,
    doc_type: str,
    language: str,
    config: Config,
    context_hint: str = "",
    existing_doc: Optional[str] = None,
) -> Iterator[str]:
    base_prompt = _DIATAXIS_PROMPTS.get(doc_type, _DIATAXIS_PROMPTS["reference"])
    system_prompt = base_prompt.format(language=language)
    if existing_doc:
        system_prompt += (
            "\n\nIMPORTANT: An existing documentation file is provided below (marked [EXISTING DOC]). "
            "Your task is to UPDATE it: integrate new content, update outdated sections, "
            "and preserve any manually written sections that are still accurate. "
            "Output the COMPLETE updated document — do not truncate."
        )
        prompt_body = (
            f"[SOURCE CODE]\n{source_code}"
            + (f"\n\n[ADDITIONAL CONTEXT]\n{context_hint}" if context_hint else "")
            + f"\n\n[EXISTING DOC]\n{existing_doc}"
        )
    else:
        prompt_body = f"[SOURCE CODE]\n{source_code}" + (
            f"\n\n[ADDITIONAL CONTEXT]\n{context_hint}" if context_hint else ""
        )
    yield from OllamaLanguageModel(config, purpose="coding").stream(prompt_body, system_prompt)


def testgen_code_stream(
    source_code: str,
    language: str,
    framework: str,
    config: Config,
    existing_test_content: Optional[str] = None,
    rag_context: Optional[str] = None,
) -> Iterator[str]:
    if existing_test_content:
        system_prompt = (
            f"You are an expert SDET (Software Development Engineer in Test). "
            f"You will be provided with {language} source code and its existing {framework} unit test file. "
            "Your task is to update the existing test file. Add new tests for any uncovered methods or edge cases, "
            "and modify existing tests if the source signatures have changed. "
            "CRITICAL: Do NOT remove or delete existing valid tests. Output ONLY the entire updated test file code, "
            "no markdown wrappers unless requested."
        )
        prompt_body = f"Framework: {framework}\n\n[SOURCE CODE]\n{source_code}\n\n[EXISTING TEST CODE]\n{existing_test_content}"
    else:
        system_prompt = (
            f"You are an expert SDET (Software Development Engineer in Test). "
            f"Write unit tests for the following {language} code using the {framework} framework. "
            "Identify edge cases, null checks, and happy paths. "
            "Structure every test strictly using the Arrange, Act, Assert (AAA) pattern. "
            "Output ONLY the test file code, no markdown wrappers unless requested."
        )
        prompt_body = f"Framework: {framework}\n\n[SOURCE CODE]\n{source_code}"
    if rag_context:
        system_prompt += (
            "\n\nYou are also provided with [ADDITIONAL REPOSITORY CONTEXT] containing "
            "related interfaces, traits, dependencies, and helper classes from the same codebase. "
            "Use this context to accurately mock dependencies, type-hint parameters, and understand "
            "the contracts that the code under test relies on."
        )
        prompt_body += f"\n\n[ADDITIONAL REPOSITORY CONTEXT]\n{rag_context}"
    yield from OllamaLanguageModel(config, purpose="coding").stream(prompt_body, system_prompt)


def summarize_file(content: str, config: Config) -> Optional[str]:
    system_prompt = (
        "Summarize the purpose, main components, and obvious technical debt of this code in 3 bullet points. "
        "Keep it extremely brief."
    )
    return OllamaLanguageModel(config, purpose="fast").generate(content, system_prompt)


def repo_architect_stream(tree: str, summaries: str, config: Config) -> Iterator[str]:
    system_prompt = (
        "You are a Lead Software Architect. Based on the provided file tree and summaries, "
        "conduct a complete audit of the repository. Identify systemic architectural flaws, "
        "SOLID violations, and technical debt. Output a comprehensive Markdown report including "
        "an 'Architecture Overview' and a 'Prioritized Action Plan'."
    )
    prompt = f"[DIRECTORY STRUCTURE]\n{tree}\n\n[FILE SUMMARIES]\n{summaries}"
    yield from OllamaLanguageModel(config, purpose="default").stream(prompt, system_prompt)


def get_embedding(text: str, config: Config) -> list[float]:
    return OllamaEmbeddingModel(config).embed(text)


def stream_generate(prompt: str, system: str, config: Config) -> Iterator[str]:
    yield from OllamaLanguageModel(config).stream(prompt, system)
