"""Tests for devtool.services.patch_service — SEARCH/REPLACE parser and applier."""

import pytest

from devtool.services.patch_service import Patch, PatchSet, apply_patch, parse_patches


# ── parse_patches ────────────────────────────────────────────────────────────


class TestParsePatchesSingle:
    def test_single_block(self):
        text = """Some review text.

<<<< SEARCH file:src/auth.py
password = request.GET['pw']
==== REPLACE
password = request.POST.get('pw', '')
>>>>

More commentary."""
        ps = parse_patches(text)
        assert ps.total == 1
        assert ps.patches[0].file == "src/auth.py"
        assert "request.GET" in ps.patches[0].search
        assert "request.POST" in ps.patches[0].replace

    def test_multiple_blocks(self):
        text = """
<<<< SEARCH file:a.py
old_a
==== REPLACE
new_a
>>>>

<<<< SEARCH file:b.py
old_b
==== REPLACE
new_b
>>>>
"""
        ps = parse_patches(text)
        assert ps.total == 2
        assert ps.patches[0].file == "a.py"
        assert ps.patches[1].file == "b.py"

    def test_no_blocks(self):
        ps = parse_patches("Just plain review text with no patches.")
        assert ps.total == 0

    def test_multiline_search_replace(self):
        text = """
<<<< SEARCH file:foo.py
def old():
    return 1
==== REPLACE
def new():
    return 2
>>>>
"""
        ps = parse_patches(text)
        assert ps.total == 1
        assert "def old():" in ps.patches[0].search
        assert "def new():" in ps.patches[0].replace


class TestPatchSet:
    def test_applied_count(self):
        ps = PatchSet(patches=[
            Patch(file="a.py", search="x", replace="y", applied=True),
            Patch(file="b.py", search="x", replace="y", applied=False),
        ])
        assert ps.applied_count == 1
        assert ps.total == 2


# ── apply_patch ──────────────────────────────────────────────────────────────


class TestApplyPatch:
    def test_successful_apply(self, tmp_path):
        target = tmp_path / "code.py"
        target.write_text("x = 1\ny = 2\n")

        patch = Patch(file="code.py", search="x = 1", replace="x = 42")
        result = apply_patch(patch, base_dir=tmp_path)

        assert result.applied is True
        assert result.error is None
        assert "x = 42" in target.read_text()
        assert "y = 2" in target.read_text()

    def test_file_not_found(self, tmp_path):
        patch = Patch(file="missing.py", search="x", replace="y")
        result = apply_patch(patch, base_dir=tmp_path)

        assert result.applied is False
        assert "not found" in result.error.lower()

    def test_search_not_found(self, tmp_path):
        target = tmp_path / "code.py"
        target.write_text("a = 1\n")

        patch = Patch(file="code.py", search="NONEXISTENT", replace="y")
        result = apply_patch(patch, base_dir=tmp_path)

        assert result.applied is False
        assert "not found" in result.error.lower()

    def test_whitespace_normalization(self, tmp_path):
        target = tmp_path / "code.py"
        target.write_text("x = 1   \ny = 2  \n")  # trailing spaces

        patch = Patch(file="code.py", search="x = 1\ny = 2", replace="x = 42\ny = 99")
        result = apply_patch(patch, base_dir=tmp_path)

        assert result.applied is True
        content = target.read_text()
        assert "x = 42" in content

    def test_only_replaces_first_occurrence(self, tmp_path):
        target = tmp_path / "code.py"
        target.write_text("x = 1\nx = 1\n")

        patch = Patch(file="code.py", search="x = 1", replace="x = 2")
        result = apply_patch(patch, base_dir=tmp_path)

        assert result.applied is True
        content = target.read_text()
        assert content.count("x = 2") == 1
        assert content.count("x = 1") == 1
