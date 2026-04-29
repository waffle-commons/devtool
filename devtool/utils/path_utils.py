"""File-system path utilities: collecting source files, ignore-dir logic."""

from pathlib import Path

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
        "__pycache__",
        "dist",
        "build",
    }
)

_SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py", ".php", ".cs", ".ts", ".js", ".java", ".kt", ".go",
        ".rb", ".rs", ".c", ".cpp", ".h", ".jsx", ".tsx", ".vue",
    }
)


def collect_source_files(root: Path) -> str:
    """Recursively collect source file contents from a directory, skipping binary/dependency dirs."""
    parts: list[str] = []
    for item in sorted(root.rglob("*")):
        if any(part in _IGNORE_DIRS for part in item.parts):
            continue
        if item.is_file() and item.suffix.lower() in _SOURCE_EXTENSIONS:
            try:
                content = item.read_text(errors="replace")
                parts.append(f"### File: {item}\n{content}")
            except Exception:
                pass
    return "\n\n".join(parts)
