# devtool 0.1.0-alpha3 — Documentation Index

**Release:** May 18, 2026  
**Status:** Feature-Complete Alpha  
**Version:** `0.1.0-alpha3`

---

## 📚 Documentation Files

### For Users & Teams
- **[RELEASE_NOTES.md](./RELEASE_NOTES.md)** ← Start here
  - Complete overview of all changes in alpha3
  - New commands and features
  - Installation & quick start
  - 11 commands reference table

- **[RELEASE_SUMMARY.md](./RELEASE_SUMMARY.md)**
  - Quick summary of what's new
  - List of changed/new files
  - Test results
  - Next steps

- **[CHANGELOG.md](./CHANGELOG.md)**
  - Detailed changelog with version history
  - All improvements and fixes documented
  - Clear distinction between Added/Fixed/Improved

### For Developers
- **[CLAUDE.md](./CLAUDE.md)**
  - System guide for LLM development on this project
  - Build & test commands
  - Code style guidelines
  - Architecture map

- **[README.md](./README.md)**
  - Project overview
  - Architecture diagram
  - Design principles
  - Features summary

### RFCs (Request for Comments)
All 17 RFCs are in `specs/RFCs/`:

**Newly Implemented (alpha3):**
- [RFC 013: Anonymization Engine](./specs/RFCs/RFC_013_Anonymization_Engine.md) — `devtool anonymize`
- [RFC 014: Secrets Scanner](./specs/RFCs/RFC_014_Secrets_Scanner.md) — Pre-LLM middleware
- [RFC 015: Synthetic Data Generator](./specs/RFCs/RFC_015_Synthetic_Data_Generator.md) — `devtool mock-data`

**Previously Implemented (alpha1-alpha2):**
- [RFC 001](./specs/RFCs/RFC_001_Commit_Generator.md) — Commit message generation
- [RFC 002](./specs/RFCs/RFC_002_Code_Review.md) — Code review with auto-fix
- [RFC 003](./specs/RFCs/RFC_003_Unit_Testing.md) — Test generation
- [RFC 004](./specs/RFCs/RFC_004_Security_Analysis.md) — Security audit
- [RFC 005](./specs/RFCs/RFC_005_Diataxis_Generator.md) — Documentation generation
- [RFC 006](./specs/RFCs/RFC_006_Repository_Analysis.md) — Repository analysis
- [RFC 007](./specs/RFCs/RFC_007_Local_Repository_RAG.md) — RAG indexing
- [RFC 008](./specs/RFCs/RFC_008_Test_Suite_Cleanup_&_Automation.md) — Test infrastructure
- [RFC 009](./specs/RFCs/RFC_009_CrossCommand_RAG_Integration.md) — RAG integration
- [RFC 010](./specs/RFCs/RFC_010_AST_Semantic_Chunking.md) — AST chunking
- [RFC 011](./specs/RFCs/RFC_011_Interactive_AutoFixs.md) — Auto-fix patches
- [RFC 012](./specs/RFCs/RFC_012_MultiModels_Routing.md) — Multi-model routing
- [RFC 016](./specs/RFCs/RFC_016_Mini_RAG_Context.md) — Mini RAG context
- [RFC 017](./specs/RFCs/RFC_017_Cloud_ready.md) — Cloud-ready OpenAI support

### Roadmaps & Planning
- [AIT-ALPHA1-ROADMAP.md](./specs/Roadmaps/AIT-ALPHA1-ROADMAP.md)
- [AIT-ALPHA2-ROADMAP.md](./specs/Roadmaps/AIT-ALPHA2-ROADMAP.md)

### Code Documentation
- `devtool/` — Source code (all modules have docstrings)
- `tests/` — 370+ tests with clear naming and documentation
- `docs/` — Tutorial and reference documentation

---

## 🚀 Quick Start

### Installation
```bash
git clone https://github.com/anomalyco/devtool
cd devtool
make dev                # Setup Python venv + dependencies
```

### Run Tests
```bash
make test               # Run all 370+ tests
make lint               # Style check (pre-existing issues tolerated)
```

### First Command
```bash
# Ensure Ollama is running:
ollama serve

# In another terminal:
devtool --help          # View all 11 commands
devtool commit          # Try generating a commit message
```

---

## 📊 Current Status

### Commands Implemented (11/11)
✅ commit, review, testgen, sec-audit, docgen, repo-analysis, index, ask, debug-ollama, **anonymize**, **mock-data**

### RFCs Implemented (17/17)
✅ All RFCs (001-017) fully implemented

### Test Coverage
✅ 81%+ coverage (370+ tests)

### Code Quality
✅ Type hints, DDD architecture, clean layer separation

---

## 📝 Key Files in This Release

### New Utilities
- `devtool/utils/anonymizer.py` — Anonymization engine (RFC 013)
- `devtool/utils/secrets_scanner.py` — Secrets detection (RFC 014)

### New Commands
- `devtool/commands/anonymize.py` — Anonymize command (RFC 013)
- `devtool/commands/mock_data.py` — Mock data command (RFC 015)

### Modified Core Files
- `devtool/main.py` — Registered 2 new commands
- `devtool/commands/commit.py` — Added secrets middleware
- `devtool/commands/sec_audit.py` — Added secrets middleware
- `devtool/services/generation_service.py` — Added generic `generate_text()`
- `devtool/prompts.py` — Added mock-data system prompt

### Tests
- `tests/test_anonymizer.py` (11 tests)
- `tests/test_secrets_scanner.py` (18 tests)
- `tests/test_option_c_commands.py` (integration tests)

---

## 🔗 Links

- **GitHub:** https://github.com/anomalyco/devtool
- **Issue Tracker:** https://github.com/anomalyco/opencode/issues
- **Ollama:** https://ollama.com

---

## 📞 Getting Help

1. **Stuck with setup?** → See [RELEASE_NOTES.md](./RELEASE_NOTES.md) "Installation & Quick Start"
2. **Want to contribute?** → See [CLAUDE.md](./CLAUDE.md) for dev guidelines
3. **Questions about commands?** → Run `devtool <command> --help`
4. **Found a bug?** → File an issue on GitHub

---

**Happy secure coding! 🔐**

devtool — Privacy-First AI DevSecOps for Regulated Environments
