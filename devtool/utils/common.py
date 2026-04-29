"""Backward-compatible re-exports from split utility modules.

New code should import directly from the specific module:
  - devtool.utils.path_utils
  - devtool.utils.language_utils
  - devtool.utils.docgen_utils
"""

from .path_utils import _IGNORE_DIRS, _SOURCE_EXTENSIONS, collect_source_files

from .language_utils import LANGUAGE_MAPPING, detect_language_from_dir

from .docgen_utils import (
    DocType,
    DOC_TYPE_LABELS,
    ALL_DOC_TYPES,
    run_single_docgen,
)

__all__ = [
    "_IGNORE_DIRS",
    "_SOURCE_EXTENSIONS",
    "collect_source_files",
    "LANGUAGE_MAPPING",
    "detect_language_from_dir",
    "DocType",
    "DOC_TYPE_LABELS",
    "ALL_DOC_TYPES",
    "run_single_docgen",
]
