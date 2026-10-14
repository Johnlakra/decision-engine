"""Niche API shapes (FR-70, ADR 0009)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

LayaMode = Literal["off", "shadow", "on"]


class NicheRow(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "inbox",
                    "label": "Inbox and DMs",
                    "description": "a personal or work email or direct message",
                    "enabled": True,
                    "autonomy": "ask",
                    "auto_actions": [],
                    "source": "yaml",
                    "version": 1,
                    "laya_mode": "shadow",
                }
            ]
        }
    )

    name: str
    label: str
    description: str
    enabled: bool
    autonomy: Literal["suggest", "ask", "auto"]
    auto_actions: list[str]
    source: Literal["yaml", "db"]
    version: int
    laya_mode: LayaMode


class NicheList(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "data": [
                        {
                            "name": "generic",
                            "label": "Generic",
                            "description": "anything that does not fit another niche",
                            "enabled": True,
                            "autonomy": "ask",
                            "auto_actions": [],
                            "source": "yaml",
                            "version": 1,
                            "laya_mode": "shadow",
                        }
                    ]
                }
            ]
        }
    )

    data: list[NicheRow]


class NicheDetail(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "inbox",
                    "source": "yaml",
                    "version": 1,
                    "config": {"name": "inbox", "enabled": True, "autonomy": "ask"},
                    "yaml": "name: inbox\nenabled: true\nautonomy: ask\n",
                }
            ]
        }
    )

    name: str
    source: Literal["yaml", "db"]
    version: int
    config: dict[str, Any]
    yaml: str
