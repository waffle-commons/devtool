"""Every third-party module devtool imports must be a declared dependency (RFC 028, P0).

A fresh ``pip install`` crashed at startup because ``click`` was imported but never
declared: Typer 0.28 stopped installing it. This test catches that class of bug in an
ordinary test run, before a release does.
"""

import ast
import re
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared_distributions() -> set[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    return {
        _normalize(re.split(r"[<>=!~;\[ ]", dep, maxsplit=1)[0])
        for dep in project["dependencies"]
    }


def _catches_import_error(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(
        isinstance(n, ast.Name)
        and n.id in {"ImportError", "ModuleNotFoundError", "Exception"}
        for n in names
    )


def _optional_imports(tree: ast.AST) -> set[int]:
    """Imports inside `try: ... except ImportError`: optional by construction."""
    optional: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(
            _catches_import_error(h) for h in node.handlers
        ):
            for statement in node.body:
                optional.update(
                    id(inner)
                    for inner in ast.walk(statement)
                    if isinstance(inner, (ast.Import, ast.ImportFrom))
                )
    return optional


def _third_party_imports() -> set[str]:
    modules: set[str] = set()
    for path in (ROOT / "devtool").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        optional = _optional_imports(tree)
        for node in ast.walk(tree):
            if id(node) in optional:
                continue
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    return {m for m in modules if m not in sys.stdlib_module_names and m != "devtool"}


def test_every_third_party_import_is_a_declared_dependency() -> None:
    declared = _declared_distributions()
    providers = packages_distributions()
    missing = sorted(
        module
        for module in _third_party_imports()
        if not any(
            _normalize(dist) in declared for dist in providers.get(module, [module])
        )
    )
    assert (
        not missing
    ), f"imported by devtool but not declared in pyproject.toml: {missing}"
