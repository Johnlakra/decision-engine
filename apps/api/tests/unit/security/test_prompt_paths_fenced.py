"""Every module that sends a prompt fences remote text and is the only LLM door (NFR-05, NFR-07)."""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[3] / "app"
LLM_CALLS = {"complete_json", "complete_text"}
PROVIDER_SDKS = {"litellm", "openai", "anthropic", "groq", "google"}


def _modules() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if "__pycache__" not in p.parts)


def _calls_gateway(tree: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Attribute) and n.attr in LLM_CALLS and _is_gateway(n.value)
        for n in ast.walk(tree)
    )


def _is_gateway(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "gateway"


def _imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def test_prompt_paths_exist() -> None:
    callers = {
        p.relative_to(APP).as_posix()
        for p in _modules()
        if _calls_gateway(ast.parse(p.read_text()))
    }
    assert {
        "graph/nodes/decide.py",
        "graph/nodes/extract.py",
        "graph/oneshot.py",
        "triage/fallback.py",
        "normalise/llm_normaliser.py",
    } <= callers


def test_every_gateway_caller_uses_fence() -> None:
    offenders = []
    for path in _modules():
        tree = ast.parse(path.read_text())
        if path.is_relative_to(APP / "llm") or not _calls_gateway(tree):
            continue
        if "fence" not in _imports(tree) and "app.graph.text" not in _imports_with_modules(tree):
            offenders.append(path.relative_to(APP).as_posix())
    assert offenders == []


OUTSIDE_LLM = [p for p in _modules() if not p.is_relative_to(APP / "llm")]


@pytest.mark.parametrize("path", OUTSIDE_LLM, ids=lambda p: p.relative_to(APP).as_posix())
def test_no_provider_sdk_outside_llm_package(path: Path) -> None:
    roots = {name.split(".")[0] for name in _imports_with_modules(ast.parse(path.read_text()))}
    assert not roots & PROVIDER_SDKS


def _imports_with_modules(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found
