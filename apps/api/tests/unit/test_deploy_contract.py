"""Static contract of the one-command stack and worker sizing (NFR-12, NFR-02)."""

import re
from pathlib import Path

import yaml

from app.core.config import Settings

REPO = Path(__file__).resolve().parents[4]
MAX_BATCH = 32  # NFR-02: worker batches of up to 32 items
MAKE_TARGETS = {"dev", "test", "lint", "migrate", "laya-up", "seed", "eval"}


def _compose() -> dict:  # type: ignore[type-arg]
    return yaml.safe_load((REPO / "docker-compose.yml").read_text())  # type: ignore[no-any-return]


def test_default_stack_runs_db_redis_api_and_worker_without_extra_profiles() -> None:
    services = _compose()["services"]
    default = {name for name, spec in services.items() if not spec.get("profiles")}
    assert {"db", "redis", "api", "worker"} <= default
    assert services["laya"]["profiles"] == ["laya"]  # opt-in, so `docker compose up` is enough


def test_worker_waits_for_a_healthy_db() -> None:
    worker = _compose()["services"]["worker"]
    assert worker["depends_on"]["db"]["condition"] == "service_healthy"


def test_compose_has_no_hardcoded_provider_keys() -> None:
    text = (REPO / "docker-compose.yml").read_text()
    assert not re.search(r"(API_KEY|TOKEN|SECRET)\s*:\s*['\"]?[A-Za-z0-9]{12,}", text)


def test_makefile_declares_the_documented_targets() -> None:
    targets = set(re.findall(r"^([a-z][a-z-]*):", (REPO / "Makefile").read_text(), re.M))
    assert MAKE_TARGETS <= targets


def test_worker_batch_never_exceeds_32() -> None:
    assert 1 <= Settings(_env_file=None).worker_batch_size <= MAX_BATCH  # type: ignore[call-arg]
