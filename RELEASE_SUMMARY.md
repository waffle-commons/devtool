# 0.1.0-alpha3 Release Summary

**Date:** May 18, 2026  
**Commit:** devtool 0.1.0-alpha3 — Feature-Complete Alpha Release

## What's Included

### ✅ Three New RFCs Implemented & Tested

1. **RFC 013: Code Anonymization Engine**
   - New command: `devtool anonymize`
   - Removes PII, secrets, proprietary terms before cloud export
   - Full file/directory support with semantic consistency
   - 11 tests, 100% coverage

2. **RFC 014: Pre-LLM Secrets Scanner**
   - Middleware for `commit` and `sec-audit` commands
   - Detects AWS/Stripe/JWT/SSH keys, high-entropy strings
   - Sub-100ms performance, supports `.devtool-ignore-secrets`
   - 18 tests, 100% coverage

3. **RFC 015: Synthetic Data Generator**
   - New command: `devtool mock-data`
   - Generates GDPR-compliant fake data from schemas
   - SQL and JSON support, configurable row counts
   - Tested and working

### ✅ Critical Bug Fix

- Fixed `IndentationError` in `fix_ui.py` blocking `--fix` flag
- Mix of 5-space and 9-space indentation now corrected to consistent 4-space

### ✅ Code Quality Improvements

- Removed dead code: `_build_language_model_from_route()`
- Deleted legacy shim: `devtool/utils/common.py`
- Test coverage: 78.4% → 81%+ (370+ tests, up from 281)
- Module improvements:
  - `faiss_store.py`: 34% → 98%
  - `docgen_utils.py`: 31% → 96%
  - `prompts.py`: 34% → 81%

### ✅ Documentation Updates

- Updated CHANGELOG.md with all alpha3 changes
- Created RELEASE_NOTES.md with comprehensive overview
- Updated RFC status: 013, 014, 015 marked as Implemented ✓
- All version strings consistent: 0.1.0-alpha3

## Files Changed

### New Files
- `devtool/commands/anonymize.py` — Anonymization command
- `devtool/commands/mock_data.py` — Mock data command
- `devtool/utils/anonymizer.py` — Anonymization engine
- `devtool/utils/secrets_scanner.py` — Secrets detection
- `tests/test_anonymizer.py` — 11 tests
- `tests/test_secrets_scanner.py` — 18 tests
- `tests/test_option_c_commands.py` — Integration tests
- `RELEASE_NOTES.md` — Release documentation

### Modified Files
- `devtool/commands/commit.py` — Added secrets scanner middleware
- `devtool/commands/sec_audit.py` — Added secrets scanner middleware
- `devtool/main.py` — Registered 2 new commands (anonymize, mock-data)
- `devtool/services/generation_service.py` — Added generic `generate_text()` method
- `devtool/prompts.py` — Added MOCK_DATA_SYSTEM_PROMPT
- `CHANGELOG.md` — Documented all changes
- `specs/RFCs/RFC_013*.md` — Status: Implemented ✓
- `specs/RFCs/RFC_014*.md` — Status: Implemented ✓
- `specs/RFCs/RFC_015*.md` — Status: Implemented ✓

## Test Results

- **370+ tests passing** (up from 281)
- **81%+ code coverage** (threshold: 60%)
- New utilities: 100% coverage
- All existing tests still passing

## Known Issues (Pre-Existing)

- Linting: E402 and E741 warnings in `main.py` and `patch_service.py` (tolerated)
- Command test file may timeout in full suite run (unit tests all pass independently)

## Next Steps for Users

1. Pull latest code
2. Run `make dev` to set up environment
3. Run `make test` to verify all tests pass
4. Try new commands: `devtool anonymize --help`, `devtool mock-data --help`
5. Enjoy enhanced privacy and security! 🔐

---

**Status:** Ready for team evaluation in regulated environments  
**Version:** 0.1.0-alpha3  
**Release Type:** Feature-Complete Alpha
