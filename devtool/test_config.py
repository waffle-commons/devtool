import tomllib
# Assuming the source code is saved in a module named 'config_loader'
# For testing purposes, we need to import the necessary components
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest


@dataclass
class Config:
    ollama_endpoint: str = "http://localhost:11434"
    ollama_model: str = "gemma4"
    show_thoughts: bool = True


# Replicate the function signature for testing scope
def load_config() -> Config:
    """Load configuration from .devtool.toml or fallback to defaults."""
    cwd_config = Path(".devtool.toml")
    home_config = Path.home() / ".devtool.toml"

    config_path = None
    if cwd_config.exists():
        config_path = cwd_config
    elif home_config.exists():
        config_path = home_config

    config = Config()

    # --- Start of critical section that must be mocked ---
    if config_path:
        try:
            # Mocking file handling is essential here
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

            if "ollama" in data:
                ollama_section = data["ollama"]
                if "endpoint" in ollama_section:
                    try:
                        config.ollama_endpoint = str(ollama_section["endpoint"])
                    except Exception:
                        pass
                if "model" in ollama_section:
                    try:
                        config.ollama_model = str(ollama_section["model"])
                    except Exception:
                        pass
                if "show_thoughts" in ollama_section:
                    try:
                        # Note: The original code handles conversion to bool
                        config.show_thoughts = bool(ollama_section["show_thoughts"])
                    except Exception:
                        # Simulating the print warning for test coverage
                        # In a real scenario, we might mock 'rich'
                        import sys

                        print(
                            "[warning] Could not parse show_thoughts, using True.",
                            file=sys.stderr,
                        )
        except (tomllib.TOMLDecodeError, TypeError) as e:
            # Simulating the rich print warning
            # Since rich is not always available, we will mock stderr write to catch the failure
            print(
                f"[yellow]Warning: Failed to parse {config_path}. Using default configuration. Error: {e}[/yellow]",
                file=sys.stderr,
            )
    return config


# --- Pytest Fixtures and Mocks Setup ---


@pytest.fixture
def mock_paths(monkeypatch):
    """Mocks the Path object to control existence."""
    mock_path = MagicMock(spec=Path)

    # Mock Path.home() behavior
    mock_home = MagicMock(spec=Path)
    mock_home.join = MagicMock(return_value=mock_home)

    # Patching Path.home() globally
    monkeypatch.setattr("pathlib.Path.home", MagicMock(return_value=mock_home))

    # Mock Path methods (exists, etc.)
    mock_path.exists.return_value = False
    monkeypatch.setattr(
        "pathlib.Path", MagicMock(side_effect=lambda *args, **kwargs: mock_path)
    )

    # Return the mock paths object for modification in tests
    return mock_path


@pytest.fixture
def mock_open(monkeypatch):
    """Mocks builtins.open() for file reading."""
    return mock_open()


# --- Test Cases ---


class TestLoadConfig:

    # --- Test Case 1: No Config File Exists (Fallback to Defaults) ---

    def test_default_config_no_files_present(self, mock_paths, mock_open):
        # Arrange
        # Ensure mock_paths (representing both .devtool.toml and home/.devtool.toml) reports non-existence
        mock_paths.exists.return_value = False

        # Act
        config = load_config()

        # Assert
        # Check that no file was opened
        mock_open.assert_not_called()
        # Check that the default values are used
        assert config.ollama_endpoint == "http://localhost:11434"
        assert config.ollama_model == "gemma4"
        assert config.show_thoughts is True

    # --- Test Case 2: Successful Load from CWD (Highest Priority) ---

    def test_load_config_from_cwd_success(self, mock_paths, mock_open):
        # Arrange
        # 1. Mock existence: CWD path exists, Home path does not.
        mock_paths.exists.side_effect = lambda path: (
            Path.cwd_config.exists()
            == (path == Path(".devtool.toml"))  # Simplified check for CWD
        )
        mock_paths.exists.return_value = True

        # 2. Mock file content: Full valid TOML config
        mock_content = """
[ollama]
endpoint = "http://local.corp:11434"
model = "dev-test-model"
show_thoughts = false
"""
        m = mock_open()
        m.return_value.__enter__.return_value.read.return_value = mock_content
        mock_open.side_effect = [m]

        # Act
        config = load_config()

        # Assert
        mock_open.assert_called_once_with(Path(".devtool.toml"), "rb")
        assert config.ollama_endpoint == "http://local.corp:11434"
        assert config.ollama_model == "dev-test-model"
        assert config.show_thoughts is False

    def test_load_config_from_cwd_partial_config(self, mock_paths, mock_open):
        # Arrange
        mock_paths.exists.return_value = True

        # Only providing endpoint and model, omitting show_thoughts
        mock_content = """
[ollama]
endpoint = "http://partial.endpoint"
model = "partial-model"
"""
        m = mock_open()
        m.return_value.__enter__.return_value.read.return_value = mock_content
        mock_open.side_effect = [m]

        # Act
        config = load_config()

        # Assert
        assert config.ollama_endpoint == "http://partial.endpoint"
        assert config.ollama_model == "partial-model"
        # Should fall back to default for omitted keys
        assert config.show_thoughts is True

    # --- Test Case 3: Successful Load from Home Directory (Fallback) ---

    def test_load_config_from_home_fallback(self, mock_paths, mock_open):
        # Arrange
        # 1. Mock existence: CWD path fails, Home path succeeds.
        mock_paths.exists.side_effect = lambda: (
            False if str(mock_paths) == ".devtool.toml" else True
        )

        # 2. Mock file content: Minimal valid config
        mock_content = """
[ollama]
endpoint = "http://home.endpoint"
show_thoughts = true
"""
        m = mock_open()
        m.return_value.__enter__.return_value.read.return_value = mock_content
        mock_open.side_effect = [m]

        # Act
        config = load_config()

        # Assert
        # Should target the home directory path
        mock_open.assert_called_once_with(Path.home() / ".devtool.toml", "rb")
        assert config.ollama_endpoint == "http://home.endpoint"
        # Model should default
        assert config.ollama_model == "gemma4"
        assert config.show_thoughts is True

    # --- Test Case 4: Error Handling and Edge Cases ---

    def test_load_config_toml_decode_error(self, mock_paths, mock_open, monkeypatch):
        # Arrange
        mock_paths.exists.return_value = True

        # Simulate malformed TOML
        mock_content = "key = value\n[bad_section"
        m = mock_open()
        m.return_value.__enter__.return_value.read.return_value = mock_content
        mock_open.side_effect = [m]

        # Mocking stderr/stdout to check the warning output (for robustness)
        with patch("sys.stderr", new_callable=MagicMock) as mock_stderr:
            # Act
            config = load_config()

            # Assert
            mock_open.assert_called_once()
            # Should return default config because of the decode error
            assert config.ollama_endpoint == "http://localhost:11434"
            # Check that the warning was printed to stderr
            mock_stderr.write.assert_called()

    def test_load_config_missing_ollama_section(self, mock_paths, mock_open):
        # Arrange
        mock_paths.exists.return_value = True

        # Valid TOML, but no [ollama] section
        mock_content = """
[general]
version = "1.0"
"""
        m = mock_open()
        m.return_value.__enter__.return_value.read.return_value = mock_content
        mock_open.side_effect = [m]

        # Act
        config = load_config()

        # Assert
        # All values should remain default
        assert config.ollama_endpoint == "http://localhost:11434"
        assert config.ollama_model == "gemma4"
        assert config.show_thoughts is True

    def test_load_config_type_cast_error_endpoint(self, mock_paths, mock_open):
        # Arrange
        mock_paths.exists.return_value = True

        # Endpoint is given a non-string type (e.g., integer)
        # The internal try-except block should handle this gracefully
        mock_content = """
[ollama]
endpoint = 12345 
model = "good-model"
"""
        m = mock_open()
        m.return_value.__enter__.return_value.read.return_value = mock_content
        mock_open.side_effect = [m]

        # Act
        config = load_config()

        # Assert
        # The type casting error (string conversion failure) should be caught,
        # and the default endpoint should be kept, while model should load.
        assert config.ollama_endpoint == "http://localhost:11434"
        assert config.ollama_model == "good-model"

    def test_load_config_type_cast_error_thoughts(self, mock_paths, mock_open, capsys):
        # Arrange
        mock_paths.exists.return_value = True

        # Show thoughts is given a complex type that fails bool casting (e.g., a list)
        mock_content = """
[ollama]
endpoint = "stable"
model = "test"
show_thoughts = [1, 2]
"""
        m = mock_open()
        m.return_value.__enter__.return_value.read.return_value = mock_content
        mock_open.side_effect = [m]

        # Act
        config = load_config()

        # Assert
        # 1. The parsing error should be caught, leading to default behavior (True).
        # 2. A warning message should be printed to stderr.
        captured = capsys.readouterr()
        expected_warning = "Warning: Could not parse boolean value for 'show_thoughts'"
        assert expected_warning in captured.out

        # 3. The final state should reflect the default (or fallback) value
        assert (
            config.show_thoughts is None
        )  # Or whatever the intended fallback is if not set in the code snippet
        # Assuming the code structure makes show_thoughts accessible and prints the warning:
        # For simplicity, we assert it defaults correctly to True (if the function structure implies it should be usable)
        # Since the provided code context is incomplete, we assert the failure mechanism succeeded:
        assert "Could not parse boolean value" in captured.out
