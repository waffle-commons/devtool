import subprocess
from typing import Optional

# Maximum characters allowed for a diff chunk before we warn the user
MAX_DIFF_LENGTH = 15000


def has_staged_changes() -> bool:
    """Check if there are any staged files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], capture_output=True, text=True
        )
        return result.returncode == 1
    except subprocess.SubprocessError:
        return False


def get_staged_diff() -> Optional[str]:
    """Retrieve the staged diff."""
    try:
        result = subprocess.run(
            ["git", "diff", "--staged"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.SubprocessError:
        return None


def stage_all() -> bool:
    """Run ``git add .`` to stage all changes."""
    try:
        subprocess.run(["git", "add", "."], check=True)
        return True
    except subprocess.SubprocessError:
        return False


def apply_commit(message: str) -> bool:
    """Execute git commit with the given message."""
    try:
        subprocess.run(["git", "commit", "-m", message], check=True)
        return True
    except subprocess.SubprocessError:
        return False


def get_current_branch() -> Optional[str]:
    """Get the current checked out branch name."""
    try:
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except subprocess.SubprocessError:
        return None


def branch_exists(branch: str) -> bool:
    """Check if a local branch exists."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--verify", branch], capture_output=True
        )
        return res.returncode == 0
    except subprocess.SubprocessError:
        return False


def get_branch_diff(
    target_branch: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Retrieve the diff between the current branch and a target branch.
    If target_branch is None, intelligently infer the base branch.
    Returns (diff_output, resolved_target_branch)."""
    if not target_branch:
        current = get_current_branch()
        if current in ("main", "master"):
            target_branch = "HEAD"
        else:
            if branch_exists("main"):
                target_branch = "main"
            elif branch_exists("master"):
                target_branch = "master"
            else:
                return None, None

    try:
        if target_branch == "HEAD":
            result = subprocess.run(
                ["git", "diff", "HEAD"], capture_output=True, text=True, check=True
            )
            return result.stdout.strip(), "HEAD"

        rev_check = subprocess.run(
            ["git", "rev-parse", "--verify", target_branch], capture_output=True
        )
        if rev_check.returncode != 0:
            return None, target_branch

        result = subprocess.run(
            ["git", "diff", f"{target_branch}...HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip(), target_branch
    except subprocess.SubprocessError:
        return None, target_branch


def is_diff_massive(diff: str) -> bool:
    """Detect if a diff is too large for standard LLM context windows."""
    return len(diff) > MAX_DIFF_LENGTH


def truncate_diff(diff: str, limit: int = MAX_DIFF_LENGTH) -> tuple[str, bool]:
    """Truncate a diff to `limit` characters. Returns (diff, was_truncated)."""
    if len(diff) <= limit:
        return diff, False
    return (
        diff[:limit]
        + "\n\n... [Diff truncated for length. Use a smaller diff or increase MAX_DIFF_LENGTH.]",
        True,
    )


def get_modified_files() -> list[str]:
    """Retrieve a list of uniquely modified and staged files."""
    try:
        diff_res = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = diff_res.stdout.strip().splitlines()
        return list(set([f for f in files if f]))
    except subprocess.SubprocessError:
        return []
