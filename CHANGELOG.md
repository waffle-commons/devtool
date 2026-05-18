# Changelog

All notable changes to devtool are documented in this file.

## [0.1.0-alpha3] — 2026-05-18

### Added (RFC 013, 014, 015)
- **RFC 013: `devtool anonymize`** — New command for sanitizing code before cloud export. Removes PII, hardcoded secrets, and proprietary terms while maintaining semantic consistency. Supports file and directory inputs with optional `.devtool-dictionary.toml` blocklist. ✓
- **RFC 014: Secrets Scanner** — Pre-LLM middleware that scans `devtool commit` and `devtool sec-audit` diffs for high-entropy secrets, AWS keys, Stripe keys, JWT tokens, and SSH private keys. Aborts with clear error message if secrets detected. Supports `.devtool-ignore-secrets` for false positive bypass. ✓
- **RFC 015: `devtool mock-data`** — New command for generating realistic, completely synthetic, GDPR-compliant test data. Accepts SQL or JSON schemas and generates N rows of fake but logically consistent data using local LLM. ✓

### Fixed
- **Critical:** Fixed `IndentationError` in `devtool/fix_ui.py` that prevented the `--fix` flag from working in `pre-review` and `sec-audit` commands. The `_render_diff()` function had inconsistent indentation (mix of 5-space and 9-space indents) that was not parseable by Python. ✓

### Improved
- Removed dead code `_build_language_model_from_route()` from `container.py` (unreachable RFC 017 implementation scaffold with TODO comments)
- Deleted unused backward-compat shim `devtool/utils/common.py` (marked as legacy, no internal callers)
- Added comprehensive test coverage for low-coverage modules:
  - `faiss_store.py`: 34% → 98% coverage (added 18 tests for save/load/search/reconstruct operations)
  - `docgen_utils.py`: 31% → 96% coverage (added 14 tests for Diataxis document generation orchestration)
  - `prompts.py`: 34% → 81% coverage (added 39 tests covering all prompt template functions)
  - `anonymizer.py`: New module with 11 tests (100% coverage)
  - `secrets_scanner.py`: New module with 18 tests (100% coverage)
- Overall test coverage: 78.4% → **81%+** (370+ tests, up from 281)
- Extended `GenerationService` with generic `generate_text()` method for flexible LLM invocation

### Notes
- All 370+ tests passing
- 81%+ code coverage (threshold: 60%)
- The `--fix` flag is now fully functional for interactive patch preview and application
- All three proposed RFCs (013, 014, 015) are now **implemented and tested**
- Pre-existing linting issues in `main.py` and `patch_service.py` (E402, E741) remain—outside this release scope
- 11 core commands now available (added `anonymize`, `mock-data`)

---

## [0.1.0-alpha2] — Previous Release

Initial alpha release with 9 core commands:
- `commit` — AI-powered conventional commit generation
- `review` — Code review with optional auto-fix
- `testgen` — Unit test generation (multi-framework)
- `sec-audit` — Security audit with optional auto-fix
- `docgen` — Documentation generation (Diataxis-compliant)
- `repo-analysis` — Repository-wide analysis
- `index` — RAG index management
- `ask` — RAG semantic search query
- `debug-ollama` — Ollama diagnostics

### Status
- Multi-model routing (fast/coding/review/default)
- OpenAI-compatible provider support
- AST-aware semantic chunking (Python/PHP/C#)
- Dual index backend (FAISS / linear fallback)
- TOML configuration with ENV var expansion
