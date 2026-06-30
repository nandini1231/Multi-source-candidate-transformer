"""Abstract base class for all source adapters.

Contract:
- parse() returns list[SourceRecord], one per candidate found.
- Adapters parse ONLY — no normalization, validation, or merging.
- All errors surface via SourceRecord.parse_errors — never raises.
- Adding a new source = subclass BaseAdapter; nothing else changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.models.source_record import SourceRecord, SourceType
from src.utils.logging import get_logger

logger = get_logger(__name__)


class BaseAdapter(ABC):
    """Interface every source adapter must implement."""

    source_type: SourceType

    @abstractmethod
    def parse(self, file_path: Path) -> list[SourceRecord]:
        """Parse a source file. Never raises — errors go into SourceRecord.parse_errors."""
        ...

    @abstractmethod
    def can_handle(self, file_path: Path) -> bool:
        """Return True if this adapter can process the given file."""
        ...

    def safe_parse(self, file_path: Path) -> list[SourceRecord]:
        """Wrapper around parse() that catches unexpected exceptions."""
        try:
            return self.parse(file_path)
        except Exception as exc:
            logger.warning("Unhandled error parsing %s: %s", file_path, exc)
            return [SourceRecord(
                source_type=self.source_type,
                source_file=str(file_path),
                parse_errors=[f"Unhandled parse error: {exc}"],
            )]
