"""AST-aware semantic chunking using tree-sitter for Python, PHP, and C#.

This module parses source code into an Abstract Syntax Tree (AST) and extracts
logical chunks by class/method/function definitions, preserving semantic structure.
For unsupported languages, falls back to naive character-based chunking.
"""

from pathlib import Path
from typing import Optional

from tree_sitter import Language, Node, Parser

try:
    import tree_sitter_python as tspython
except ImportError:
    tspython = None  # type: ignore

try:
    import tree_sitter_php as tsphp
except ImportError:
    tsphp = None  # type: ignore

try:
    import tree_sitter_c_sharp as tscsharp
except ImportError:
    tscsharp = None  # type: ignore

# Constants
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Language parsers (lazy-initialized)
_py_parser: Optional[Parser] = None
_php_parser: Optional[Parser] = None
_cs_parser: Optional[Parser] = None


def _get_py_parser() -> Optional[Parser]:
    """Get or initialize Python parser."""
    global _py_parser
    if _py_parser is None and tspython is not None:
        _py_parser = Parser()
        _py_parser.language = Language(tspython.language())
    return _py_parser


def _get_php_parser() -> Optional[Parser]:
    """Get or initialize PHP parser."""
    global _php_parser
    if _php_parser is None and tsphp is not None:
        _php_parser = Parser()
        _php_parser.language = Language(tsphp.language_php())
    return _php_parser


def _get_cs_parser() -> Optional[Parser]:
    """Get or initialize C# parser."""
    global _cs_parser
    if _cs_parser is None and tscsharp is not None:
        _cs_parser = Parser()
        _cs_parser.language = Language(tscsharp.language())
    return _cs_parser


def _get_node_text(node: Node, source: bytes) -> str:
    """Extract node text from source bytes."""
    return source[node.start_byte : node.end_byte].decode("utf8", errors="replace")


def _chunk_text(
    text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[dict[str, str]]:
    """Naive character-level chunking (fallback for unsupported languages)."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end]
        chunks.append(
            {
                "text": chunk_text,
                "symbol_type": "text",
                "symbol_name": "",
                "parent_class": "",
            }
        )
        start += chunk_size - overlap
    return chunks if chunks else []


def _extract_python_chunks(source: bytes, text: str) -> list[dict[str, str]]:
    """Extract function/class/top-level assignment chunks from Python source."""
    parser = _get_py_parser()
    if parser is None:
        return _chunk_text(text)

    try:
        tree = parser.parse(source)
    except Exception:
        return _chunk_text(text)

    chunks: list[dict[str, str]] = []

    def traverse(node: Node, parent_class: str = "") -> None:
        """Traverse AST and extract target nodes."""
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name_text = _get_node_text(name_node, source)
                node_text = _get_node_text(node, source)

                # Split if oversized
                if len(node_text) > CHUNK_SIZE:
                    for sub_chunk in _chunk_text(node_text):
                        sub_chunk["symbol_type"] = "function_definition"
                        sub_chunk["symbol_name"] = name_text
                        sub_chunk["parent_class"] = parent_class
                        chunks.append(sub_chunk)
                else:
                    chunks.append(
                        {
                            "text": node_text,
                            "symbol_type": "function_definition",
                            "symbol_name": name_text,
                            "parent_class": parent_class,
                        }
                    )

        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name_text = _get_node_text(name_node, source)
                node_text = _get_node_text(node, source)

                # Split if oversized
                if len(node_text) > CHUNK_SIZE:
                    for sub_chunk in _chunk_text(node_text):
                        sub_chunk["symbol_type"] = "class_definition"
                        sub_chunk["symbol_name"] = name_text
                        sub_chunk["parent_class"] = ""
                        chunks.append(sub_chunk)
                else:
                    chunks.append(
                        {
                            "text": node_text,
                            "symbol_type": "class_definition",
                            "symbol_name": name_text,
                            "parent_class": "",
                        }
                    )

                # Traverse class body for methods
                body_node = node.child_by_field_name("body")
                if body_node:
                    for child in body_node.children:
                        traverse(child, parent_class=name_text)
                return

        elif node.type == "decorated_definition":
            # Handle decorated functions/classes
            definition_node = node.child_by_field_name("definition")
            if definition_node:
                traverse(definition_node, parent_class)
            return

        elif node.type == "expression_statement":
            # Top-level assignments (constants)
            if not parent_class:  # Only at module level
                node_text = _get_node_text(node, source)
                if node_text.strip():
                    chunks.append(
                        {
                            "text": node_text,
                            "symbol_type": "expression_statement",
                            "symbol_name": "",
                            "parent_class": "",
                        }
                    )
            return

        # Recurse into children
        for child in node.children:
            traverse(child, parent_class)

    root = tree.root_node
    traverse(root)

    return chunks if chunks else _chunk_text(text)


def _extract_php_chunks(source: bytes, text: str) -> list[dict[str, str]]:
    """Extract function/class/method/property/const chunks from PHP source."""
    parser = _get_php_parser()
    if parser is None:
        return _chunk_text(text)

    try:
        tree = parser.parse(source)
    except Exception:
        return _chunk_text(text)

    chunks: list[dict[str, str]] = []

    def traverse(node: Node, parent_class: str = "") -> None:
        """Traverse AST and extract target nodes."""
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name_text = _get_node_text(name_node, source)
                node_text = _get_node_text(node, source)

                if len(node_text) > CHUNK_SIZE:
                    for sub_chunk in _chunk_text(node_text):
                        sub_chunk["symbol_type"] = "function_definition"
                        sub_chunk["symbol_name"] = name_text
                        sub_chunk["parent_class"] = parent_class
                        chunks.append(sub_chunk)
                else:
                    chunks.append(
                        {
                            "text": node_text,
                            "symbol_type": "function_definition",
                            "symbol_name": name_text,
                            "parent_class": parent_class,
                        }
                    )

        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name_text = _get_node_text(name_node, source)
                node_text = _get_node_text(node, source)

                if len(node_text) > CHUNK_SIZE:
                    for sub_chunk in _chunk_text(node_text):
                        sub_chunk["symbol_type"] = "class_declaration"
                        sub_chunk["symbol_name"] = name_text
                        sub_chunk["parent_class"] = ""
                        chunks.append(sub_chunk)
                else:
                    chunks.append(
                        {
                            "text": node_text,
                            "symbol_type": "class_declaration",
                            "symbol_name": name_text,
                            "parent_class": "",
                        }
                    )

                # Traverse class body for methods/properties
                body_node = node.child_by_field_name("body")
                if body_node:
                    for child in body_node.children:
                        traverse(child, parent_class=name_text)
                return

        elif node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name_text = _get_node_text(name_node, source)
                node_text = _get_node_text(node, source)

                if len(node_text) > CHUNK_SIZE:
                    for sub_chunk in _chunk_text(node_text):
                        sub_chunk["symbol_type"] = "method_declaration"
                        sub_chunk["symbol_name"] = name_text
                        sub_chunk["parent_class"] = parent_class
                        chunks.append(sub_chunk)
                else:
                    chunks.append(
                        {
                            "text": node_text,
                            "symbol_type": "method_declaration",
                            "symbol_name": name_text,
                            "parent_class": parent_class,
                        }
                    )

        elif node.type == "property_declaration":
            node_text = _get_node_text(node, source)
            if node_text.strip():
                chunks.append(
                    {
                        "text": node_text,
                        "symbol_type": "property_declaration",
                        "symbol_name": "",
                        "parent_class": parent_class,
                    }
                )

        elif node.type == "const_declaration":
            node_text = _get_node_text(node, source)
            if node_text.strip():
                chunks.append(
                    {
                        "text": node_text,
                        "symbol_type": "const_declaration",
                        "symbol_name": "",
                        "parent_class": parent_class,
                    }
                )

        # Recurse
        for child in node.children:
            traverse(child, parent_class)

    root = tree.root_node
    traverse(root)

    return chunks if chunks else _chunk_text(text)


def _extract_csharp_chunks(source: bytes, text: str) -> list[dict[str, str]]:
    """Extract class/method/constructor/field/property chunks from C# source."""
    parser = _get_cs_parser()
    if parser is None:
        return _chunk_text(text)

    try:
        tree = parser.parse(source)
    except Exception:
        return _chunk_text(text)

    chunks: list[dict[str, str]] = []

    def traverse(node: Node, parent_class: str = "") -> None:
        """Traverse AST and extract target nodes."""
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name_text = _get_node_text(name_node, source)
                node_text = _get_node_text(node, source)

                if len(node_text) > CHUNK_SIZE:
                    for sub_chunk in _chunk_text(node_text):
                        sub_chunk["symbol_type"] = "class_declaration"
                        sub_chunk["symbol_name"] = name_text
                        sub_chunk["parent_class"] = ""
                        chunks.append(sub_chunk)
                else:
                    chunks.append(
                        {
                            "text": node_text,
                            "symbol_type": "class_declaration",
                            "symbol_name": name_text,
                            "parent_class": "",
                        }
                    )

                # Traverse class body
                body_node = node.child_by_field_name("body")
                if body_node:
                    for child in body_node.children:
                        traverse(child, parent_class=name_text)
                return

        elif node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name_text = _get_node_text(name_node, source)
                node_text = _get_node_text(node, source)

                if len(node_text) > CHUNK_SIZE:
                    for sub_chunk in _chunk_text(node_text):
                        sub_chunk["symbol_type"] = "method_declaration"
                        sub_chunk["symbol_name"] = name_text
                        sub_chunk["parent_class"] = parent_class
                        chunks.append(sub_chunk)
                else:
                    chunks.append(
                        {
                            "text": node_text,
                            "symbol_type": "method_declaration",
                            "symbol_name": name_text,
                            "parent_class": parent_class,
                        }
                    )

        elif node.type == "constructor_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name_text = _get_node_text(name_node, source)
                node_text = _get_node_text(node, source)

                if len(node_text) > CHUNK_SIZE:
                    for sub_chunk in _chunk_text(node_text):
                        sub_chunk["symbol_type"] = "constructor_declaration"
                        sub_chunk["symbol_name"] = name_text
                        sub_chunk["parent_class"] = parent_class
                        chunks.append(sub_chunk)
                else:
                    chunks.append(
                        {
                            "text": node_text,
                            "symbol_type": "constructor_declaration",
                            "symbol_name": name_text,
                            "parent_class": parent_class,
                        }
                    )

        elif node.type == "property_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name_text = _get_node_text(name_node, source)
                node_text = _get_node_text(node, source)

                chunks.append(
                    {
                        "text": node_text,
                        "symbol_type": "property_declaration",
                        "symbol_name": name_text,
                        "parent_class": parent_class,
                    }
                )

        elif node.type == "field_declaration":
            node_text = _get_node_text(node, source)
            if node_text.strip():
                chunks.append(
                    {
                        "text": node_text,
                        "symbol_type": "field_declaration",
                        "symbol_name": "",
                        "parent_class": parent_class,
                    }
                )

        # Recurse
        for child in node.children:
            traverse(child, parent_class)

    root = tree.root_node
    traverse(root)

    return chunks if chunks else _chunk_text(text)


def chunk_file(filepath: Path, text: str) -> list[dict[str, str]]:
    """Chunk a source file using AST parsing, with fallback to naive chunking.

    Args:
        filepath: Path to the source file (used for extension detection).
        text: Full source code as string.

    Returns:
        List of chunk dicts with keys: text, symbol_type, symbol_name, parent_class.
        On error or unsupported extension, falls back to naive character chunking.
    """
    if not text or not text.strip():
        return []

    # Detect language from extension
    suffix = filepath.suffix.lower()

    # Encode to bytes for parser
    try:
        source_bytes = text.encode("utf8")
    except Exception:
        return _chunk_text(text)

    # Dispatch by language
    if suffix == ".py":
        return _extract_python_chunks(source_bytes, text)
    elif suffix == ".php":
        return _extract_php_chunks(source_bytes, text)
    elif suffix == ".cs":
        return _extract_csharp_chunks(source_bytes, text)
    else:
        # Unsupported extension: fall back to naive chunking
        return _chunk_text(text)
