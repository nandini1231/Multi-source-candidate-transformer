"""Recruiter CSV adapter.

Parses CSV exports with columns: name, email, phone, current_company, title, linkedin, location.
Column names are case-insensitive. Extra columns are ignored. Missing columns produce warnings.
Multi-value fields (emails, phones) split on ';' or ','.
"""

from __future__ import annotations

import csv
from pathlib import Path

from src.adapters.base import BaseAdapter
from src.models.source_record import ExtractionMethod, RawField, SourceRecord, SourceType
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Canonical CSV header → SourceRecord field
_COLUMN_MAP: dict[str, str] = {
    "name": "full_name",
    "full_name": "full_name",
    "fullname": "full_name",
    "email": "emails",
    "email_address": "emails",
    "emailaddress": "emails",
    "phone": "phones",
    "phone_number": "phones",
    "phonenumber": "phones",
    "mobile": "phones",
    "current_company": "current_company",
    "company": "current_company",
    "employer": "current_company",
    "title": "current_title",
    "job_title": "current_title",
    "jobtitle": "current_title",
    "position": "current_title",
    "headline": "headline",
    "summary": "headline",
    "linkedin": "linkedin_url",
    "linkedin_url": "linkedin_url",
    "linkedinurl": "linkedin_url",
    "github": "github_url",
    "github_url": "github_url",
    "location": "location_raw",
    "city": "location_raw",
    "address": "location_raw",
    "years_experience": "years_experience",
    "experience_years": "years_experience",
}


class RecruiterCSVAdapter(BaseAdapter):
    """Parses recruiter CSV exports into SourceRecord objects."""

    source_type = SourceType.RECRUITER_CSV

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".csv"

    def parse(self, file_path: Path) -> list[SourceRecord]:
        """Parse each CSV row into a SourceRecord. Never raises."""
        records: list[SourceRecord] = []

        try:
            with open(file_path, encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames is None:
                    return [SourceRecord(
                        source_type=self.source_type,
                        source_file=str(file_path),
                        parse_errors=["CSV file has no headers"],
                    )]

                # Build normalised header → original header map
                header_map: dict[str, str] = {
                    h.strip().lower(): h for h in reader.fieldnames if h
                }
                warnings: list[str] = []
                for norm_h in header_map:
                    if norm_h not in _COLUMN_MAP:
                        warnings.append(f"Unrecognised column: '{norm_h}' — ignored")

                for row_num, row in enumerate(reader, start=2):
                    record = self._parse_row(row, header_map, str(file_path))
                    record.parse_warnings.extend(warnings)
                    records.append(record)

        except FileNotFoundError:
            records.append(SourceRecord(
                source_type=self.source_type,
                source_file=str(file_path),
                parse_errors=[f"File not found: {file_path}"],
            ))
        except Exception as exc:
            records.append(SourceRecord(
                source_type=self.source_type,
                source_file=str(file_path),
                parse_errors=[f"CSV parse error: {exc}"],
            ))

        logger.info("CSV adapter: parsed %d record(s) from %s", len(records), file_path.name)
        return records

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_row(
        self,
        row: dict[str, str],
        header_map: dict[str, str],
        source_file: str,
    ) -> SourceRecord:
        record = SourceRecord(
            source_type=self.source_type,
            source_file=source_file,
        )

        for norm_header, original_header in header_map.items():
            target_field = _COLUMN_MAP.get(norm_header)
            if target_field is None:
                continue

            cell = row.get(original_header, "").strip()
            if not cell:
                continue

            rf = self._make_field(cell)

            if target_field == "emails":
                record.emails.extend(self._split_multi(cell))
            elif target_field == "phones":
                record.phones.extend(self._split_multi(cell))
            elif target_field == "full_name":
                record.full_name = rf
            elif target_field == "current_company":
                record.current_company = rf
            elif target_field == "current_title":
                record.current_title = rf
            elif target_field == "headline":
                record.headline = rf
            elif target_field == "linkedin_url":
                record.linkedin_url = rf
            elif target_field == "github_url":
                record.github_url = rf
            elif target_field == "location_raw":
                record.location_raw = rf
            elif target_field == "years_experience":
                record.years_experience = rf

        return record

    def _make_field(self, value: str) -> RawField:
        return RawField(
            value=value,
            source=SourceType.RECRUITER_CSV,
            extraction_method=ExtractionMethod.DIRECT,
            raw_text=value,
        )

    def _split_multi(self, cell: str) -> list[RawField]:
        """Split a cell on ';' or ',' for multi-value fields."""
        separators = [";", ","] if ";" in cell else [","]
        parts = [cell]
        for sep in separators:
            new_parts = []
            for p in parts:
                new_parts.extend(p.split(sep))
            parts = new_parts
        return [
            RawField(
                value=p.strip(),
                source=SourceType.RECRUITER_CSV,
                extraction_method=ExtractionMethod.DIRECT,
                raw_text=p.strip(),
            )
            for p in parts if p.strip()
        ]
