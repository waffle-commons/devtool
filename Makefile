# =============================================================================
# Makefile — devtool CLI
# Gestion du cycle de vie du projet (venv, tests, build, installation)
# =============================================================================

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
BUILD       := $(VENV)/bin/python3 -m build

# Version cible de Black déduite dynamiquement desde Python du venv
# Ex : Python 3.12.x → --target-version py312
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

# Couleurs pour les messages dans le terminal
BOLD        := \033[1m
GREEN       := \033[0;32m
YELLOW      := \033[0;33m
CYAN        := \033[0;36m
RESET       := \033[0m

# ---------------------------------------------------------------------------
# Cible par défaut
# ---------------------------------------------------------------------------

# Lance la création du venv et l'installation des dépendances par défaut
.DEFAULT_GOAL := all

.PHONY: all
all: venv install-deps
	@echo "$(GREEN)$(BOLD)✓ Environnement prêt. Activez le venv avec : source $(VENV)/bin/activate$(RESET)"

# ---------------------------------------------------------------------------
# Gestion de l'environnement virtuel
# ---------------------------------------------------------------------------

# Crée l'environnement virtuel Python isolé
.PHONY: venv
venv:
	@echo "$(CYAN)→ Création de l'environnement virtuel dans ./$(VENV)/...$(RESET)"
	python3 -m venv $(VENV)
	@echo "$(GREEN)✓ Environnement virtuel créé.$(RESET)"

# Installe toutes les dépendances du projet (prod + dev/test)
.PHONY: install-deps
install-deps: venv
	@echo "$(CYAN)→ Mise à jour de pip...$(RESET)"
	$(PIP) install --upgrade pip --quiet
	@echo "$(CYAN)→ Installation des dépendances de production...$(RESET)"
	$(PIP) install -e . --quiet
	@echo "$(CYAN)→ Installation des dépendances de test (pytest, pytest-mock)...$(RESET)"
	$(PIP) install -e ".[test]" --quiet
	@echo "$(CYAN)→ Installation des outils de qualité de code (ruff, black, isort)...$(RESET)"
	$(PIP) install ruff black isort --quiet
	@echo "$(GREEN)✓ Toutes les dépendances sont installées.$(RESET)"

# Lance un sous-shell avec le venv activé (WSL compatible)
.PHONY: shell
shell:
	@echo "$(YELLOW)→ Lancement d'un shell avec le venv activé...$(RESET)"
	@echo "$(YELLOW)  Quittez avec 'exit' pour revenir à votre shell principal.$(RESET)"
	source $(VENV)/bin/activate && exec $$SHELL

# ---------------------------------------------------------------------------
# Qualité du code
# ---------------------------------------------------------------------------

# Lance le formateur Black et le vérificateur de style Ruff sur le code source
.PHONY: lint
lint: install-deps
	@echo "$(CYAN)→ Version Python cible pour Black : $(BLACK_TARGET)$(RESET)"
	@echo "$(CYAN)→ Vérification du formatage avec Black...$(RESET)"
	$(BLACK) --check --target-version $(BLACK_TARGET) $(SRC_DIR)/
	@echo "$(CYAN)→ Analyse statique avec Ruff...$(RESET)"
	$(RUFF) check $(SRC_DIR)/
	@echo "$(CYAN)→ Vérification des imports avec isort...$(RESET)"
	$(ISORT) --check-only $(SRC_DIR)/
	@echo "$(GREEN)✓ Qualité du code validée.$(RESET)"

# Applique automatiquement les corrections de formatage
.PHONY: format
format: install-deps
	@echo "$(CYAN)→ Version Python cible pour Black : $(BLACK_TARGET)$(RESET)"
	@echo "$(CYAN)→ Formatage automatique avec Black...$(RESET)"
	$(BLACK) --target-version $(BLACK_TARGET) $(SRC_DIR)/
	@echo "$(CYAN)→ Tri des imports avec isort...$(RESET)"
	$(ISORT) $(SRC_DIR)/
	@echo "$(CYAN)→ Correction automatique avec Ruff...$(RESET)"
	$(RUFF) check --fix $(SRC_DIR)/
	@echo "$(GREEN)✓ Formatage terminé.$(RESET)"

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# Exécute la suite de tests via pytest
.PHONY: test
test: install-deps
	@echo "$(CYAN)→ Lancement des tests avec pytest...$(RESET)"
	$(PYTEST) $(TEST_DIR)/ -v --tb=short
	@echo "$(GREEN)✓ Tests terminés.$(RESET)"

# Exécute les tests avec rapport de couverture de code
.PHONY: test-cov
test-cov: install-deps
	@echo "$(CYAN)→ Lancement des tests avec couverture de code...$(RESET)"
	$(PIP) install pytest-cov --quiet
	$(PYTEST) $(TEST_DIR)/ -v --tb=short --cov=$(SRC_DIR) --cov-report=term-missing
	@echo "$(GREEN)✓ Rapport de couverture généré.$(RESET)"

# ---------------------------------------------------------------------------
# Build du paquet
# ---------------------------------------------------------------------------

# Construit le paquet Python (wheel + sdist) dans ./dist/
.PHONY: build
build: install-deps
	@echo "$(CYAN)→ Construction du paquet Python (wheel + sdist)...$(RESET)"
	$(PIP) install build --quiet
	$(PYTHON) -m build
	@echo "$(GREEN)✓ Paquet construit dans ./$(DIST_DIR)/$(RESET)"

# ---------------------------------------------------------------------------
# Installation locale (WSL / système)
# ---------------------------------------------------------------------------

# Installe 'devtool' globalement pour l'utilisateur courant via pipx
# Assure que ~/.local/bin est dans le PATH WSL
.PHONY: install-local
install-local:
	@echo "$(CYAN)→ Installation globale de 'devtool' via pipx...$(RESET)"
	pipx install --force .
	@echo "$(GREEN)✓ 'devtool' installé globalement. Testez avec : devtool --help$(RESET)"
	@echo "$(YELLOW)  Si la commande est introuvable, ajoutez ceci à votre ~/.bashrc :$(RESET)"
	@echo '      export PATH="$$HOME/.local/bin:$$PATH"'

# Alternative : installation en mode développement (pip install -e .) dans le venv
.PHONY: install-dev
install-dev: venv
	@echo "$(CYAN)→ Installation en mode éditable dans le venv (pip install -e .)...$(RESET)"
	$(PIP) install -e ".[test]"
	@echo "$(GREEN)✓ 'devtool' installé en mode développement dans le venv.$(RESET)"
	@echo "$(YELLOW)  Activez le venv pour utiliser la commande : source $(VENV)/bin/activate$(RESET)"

# Désinstalle 'devtool' de l'installation globale pipx
.PHONY: uninstall
uninstall:
	@echo "$(CYAN)→ Désinstallation de 'devtool'...$(RESET)"
	pipx uninstall $(PACKAGE) || pip3 uninstall -y $(PACKAGE)
	@echo "$(GREEN)✓ 'devtool' désinstallé.$(RESET)"

# ---------------------------------------------------------------------------
# Nettoyage
# ---------------------------------------------------------------------------

# Supprime le venv, les caches, les artefacts de build et les fichiers temporaires
.PHONY: clean
clean:
	@echo "$(CYAN)→ Suppression de l'environnement virtuel...$(RESET)"
	rm -rf $(VENV)
	@echo "$(CYAN)→ Suppression des caches Python...$(RESET)"
	find . -type d -name "__pycache__" -not -path "./.git/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -not -path "./.git/*" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -not -path "./.git/*" -delete 2>/dev/null || true
	@echo "$(CYAN)→ Suppression des artefacts de build...$(RESET)"
	rm -rf $(DIST_DIR)/ build/ *.egg-info/ src/*.egg-info/
	@echo "$(CYAN)→ Suppression des fichiers de couverture de test...$(RESET)"
	rm -rf .coverage htmlcov/ .pytest_cache/ .ruff_cache/
	@echo "$(GREEN)✓ Projet nettoyé.$(RESET)"

# ---------------------------------------------------------------------------
# Aide
# ---------------------------------------------------------------------------

# Affiche la liste des cibles disponibles et leur description
.PHONY: help
help:
	@echo ""
	@echo "$(BOLD)devtool — Cibles Makefile disponibles$(RESET)"
	@echo "─────────────────────────────────────────────"
	@echo "$(CYAN)Environnement :$(RESET)"
	@echo "  make venv           Crée l'environnement virtuel Python"
	@echo "  make install-deps   Installe toutes les dépendances (prod + test + lint)"
	@echo "  make shell          Lance un sous-shell avec le venv activé"
	@echo ""
	@echo "$(CYAN)Qualité du code :$(RESET)"
	@echo "  make lint           Vérifie le style (black, ruff, isort)"
	@echo "  make format         Applique le formatage automatique"
	@echo ""
	@echo "$(CYAN)Tests :$(RESET)"
	@echo "  make test           Lance la suite de tests (pytest)"
	@echo "  make test-cov       Lance les tests avec rapport de couverture"
	@echo ""
	@echo "$(CYAN)Build & Installation :$(RESET)"
	@echo "  make build          Construit le paquet Python (wheel + sdist)"
	@echo "  make install-local  Installe 'devtool' globalement via pipx"
	@echo "  make install-dev    Installe en mode développement dans le venv"
	@echo "  make uninstall      Désinstalle 'devtool' du système"
	@echo ""
	@echo "$(CYAN)Nettoyage :$(RESET)"
	@echo "  make clean          Supprime venv, caches et artefacts de build"
	@echo ""
