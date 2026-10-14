"""Stats shapes (FR-60, FR-64)."""

from pydantic import BaseModel, ConfigDict


class LlmBudgetOut(BaseModel):
    provider: str
    requests_used: int
    requests_limit: int | None
    tokens_used: int
    tokens_limit: int | None


class StatsToday(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "date": "2026-10-14",
                    "items_in": 42,
                    "decided": 9,
                    "auto_handled": 3,
                    "discarded": 20,
                    "by_status": {"awaiting_approval": 6, "discarded": 20, "done": 16},
                    "by_niche": {"news_radar": 30, "unassigned": 12},
                    "llm": [
                        {
                            "provider": "gemini",
                            "requests_used": 120,
                            "requests_limit": 500,
                            "tokens_used": 84000,
                            "tokens_limit": None,
                        }
                    ],
                    "laya_mode": "shadow",
                    "laya_agreement": 0.87,
                }
            ]
        }
    )

    date: str
    items_in: int
    decided: int
    auto_handled: int
    discarded: int
    by_status: dict[str, int]
    by_niche: dict[str, int]
    llm: list[LlmBudgetOut]
    laya_mode: str
    laya_agreement: float | None
