"""Projector — applies ProjectionConfig to a CanonicalProfile to produce output JSON.

Canonical record is NEVER mutated here. Projection is read-only.

Path syntax supported in ProjectionField.from_:
    "full_name"          → profile.full_name
    "emails[0]"          → profile.emails[0] if exists
    "emails[1:]"         → profile.emails[1:] (remaining after primary)
    "skills[].name"      → [s.name for s in profile.skills]
    "location.country"   → profile.location.country
"""

from __future__ import annotations

import re
from typing import Any

from src.models.canonical import CanonicalProfile
from src.models.projection_config import ProjectionConfig, ProjectionField
from src.normalize.phones import normalize_phone
from src.normalize.skills import normalize_skill
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ProjectionError(Exception):
    """Raised when a required field is missing and on_missing='error'."""


class Projector:
    """Applies a ProjectionConfig to a CanonicalProfile."""

    def __init__(self, config: ProjectionConfig) -> None:
        self.config = config

    def project(self, profile: CanonicalProfile) -> dict[str, Any]:
        """
        Project a CanonicalProfile into a flat output dict.

        Returns:
            Output dict ready for JSON serialization.
        """
        output: dict[str, Any] = {}

        for pf in self.config.fields:
            source_path = pf.from_ or pf.path
            value = self._resolve_path(profile, source_path)

            # Apply normalization directive
            if value is not None:
                value = self._apply_normalization(value, pf.normalize)

            # Handle missing (empty lists are valid projected values)
            if value is None or value == "":
                if self.config.on_missing == "omit":
                    continue
                if self.config.on_missing == "error" and pf.required:
                    raise ProjectionError(
                        f"Required field '{pf.path}' is missing and on_missing='error'"
                    )
                output[pf.path] = None
            else:
                # Serialize Pydantic models to plain dicts
                from pydantic import BaseModel as _BM
                if isinstance(value, _BM):
                    value = value.model_dump()
                elif isinstance(value, list):
                    value = [v.model_dump() if isinstance(v, _BM) else v for v in value]
                output[pf.path] = value

        # Inject meta fields
        output = self._inject_meta_fields(output, profile)

        return output

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def _resolve_path(self, profile: CanonicalProfile, path: str) -> Any:
        """
        Resolve a path expression against the canonical profile.

        Handles: "field", "field[0]", "field[].subfield", "field.subfield"
        """
        if not path:
            return None

        # "field[].subfield" → list map
        m = re.match(r"^(\w+)\[\]\.([\w\.]+)$", path)
        if m:
            list_field, subfield = m.group(1), m.group(2)
            items = getattr(profile, list_field, None)
            if not isinstance(items, list):
                return None
            return [self._get_nested(item, subfield) for item in items]

        # "field[N:]" → list slice from index N to end
        m = re.match(r"^(\w+)\[(\d+):\]$", path)
        if m:
            list_field, start = m.group(1), int(m.group(2))
            items = getattr(profile, list_field, None)
            if isinstance(items, list):
                return items[start:]
            return None

        # "field[N]" → single index
        m = re.match(r"^(\w+)\[(\d+)\]$", path)
        if m:
            list_field, idx = m.group(1), int(m.group(2))
            items = getattr(profile, list_field, None)
            if isinstance(items, list) and idx < len(items):
                return items[idx]
            return None

        # "field.subfield" → nested attribute
        if "." in path:
            parts = path.split(".", 1)
            parent = getattr(profile, parts[0], None)
            if parent is None:
                return None
            return self._get_nested(parent, parts[1])

        # Simple field
        return getattr(profile, path, None)

    def _get_nested(self, obj: Any, path: str) -> Any:
        """Traverse a dot-separated path on an arbitrary object."""
        for part in path.split("."):
            if obj is None:
                return None
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                obj = getattr(obj, part, None)
        return obj

    # ------------------------------------------------------------------
    # Normalization directives
    # ------------------------------------------------------------------

    def _apply_normalization(self, value: Any, normalize: str | None) -> Any:
        """Apply a per-field normalization directive."""
        if normalize is None:
            return value

        directive = normalize.upper()

        if directive == "E164":
            if isinstance(value, str):
                return normalize_phone(value) or value
            if isinstance(value, list):
                return [normalize_phone(v) or v for v in value if v]
            return value

        if directive == "CANONICAL":
            if isinstance(value, str):
                return normalize_skill(value)
            if isinstance(value, list):
                return [normalize_skill(v) if isinstance(v, str) else v for v in value]
            return value

        return value

    # ------------------------------------------------------------------
    # Meta fields injection
    # ------------------------------------------------------------------

    def _inject_meta_fields(
        self, output: dict[str, Any], profile: CanonicalProfile
    ) -> dict[str, Any]:
        """Append optional metadata based on projection config toggles."""
        if self.config.include_confidence:
            output["overall_confidence"] = profile.overall_confidence
            output["data_quality_score"] = profile.data_quality_score
            output["status"] = profile.status.value
            if profile.review_reasons:
                output["review_reasons"] = profile.review_reasons

        if self.config.include_confidence_explanation:
            output["confidence_details"] = [
                cd.model_dump() for cd in profile.confidence_details
            ]

        if self.config.include_provenance:
            output["provenance"] = [p.model_dump() for p in profile.provenance]

        if self.config.include_conflict_log:
            output["conflict_log"] = [c.model_dump() for c in profile.conflict_log]

        return output

    # ------------------------------------------------------------------
    # Output validation
    # ------------------------------------------------------------------

    def validate_output(self, output: dict[str, Any]) -> list[str]:
        """Validate projected output against declared field types."""
        errors: list[str] = []
        type_checks = {
            "string": str,
            "number": (int, float),
            "object": dict,
            "object[]": list,
            "string[]": list,
        }

        for pf in self.config.fields:
            val = output.get(pf.path)
            if val is None:
                if pf.required:
                    errors.append(f"Required field '{pf.path}' is null in output")
                continue

            expected = type_checks.get(pf.type)
            if expected and not isinstance(val, expected):
                # Pydantic sub-models serialize as dict — treat as dict
                from pydantic import BaseModel as _BM
                if pf.type == "object" and isinstance(val, _BM):
                    continue
                errors.append(
                    f"Field '{pf.path}': expected {pf.type}, got {type(val).__name__}"
                )

        return errors
