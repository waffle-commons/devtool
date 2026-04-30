# devtool

**Local AI DevSecOps Assistant — Zero Data Retention, Full Engineering Power.**

`devtool` is a privacy-first, local CLI that brings AI-powered DevSecOps capabilities directly into your terminal. Built for regulated environments (FinTech, LegalTech, Healthcare) where sending code to cloud APIs is not an option, it leverages [Ollama](https://ollama.com) for local LLM inference and [FAISS](https://github.com/facebookresearch/faiss) for semantic code search — ensuring **zero data ever leaves your machine**.

---

## Key Features

| Capability | Description |
|---|---|
| **Zero Data Retention** | All inference runs locally via Ollama. No telemetry, no cloud calls, no data exfiltration. |
| **Shift-Left DevSecOps** | Security audits (OWASP Top 10), code review, and test generation — all before code reaches CI. |
| **Local RAG** | FAISS-powered vector index of your codebase for context-aware answers and enriched commands. |
| **Streaming Rich UI** | Real-time token streaming with a polished terminal interface via [Rich](https://github.com/Textualize/rich). |
| **Multi-Model Routing** | Route tasks to specialized models (coding, review, fast, embedding) via a single `[models]` config. |
| **Per-Task Performance Tuning** | Independent `num_ctx` and `num_predict` limits per purpose — fast tasks stay fast. |
| **Interactive Auto-Fix** | `--fix` flag on review and audit commands generates unified diffs and offers interactive patch application. |
| **Clean DDD Architecture** | Strict separation: `commands/` (thin controllers), `services/` (business logic), `utils/` (infrastructure), `prompts.py` (prompt engineering). |

---

## Architecture Overview

```
devtool/
├── commands/               # Typer CLI controllers (thin layer, no business logic)
│   └── _rag_helpers.py     # Shared RAG context injection helper (DRY)
├── services/               # Domain logic
│   ├── generation_service.py  # Orchestrates prompts + LLM (SRP)
│   ├── rag_service.py         # FAISS indexing and semantic search
│   ├── patch_service.py       # SEARCH/REPLACE patch parsing and application
│   └── faiss_store.py         # IIndexStore implementation
├── utils/                  # Infrastructure adapters
│   ├── ollama_client.py       # Pure HTTP transport (ILanguageModel, IEmbeddingModel)
│   ├── git_utils.py           # Git subprocess operations
│   ├── language_utils.py      # Language detection and framework mapping
│   ├── path_utils.py          # File collection and filtering
│   └── docgen_utils.py        # Diataxis docgen orchestration
├── prompts.py              # ALL prompt templates (single responsibility)
├── interfaces.py           # Abstract contracts (ILanguageModel, IEmbeddingModel, IIndexStore)
├── container.py            # Dependency injection wiring
├── config.py               # TOML configuration with per-purpose resolution
├── stream.py               # Token streaming engine (<think> tag parsing)
├── view.py                 # Rich UI rendering (Live panels)
└── main.py                 # Typer app entrypoint
```

**Design principles enforced:**

- **Single Responsibility** — Prompt engineering lives in `prompts.py`, HTTP transport in `ollama_client.py`, orchestration in `generation_service.py`. No module does two jobs.
- **Dependency Inversion** — All commands resolve services through `container.py`. Concrete implementations are injected, never imported directly.
- **DRY** — Repeated patterns (RAG injection, stream rendering) are extracted into shared helpers.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | >= 3.9 (3.12+ recommended) |
| OS | Linux / WSL2 (macOS supported) |
| [Ollama](https://ollama.com) | Latest, running locally |
| [pipx](https://pypa.github.io/pipx/) | For isolated CLI installation |

**Required Ollama models** (pull before first use):

```bash
# These must match your [models] section in .devtool.toml
ollama pull gemma4:latest
ollama pull qwen3-coder:latest
ollama pull qwen3:0.6b
ollama pull qwen3-embedding:latest
```

---

## Installation

### Via pipx (recommended)

```bash
git clone <repository-url> && cd devtool
make install-local
```

This runs `pipx install --force .` and makes `devtool` available globally.

### Development mode

```bash
make venv
make install-deps
# or simply:
make install-dev   # pip install -e ".[test]"
```

### Verify installation

```bash
devtool debug-ollama
```

---

## Configuration

Copy the example configuration to your project root:

```bash
cp .devtool.toml.example .devtool.toml
```

### `.devtool.toml`

```toml
[ollama]
endpoint = "http://localhost:11434"
show_thoughts = true
request_timeout = 300
num_ctx = 8192
keep_alive = "10m"
# Per-purpose performance tuning
num_ctx_fast = 4096
num_ctx_coding = 8192
num_ctx_review = 12288
num_predict_fast = 512
num_predict_coding = 4096
num_predict_review = 4096
num_predict_default = 4096

[models]
# Single source of truth for ALL model assignments.
# No model keys belong in [ollama] — only here.
default   = "gemma4:latest"
coding    = "qwen3-coder:latest"
fast      = "qwen3:0.6b"
review    = "gemma4:latest"
embedding = "qwen3-embedding:latest"
```

### Configuration Reference

**`[ollama]` — Connection and Performance**

| Key | Description | Default |
|---|---|---|
| `endpoint` | Ollama API base URL | `http://localhost:11434` |
| `show_thoughts` | Display model `<think>` reasoning tokens | `true` |
| `request_timeout` | HTTP timeout in seconds | `300` |
| `num_ctx` | Default context window (tokens) | `8192` |
| `keep_alive` | Keep model in VRAM between calls (`"10m"`, `"1h"`, `"0"`) | `"10m"` |
| `num_ctx_fast` | Context window for fast tasks (commit) | `4096` |
| `num_ctx_coding` | Context window for coding tasks (testgen, docgen) | `8192` |
| `num_ctx_review` | Context window for review tasks (review, sec-audit) | `12288` |
| `num_predict_fast` | Max output tokens for fast tasks | `512` |
| `num_predict_coding` | Max output tokens for coding tasks | `4096` |
| `num_predict_review` | Max output tokens for review tasks | `4096` |
| `num_predict_default` | Fallback max output tokens | `4096` |

**`[models]` — Single Source of Truth for Model Routing**

| Key | Purpose | Recommendation |
|---|---|---|
| `default` | General tasks, RAG Q&A | Balanced model |
| `coding` | Test generation, documentation | Coding-optimized model |
| `fast` | Commit messages, file summaries | Smallest/fastest model |
| `review` | Code review, security audit | Largest available model |
| `embedding` | RAG vector embeddings | Embedding-specific model |

> **Performance tip:** To avoid cold-start swaps between models, set `default`, `coding`, and `review` to the **same model**. Ollama unloads/reloads when switching models, which adds 5-30s latency per swap.

---

## Commands Reference

### `devtool commit`

Analyze staged git changes and generate a [Conventional Commits](https://www.conventionalcommits.org/) message.

```bash
git add -A
devtool commit
```

Uses the `fast` model with minimal context window for speed.

---

### `devtool review`

Analyze the current branch against a target branch for code smells, SOLID violations, and quality issues.

```bash
devtool review --compare main
devtool review --compare develop --use-rag
devtool review --compare main --fix
```

| Flag | Description |
|---|---|
| `--compare`, `-c` | Target branch to diff against (auto-infers if omitted) |
| `--use-rag` | Enrich analysis with RAG context from the indexed codebase |
| `--fix` | Generate unified diffs and offer interactive patch application |

---

### `devtool sec-audit`

Run an OWASP Top 10-focused security audit on a file, directory, or staged diff.

```bash
devtool sec-audit src/auth/
devtool sec-audit --staged
devtool sec-audit src/api.py --use-rag --fix
```

| Flag | Description |
|---|---|
| `--staged` | Audit the current staged git diff |
| `--use-rag` | Enrich with cross-file caller context for source-to-sink analysis |
| `--fix` | Interactive patch application for findings |

Returns non-zero exit codes for CI integration.

---

### `devtool testgen`

Generate or update unit tests for a specific file (or batch process modified files).

```bash
devtool testgen src/services/auth_service.py
devtool testgen src/services/auth_service.py --framework pytest
devtool testgen --use-rag
```

| Flag | Description |
|---|---|
| `--framework` | Test framework to target (e.g., `pytest`, `jest`, `phpunit`) |
| `--use-rag` | Use RAG context for better dependency mocking |

---

### `devtool docgen`

Generate [Diataxis](https://diataxis.fr/)-structured Markdown documentation from source code.

```bash
devtool docgen src/services/rag_service.py --type reference
devtool docgen src/commands/ --type howto --output-dir ./docs
devtool docgen --type tutorial --context "Onboarding new developers"
devtool docgen src/  # Complete Mode: generates all 4 quadrants
```

| Flag | Description |
|---|---|
| `--type` | Diataxis quadrant: `tutorial`, `howto`, `reference`, `explanation` |
| `--output-dir` | Output directory (default: `./docs`) |
| `--context` | Additional context to guide generation |

Omit `--type` to run **Complete Mode** (all four quadrants generated sequentially).

---

### `devtool repo-analysis`

Run a holistic architectural audit of the entire repository using Map-Reduce analysis.

```bash
devtool repo-analysis
devtool repo-analysis ./src --use-rag
```

| Flag | Description |
|---|---|
| `--use-rag` | Use FAISS index for accelerated analysis (skips per-file summarization) |

---

### `devtool index`

Build (or rebuild) a local FAISS vector index of the codebase for RAG queries.

```bash
devtool index .
devtool index src/ --update
```

| Flag | Description |
|---|---|
| `--update`, `-u` | Incrementally update the existing index (only re-embed changed files) |

---

### `devtool ask`

Ask a semantic question against the indexed codebase.

```bash
devtool ask "How is authentication handled?"
devtool ask "Where are database migrations defined?" --top-k 10
```

| Flag | Description |
|---|---|
| `--top-k`, `-k` | Number of relevant chunks to retrieve (default: 5) |
| `--dir`, `-d` | Directory scope for the search (default: `.`) |

---

### `devtool debug-ollama`

Diagnose the Ollama connection and verify that **all configured models** are available.

```bash
devtool debug-ollama
```

Checks every model in your `[models]` section and reports missing ones with the exact `ollama pull` commands needed.

---

## Performance Tuning Guide

If `devtool` feels slow, here are the levers to pull (in order of impact):

1. **Reduce `num_ctx`** — The biggest factor. A 16K context allocates ~2GB VRAM on load. Use 4096 for commit, 8192 for code tasks.

2. **Set `keep_alive = "10m"`** — Prevents Ollama from unloading models between commands (default is 5 min).

3. **Use the same model for multiple purposes** — Every model swap triggers a full unload/reload cycle (5-30s). Set `review = "gemma4:latest"` and `default = "gemma4:latest"` to avoid swaps.

4. **Cap `num_predict`** — Without a limit, models can generate thousands of tokens. `512` for commits, `4096` for reviews.

5. **Use smaller models for fast tasks** — `qwen3:0.6b` generates commit messages in 2-3s vs 15-20s for larger models.

---

## Roadmap — Alpha 2 (May–June 2026)

| Phase | Theme | Key Deliverables |
|---|---|---|
| **0** | Audit Remediation | DI container, extracted prompts, thin controllers, security hardening |
| **1** | Unbreakable Foundations | Full test suite (>80% coverage), multi-model routing |
| **2** | Contextual Intelligence | AST semantic chunking via tree-sitter, cross-command RAG |
| **3** | Active Engineering | Interactive auto-fix with unified diff parsing |

### Upcoming Highlights

- **AST Semantic Chunking (RFC 010)** — Replace naive line-based chunking with tree-sitter AST parsing for PHP, C#, and Python, producing semantically meaningful index entries.
- **Multi-Model Routing (RFC 012)** — Automatically dispatch tasks to the optimal local model based on task type.
- **Cross-Command RAG (RFC 009)** — Every analysis command (`review`, `sec-audit`, `testgen`) can pull relevant codebase context via `--use-rag`.
- **Interactive Auto-Fix (RFC 011)** — `--fix` flag generates patches and presents an interactive TUI for applying, skipping, or editing each hunk.

---

## Development

```bash
make format      # Auto-format with Black, isort, Ruff
make lint        # Check formatting and linting
make test        # Run pytest (78 tests)
make test-cov    # Run pytest with coverage report
make build       # Build wheel + sdist
```

---

## License

See [LICENSE](./LICENSE) for details.

---

## Contributing

Contributions are welcome. Please:

1. Fork the repository and create a feature branch.
2. Follow the existing code style (`make format && make lint`).
3. Add tests for new functionality.
4. Reference the relevant RFC from `specs/RFCs/` in your PR description.

For major changes, open an issue first to discuss the approach.
