"""Triage service: one Laya batch for many items, LLM fallback, never loses an item.

FR-20 (batch), FR-21 (core + niche questions), FR-22 (gating), FR-23 (modes), FR-24 (fallback,
shadow), FR-25 (risk), NFR-03 (Laya can never lose an item). docs/LAYA.md sections 2 and 4.

An item resolves its mode once, after the core Laya call: per-niche override for the hinted (or
Laya-suggested) niche > tenant `laya_mode` > env default (`shadow`).
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.graph.sensitivity import effective_sensitivity
from app.integrations import events
from app.models import Item
from app.models.enums import ItemStatus, Risk
from app.models.status import transition
from app.models.tenant_settings import TenantSettings
from app.niches.models import NicheConfig
from app.niches.registry import FALLBACK_NICHE, NicheRegistry, get_registry
from app.schemas.triage import Answer, ShadowRecord, TriageRecord
from app.triage.answers import hint_answer, parse_laya_result
from app.triage.fallback import FallbackUnavailable, classify
from app.triage.laya_client import HttpLayaClient, LayaClient
from app.triage.modes import Mode, has_active_override, resolve_mode
from app.triage.questions import (
    NICHE,
    RISK,
    URGENCY,
    QuestionError,
    core_questions,
    niche_questions,
    state_text,
)

log = logging.getLogger(__name__)

SPAM_DISCARD_CONFIDENCE = 0.85
FALLBACK_CONCURRENCY = 4
DEFAULT_GATE = 0.75
TRIAGEABLE = frozenset({ItemStatus.NORMALISED.value, ItemStatus.NEEDS_HUMAN_TRIAGE.value})
SCAM = Risk.SCAM_OR_PHISHING.value


@dataclass(frozen=True)
class TriageOutcome:
    item_id: uuid.UUID
    status: str


@lru_cache(maxsize=2)
def _build_client(url: str, key: str, timeout: float) -> LayaClient:
    return HttpLayaClient(url, key, timeout)


def get_laya_client() -> LayaClient | None:
    """The single lookup site (tests monkeypatch it). None = Laya not configured."""
    s = get_settings()
    if not s.laya_url.strip():
        return None
    return _build_client(s.laya_url, s.laya_api_key.get_secret_value(), s.laya_timeout_seconds)


@dataclass
class _Work:
    item: Item
    state: str
    settings: dict[str, Any]
    hinted: NicheConfig | None
    mode: Mode = "shadow"
    questions: dict[str, Any] = field(default_factory=dict)
    answers: dict[str, Answer] = field(default_factory=dict)
    shadow: dict[str, Answer] = field(default_factory=dict)
    laya_consulted: bool = False
    laya_failed: bool = False
    laya_model: str | None = None
    laya_version: str | None = None
    laya_ms: int = 0
    fallback_ms: int = 0
    fallback_used: bool = False
    error: str | None = None


async def _load_settings(
    session: AsyncSession, tenant_ids: set[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    rows = await session.execute(
        select(TenantSettings.tenant_id, TenantSettings.settings).where(
            TenantSettings.tenant_id.in_(tenant_ids)
        )
    )
    return {tid: dict(value or {}) for tid, value in rows.all()}


async def _laya_batch(
    client: LayaClient | None, states: list[str], questions: dict[str, Any]
) -> list[dict[str, Any] | None]:
    if client is None or not states:
        return [None] * len(states)
    model = get_settings().laya_model.strip() or None
    try:
        results = await client.batch(states, questions, model=model)
    except Exception:  # the client should never raise; Laya must not lose items
        log.warning("laya client raised", exc_info=True)
        return [None] * len(states)
    return results if len(results) == len(states) else [None] * len(states)


def _hinted(item: Item, registry: NicheRegistry) -> NicheConfig | None:
    name = (item.hints or {}).get("niche")
    cfg = registry.get(name) if isinstance(name, str) else None
    return cfg if cfg is not None and cfg.enabled else None


def _gate(work: _Work, candidate: str | None, registry: NicheRegistry) -> float:
    cfg = work.hinted or (registry.get(candidate) if candidate else None)
    if cfg is None or cfg.name == FALLBACK_NICHE:
        # The fallback niche's own 0.0 only means "routing to generic is always allowed"; it must
        # not let low-confidence answers through. Below DEFAULT_GATE the item goes to the LLM
        # fallback or human triage, never discarded.
        return DEFAULT_GATE
    return cfg.triage.min_confidence


def _record_laya(work: _Work, result: dict[str, Any] | None) -> None:
    work.laya_consulted = True
    if result is None:
        work.laya_failed = True
        return
    work.laya_model = result.get("model") or work.laya_model
    work.laya_version = result.get("laya_version") or work.laya_version
    work.laya_ms += int(result.get("latency_ms") or 0)


def _plan(
    work: _Work,
    questions: dict[str, Any],
    result: dict[str, Any] | None,
    gate: float,
) -> list[str]:
    """Apply a Laya result per mode; return the question ids the fallback must answer."""
    work.questions.update(questions)
    parsed = parse_laya_result(questions, result)
    if work.mode == "off":
        return list(questions)
    if work.mode == "shadow":
        work.shadow.update(parsed)
        return list(questions)
    pending: list[str] = []
    for qid in questions:
        answer = parsed.get(qid)
        if answer is not None and (answer.confidence or 0.0) >= gate:
            work.answers[qid] = answer
        else:
            pending.append(qid)
    return pending


async def _run_fallback(
    work: _Work,
    questions: dict[str, Any],
    pending: list[str],
    sem: asyncio.Semaphore,
    niche: NicheConfig | None = None,
) -> None:
    if not pending or work.error:
        return
    subset = {qid: questions[qid] for qid in pending}
    sensitivity = (
        effective_sensitivity(work.item.sensitivity, niche) if niche else work.item.sensitivity
    )
    started = time.perf_counter()
    async with sem:
        try:
            answers = await classify(
                work.state,
                subset,
                sensitivity=sensitivity,  # type: ignore[arg-type]
                item_id=str(work.item.id),
                language=work.item.language or "en",
            )
        except FallbackUnavailable:
            work.error = "fallback_unavailable"
            return
        except Exception:
            log.warning("fallback raised item=%s", work.item.id, exc_info=True)
            work.error = "fallback_unavailable"
            return
        finally:
            work.fallback_ms += int((time.perf_counter() - started) * 1000)
    work.answers.update(answers)
    work.fallback_used = True


def _routed_niche(work: _Work, registry: NicheRegistry) -> NicheConfig:
    answer = work.answers.get(NICHE)
    cfg = registry.get(answer.choice) if answer and answer.choice else None
    generic = registry.get(FALLBACK_NICHE)
    return cfg if cfg is not None and cfg.enabled else generic or next(iter(registry.enabled()))


def _is_spam(answer: Answer | None) -> bool:
    return bool(
        answer and answer.choice == "spam" and (answer.confidence or 0) >= SPAM_DISCARD_CONFIDENCE
    )


def _spam_needs_review(work: _Work) -> bool:
    """A spam verdict backed only by the LLM fallback's self-reported confidence (NFR-03).

    Terminal discard needs Laya to agree: a Laya-sourced answer (mode on) or its shadow answer.
    """
    risk = work.answers.get(RISK)
    if not _is_spam(risk) or (risk and risk.source == "laya"):
        return False
    return not _is_spam(work.shadow.get(RISK))


def _discard_reason(work: _Work, niche: NicheConfig) -> str | None:
    if _is_spam(work.answers.get(RISK)):
        return "spam"
    for rule in niche.triage.discard_if:
        answer = work.answers.get(rule.question)
        if (
            answer
            and answer.choice == rule.choice
            and (answer.confidence or 0) >= rule.min_confidence
        ):
            return f"discard_if:{rule.question}"
    return None


def _decided_by(work: _Work) -> Literal["laya", "llm_fallback"]:
    laya_only = bool(work.answers) and all(
        a.source in ("laya", "hint") for a in work.answers.values()
    )
    return "laya" if work.mode == "on" and laya_only and not work.fallback_used else "llm_fallback"


def _record(work: _Work) -> TriageRecord:
    shadow = None
    if work.mode == "shadow":
        shadow = ShadowRecord(
            answers=work.shadow or None,
            model=work.laya_model,
            latency_ms=work.laya_ms if work.laya_consulted else None,
            error="laya_unavailable" if work.laya_failed or not work.shadow else None,
        )
    return TriageRecord(
        mode=work.mode,
        model=work.laya_model,
        laya_version=work.laya_version,
        fallback=work.fallback_used or work.error is not None,
        decided_by=_decided_by(work),
        answers=work.answers,
        questions=work.questions,
        shadow=shadow,
        latency_ms=work.laya_ms + work.fallback_ms,
        error=work.error,
    )


def _finalise(work: _Work, registry: NicheRegistry) -> str:
    item = work.item
    item.laya_mode = work.mode
    if work.error:
        item.triage = _record(work).model_dump(mode="json")
        transition(item, ItemStatus.NEEDS_HUMAN_TRIAGE)
        return item.status
    niche = _routed_niche(work, registry)
    urgency = work.answers.get(URGENCY)
    risk = work.answers.get(RISK)
    item.niche = niche.name
    item.urgency = urgency.level if urgency and urgency.level is not None else None
    item.risk = risk.choice if risk and risk.choice in Risk.values() else None
    item.triage = _record(work).model_dump(mode="json")
    if _spam_needs_review(work):
        transition(item, ItemStatus.NEEDS_HUMAN_TRIAGE)
        return item.status
    reason = _discard_reason(work, niche)
    transition(item, ItemStatus.DISCARDED if reason else ItemStatus.TRIAGED)
    return item.status


def _fail(work: _Work, error: str) -> None:
    work.error = work.error or error


def _core_for(work: _Work, core: dict[str, Any]) -> dict[str, Any]:
    if work.hinted is None:
        return core
    questions = {q: s for q, s in core.items() if q != NICHE}
    return {**questions, **niche_questions(work.hinted)}


async def _phase_core(
    works: list[_Work],
    core: dict[str, Any],
    client: LayaClient | None,
    registry: NicheRegistry,
    default_mode: str,
    sem: asyncio.Semaphore,
) -> None:
    groups: dict[str | None, list[_Work]] = defaultdict(list)
    for work in works:
        groups[work.hinted.name if work.hinted else None].append(work)
    plans: list[tuple[_Work, dict[str, Any], list[str]]] = []
    for members in groups.values():
        questions = _core_for(members[0], core)
        consult = [
            w
            for w in members
            if resolve_mode(w.settings, w.hinted.name if w.hinted else None, default_mode) != "off"
            or has_active_override(w.settings)
        ]
        results = dict(
            zip(
                (id(w) for w in consult),
                await _laya_batch(client, [w.state for w in consult], questions),
                strict=True,
            )
        )
        for work in members:
            result = results.get(id(work))
            consulted = id(work) in results
            if consulted:
                _record_laya(work, result)
            parsed_niche = (
                parse_laya_result({NICHE: questions.get(NICHE)}, result)
                if (NICHE in questions and result)
                else {}
            )
            candidate = work.hinted.name if work.hinted else None
            if candidate is None and NICHE in parsed_niche:
                candidate = parsed_niche[NICHE].choice
            work.mode = resolve_mode(work.settings, candidate, default_mode)
            if work.hinted:
                work.answers[NICHE] = hint_answer(work.hinted.name)
            gate = _gate(work, candidate, registry)
            plans.append((work, questions, _plan(work, questions, result, gate)))
    await asyncio.gather(*(_run_fallback(w, q, p, sem) for w, q, p in plans))


async def _phase_niche(
    works: list[_Work], client: LayaClient | None, registry: NicheRegistry, sem: asyncio.Semaphore
) -> None:
    groups: dict[str, list[_Work]] = defaultdict(list)
    for work in works:
        if work.error or work.hinted is not None:
            continue
        routed = _routed_niche(work, registry)
        if routed.triage.questions:
            groups[routed.name].append(work)
    plans: list[tuple[_Work, dict[str, Any], list[str], NicheConfig]] = []
    for name, members in groups.items():
        cfg = registry.get(name)
        if cfg is None:
            continue
        questions = niche_questions(cfg)
        laya_members = [w for w in members if w.mode != "off"]
        results = dict(
            zip(
                (id(w) for w in laya_members),
                await _laya_batch(client, [w.state for w in laya_members], questions),
                strict=True,
            )
        )
        for work in members:
            result = results.get(id(work))
            if id(work) in results:
                _record_laya(work, result)
            plans.append(
                (work, questions, _plan(work, questions, result, cfg.triage.min_confidence), cfg)
            )
    await asyncio.gather(*(_run_fallback(w, q, p, sem, c) for w, q, p, c in plans))


def _content_state(item: Item) -> str:
    return state_text(item.content or {"title": ""})


async def triage_items(
    session: AsyncSession, items: Sequence[Item], *, registry: NicheRegistry | None = None
) -> list[TriageOutcome]:
    """Triage `items` with ONE core Laya batch. Never raises for Laya or LLM failure."""
    registry = registry or get_registry()
    todo = [i for i in items if i.status in TRIAGEABLE]
    outcomes: dict[uuid.UUID, str] = {i.id: i.status for i in items}
    if todo:
        for item, status in await _triage(session, todo, registry):
            outcomes[item.id] = status
    return [TriageOutcome(item.id, outcomes[item.id]) for item in items]


async def _triage(
    session: AsyncSession, todo: list[Item], registry: NicheRegistry
) -> list[tuple[Item, str]]:
    tenant_settings = await _load_settings(session, {i.tenant_id for i in todo})
    works = [
        _Work(i, _content_state(i), tenant_settings.get(i.tenant_id, {}), _hinted(i, registry))
        for i in todo
    ]
    default_mode = get_settings().laya_mode
    sem = asyncio.Semaphore(FALLBACK_CONCURRENCY)
    try:
        core = core_questions(registry.enabled())
    except QuestionError:
        log.error("core questions invalid; parking items for human triage", exc_info=True)
        for work in works:
            _fail(work, "questions_invalid")
        core = {}
    client = get_laya_client()
    if core:
        try:
            await _phase_core(works, core, client, registry, default_mode, sem)
            await _phase_niche(works, client, registry, sem)
        except Exception:
            log.error("triage stage failed unexpectedly", exc_info=True)
            for work in works:
                if not work.answers:
                    _fail(work, "triage_error")
    return [(w.item, await _complete(session, w, registry)) for w in works]


async def _complete(session: AsyncSession, work: _Work, registry: NicheRegistry) -> str:
    try:
        status = _finalise(work, registry)
    except Exception:
        log.error("finalise failed item=%s", work.item.id, exc_info=True)
        work.error = "triage_error"
        status = _finalise(work, registry)
    if status != ItemStatus.NEEDS_HUMAN_TRIAGE.value:
        await events.emit(
            session,
            tenant_id=work.item.tenant_id,
            event="item.triaged",
            item_id=work.item.id,
            extra={"status": status},
        )
    return status


__all__ = ["TriageOutcome", "get_laya_client", "triage_items"]
