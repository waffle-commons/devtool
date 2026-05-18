# Changelog

All notable changes to devtool are documented in this file.

## [0.1.0-alpha3] — 2026-05-18

### Fixed
- **Critical:** Fixed `IndentationError` in `devtool/fix_ui.py` that prevented the `--fix` flag from working in `pre-review` and `sec-audit` commands. The `_render_diff()` function had inconsistent indentation (mix of 5-space and 9-space indents) that was not parseable by Python. ✓

### Improved
- Removed dead code `_build_language_model_from_route()` from `container.py` (unreachable RFC 017 implementation scaffold with TODO comments)
- Deleted unused backward-compat shim `devtool/utils/common.py` (marked as legacy, no internal callers)
- Added comprehensive test coverage for low-coverage modules:
  - `faiss_store.py`: 34% → 98% coverage (added 18 tests for save/load/search/reconstruct operations)
  - `docgen_utils.py`: 31% → 96% coverage (added 14 tests for Diataxis document generation orchestration)
  - `prompts.py`: 34% → 81% coverage (added 39 tests covering all prompt template functions)
- Overall test coverage: 78.4% → **81.36%** (334 tests, up from 281)

### Notes
- All 334 tests passing
- 81.36% code coverage (threshold: 60%)
- The `--fix` flag is now fully functional for interactive patch preview and application
- Pre-existing linting issues in `main.py` and `patch_service.py` (E402, E741) remain—outside this release scope

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
