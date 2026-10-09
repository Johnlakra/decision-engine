"""Scripted LLM answers for the school-ERP scenario and a schema-walking classify responder."""

from typing import Any

import pytest
from pydantic import BaseModel

from app.llm import gateway
from tests.fakes.fake_llm import FakeLLM

SCHOOL_ERP_BRIEF = (
    "We are a 3-person team building a school ERP (fees, attendance, report cards) for 12 "
    "government-aided schools in Punjab. Budget is Rs 0 to start. Schools have patchy internet, "
    "so it must work offline. Teachers use cheap Android phones. Which stack should we use?"
)
EXTRACTED: dict[str, Any] = {
    "project_type": "mobile_app",
    "team_size": 3,
    "team_skills": ["python", "react"],
    "budget_inr_month": 0,
    "users_expected": 2000,
    "offline_needed": True,
    "languages_needed": ["en", "hi", "pa"],
}
DECISION: dict[str, Any] = {
    "options": [
        {
            "id": "A",
            "label": "Expo app with local SQLite sync and a free Postgres tier",
            "actions": [],
        },
        {"id": "B", "label": "Next.js PWA with offline cache on a small VPS", "actions": []},
    ],
    "recommended": "A",
    "rationale": (
        "Offline-first matters most here. Option A fits cheap Android phones. It costs nothing."
    ),
    "evidence": [],
    "confidence": 0.8,
}
PREFERRED = ("tech_stack", "A", "normal")


def sample_for(schema: dict[str, Any], root: dict[str, Any]) -> Any:
    """Smallest valid instance of a JSON schema, preferring routing answers for tech_stack."""
    if "$ref" in schema:
        node: Any = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            node = node[part]
        return sample_for(node, root)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return next((v for v in PREFERRED if v in schema["enum"]), schema["enum"][0])
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [o for o in schema[key] if o.get("type") != "null"] or schema[key]
            return sample_for(options[0], root)
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        props = schema.get("properties", {})
        return {name: sample_for(sub, root) for name, sub in props.items()}
    if kind == "array":
        return []
    if kind == "integer":
        return int(schema.get("minimum", 0))
    if kind == "number":
        return float(schema.get("maximum", 0.9)) if schema.get("maximum", 2) <= 1 else 0.9
    if kind == "boolean":
        return True
    return "A"


def auto_classify(schema: type[BaseModel]) -> BaseModel:
    json_schema = schema.model_json_schema()
    return schema.model_validate(sample_for(json_schema, json_schema))


def install_llm(fake: FakeLLM, monkeypatch: pytest.MonkeyPatch) -> FakeLLM:
    """Script extract + decide (repeating), auto-answer classify unless the test scripted it."""
    fake.script("normalise", {"entities": EXTRACTED}, repeat=True)  # ExtractOut shape
    fake.script("decide", DECISION, repeat=True)

    async def complete_json(
        purpose: str, schema: type[BaseModel], *args: Any, **kwargs: Any
    ) -> Any:
        if purpose == "classify" and not fake._scripts.get("classify"):
            fake.script("classify", auto_classify(schema))
        return await fake.complete_json(purpose, schema, *args, **kwargs)

    monkeypatch.setattr(gateway, "complete_json", complete_json)
    return fake


def extract_calls(fake: FakeLLM) -> list[Any]:
    """Extract uses purpose ``normalise`` with the ``ExtractOut`` schema (plan 1.4a)."""
    return [
        c
        for c in fake.calls_for("normalise")
        if c.schema is not None and c.schema.__name__ == "ExtractOut"
    ]
