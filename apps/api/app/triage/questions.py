"""Laya question builders and the one state_text builder (FR-20, FR-21; docs/LAYA.md section 2).

`state_text` is shared by live triage, evals and the training export so train/serve never drift.
"""

import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from app.core.config import get_settings
from app.niches.models import NicheConfig
from app.security.untrusted import as_data

MAX_OPTIONS = 12  # docs/LAYA.md rule 3: Laya is weak with many options
BODY_CHARS = 600
TITLE_CHARS = 500
SENDER_CHARS = 200
CRITERION_CHARS = 300  # laya_question.schema.json maxLength
SCHEMA_FILE = "laya_question.schema.json"

NEEDS_DECISION = "needs_decision"
NICHE = "niche"
URGENCY = "urgency"
RISK = "risk"
CORE_IDS = (NEEDS_DECISION, NICHE, URGENCY, RISK)
URGENCY_LEVELS = 3


class QuestionError(ValueError):
    """A question set cannot be sent to Laya (invalid schema or too many options)."""


def state_text(content: Mapping[str, Any]) -> str:
    """Title + sender + first 600 body chars, every piece through as_data."""
    title = as_data(str(content.get("title") or ""), max_chars=TITLE_CHARS)
    sender = as_data(str(content.get("sender") or ""), max_chars=SENDER_CHARS)
    body = as_data(str(content.get("body") or "")[:BODY_CHARS], max_chars=BODY_CHARS * 2)
    lines = [f"Subject: {title}"]
    if sender:
        lines.append(f"From: {sender}")
    if body:
        lines.extend(["", body])
    return "\n".join(lines)


@lru_cache(maxsize=4)
def _validator(schema_dir: str) -> Draft202012Validator:
    schema = json.loads((Path(schema_dir) / SCHEMA_FILE).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_questions(questions: Mapping[str, Any], *, schema_dir: Path | None = None) -> None:
    """Raise QuestionError unless every question matches schemas/laya_question.schema.json."""
    validator = _validator(str(schema_dir or get_settings().schemas_dir))
    for qid, question in questions.items():
        errors = sorted(validator.iter_errors(question), key=lambda e: list(e.path))
        if errors:
            raise QuestionError(f"question {qid!r} is invalid: {errors[0].message}")
        criteria = question["criteria"]
        if len(criteria) > MAX_OPTIONS:
            raise QuestionError(f"question {qid!r} has {len(criteria)} options (max {MAX_OPTIONS})")


def core_questions(enabled: Sequence[NicheConfig]) -> dict[str, Any]:
    """needs_decision, niche (enabled niche descriptions), urgency, risk."""
    if not enabled:
        raise QuestionError("no enabled niche")
    if len(enabled) > MAX_OPTIONS:
        raise QuestionError(
            f"{len(enabled)} enabled niches exceed {MAX_OPTIONS}; coarse-to-fine is out of scope"
        )
    questions: dict[str, Any] = {
        NEEDS_DECISION: {
            "type": "choice",
            "instructions": "Does this require the owner to decide or act?",
            "criteria": {
                "A": "yes, a decision or action is needed",
                "B": "no, informational only",
            },
        },
        NICHE: {
            "type": "choice",
            "instructions": "Which area does this belong to?",
            "criteria": {n.name: n.description[:CRITERION_CHARS] for n in enabled},
        },
        URGENCY: {
            "type": "score",
            "instructions": "How soon must the owner act?",
            "criteria": ["can wait a week or more", "this week", "today or overdue"],
        },
        RISK: {
            "type": "choice",
            "instructions": "Is this a normal message, spam, or a scam/phishing attempt?",
            "criteria": {
                "normal": "a normal legitimate item",
                "spam": "unwanted bulk marketing",
                "scam_or_phishing": "asks for passwords, OTP, money to strangers, or fakes a brand",
            },
        },
    }
    validate_questions(questions)
    return questions


def niche_questions(niche: NicheConfig) -> dict[str, Any]:
    """The niche's own questions (ids that clash with a core id are dropped)."""
    questions = {q: dict(spec) for q, spec in niche.triage.questions.items() if q not in CORE_IDS}
    validate_questions(questions)
    return questions
