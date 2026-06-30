"""Pydantic model for projection_config.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ProjectionField(BaseModel):
    path: str
    from_: str | None = Field(None, alias="from")
    type: str = "string"
    required: bool = False
    normalize: str | None = None

    model_config = {"populate_by_name": True}


class ProjectionConfig(BaseModel):
    fields: list[ProjectionField] = Field(default_factory=list)
    include_confidence: bool = True
    include_confidence_explanation: bool = False
    include_provenance: bool = False
    include_conflict_log: bool = False
    on_missing: Literal["null", "omit", "error"] = "null"

    @classmethod
    def from_file(cls, path: Path) -> "ProjectionConfig":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls.model_validate({k: v for k, v in raw.items() if not k.startswith("_")})

    @classmethod
    def full_canonical(cls) -> "ProjectionConfig":
        p = Path("config/default_projection.json")
        if p.exists():
            return cls.from_file(p)
        return cls()
