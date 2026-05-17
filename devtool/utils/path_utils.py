"""File-system path utilities: collecting source files, ignore-dir logic.

This module is the single source of truth for the ``_IGNORE_DIRS`` set and
the helper used to decide whether a path lives inside an ignored directory.
``rag_service`` and ``repo_analysis`` import from here instead of redefining
the set locally.
"""

from pathlib import Path

# Directory *names* (not paths) that should be skipped during traversal.
# Names are matched against directory components RELATIVE TO the scan root —
# absolute-path components are never inspected, so a benign macOS temp path
# such as ``/private/var/folders/...`` is NOT skipped just because it
# contains a "var" segment.
_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        "vendor",
        "node_modules",
        ".git",
        "bin",
        "obj",
        "var",
        "cache",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".devtool",
    }
)

_SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".php",
        ".cs",
        ".ts",
        ".js",
        ".java",
        ".kt",
        ".go",
        ".rb",
        ".rs",
        ".c",
        ".cpp",
        ".h",
        ".jsx",
        ".tsx",
        ".vue",
    }
)


def is_ignored_path(path: Path, root: Path) -> bool:
    """Return True if *path* lives inside an ignored directory relative to *root*.

    The check inspects only the directory components BETWEEN ``root`` and
    ``path`` — components of ``root`` itself are out of scope. This makes the
    function robust against the scan root being placed inside a directory
    whose name happens to be in ``_IGNORE_DIRS`` (e.g. macOS tmp dirs under
    ``/private/var/folders/...``).
    """
    try:
        rel = path.relative_to(root)
    except ValueError:
        # *path* is not under *root* — fall back to the path's own parts.
        rel = path
    return any(part in _IGNORE_DIRS for part in rel.parts)


def collect_source_files(root: Path) -> str:
    """Recursively collect source file contents from a directory, skipping binary/dependency dirs."""
    parts: list[str] = []
    for item in sorted(root.rglob("*")):
        if is_ignored_path(item, root):
            continue
        if item.is_file() and item.suffix.lower() in _SOURCE_EXTENSIONS:
            try:
                content = item.read_text(errors="replace")
                parts.append(f"### File: {item}\n{content}")
            except Exception:
                pass
    return "\n\n".join(parts)
