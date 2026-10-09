"""Seed script (FR-01): ingest_one only, idempotent, bounded, never calls an LLM."""

import json
import threading
import urllib.error
import urllib.request
from collections import Counter

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item, Job, Tenant
from app.schemas.ingest import IngestItemIn
from app.security.hmac import InvalidSignature, sign
from scripts import accept_phase1, seed, webhook_receiver
from tests.fakes.fake_llm import FakeLLM

pytestmark = pytest.mark.integration

SECRET = b"s3cr3t-for-receiver"
EXPECTED_ROWS = 50


async def _count(session: AsyncSession, tenant: Tenant) -> int:
    stmt = select(func.count()).select_from(Item).where(Item.tenant_id == tenant.id)
    return int((await session.execute(stmt)).scalar_one())


def test_every_row_validates_against_the_ingest_schema() -> None:
    rows = seed.load_rows(limit=EXPECTED_ROWS)

    assert len(rows) == EXPECTED_ROWS
    assert all(isinstance(row, IngestItemIn) for row in rows)
    assert {row.source for row in rows} == {"seed"}
    assert len({row.source_ref for row in rows}) == EXPECTED_ROWS
    for row in rows:
        assert row.hints is not None
        assert row.hints.title and row.hints.body and row.hints.language in {"en", "hi", "pa"}


def test_demo_text_is_synthetic() -> None:
    rows = seed.load_rows(50)
    blob = " ".join(json.dumps(r.model_dump(mode="json"), ensure_ascii=False) for r in rows)

    emails = {w for w in blob.replace('"', " ").split() if "@" in w}
    assert all(e.rstrip(",.").endswith("@example.com") for e in emails)
    assert "+91" not in blob


def test_limit_is_respected_and_samples_several_niche_shapes() -> None:
    rows = seed.load_rows(limit=7)

    assert len(rows) == 7
    assert len(Counter(r.source_ref.split("-")[1] for r in rows)) >= 5


@pytest.mark.parametrize("limit", [0, -1])
def test_non_positive_limit_is_rejected(limit: int) -> None:
    with pytest.raises(ValueError):
        seed.load_rows(limit=limit)


async def test_seed_loads_all_items_and_enqueues_jobs(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    result = await seed.seed_items(db_session, tenant.id, seed.load_rows(EXPECTED_ROWS))

    assert (result.created, result.existing) == (EXPECTED_ROWS, 0)
    assert await _count(db_session, tenant) == EXPECTED_ROWS
    jobs = (await db_session.execute(select(func.count()).select_from(Job))).scalar_one()
    assert jobs >= EXPECTED_ROWS


async def test_seed_twice_creates_zero_new_items(db_session: AsyncSession, tenant: Tenant) -> None:
    rows = seed.load_rows(EXPECTED_ROWS)
    await seed.seed_items(db_session, tenant.id, rows)

    second = await seed.seed_items(db_session, tenant.id, rows)

    assert (second.created, second.existing) == (0, EXPECTED_ROWS)
    assert await _count(db_session, tenant) == EXPECTED_ROWS


async def test_seed_with_limit_stores_only_that_many(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    result = await seed.seed_items(db_session, tenant.id, seed.load_rows(limit=5))

    assert result.created == 5
    assert await _count(db_session, tenant) == 5


async def test_seeding_calls_no_llm(
    db_session: AsyncSession, tenant: Tenant, fake_llm: FakeLLM
) -> None:
    await seed.seed_items(db_session, tenant.id, seed.load_rows(EXPECTED_ROWS))

    assert fake_llm.calls == []


# --- webhook receiver (L2) ---------------------------------------------------------------


def test_receiver_accepts_a_server_signed_body() -> None:
    body = json.dumps({"event": "decision.made", "id": "evt-1", "data": {}}).encode()

    line = webhook_receiver.check_delivery(SECRET, body, sign(SECRET, body))

    assert line == "signature OK decision.made evt-1"


def test_receiver_rejects_a_tampered_body() -> None:
    body = json.dumps({"event": "decision.made", "id": "evt-1", "data": {}}).encode()
    header = sign(SECRET, body)

    with pytest.raises(InvalidSignature):
        webhook_receiver.check_delivery(SECRET, body + b" ", header)


def test_receiver_rejects_wrong_secret_and_missing_header() -> None:
    body = b'{"event":"decision.made","id":"x"}'

    with pytest.raises(InvalidSignature):
        webhook_receiver.check_delivery(b"other-secret-value", body, sign(SECRET, body))
    with pytest.raises(InvalidSignature):
        webhook_receiver.check_delivery(SECRET, body, "")


def _post(url: str, body: bytes, header: str) -> int:
    request = urllib.request.Request(  # noqa: S310 - localhost
        url, data=body, headers={"X-DE-Signature": header}
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - localhost
            return int(response.status)
    except urllib.error.HTTPError as error:
        return error.code


def test_receiver_http_server_answers_200_for_valid_and_401_for_tampered() -> None:
    server = webhook_receiver.build_server("127.0.0.1", 0, SECRET)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/hook"
        body = b'{"event":"decision.made","id":"evt-2"}'
        header = sign(SECRET, body)

        assert _post(url, body, header) == 200
        assert _post(url, body + b"x", header) == 401
    finally:
        server.shutdown()
        server.server_close()


# --- live acceptance runner gating (L1-L3) -----------------------------------------------


def test_accept_reports_every_missing_prerequisite() -> None:
    missing = accept_phase1.missing_prerequisites(
        has_llm_key=False, has_token_enc_key=False, allows_private_urls=False, api_key=""
    )

    assert missing == [
        "an LLM key (GEMINI_API_KEY or GROQ_API_KEY)",
        "TOKEN_ENC_KEY",
        "WEBHOOK_ALLOW_PRIVATE_URLS=true",
        "DE_API_KEY (an admin key from `make api-key`)",
    ]


def test_accept_runs_when_nothing_is_missing() -> None:
    assert (
        accept_phase1.missing_prerequisites(
            has_llm_key=True, has_token_enc_key=True, allows_private_urls=True, api_key="k"
        )
        == []
    )


def test_accept_main_exits_zero_with_skipped_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(accept_phase1, "missing_prerequisites", lambda **_: ["TOKEN_ENC_KEY"])

    code = accept_phase1.main([])

    assert code == 0
    assert "skipped: missing TOKEN_ENC_KEY" in capsys.readouterr().out


def test_accept_judges_a_decision() -> None:
    good = {
        "status": "awaiting_approval",
        "niche": "tech_stack",
        "decision": {"options": [{"id": "a"}, {"id": "b"}], "recommended": "a"},
        "triage": {"shadow": {"error": "laya_unavailable"}},
    }

    assert accept_phase1.judge_item(good, expect_laya_down=False) == []
    assert accept_phase1.judge_item(good, expect_laya_down=True) == []
    bad = {**good, "niche": "generic", "decision": {"options": [{"id": "a"}]}, "triage": {}}
    problems = accept_phase1.judge_item(bad, expect_laya_down=True)
    assert len(problems) == 3
