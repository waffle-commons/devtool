# =============================================================================
# Makefile — devtool CLI (Cross-platform: Linux/WSL & macOS)
# =============================================================================

# Variables
PYTHON := python3
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
PIPX := pipx

.PHONY: help dev test lint clean install-global uninstall-global

help:
	@echo "🚀 DevTool Makefile (macOS & Linux compatible)"
	@echo "--------------------------------------------------------"
	@echo "  make dev            : Crée le venv et installe les dépendances (locales)"
	@echo "  make test           : Lance les tests unitaires via pytest"
	@echo "  make lint           : Formate et vérifie le code (black, ruff, isort)"
	@echo "  make install-global : Installe l'outil globalement via pipx"
	@echo "  make uninstall-global: Désinstalle l'outil de pipx"
	@echo "  make clean          : Nettoie le cache, le venv et les fichiers temporaires"
	@echo "--------------------------------------------------------"

# Règle silencieuse pour créer l'environnement virtuel si inexistant
$(VENV)/bin/activate:
	@echo "📦 Création de l'environnement virtuel..."
	$(PYTHON) -m venv $(VENV)
	@echo "⬇️ Installation des dépendances via $(VENV_PYTHON) -m pip..."
	$(VENV_PYTHON) -m pip install --upgrade pip setuptools wheel
	$(VENV_PYTHON) -m pip install -e .
	$(VENV_PYTHON) -m pip install pytest pytest-mock ruff black isort
	@touch $(VENV)/bin/activate

dev: $(VENV)/bin/activate
	@echo "✅ Environnement de développement prêt. Activez-le avec : source $(VENV)/bin/activate"

test: dev
	@echo "🧪 Lancement des tests..."
	$(VENV_PYTHON) -m pytest tests/ -v

lint: dev
	@echo "🧹 Lancement du formattage et du linter..."
	$(VENV_PYTHON) -m isort devtool/ tests/
	$(VENV_PYTHON) -m black devtool/ tests/
	$(VENV_PYTHON) -m ruff check devtool/ tests/ --fix

install-global:
	@echo "🌍 Installation globale de devtool via pipx..."
	$(PIPX) install . --force
	@echo "✅ Installation terminée ! Tapez 'devtool' dans votre terminal."

uninstall-global:
	@echo "🗑️ Désinstallation globale..."
	$(PIPX) uninstall devtool

clean:
	@echo "🧼 Nettoyage du projet..."
	rm -rf $(VENV)
	rm -rf .pytest_cache .ruff_cache devtool.egg-info build dist
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".DS_Store" -delete
	@echo "✨ Projet nettoyé."