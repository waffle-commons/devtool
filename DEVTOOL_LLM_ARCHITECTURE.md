# DevTool LLM Client Architecture Analysis

**Date:** 2026-05-13  
**Scope:** Current LLM integration structure, configuration schema, dependency injection, and extension points.

---

## 1. Current LLM Client Structure

### File: `devtool/utils/ollama_client.py`

**Purpose:** Pure infrastructure adapter for HTTP transport to local Ollama API.

#### Classes

**`OllamaLanguageModel(ILanguageModel)` [126:348]**
- Constructor: `__init__(config: Config, *, purpose: str = "default")`
- Properties:
  - `model_name: str` — currently resolved model name (read-only)
- Public Methods (ILanguageModel interface):
  - `generate(prompt: str, system: str) -> Optional[str]` — synchronous, non-streaming text generation
  - `stream(prompt: str, system: str) -> Iterator[str]` — streaming text generation, yields string chunks
- Public Methods (convenience):
  - `list_models() -> Optional[list[dict]]` — fetches installed models via GET `/api/tags`

**`OllamaEmbeddingModel(IEmbeddingModel)` [206:244]**
- Constructor: `__init__(config: Config)`
- Public Methods (IEmbeddingModel interface):
  - `embed(text: str) -> list[float]` — returns vector embedding for text

**Custom Exceptions:**
- `OllamaRequestError(status_code: int, body: str)` — HTTP error wrapper
- `OllamaEmbeddingError(model_name: str, original_error: str)` — embedding-specific error with actionable suggestion

#### Helper Functions (Private)
- `_handle_request_exception(e: requests.exceptions.RequestException, url: str) -> None` — rich error formatting
- `_fetch_raw_lines(endpoint: str, model: str, payload: dict, timeout: int) -> Generator[bytes, None, None]` — base network layer
- `_parse_stream(raw_lines: Generator[bytes, None, None]) -> Iterator[str]` — JSON-line parsing

#### Backward-Compatible Module-Level Functions (lines 247–348)
These thin wrappers keep old callers working but are deprecated for new code:
- `list_models(config: Config) -> Optional[list[dict]]`
- `generate_commit_message(diff: str, config: Config) -> Optional[str]`
- `pre_review_code_stream(diff: str, config: Config, rag_context: Optional[str] = None, *, fix_mode: bool = False) -> Iterator[str]`
- `sec_audit_stream(code: str, config: Config, rag_context: Optional[str] = None, *, fix_mode: bool = False) -> Iterator[str]`
- `docgen_stream(...) -> Iterator[str]`
- `testgen_code_stream(...) -> Iterator[str]`
- `summarize_file(content: str, config: Config) -> Optional[str]`
- `repo_architect_stream(tree: str, summaries: str, config: Config) -> Iterator[str]`
- `get_embedding(text: str, config: Config) -> list[float]`
- `stream_generate(prompt: str, system: str, config: Config) -> Iterator[str]`

#### HTTP Transport Details
- Uses `requests` library (not httpx)
- Endpoint: `{config.ollama_endpoint}/api/generate` (text generation)
- Endpoint: `{config.ollama_endpoint}/api/embeddings` (embeddings)
- Endpoint: `{config.ollama_endpoint}/api/tags` (model listing)
- Streaming via `requests.post(..., stream=True).iter_lines()`
- JSON-line format parsing: `data.get("response")` from each JSON object
- Timeout: `config.request_timeout` (default 300s, tunable per purpose)
- Keep-alive: `config.keep_alive` (default "10m")

#### Configuration Injection
```python
model = OllamaLanguageModel(config, purpose="fast")
# Automatically resolves:
# - self._endpoint = config.ollama_endpoint
# - self._model = config.resolve_model("fast")
# - self._timeout = config.request_timeout
# - self._num_ctx = config.resolve_num_ctx("fast")
# - self._num_predict = config.resolve_num_predict("fast")
# - self._keep_alive = config.keep_alive
```

---

## 2. Configuration Schema

### File: `devtool/config.py`

**Data Structure:** `Config` (dataclass, immutable)

#### Connection & Performance Settings
```python
ollama_endpoint: str = "http://localhost:11434"
show_thoughts: bool = True
request_timeout: int = 300  # seconds
num_ctx: int = 8192  # default context window
keep_alive: str = "10m"  # model keep-alive duration
```

#### Model Assignment (RFC 012 - Multi-Model Routing)
```python
ollama_model: str = "gemma4"  # default/fallback
model_coding: str = ""  # testgen, docgen (e.g., "qwen2.5-coder")
model_fast: str = ""  # commit messages (e.g., "qwen:0.5b")
model_review: str = ""  # pre-review, sec-audit (e.g., "gemma4")
embedding_model: str = "nomic-embed-text"
```

#### Per-Purpose Performance Tuning
```python
num_ctx_fast: int = 4096  # commit messages: small context
num_ctx_coding: int = 8192  # testgen, docgen: medium context
num_ctx_review: int = 12288  # pre-review, sec-audit: large context
num_predict_fast: int = 512  # commit messages: short output
num_predict_coding: int = 4096  # testgen, docgen: longer output
num_predict_review: int = 4096  # reviews: structured but capped
num_predict_default: int = 4096  # fallback
```

#### Resolution Methods
- `resolve_model(purpose: str) -> str` — returns model name for purpose, falls back to default
- `resolve_num_ctx(purpose: str) -> int` — returns context window for purpose
- `resolve_num_predict(purpose: str) -> int` — returns max output tokens for purpose

#### TOML Mapping

**[ollama] section** (connection + performance settings ONLY):
```toml
[ollama]
endpoint = "http://localhost:11434"
show_thoughts = true
request_timeout = 300
num_ctx = 8192
keep_alive = "10m"
num_ctx_fast = 4096
num_ctx_coding = 8192
num_ctx_review = 12288
num_predict_fast = 512
num_predict_coding = 4096
num_predict_review = 4096
num_predict_default = 4096
```

**[models] section** (SINGLE SOURCE OF TRUTH for model assignments):
```toml
[models]
default   = "gemma3n:e4b"
coding    = "qwen3-coder:latest"
fast      = "qwen3.5:0.8b"
review    = "qwen3-coder:latest"
embedding = "nomic-embed-text:latest"
```

#### Config Loading (`load_config() -> Config`)
- Searches for `.devtool.toml` in: CWD → home directory → fallback to defaults
- Model names loaded **exclusively** from [models] section
- [ollama] section handles connection and performance settings only
- Deprecated: model keys in [ollama] section trigger warnings

#### Current API Key / Env Expansion Support
**NONE.** The current implementation does NOT support:
- API key authentication
- Bearer token headers
- Environment variable expansion in config values
- Custom HTTP headers

---

## 3. Interfaces (Abstract Base Classes)

### File: `devtool/interfaces.py`

**`ILanguageModel(ABC)` [11:22]**
```python
@abstractmethod
def generate(self, prompt: str, system: str) -> Optional[str]:
    """Synchronous, non-streaming text generation. Returns full response or None."""

@abstractmethod
def stream(self, prompt: str, system: str) -> Iterator[str]:
    """Streaming text generation. Yields string chunks."""
```

**`IEmbeddingModel(ABC)` [25:31]**
```python
@abstractmethod
def embed(self, text: str) -> list[float]:
    """Return a vector embedding for *text*."""
```

**`IIndexStore(ABC)` [34:59]** (not LLM-related, but part of injection framework)
- `save(vectors, metadata, store_path) -> None`
- `load(store_path) -> (index_handle, metadata)`
- `search(index, query_vector, top_k) -> list[tuple[float, int]]`
- `exists(store_path) -> bool`

---

## 4. Dependency Injection Wiring

### File: `devtool/container.py`

**Pattern:** Function-based DI with `@lru_cache` singletons.

#### Key Functions

**`get_config() -> Config`** [14:17]
- **Singleton via `@lru_cache(maxsize=1)`**
- Returns `load_config()` once, cached thereafter
- No parameters; calls `Config.load_config()` to read `.devtool.toml`

**`get_language_model(purpose: str = "default") -> ILanguageModel`** [20:24]
- **NOT cached** (purpose-aware routing)
- Returns `OllamaLanguageModel(get_config(), purpose=purpose)`
- Each call creates a new instance (allows per-purpose model selection)

**`get_embedding_model() -> IEmbeddingModel`** [27:31]
- **Singleton via `@lru_cache(maxsize=1)`**
- Returns `OllamaEmbeddingModel(get_config())`

**`get_index_store() -> IIndexStore`** [34:38]
- **Singleton via `@lru_cache(maxsize=1)`**
- Returns `FaissIndexStore()`

**`get_rag_service()`** [41:48]
- **Singleton via `@lru_cache(maxsize=1)`**
- Returns `RAGService(embedder=get_embedding_model(), store=get_index_store())`

**`get_generation_service()`** [51:63]
- **Singleton via `@lru_cache(maxsize=1)`**
- Returns **pre-wired** `GenerationService` with purpose-routed models:
  - `fast_model=get_language_model("fast")`
  - `coding_model=get_language_model("coding")`
  - `review_model=get_language_model("review")`
  - `default_model=get_language_model("default")`
- All purpose-routed models are **created once and reused** (via `@lru_cache` on container functions)

---

## 5. Service Layer (Business Logic)

### File: `devtool/services/generation_service.py`

**`GenerationService` [28:167]**
- Orchestrates prompt building + LLM invocation
- Constructor accepts 4 pre-wired `ILanguageModel` instances (dependency injection)
- Each method:
  1. Builds prompt via `prompts.py` module
  2. Delegates to appropriate injected model
  3. Returns plain data (strings, lists, iterators)

**Example Method:**
```python
def generate_commit_message(self, diff: str) -> Optional[str]:
    system, user = commit_prompt(diff)
    return self._fast.generate(user, system)
```

---

## 6. Command Usage Pattern

### Example: `devtool/commands/commit.py`

```python
def commit_cmd() -> None:
    config = get_config()  # Get config singleton
    gen_service = get_generation_service()  # Get pre-wired service

    # ... git operations ...

    commit_msg = gen_service.generate_commit_message(diff)  # Call service
    # Returns Optional[str], display via Rich console
```

### Example: `devtool/commands/pre_review.py` (lines 35–98)

```python
def pre_review_cmd(...) -> None:
    config = get_config()
    gen_service = get_generation_service()

    # ... extract diff, optional RAG context ...

    raw_stream = gen_service.pre_review_stream(
        diff,
        rag_context=rag_context,
        fix_mode=fix,
    )
    # Stream tokens, format with OllamaStreamProcessor, display with ReviewRenderer
```

**Pattern Summary:**
1. Commands retrieve `config` and `gen_service` from container
2. Commands pass domain data to service methods
3. Services delegate to injected models via `ILanguageModel` interface
4. Models (OllamaLanguageModel) handle HTTP transport
5. Commands format output for terminal display (Rich)

---

## 7. Test Mocking Infrastructure

### File: `tests/conftest.py`

**Mock Implementations:**

**`FakeLanguageModel(ILanguageModel)` [34:49]**
- `generate()` returns canned response
- `stream()` yields pre-defined chunks
- Used in fixtures: `@pytest.fixture def fake_llm()`

**`FakeEmbeddingModel(IEmbeddingModel)` [72:80]**
- `embed()` returns deterministic pseudo-embedding based on text hash
- Fixture: `@pytest.fixture def fake_embedder()`

**`FakeIndexStore(IIndexStore)` [91:126]**
- In-memory vector store (no FAISS)
- Fixture: `@pytest.fixture def fake_store()`

**Test Pattern:** Inject fake models into GenerationService for isolated testing:
```python
gen_service = GenerationService(
    fast_model=fake_llm,
    coding_model=fake_llm,
    review_model=fake_llm,
    default_model=fake_llm,
)
```

---

## 8. Dependencies & Package Status

### File: `pyproject.toml`

**Current Dependencies:**
```python
dependencies = [
    "typer>=0.9.0",      # CLI framework
    "requests",          # HTTP client (NO version pinned)
    "rich",              # Terminal formatting
    "tomli; python_version < '3.11'",  # TOML parsing
    "faiss-cpu",         # Vector index
    "numpy",             # Numerical computing
    "tree-sitter>=0.21", # Code parsing
    "tree-sitter-python>=0.21",
    "tree-sitter-php>=0.21",
    "tree-sitter-c-sharp>=0.21",
]
```

**`httpx` Status:** NOT currently used or listed. Current implementation uses `requests`.

**Rationale for `requests` vs `httpx`:**
- `requests` is synchronous, sufficient for current Ollama integration
- `httpx` is async-capable but adds complexity without current benefit
- No streaming advantages in current use case (streaming already handled via iter_lines)

---

## 9. No Existing LLMProvider Abstraction

**Finding:** There is **NO** existing `LLMProvider` or similar factory/router abstraction.

**Current Limitations:**
1. **Single Ollama Hardcoding:** Only Ollama is supported; no pluggable backends
2. **No API Key Support:** Zero support for authentication headers (Bearer, X-API-Key, etc.)
3. **No Environment Variable Expansion:** Config strings are literal (cannot reference $OLLAMA_KEY)
4. **No Custom Headers:** Cannot inject Authorization headers, custom User-Agent, etc.
5. **No Provider Routing:** No factory to select backend based on config (Ollama vs OpenAI vs Anthropic, etc.)

**Architectural Gap:** 
- If we want to support multiple LLM providers (Ollama, OpenAI, Anthropic, etc.), we'd need:
  1. Provider enum or string in Config (e.g., `provider: str = "ollama"`)
  2. Abstract `ILLMProvider` that wraps `ILanguageModel` creation + config
  3. Factory in `container.py` to instantiate correct provider
  4. Separate client classes per provider (e.g., `OpenAILanguageModel(ILanguageModel)`)

---

## 10. Summary Table

| Aspect | Current Implementation |
|--------|------------------------|
| **HTTP Client** | `requests` (sync) |
| **Ollama Endpoint** | Config-driven, default `http://localhost:11434` |
| **Auth Support** | None (no API keys, Bearer tokens, custom headers) |
| **Model Routing** | Per-purpose (RFC 012): fast, coding, review, default |
| **Context Tuning** | Per-purpose num_ctx and num_predict |
| **Streaming** | Yes, via `requests.post(..., stream=True).iter_lines()` |
| **Timeout** | Configurable per-request, default 300s |
| **Error Handling** | Rich console output with actionable suggestions |
| **Embedding Support** | Yes, via `/api/embeddings` endpoint |
| **LLM Provider Abstraction** | None (Ollama only) |
| **API Key Injection** | Not supported |
| **Env Expansion** | Not supported |
| **Testability** | Good (interface-based, mock-friendly) |
| **Config Loading** | TOML-based, singleton via DI |

---

## 11. Key Extension Points

If implementing multi-provider support or API key injection, these areas would change:

1. **`Config` dataclass** — add `provider: str`, `api_key: Optional[str]`, `auth_header: Optional[str]`
2. **`load_config()`** — add env var expansion logic, API key resolution
3. **`container.py`** — add factory function to select provider at runtime
4. **New file: `devtool/providers/`** — module for provider-specific implementations
5. **Interfaces might expand** — add optional auth methods to `ILanguageModel`?
6. **Tests** — mock different providers independently

---

## 12. File Paths (Absolute)

- `/home/leslie/github/waffle-commons/devtool/devtool/utils/ollama_client.py` — Ollama HTTP client
- `/home/leslie/github/waffle-commons/devtool/devtool/config.py` — Config schema & loading
- `/home/leslie/github/waffle-commons/devtool/devtool/container.py` — Dependency injection
- `/home/leslie/github/waffle-commons/devtool/devtool/interfaces.py` — Abstract base classes
- `/home/leslie/github/waffle-commons/devtool/devtool/services/generation_service.py` — Service layer
- `/home/leslie/github/waffle-commons/devtool/devtool/commands/commit.py` — Example command (commit)
- `/home/leslie/github/waffle-commons/devtool/devtool/commands/pre_review.py` — Example command (review)
- `/home/leslie/github/waffle-commons/devtool/tests/conftest.py` — Mock fixtures
- `/home/leslie/github/waffle-commons/devtool/tests/test_ollama_client.py` — LLM client tests
- `/home/leslie/github/waffle-commons/devtool/pyproject.toml` — Dependencies

