"""Tests for devtool.utils.git_utils — Git operations and diff utilities."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

# Mark entire module as slow tests
pytestmark = pytest.mark.slow

from devtool.utils.git_utils import (  # noqa: E402
    MAX_DIFF_LENGTH,
    apply_commit,
    branch_exists,
    get_branch_diff,
    get_current_branch,
    get_modified_files,
    get_staged_diff,
    has_staged_changes,
    is_diff_massive,
    stage_all,
    truncate_diff,
)

# ── has_staged_changes() ──────────────────────────────────────────────────────


class TestHasStagedChanges:
    """Tests for has_staged_changes() function."""

    def test_returns_true_when_returncode_is_1(self, mocker) -> None:
        """Return True when git diff --cached --quiet returns code 1 (changes exist)."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(returncode=1)

        result = has_staged_changes()

        assert result is True
        mock_run.assert_called_once_with(
            ["git", "diff", "--cached", "--quiet", "--"],
            capture_output=True,
            text=True,
        )

    def test_returns_false_when_returncode_is_0(self, mocker) -> None:
        """Return False when git diff --cached --quiet returns code 0 (no changes)."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(returncode=0)

        result = has_staged_changes()

        assert result is False

    def test_returns_false_on_subprocess_error(self, mocker) -> None:
        """Return False when subprocess.SubprocessError is raised."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        result = has_staged_changes()

        assert result is False


# ── get_staged_diff() ─────────────────────────────────────────────────────────


class TestGetStagedDiff:
    """Tests for get_staged_diff() function."""

    def test_returns_stripped_diff_on_success(self, mocker) -> None:
        """Return stdout stripped of whitespace when command succeeds."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(
            stdout="  diff --git a/foo.py\n+print('hello')\n  "
        )

        result = get_staged_diff()

        assert result == "diff --git a/foo.py\n+print('hello')"
        mock_run.assert_called_once_with(
            ["git", "diff", "--staged", "--"],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_returns_none_on_subprocess_error(self, mocker) -> None:
        """Return None when subprocess.SubprocessError is raised."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        result = get_staged_diff()

        assert result is None

    def test_returns_empty_string_when_no_diff(self, mocker) -> None:
        """Return empty string when stdout is empty."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(stdout="")

        result = get_staged_diff()

        assert result == ""


# ── stage_all() ───────────────────────────────────────────────────────────────


class TestStageAll:
    """Tests for stage_all() function."""

    def test_returns_true_on_success(self, mocker) -> None:
        """Return True when git add . succeeds."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock()

        result = stage_all()

        assert result is True
        mock_run.assert_called_once_with(["git", "add", "."], check=True)

    def test_returns_false_on_subprocess_error(self, mocker) -> None:
        """Return False when subprocess.SubprocessError is raised."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        result = stage_all()

        assert result is False


# ── apply_commit() ────────────────────────────────────────────────────────────


class TestApplyCommit:
    """Tests for apply_commit() function."""

    def test_returns_true_on_successful_commit(self, mocker) -> None:
        """Return True when git commit succeeds."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock()

        result = apply_commit("feat: add feature")

        assert result is True
        mock_run.assert_called_once_with(
            ["git", "commit", "-m", "feat: add feature"], check=True
        )

    def test_returns_false_on_subprocess_error(self, mocker) -> None:
        """Return False when subprocess.SubprocessError is raised."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        result = apply_commit("feat: test")

        assert result is False

    def test_passes_message_correctly(self, mocker) -> None:
        """Pass the message argument to git commit -m."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock()

        apply_commit("fix: resolve bug #123")

        mock_run.assert_called_once_with(
            ["git", "commit", "-m", "fix: resolve bug #123"], check=True
        )


# ── get_current_branch() ──────────────────────────────────────────────────────


class TestGetCurrentBranch:
    """Tests for get_current_branch() function."""

    def test_returns_stripped_branch_name_on_success(self, mocker) -> None:
        """Return stdout stripped of whitespace when command succeeds."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(stdout="  feature/xyz\n  ")

        result = get_current_branch()

        assert result == "feature/xyz"
        mock_run.assert_called_once_with(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_returns_none_on_subprocess_error(self, mocker) -> None:
        """Return None when subprocess.SubprocessError is raised."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        result = get_current_branch()

        assert result is None

    def test_returns_master_branch_name(self, mocker) -> None:
        """Return master when on master branch."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(stdout="master")

        result = get_current_branch()

        assert result == "master"


# ── branch_exists() ───────────────────────────────────────────────────────────


class TestBranchExists:
    """Tests for branch_exists() function."""

    def test_returns_true_when_branch_exists(self, mocker) -> None:
        """Return True when rev-parse returns 0 (branch exists)."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(returncode=0)

        result = branch_exists("main")

        assert result is True
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--verify", "main"], capture_output=True
        )

    def test_returns_false_when_branch_does_not_exist(self, mocker) -> None:
        """Return False when rev-parse returns non-zero."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(returncode=1)

        result = branch_exists("nonexistent-branch")

        assert result is False

    def test_returns_false_on_subprocess_error(self, mocker) -> None:
        """Return False when subprocess.SubprocessError is raised."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        result = branch_exists("some-branch")

        assert result is False


# ── get_branch_diff() ─────────────────────────────────────────────────────────


class TestGetBranchDiff:
    """Tests for get_branch_diff() function."""

    def test_uses_head_when_on_main_branch(self, mocker) -> None:
        """Use HEAD as target when current branch is main."""
        mocker.patch("devtool.utils.git_utils.get_current_branch", return_value="main")
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(stdout="diff content\n")

        diff, target = get_branch_diff()

        assert target == "HEAD"
        assert diff == "diff content"
        mock_run.assert_called_once_with(
            ["git", "diff", "HEAD", "--"], capture_output=True, text=True, check=True
        )

    def test_uses_head_when_on_master_branch(self, mocker) -> None:
        """Use HEAD as target when current branch is master."""
        mocker.patch(
            "devtool.utils.git_utils.get_current_branch", return_value="master"
        )
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(stdout="diff content\n")

        diff, target = get_branch_diff()

        assert target == "HEAD"
        assert diff == "diff content"

    def test_uses_main_when_main_exists_and_on_feature_branch(self, mocker) -> None:
        """Use main as target when on feature branch and main exists."""
        mocker.patch(
            "devtool.utils.git_utils.get_current_branch", return_value="feature/test"
        )
        mocker.patch(
            "devtool.utils.git_utils.branch_exists",
            side_effect=lambda b: b == "main",
        )
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.side_effect = [
            MagicMock(returncode=0),  # rev-parse for main
            MagicMock(stdout="diff content\n"),  # git diff
        ]

        diff, target = get_branch_diff()

        assert target == "main"
        assert diff == "diff content"

    def test_uses_master_when_master_exists_and_main_does_not(self, mocker) -> None:
        """Use master as target when on feature branch, main doesn't exist, master does."""
        mocker.patch(
            "devtool.utils.git_utils.get_current_branch", return_value="feature/test"
        )
        mocker.patch(
            "devtool.utils.git_utils.branch_exists",
            side_effect=lambda b: b == "master",
        )
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.side_effect = [
            MagicMock(returncode=0),  # rev-parse for master
            MagicMock(stdout="diff content\n"),  # git diff
        ]

        diff, target = get_branch_diff()

        assert target == "master"
        assert diff == "diff content"

    def test_returns_none_none_when_neither_main_nor_master_exist(self, mocker) -> None:
        """Return (None, None) when on feature branch and neither main nor master exist."""
        mocker.patch(
            "devtool.utils.git_utils.get_current_branch", return_value="feature/test"
        )
        mocker.patch("devtool.utils.git_utils.branch_exists", return_value=False)

        diff, target = get_branch_diff()

        assert diff is None
        assert target is None

    def test_uses_explicit_target_branch(self, mocker) -> None:
        """Use provided target_branch argument."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.side_effect = [
            MagicMock(returncode=0),  # rev-parse for develop
            MagicMock(stdout="diff content\n"),  # git diff
        ]

        diff, target = get_branch_diff(target_branch="develop")

        assert target == "develop"
        assert diff == "diff content"
        # Should call rev-parse and then diff
        assert mock_run.call_count == 2

    def test_returns_none_diff_when_explicit_target_branch_invalid(
        self, mocker
    ) -> None:
        """Return (None, target_branch) when explicit target_branch doesn't exist."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(returncode=1)  # rev-parse fails

        diff, target = get_branch_diff(target_branch="invalid-branch")

        assert diff is None
        assert target == "invalid-branch"

    def test_returns_head_diff_directly(self, mocker) -> None:
        """Return diff directly when target_branch is HEAD."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(stdout="diff content\n")

        diff, target = get_branch_diff(target_branch="HEAD")

        assert target == "HEAD"
        assert diff == "diff content"
        mock_run.assert_called_once_with(
            ["git", "diff", "HEAD", "--"], capture_output=True, text=True, check=True
        )

    def test_returns_none_diff_on_subprocess_error_during_diff(self, mocker) -> None:
        """Return (None, target_branch) when diff command raises SubprocessError."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.side_effect = [
            MagicMock(returncode=0),  # rev-parse succeeds
            subprocess.CalledProcessError(1, "git"),  # git diff fails
        ]

        diff, target = get_branch_diff(target_branch="develop")

        assert diff is None
        assert target == "develop"

    def test_uses_three_dot_syntax_for_non_head_target(self, mocker) -> None:
        """Use three-dot syntax (target...HEAD) for diff against non-HEAD target."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.side_effect = [
            MagicMock(returncode=0),  # rev-parse for develop
            MagicMock(stdout="diff content\n"),  # git diff
        ]

        diff, target = get_branch_diff(target_branch="develop")

        # Check that the diff command uses three-dot syntax
        calls = mock_run.call_args_list
        diff_call = calls[1]
        assert "develop...HEAD" in diff_call[0][0]


# ── is_diff_massive() ─────────────────────────────────────────────────────────


class TestIsDiffMassive:
    """Tests for is_diff_massive() function."""

    def test_returns_false_for_small_diff(self) -> None:
        """Return False when diff is under MAX_DIFF_LENGTH."""
        small_diff = "a" * (MAX_DIFF_LENGTH - 100)
        result = is_diff_massive(small_diff)
        assert result is False

    def test_returns_false_for_diff_at_limit(self) -> None:
        """Return False when diff is exactly at MAX_DIFF_LENGTH."""
        exact_diff = "a" * MAX_DIFF_LENGTH
        result = is_diff_massive(exact_diff)
        assert result is False

    def test_returns_true_for_large_diff(self) -> None:
        """Return True when diff exceeds MAX_DIFF_LENGTH."""
        large_diff = "a" * (MAX_DIFF_LENGTH + 1)
        result = is_diff_massive(large_diff)
        assert result is True

    def test_returns_true_for_much_larger_diff(self) -> None:
        """Return True for diff much larger than limit."""
        very_large_diff = "x" * (MAX_DIFF_LENGTH * 2)
        result = is_diff_massive(very_large_diff)
        assert result is True

    def test_returns_false_for_empty_diff(self) -> None:
        """Return False for empty diff."""
        result = is_diff_massive("")
        assert result is False


# ── truncate_diff() ───────────────────────────────────────────────────────────


class TestTruncateDiff:
    """Tests for truncate_diff() function."""

    def test_returns_unchanged_diff_and_false_when_under_limit(self) -> None:
        """Return (diff, False) when diff is under limit."""
        short_diff = "diff content"
        result, was_truncated = truncate_diff(short_diff, limit=100)

        assert result == "diff content"
        assert was_truncated is False

    def test_returns_truncated_diff_and_true_when_over_limit(self) -> None:
        """Return (truncated_diff + suffix, True) when diff exceeds limit."""
        long_diff = "a" * 200
        limit = 100
        result, was_truncated = truncate_diff(long_diff, limit=limit)

        assert was_truncated is True
        assert len(result) > limit
        assert "... [Diff truncated for length" in result

    def test_respects_custom_limit_parameter(self) -> None:
        """Respect custom limit parameter instead of MAX_DIFF_LENGTH."""
        diff = "x" * 100
        custom_limit = 50
        result, was_truncated = truncate_diff(diff, limit=custom_limit)

        assert was_truncated is True
        assert len(result[:custom_limit]) == custom_limit

    def test_uses_default_limit_when_not_specified(self) -> None:
        """Use MAX_DIFF_LENGTH as default limit when not specified."""
        short_diff = "a" * (MAX_DIFF_LENGTH - 100)
        result, was_truncated = truncate_diff(short_diff)

        assert was_truncated is False
        assert result == short_diff

    def test_truncates_with_default_limit(self) -> None:
        """Truncate using MAX_DIFF_LENGTH when no limit specified."""
        long_diff = "b" * (MAX_DIFF_LENGTH + 100)
        result, was_truncated = truncate_diff(long_diff)

        assert was_truncated is True
        assert "... [Diff truncated for length" in result

    def test_truncation_message_included(self) -> None:
        """Include truncation message in truncated output."""
        long_diff = "c" * 200
        limit = 50
        result, was_truncated = truncate_diff(long_diff, limit=limit)

        assert "truncated" in result.lower()
        assert "length" in result.lower()

    def test_exact_limit_boundary(self) -> None:
        """Handle diff exactly at limit boundary."""
        diff = "d" * 100
        limit = 100
        result, was_truncated = truncate_diff(diff, limit=limit)

        assert was_truncated is False
        assert result == diff


# ── get_modified_files() ──────────────────────────────────────────────────────


class TestGetModifiedFiles:
    """Tests for get_modified_files() function."""

    def test_returns_list_of_files_on_success(self, mocker) -> None:
        """Return deduplicated list of modified files on success."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(
            stdout="src/main.py\ntest/test_main.py\nsrc/main.py\n"
        )

        result = get_modified_files()

        assert len(result) == 2
        assert "src/main.py" in result
        assert "test/test_main.py" in result
        mock_run.assert_called_once_with(
            ["git", "diff", "--name-only", "HEAD", "--"],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_returns_empty_list_when_no_files_modified(self, mocker) -> None:
        """Return empty list when stdout is empty."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(stdout="")

        result = get_modified_files()

        assert result == []

    def test_returns_empty_list_on_subprocess_error(self, mocker) -> None:
        """Return empty list when subprocess.SubprocessError is raised."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        result = get_modified_files()

        assert result == []

    def test_filters_empty_lines(self, mocker) -> None:
        """Filter out empty lines from output."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(stdout="src/a.py\n\nsrc/b.py\n\n\nsrc/c.py")

        result = get_modified_files()

        assert len(result) == 3
        assert all(f for f in result)  # No empty strings

    def test_deduplicates_file_list(self, mocker) -> None:
        """Return deduplicated list (unique files only)."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(
            stdout="same.py\nsame.py\nsame.py\ndifferent.py\n"
        )

        result = get_modified_files()

        assert len(result) == 2
        assert result.count("same.py") == 1
        assert result.count("different.py") == 1

    def test_handles_single_file(self, mocker) -> None:
        """Return list with single file when only one modified."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(stdout="only.py")

        result = get_modified_files()

        assert result == ["only.py"]

    def test_preserves_file_paths_with_directories(self, mocker) -> None:
        """Preserve full file paths including directories."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(
            stdout="src/subdir/file.py\ntest/integration/test.py\n"
        )

        result = get_modified_files()

        assert len(result) == 2
        assert "src/subdir/file.py" in result
        assert "test/integration/test.py" in result


# ── Audit Vuln 1: Git argument-injection defense (`--` terminator) ───────────
#
# Reference: specs/Audits/AIT-ALPHA1-AUDIT.md §3 Vulnerability 1.
# Every `git diff` invocation MUST terminate with `--` so that a malicious
# user-controlled ref (e.g. `--compare="--no-index"`) is parsed as a ref/path,
# not as a Git flag.


class TestGitArgumentInjectionDefense:
    """Regression tests for audit Vuln 1: end-of-options `--` terminator."""

    def test_has_staged_changes_appends_double_dash(self, mocker) -> None:
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(returncode=1)

        has_staged_changes()

        cmd = mock_run.call_args[0][0]
        assert cmd[-1] == "--", f"`--` terminator missing from {cmd!r}"

    def test_get_staged_diff_appends_double_dash(self, mocker) -> None:
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(stdout="")

        get_staged_diff()

        cmd = mock_run.call_args[0][0]
        assert cmd[-1] == "--", f"`--` terminator missing from {cmd!r}"

    def test_get_branch_diff_head_path_appends_double_dash(self, mocker) -> None:
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(stdout="")

        get_branch_diff(target_branch="HEAD")

        cmd = mock_run.call_args[0][0]
        assert cmd[-1] == "--", f"`--` terminator missing from {cmd!r}"

    def test_get_branch_diff_user_supplied_ref_appends_double_dash(
        self, mocker
    ) -> None:
        """Primary audit Vuln 1 regression: `--compare=<ref>` path."""
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.side_effect = [
            MagicMock(returncode=0),  # rev-parse succeeds
            MagicMock(stdout="diff content\n"),  # git diff
        ]

        get_branch_diff(target_branch="develop")

        diff_call_cmd = mock_run.call_args_list[1][0][0]
        assert (
            diff_call_cmd[-1] == "--"
        ), f"`--` terminator missing from {diff_call_cmd!r}"
        # And the user-controlled ref must precede the terminator
        assert "develop...HEAD" in diff_call_cmd
        assert diff_call_cmd.index("develop...HEAD") < diff_call_cmd.index("--")

    def test_get_modified_files_appends_double_dash(self, mocker) -> None:
        mock_run = mocker.patch("devtool.utils.git_utils.subprocess.run")
        mock_run.return_value = MagicMock(stdout="")

        get_modified_files()

        cmd = mock_run.call_args[0][0]
        assert cmd[-1] == "--", f"`--` terminator missing from {cmd!r}"
