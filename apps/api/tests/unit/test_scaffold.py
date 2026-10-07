"""Scaffold smoke tests. NFR-09, NFR-12."""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from fastapi import FastAPI

API_DIR = Path(__file__).resolve().parents[2]
BANNED = [
    "litellm",
    "openai",
    "anthropic",
    "google.genai",
    "google.generativeai",
    "groq",
    "cerebras",
]


def _ruff(filename: str, source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--select",
            "TID251",
            "--stdin-filename",
            filename,
            "-",
        ],
        input=source,
        capture_output=True,
        text=True,
        cwd=API_DIR,
        check=False,
    )


def test_create_app_returns_fastapi() -> None:
    from app.main import create_app

    assert isinstance(create_app(), FastAPI)


def test_banned_imports_configured() -> None:
    cfg = tomllib.loads((API_DIR / "pyproject.toml").read_text())
    banned = cfg["tool"]["ruff"]["lint"]["flake8-tidy-imports"]["banned-api"]
    assert set(BANNED) <= set(banned)
    assert "app/llm/**" in cfg["tool"]["ruff"]["lint"]["per-file-ignores"]


def test_litellm_pinned_exactly() -> None:
    cfg = tomllib.loads((API_DIR / "pyproject.toml").read_text())
    assert any(d.startswith("litellm==") for d in cfg["project"]["dependencies"])


@pytest.mark.parametrize("module", BANNED)
def test_banned_import_fires_outside_llm(module: str) -> None:
    result = _ruff("app/triage/x.py", f"import {module}\n")
    assert result.returncode != 0
    assert "TID251" in result.stdout


def test_banned_import_allowed_under_llm() -> None:
    result = _ruff("app/llm/x.py", "import litellm\n")
    assert result.returncode == 0, result.stdout
