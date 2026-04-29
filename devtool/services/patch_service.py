"""PatchService — parses structured SEARCH/REPLACE blocks from LLM output
and applies them to local files.

The expected format from the LLM is:

    <<<< SEARCH file:path/to/file.py
    original code here
    ==== REPLACE
    replacement code here
    >>>>

Multiple blocks can appear in a single LLM response.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Patch:
    """A single SEARCH/REPLACE patch targeting a file."""

    file: str
    search: str
    replace: str
    applied: bool = False
    error: Optional[str] = None


@dataclass
class PatchSet:
    """Collection of patches parsed from a single LLM response."""

    patches: list[Patch] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.patches)

    @property
    def applied_count(self) -> int:
        return sum(1 for p in self.patches if p.applied)


# ── Parser ───────────────────────────────────────────────────────────────────

_BLOCK_RE = re.compile(
    r"<{4}\s*SEARCH\s+file:(.+?)\n"   # <<<< SEARCH file:path/to/file.py
    r"(.*?)\n"                          # original code (search block)
    r"={4}\s*REPLACE\n"                # ==== REPLACE
    r"(.*?)\n"                          # replacement code
    r">{4}",                            # >>>>
    re.DOTALL,
)


def parse_patches(llm_output: str) -> PatchSet:
    """Extract all SEARCH/REPLACE blocks from raw LLM text.

    Returns a PatchSet even if no blocks are found (empty patches list).
    """
    patches: list[Patch] = []
    for match in _BLOCK_RE.finditer(llm_output):
        filepath = match.group(1).strip()
        search = match.group(2)
        replace = match.group(3)
        patches.append(Patch(file=filepath, search=search, replace=replace))
    return PatchSet(patches=patches)


# ── Applier ──────────────────────────────────────────────────────────────────


def apply_patch(patch: Patch, base_dir: Path | None = None) -> Patch:
    """Apply a single Patch to the filesystem.

    Modifies *patch* in-place: sets ``applied=True`` on success or
    ``error`` with a human-readable message on failure.
    """
    target = Path(patch.file)
    if base_dir:
        target = base_dir / target

    if not target.exists():
        patch.error = f"File not found: {target}"
        return patch

    try:
        content = target.read_text(encoding="utf-8")
    except Exception as e:
        patch.error = f"Cannot read {target}: {e}"
        return patch

    if patch.search not in content:
        # Try with normalized whitespace (strip trailing spaces per line)
        normalized_content = "\n".join(l.rstrip() for l in content.splitlines())
        normalized_search = "\n".join(l.rstrip() for l in patch.search.splitlines())
        if normalized_search in normalized_content:
            # Apply on normalized then write back
            new_content = normalized_content.replace(normalized_search, patch.replace, 1)
        else:
            patch.error = f"SEARCH block not found in {target} (content may have changed)"
            return patch
    else:
        new_content = content.replace(patch.search, patch.replace, 1)

    try:
        target.write_text(new_content, encoding="utf-8")
        patch.applied = True
    except Exception as e:
        patch.error = f"Cannot write {target}: {e}"

    return patch
