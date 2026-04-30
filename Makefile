# =============================================================================
# Makefile — devtool CLI
# Cross-platform build system (Linux + macOS)
# =============================================================================

# ---------------------------------------------------------------------------
# OS Detection
# Detects the operating system to handle GNU vs BSD userland differences.
# Used for conditional behavior where Linux and macOS diverge.
# ---------------------------------------------------------------------------
UNAME_S := $(shell uname -s)

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------
VENV        := venv
PYTHON      := $(VENV)/bin/python3
PIP         := $(VENV)/bin/pip
PYTEST      := $(VENV)/bin/pytest
RUFF        := $(VENV)/bin/ruff
BLACK       := $(VENV)/bin/black
ISORT       := $(VENV)/bin/isort

# Dynamically resolve the Python version target for Black.
# Works identically on macOS and Linux (pure Python, no shell differences).
BLACK_TARGET := $(shell \
	if [ -f $(PYTHON) ]; then \
		$(PYTHON) -c "import sys; print('py{}{}'.format(sys.version_info.major, sys.version_info.minor))"; \
	else \
		python3 -c "import sys; print('py{}{}'.format(sys.version_info.major, sys.version_info.minor))"; \
	fi)

PACKAGE     := devtool
SRC_DIR     := devtool
TEST_DIR    := tests
DIST_DIR    := dist

# Terminal colors (ANSI — works on both macOS Terminal.app and Linux terminals)
BOLD        := \033[1m
GREEN       := \033[0;32m
YELLOW      := \033[0;33m
CYAN        := \033[0;36m
RESET       := \033[0m

# ---------------------------------------------------------------------------
# Default target
# ---------------------------------------------------------------------------
.DEFAULT_GOAL := all

.PHONY: all
all: venv install-deps
	@echo "$(GREEN)$(BOLD)✓ Environment ready. Activate with: source $(VENV)/bin/activate$(RESET)"

# ---------------------------------------------------------------------------
# Virtual environment management
# ---------------------------------------------------------------------------

.PHONY: venv
venv:
	@echo "$(CYAN)→ Creating virtual environment in ./$(VENV)/...$(RESET)"
	python3 -m venv $(VENV)
	@echo "$(GREEN)✓ Virtual environment created.$(RESET)"

.PHONY: install-deps
install-deps: venv
	@echo "$(CYAN)→ Upgrading pip...$(RESET)"
	$(PIP) install --upgrade pip --quiet
	@echo "$(CYAN)→ Installing production dependencies...$(RESET)"
	$(PIP) install -e . --quiet
	@echo "$(CYAN)→ Installing test dependencies (pytest, pytest-mock)...$(RESET)"
	$(PIP) install -e ".[test]" --quiet
	@echo "$(CYAN)→ Installing code quality tools (ruff, black, isort)...$(RESET)"
	$(PIP) install ruff black isort --quiet
	@echo "$(GREEN)✓ All dependencies installed.$(RESET)"

# Launch a sub-shell with the venv activated.
# Compatible with both bash (Linux) and zsh (macOS default).
.PHONY: shell
shell:
	@echo "$(YELLOW)→ Launching a shell with the venv activated...$(RESET)"
	@echo "$(YELLOW)  Exit with 'exit' to return to your main shell.$(RESET)"
	@SHELL_BIN=$$(echo $$SHELL); source $(VENV)/bin/activate && exec $$SHELL_BIN

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------

.PHONY: lint
lint: install-deps
	@echo "$(CYAN)→ Python target version for Black: $(BLACK_TARGET)$(RESET)"
	@echo "$(CYAN)→ Checking formatting with Black...$(RESET)"
	$(BLACK) --check --target-version $(BLACK_TARGET) $(SRC_DIR)/
	@echo "$(CYAN)→ Static analysis with Ruff...$(RESET)"
	$(RUFF) check $(SRC_DIR)/
	@echo "$(CYAN)→ Checking imports with isort...$(RESET)"
	$(ISORT) --check-only $(SRC_DIR)/
	@echo "$(GREEN)✓ Code quality validated.$(RESET)"

.PHONY: format
format: install-deps
	@echo "$(CYAN)→ Python target version for Black: $(BLACK_TARGET)$(RESET)"
	@echo "$(CYAN)→ Auto-formatting with Black...$(RESET)"
	$(BLACK) --target-version $(BLACK_TARGET) $(SRC_DIR)/
	@echo "$(CYAN)→ Sorting imports with isort...$(RESET)"
	$(ISORT) $(SRC_DIR)/
	@echo "$(CYAN)→ Auto-fixing with Ruff...$(RESET)"
	$(RUFF) check --fix $(SRC_DIR)/
	@echo "$(GREEN)✓ Formatting complete.$(RESET)"

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

.PHONY: test
test: install-deps
	@echo "$(CYAN)→ Running tests with pytest...$(RESET)"
	$(PYTEST) $(TEST_DIR)/ -v --tb=short
	@echo "$(GREEN)✓ Tests complete.$(RESET)"

.PHONY: test-cov
test-cov: install-deps
	@echo "$(CYAN)→ Running tests with coverage report...$(RESET)"
	$(PIP) install pytest-cov --quiet
	$(PYTEST) $(TEST_DIR)/ -v --tb=short --cov=$(SRC_DIR) --cov-report=term-missing
	@echo "$(GREEN)✓ Coverage report generated.$(RESET)"

# ---------------------------------------------------------------------------
# Package build
# ---------------------------------------------------------------------------

.PHONY: build
build: install-deps
	@echo "$(CYAN)→ Building Python package (wheel + sdist)...$(RESET)"
	$(PIP) install build --quiet
	$(PYTHON) -m build
	@echo "$(GREEN)✓ Package built in ./$(DIST_DIR)/$(RESET)"

# ---------------------------------------------------------------------------
# Installation (cross-platform: Linux + macOS)
# ---------------------------------------------------------------------------

# Install 'devtool' globally via pipx.
# pipx works identically on Linux and macOS.
# The PATH hint adapts to the user's default shell config file.
.PHONY: install-local
install-local:
	@echo "$(CYAN)→ Installing 'devtool' globally via pipx...$(RESET)"
	pipx install --force .
	@echo "$(GREEN)✓ 'devtool' installed globally. Test with: devtool --help$(RESET)"
ifeq ($(UNAME_S),Darwin)
	@echo "$(YELLOW)  If command not found, add to your ~/.zshrc:$(RESET)"
else
	@echo "$(YELLOW)  If command not found, add to your ~/.bashrc:$(RESET)"
endif
	@echo '      export PATH="$$HOME/.local/bin:$$PATH"'

.PHONY: install-dev
install-dev: venv
	@echo "$(CYAN)→ Installing in editable mode (pip install -e .)...$(RESET)"
	$(PIP) install -e ".[test]"
	@echo "$(GREEN)✓ 'devtool' installed in development mode.$(RESET)"
	@echo "$(YELLOW)  Activate the venv to use: source $(VENV)/bin/activate$(RESET)"

.PHONY: uninstall
uninstall:
	@echo "$(CYAN)→ Uninstalling 'devtool'...$(RESET)"
	pipx uninstall $(PACKAGE) || pip3 uninstall -y $(PACKAGE)
	@echo "$(GREEN)✓ 'devtool' uninstalled.$(RESET)"

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------
# Cross-platform clean target.
# - Uses `find ... -print0 | xargs -0` which is portable across GNU and BSD find.
# - Avoids GNU-only `-not` syntax; uses `!` which works on both.
# - Removes .DS_Store (macOS) alongside Python artifacts.
# - All commands are guarded with `|| true` / `2>/dev/null` to never fail.

.PHONY: clean
clean:
	@echo "$(CYAN)→ Removing virtual environment...$(RESET)"
	rm -rf $(VENV)
	@echo "$(CYAN)→ Removing Python caches...$(RESET)"
	find . -type d -name "__pycache__" ! -path "./.git/*" -print0 2>/dev/null | xargs -0 rm -rf 2>/dev/null || true
	find . -type f -name "*.pyc" ! -path "./.git/*" -print0 2>/dev/null | xargs -0 rm -f 2>/dev/null || true
	find . -type f -name "*.pyo" ! -path "./.git/*" -print0 2>/dev/null | xargs -0 rm -f 2>/dev/null || true
	@echo "$(CYAN)→ Removing build artifacts...$(RESET)"
	rm -rf $(DIST_DIR)/ build/ *.egg-info/ src/*.egg-info/
	@echo "$(CYAN)→ Removing test and lint caches...$(RESET)"
	rm -rf .coverage htmlcov/ .pytest_cache/ .ruff_cache/
	@echo "$(CYAN)→ Removing OS artifacts...$(RESET)"
	find . -type f -name ".DS_Store" -print0 2>/dev/null | xargs -0 rm -f 2>/dev/null || true
	@echo "$(GREEN)✓ Project cleaned.$(RESET)"

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

.PHONY: help
help:
	@echo ""
	@echo "$(BOLD)devtool — Available Makefile targets$(RESET)"
	@echo "─────────────────────────────────────────────"
	@echo "$(CYAN)Environment:$(RESET)"
	@echo "  make venv           Create Python virtual environment"
	@echo "  make install-deps   Install all dependencies (prod + test + lint)"
	@echo "  make shell          Launch a sub-shell with the venv activated"
	@echo ""
	@echo "$(CYAN)Code Quality:$(RESET)"
	@echo "  make lint           Check style (black, ruff, isort)"
	@echo "  make format         Apply automatic formatting"
	@echo ""
	@echo "$(CYAN)Tests:$(RESET)"
	@echo "  make test           Run test suite (pytest)"
	@echo "  make test-cov       Run tests with coverage report"
	@echo ""
	@echo "$(CYAN)Build & Install:$(RESET)"
	@echo "  make build          Build Python package (wheel + sdist)"
	@echo "  make install-local  Install 'devtool' globally via pipx"
	@echo "  make install-dev    Install in development mode (editable)"
	@echo "  make uninstall      Uninstall 'devtool' from the system"
	@echo ""
	@echo "$(CYAN)Cleanup:$(RESET)"
	@echo "  make clean          Remove venv, caches, build artifacts, .DS_Store"
	@echo ""
