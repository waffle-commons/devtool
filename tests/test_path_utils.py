"""Tests for devtool.utils.path_utils — ignore-dir matching and source collection.

Regression coverage for Tier-0 Task T0.3: the previous implementation matched
``_IGNORE_DIRS`` against absolute-path components, which caused every file
under macOS ``tmp_path`` (``/private/var/folders/...``) to be skipped because
the path contained the segment ``var``.
"""

from __future__ import annotations

from pathlib import Path

from devtool.utils.path_utils import _IGNORE_DIRS, collect_source_files, is_ignored_path

# ── is_ignored_path ──────────────────────────────────────────────────────────


class TestIsIgnoredPath:
    """Regression suite for absolute- vs relative-part matching."""

    def test_ignored_when_relative_part_matches(self, tmp_path: Path) -> None:
        """A directory component RELATIVE to root that is in _IGNORE_DIRS is ignored."""
        nested = tmp_path / "vendor" / "lib.py"
        assert is_ignored_path(nested, tmp_path) is True

    def test_not_ignored_when_match_only_in_absolute_prefix(
        self, tmp_path: Path
    ) -> None:
        """A match in the absolute prefix of *root* (e.g. ``/var/folders/...``)
        does NOT cause *path* to be skipped — only relative parts are inspected."""
        # tmp_path on macOS is /private/var/folders/.../pytest-N/... — its
        # absolute parts contain "var", which used to wrongly skip every file.
        leaf = tmp_path / "hello.py"
        assert is_ignored_path(leaf, tmp_path) is False

    def test_ignored_when_var_appears_inside_project_root(self, tmp_path: Path) -> None:
        """``var/cache`` inside the scanned project IS ignored (Symfony-style)."""
        nested = tmp_path / "var" / "cache" / "container.php"
        assert is_ignored_path(nested, tmp_path) is True

    def test_not_ignored_for_plain_source_path(self, tmp_path: Path) -> None:
        nested = tmp_path / "src" / "module" / "main.py"
        assert is_ignored_path(nested, tmp_path) is False

    def test_dotvenv_and_devtool_are_in_ignore_set(self) -> None:
        """Sanity: the consolidated ignore set contains the items previously
        kept only inside ``rag_service`` (``venv``, ``.devtool``)."""
        assert "venv" in _IGNORE_DIRS
        assert ".devtool" in _IGNORE_DIRS
        assert ".venv" in _IGNORE_DIRS

    def test_path_outside_root_falls_back_to_absolute_parts(
        self, tmp_path: Path
    ) -> None:
        """If *path* is not under *root*, fall back to inspecting its own parts."""
        other = Path("/some/other/vendor/lib.py")
        assert is_ignored_path(other, tmp_path) is True


# ── collect_source_files ─────────────────────────────────────────────────────


class TestCollectSourceFiles:
    def test_collects_python_file_in_tmp_path(self, tmp_path: Path) -> None:
        """Smoke test: a .py file under tmp_path is reachable (regression for T0.3)."""
        (tmp_path / "hello.py").write_text("print('hi')")

        output = collect_source_files(tmp_path)

        assert "hello.py" in output
        assert "print('hi')" in output

    def test_skips_vendor_subdirectory(self, tmp_path: Path) -> None:
        (tmp_path / "src.py").write_text("ok = True")
        vendor = tmp_path / "vendor"
        vendor.mkdir()
        (vendor / "lib.py").write_text("vendored = True")

        output = collect_source_files(tmp_path)

        assert "src.py" in output
        assert "vendored = True" not in output
