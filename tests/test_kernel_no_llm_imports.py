"""Fails the build if anything under src/recovery_ledger/kernel/ imports an
LLM client. This is a headline design decision (spec section 0, 8.5, 9.1),
not a style preference — enforced mechanically here rather than by review,
because "an agent that is 99% compliant is 100% undeployable."

Checks by parsing the AST of every .py file under kernel/, rather than
grepping for strings, so it can't be defeated by a comment or a docstring
that happens to mention a banned name.
"""

from __future__ import annotations

import ast
from pathlib import Path

KERNEL_DIR = Path(__file__).parent.parent / "src" / "recovery_ledger" / "kernel"

BANNED_MODULE_PREFIXES = (
    "anthropic",
    "openai",
    "recovery_ledger.llm",
)


def _imported_module_names(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_kernel_dir_exists():
    assert KERNEL_DIR.is_dir(), f"expected {KERNEL_DIR} to exist"


def test_no_llm_imports_anywhere_under_kernel():
    violations: list[str] = []
    py_files = sorted(KERNEL_DIR.rglob("*.py"))
    assert py_files, "no .py files found under kernel/ — test would pass vacuously"

    for path in py_files:
        tree = ast.parse(path.read_text(), filename=str(path))
        for module_name in _imported_module_names(tree):
            if any(module_name == p or module_name.startswith(p + ".") for p in BANNED_MODULE_PREFIXES):
                violations.append(f"{path.relative_to(KERNEL_DIR.parent.parent.parent)}: imports {module_name!r}")

    assert not violations, "LLM import(s) found under kernel/ — the compliance kernel must stay deterministic:\n" + "\n".join(violations)
