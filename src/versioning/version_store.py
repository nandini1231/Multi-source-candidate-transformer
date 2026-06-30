"""Version store — preserves canonical profile snapshots across runs.

In-memory by default.
Persists to data/versions/{candidate_id}.json when persist_dir is provided.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from src.models.canonical import CanonicalProfile, VersionSnapshot
from src.utils.logging import get_logger

logger = get_logger(__name__)


class VersionStore:

    def __init__(self, persist_dir: Path | None = None) -> None:
        self.persist_dir = persist_dir
        self._memory: dict[str, list[VersionSnapshot]] = {}

    def snapshot(self, profile: CanonicalProfile) -> VersionSnapshot:
        """Create and store a new VersionSnapshot for the profile."""
        history = self._memory.setdefault(profile.candidate_id, [])
        version_num = len(history) + 1

        snap = VersionSnapshot(
            version=version_num,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
            sources=list({s for snap in profile.versions for s in snap.sources}),
            snapshot_hash=self._compute_hash(profile),
        )
        history.append(snap)

        if self.persist_dir:
            self._persist(profile.candidate_id)

        return snap

    def history(self, candidate_id: str) -> list[VersionSnapshot]:
        """Return version history, oldest first."""
        if candidate_id not in self._memory and self.persist_dir:
            self._load(candidate_id)
        return self._memory.get(candidate_id, [])

    def _compute_hash(self, profile: CanonicalProfile) -> str:
        """SHA-256 of core profile fields (sorted keys). Stable across runs."""
        core = {
            "candidate_id": profile.candidate_id,
            "full_name": profile.full_name,
            "emails": sorted(profile.emails),
            "phones": sorted(profile.phones),
        }
        raw = json.dumps(core, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _persist(self, candidate_id: str) -> None:
        if not self.persist_dir:
            return
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        path = self.persist_dir / f"{candidate_id}.json"
        data = [s.model_dump() for s in self._memory.get(candidate_id, [])]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self, candidate_id: str) -> None:
        if not self.persist_dir:
            return
        path = self.persist_dir / f"{candidate_id}.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._memory[candidate_id] = [VersionSnapshot(**item) for item in data]
        except Exception as exc:
            logger.warning("Could not load version history for %s: %s", candidate_id, exc)
