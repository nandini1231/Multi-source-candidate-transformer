"""Resume adapter — handles PDF and DOCX files.

Extraction strategy (layered):
  1. Raw text extraction with optional layout reconstruction (PDF).
  2. Section detection via heading ontology (fuzzy keyword match).
  3. Specialized field extractors (name, skills, education, experience/projects).
  4. Conservative fallbacks — skip ambiguous values rather than guess.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import phonenumbers

from src.adapters.base import BaseAdapter
from src.models.source_record import ExtractionMethod, RawField, SourceRecord, SourceType
from src.utils.helpers import is_present_marker
from src.utils.logging import get_logger

logger = get_logger(__name__)

_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc"}

# Section heading keywords (lower-case) — maps many resume variants to canonical sections
_SECTION_KEYWORDS: dict[str, list[str]] = {
    "CONTACT": [
        "contact", "personal information", "contact information", "contact details",
    ],
    "SUMMARY": [
        "summary", "profile", "objective", "about me", "professional summary",
        "career objective", "about",
    ],
    "EXPERIENCE": [
        "experience", "work experience", "employment", "work history",
        "professional experience", "career history", "employment history",
        "internship", "internships", "work",
    ],
    "EDUCATION": [
        "education", "academic", "qualifications", "educational background",
        "academic background", "degrees", "academics",
    ],
    "SKILLS": [
        "skills", "technical skills", "core competencies", "technologies",
        "expertise", "key skills", "competencies", "tech stack",
        "technical skills and interests", "skills and interests",
    ],
    "PROJECTS": [
        "projects", "project experience", "key projects", "personal projects",
        "academic projects",
    ],
    "CERTIFICATIONS": [
        "certifications", "certificates", "licenses",
    ],
    "ACHIEVEMENTS": ["achievements", "awards", "honors", "honours"],
    "COURSEWORK": ["coursework", "relevant coursework", "courses"],
}

# Email pattern
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Date range patterns
_DATE_RANGE_RE = re.compile(
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,\.]*\d{2,4}"
    r"(?:\s*[-–—to]+\s*"
    r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,\.]*\d{2,4}|present|current|now))?",
    re.IGNORECASE,
)
_YEAR_RANGE_RE = re.compile(
    r"\b((?:19|20)\d{2})\s*[-–—to]+\s*((?:19|20)\d{2}|present|current|now)\b",
    re.IGNORECASE,
)
# Broader range for experience extraction — validator enforces configured year bounds.
_BROAD_YEAR_RANGE_RE = re.compile(
    r"\b(\d{4})\s*[-–—to]+\s*(\d{4}|present|current|now)\b",
    re.IGNORECASE,
)
_SINGLE_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

_DEGREE_RE = re.compile(
    r"\b(b\.?tech|b\.?e|b\.?sc|b\.?com|b\.?a|m\.?tech|m\.?sc|m\.?s|m\.?b\.?a|"
    r"ph\.?d|bachelor|master|doctorate|diploma|associate|intermediate|class\s+\d+|"
    r"10th|12th)\b",
    re.IGNORECASE,
)

_INSTITUTION_RE = re.compile(
    r"\b(university|institute|institution|college|school|academy|nit|iit|iiit)\b",
    re.IGNORECASE,
)

_SKILL_LABEL_RE = re.compile(
    r"^(programming languages|languages|expertise|tools/frameworks|tools|frameworks|"
    r"soft skills|technical skills|databases|platforms)[:\s]+(.+)$",
    re.IGNORECASE,
)

_CONTACT_SPLIT_RE = re.compile(
    r"\s+(?:Email|E-mail|Mobile|Phone|Tel|LinkedIn|GitHub|LeetCode|Portfolio)[:\s]",
    re.IGNORECASE,
)

_NAME_LINE_RE = re.compile(
    r"^[A-Z][a-zA-Z'\-]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-zA-Z'\-]+){0,3}$",
)

_BULLET_ONLY_RE = re.compile(r"^[•●▪◦\-–—]\s*$")

_LOCATION_SUFFIX_RE = re.compile(
    r"^(.+?)\s+([A-Z][a-zA-Z\s]+),\s*(India|USA|UK|United States|United Kingdom|Canada|Australia)\s*$",
)


class ResumeAdapter(BaseAdapter):
    """Parses PDF and DOCX resume files into SourceRecord objects."""

    source_type = SourceType.RESUME

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in _SUPPORTED_EXTENSIONS

    def parse(self, file_path: Path) -> list[SourceRecord]:
        """Parse one resume file → one SourceRecord."""
        record = SourceRecord(
            source_type=self.source_type,
            source_file=str(file_path),
        )

        ext = file_path.suffix.lower()
        try:
            if ext == ".pdf":
                text = self._extract_text_pdf(file_path)
            elif ext in {".docx", ".doc"}:
                text = self._extract_text_docx(file_path)
            else:
                record.parse_errors.append(f"Unsupported file extension: {ext}")
                return [record]
        except Exception as exc:
            record.parse_errors.append(f"Text extraction failed: {exc}")
            logger.warning("Resume extraction failed for %s: %s", file_path.name, exc)
            return [record]

        if not text.strip():
            record.parse_warnings.append("Extracted text is empty")
            return [record]

        sections = self._detect_sections(text)
        self._fill_record(record, text, sections)
        logger.info("Resume adapter: parsed %s", file_path.name)
        return [record]

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------

    def _extract_text_pdf(self, file_path: Path) -> str:
        import pdfplumber

        pages: list[str] = []
        with pdfplumber.open(str(file_path)) as pdf:
            for page in pdf.pages:
                layout_text = self._reconstruct_page_layout(page)
                if layout_text:
                    pages.append(layout_text)
        return "\n".join(pages)

    def _reconstruct_page_layout(self, page: Any) -> str:
        """
        Rebuild page text using word positions so two-column headers
        (name left, contact right) become separate lines.
        """
        words = page.extract_words(x_tolerance=3, y_tolerance=3) or []
        if not words:
            return page.extract_text() or ""

        lines = self._group_words_into_lines(words)
        page_width = float(page.width or 612)
        reconstructed: list[str] = []

        for line_words in lines:
            line_text = self._line_words_to_text(line_words, page_width)
            if line_text.strip():
                reconstructed.append(line_text)

        return "\n".join(reconstructed)

    def _group_words_into_lines(
        self, words: list[dict[str, Any]], y_tolerance: float = 5.0
    ) -> list[list[dict[str, Any]]]:
        sorted_words = sorted(words, key=lambda w: (round(w["top"], 1), w["x0"]))
        lines: list[list[dict[str, Any]]] = []
        current_line: list[dict[str, Any]] = []
        current_top: float | None = None

        for word in sorted_words:
            top = round(word["top"], 1)
            if current_top is None or abs(top - current_top) <= y_tolerance:
                current_line.append(word)
                current_top = top if current_top is None else current_top
            else:
                if current_line:
                    lines.append(current_line)
                current_line = [word]
                current_top = top

        if current_line:
            lines.append(current_line)

        return lines

    def _line_words_to_text(
        self, words: list[dict[str, Any]], page_width: float
    ) -> str:
        if not words:
            return ""

        sorted_words = sorted(words, key=lambda w: w["x0"])
        if len(sorted_words) == 1:
            return sorted_words[0]["text"]

        # Detect a column gap (two-column layout)
        max_gap = 0.0
        split_idx = 0
        for i in range(len(sorted_words) - 1):
            gap = sorted_words[i + 1]["x0"] - sorted_words[i]["x1"]
            if gap > max_gap:
                max_gap = gap
                split_idx = i + 1

        min_column_gap = max(page_width * 0.12, 40.0)
        if max_gap >= min_column_gap and split_idx > 0:
            left = sorted_words[:split_idx]
            right = sorted_words[split_idx:]
            left_text = " ".join(w["text"] for w in left)
            right_text = " ".join(w["text"] for w in right)
            return f"{left_text}\n{right_text}"

        return " ".join(w["text"] for w in sorted_words)

    def _extract_text_docx(self, file_path: Path) -> str:
        from docx import Document

        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    # ------------------------------------------------------------------
    # Section detection
    # ------------------------------------------------------------------

    def _detect_sections(self, text: str) -> dict[str, str]:
        """Split text into named sections using heading keyword detection."""
        lines = text.splitlines()
        sections: dict[str, str] = {"FULL": text}
        current_section = "HEADER"
        section_lines: dict[str, list[str]] = {current_section: []}

        for line in lines:
            stripped = line.strip()
            detected = self._identify_section_header(stripped)
            if detected:
                current_section = detected
                if current_section not in section_lines:
                    section_lines[current_section] = []
            else:
                section_lines.setdefault(current_section, []).append(line)

        for sec, sec_lines in section_lines.items():
            sections[sec] = "\n".join(sec_lines)

        return sections

    def _identify_section_header(self, line: str) -> str | None:
        """Return section name if line is a section heading, else None."""
        if not line or len(line) > 60:
            return None
        lower = line.lower().strip(" :•–—-|")
        word_count = len(lower.split())
        # Body sentences are not section headings
        if word_count > 6:
            return None

        for section_name, keywords in _SECTION_KEYWORDS.items():
            for kw in keywords:
                if lower == kw or lower.rstrip(":") == kw:
                    return section_name
                if lower.startswith(kw + ":"):
                    return section_name
                # ALL-CAPS headings (EXPERIENCE, SKILLS, ...)
                if line.strip().isupper() and word_count <= 3 and lower == kw:
                    return section_name
                # Multi-word keywords only (e.g. "work experience", "technical skills")
                if " " in kw and (
                    lower == kw
                    or lower.startswith(kw + " ")
                    or lower.startswith(kw + ":")
                ):
                    return section_name
        return None

    # ------------------------------------------------------------------
    # Record population
    # ------------------------------------------------------------------

    def _fill_record(
        self, record: SourceRecord, full_text: str, sections: dict[str, str]
    ) -> None:
        header_text = sections.get("HEADER", "") + "\n" + sections.get("CONTACT", "")
        full_text_for_contact = sections.get("FULL", full_text)

        record.emails = self._extract_emails(full_text_for_contact)
        record.phones = self._extract_phones(full_text_for_contact)

        name = self._extract_name(sections.get("HEADER", full_text[:600]), full_text)
        if name:
            record.full_name = name

        summary_text = sections.get("SUMMARY", "")
        if summary_text.strip():
            record.headline = self._make_field(
                summary_text.strip()[:200], ExtractionMethod.HEURISTIC
            )

        location = self._extract_location(header_text)
        if location:
            record.location_raw = self._make_field(location, ExtractionMethod.REGEX)

        linkedin = self._extract_linkedin(full_text_for_contact)
        if linkedin:
            record.linkedin_url = self._make_field(linkedin, ExtractionMethod.REGEX)

        github = self._extract_url(full_text_for_contact, "github")
        if github:
            record.github_url = self._make_field(github, ExtractionMethod.REGEX)

        leetcode = self._extract_leetcode(full_text_for_contact)
        if leetcode:
            record.leetcode_url = self._make_field(leetcode, ExtractionMethod.REGEX)

        portfolio = self._extract_portfolio_url(full_text_for_contact)
        if portfolio:
            record.portfolio_url = self._make_field(portfolio, ExtractionMethod.REGEX)

        record.skills_raw = self._extract_skills(sections.get("SKILLS", ""))

        # Experience only from EXPERIENCE section (not projects)
        record.experience_raw = self._extract_experience(sections.get("EXPERIENCE", ""))
        record.projects_raw = self._extract_projects(sections.get("PROJECTS", ""))

        record.education_raw = self._extract_education(sections.get("EDUCATION", ""))

    def _merge_section_texts(self, *parts: str) -> str:
        non_empty = [p.strip() for p in parts if p and p.strip()]
        return "\n\n".join(non_empty)

    # ------------------------------------------------------------------
    # Field extractors
    # ------------------------------------------------------------------

    def _extract_emails(self, text: str) -> list[RawField]:
        found = list(dict.fromkeys(_EMAIL_RE.findall(text)))
        return [
            RawField(
                value=e.lower(),
                source=SourceType.RESUME,
                extraction_method=ExtractionMethod.REGEX,
                raw_text=e,
            )
            for e in found
        ]

    def _extract_phones(self, text: str, default_region: str = "IN") -> list[RawField]:
        found: list[RawField] = []
        seen: set[str] = set()
        try:
            for match in phonenumbers.PhoneNumberMatcher(text, default_region):
                e164 = phonenumbers.format_number(
                    match.number, phonenumbers.PhoneNumberFormat.E164
                )
                if e164 not in seen:
                    seen.add(e164)
                    found.append(
                        RawField(
                            value=e164,
                            source=SourceType.RESUME,
                            extraction_method=ExtractionMethod.REGEX,
                            raw_text=match.raw_string,
                        )
                    )
        except Exception:
            pass
        return found

    def _extract_name(self, header_text: str, full_text: str = "") -> RawField | None:
        """
        Multi-strategy name extraction:
          1. Text before contact keywords on merged header lines
          2. Standalone name line (1–4 capitalized tokens)
          3. First line of reconstructed layout header
        """
        search_text = header_text or full_text[:600]
        for line in search_text.splitlines():
            line = line.strip()
            if not line:
                continue

            merged_name = self._name_from_merged_contact_line(line)
            if merged_name:
                return self._make_field(merged_name, ExtractionMethod.HEURISTIC)

            if self._looks_like_name_line(line):
                return self._make_field(line, ExtractionMethod.HEURISTIC)

        return None

    def _name_from_merged_contact_line(self, line: str) -> str | None:
        """Extract name from 'Nandini Email: ...' or 'Name | email | phone' style lines."""
        if "|" in line and "@" in line:
            before_pipe = line.split("|", 1)[0].strip()
            if before_pipe and "@" not in before_pipe and self._looks_like_name(before_pipe):
                return before_pipe

        if "@" in line:
            before_at = line.split("@", 1)[0].strip()
            m = _CONTACT_SPLIT_RE.search(before_at)
            if m:
                candidate = before_at[: m.start()].strip()
                if self._looks_like_name(candidate):
                    return candidate

        m = _CONTACT_SPLIT_RE.search(line)
        if m:
            candidate = line[: m.start()].strip()
            if self._looks_like_name(candidate):
                return candidate

        return None

    def _looks_like_name_line(self, line: str) -> bool:
        if not line or len(line) > 60:
            return False
        if any(char.isdigit() for char in line):
            return False
        if "@" in line or "http" in line.lower():
            return False
        if self._identify_section_header(line):
            return False
        if _CONTACT_SPLIT_RE.search(line):
            return False
        return bool(_NAME_LINE_RE.match(line))

    def _looks_like_name(self, text: str) -> bool:
        text = text.strip()
        if not text or len(text) > 60:
            return False
        if any(char.isdigit() for char in text):
            return False
        if "@" in text or "http" in text.lower():
            return False
        return bool(_NAME_LINE_RE.match(text))

    def _extract_location(self, text: str) -> str | None:
        _LOC_RE = re.compile(
            r"(?:location|address|city|based in|located in)[:\s]+([^\n]+)",
            re.IGNORECASE,
        )
        m = _LOC_RE.search(text)
        if m:
            return m.group(1).strip()

        _CITY_RE = re.compile(r"\b([A-Z][a-zA-Z\s]+),\s*([A-Z][a-zA-Z\s]+)\b")
        m2 = _CITY_RE.search(text)
        if m2:
            return m2.group(0).strip()

        return None

    def _extract_linkedin(self, text: str) -> str | None:
        url = self._extract_url(text, "linkedin")
        if url:
            return url
        m = re.search(
            r"linkedin[:\s]+(?:https?://(?:www\.)?linkedin\.com/in/)?([^\s,\n]+)",
            text,
            re.IGNORECASE,
        )
        if m:
            handle = m.group(1).strip("/")
            if "linkedin.com" in handle.lower():
                if not handle.startswith("http"):
                    return f"https://{handle.lstrip('/')}"
                return handle
            return f"https://linkedin.com/in/{handle}"
        return None

    def _extract_leetcode(self, text: str) -> str | None:
        url = self._extract_url(text, "leetcode")
        if url:
            return url
        m = re.search(
            r"leetcode[:\s]+(?:https?://(?:www\.)?leetcode\.com/u?/?)?([^\s,\n]+)",
            text,
            re.IGNORECASE,
        )
        if not m:
            return None
        handle = m.group(1).strip("/")
        if handle.startswith("http"):
            return handle
        return f"https://leetcode.com/u/{handle}"

    def _extract_portfolio_url(self, text: str) -> str | None:
        m = re.search(
            r"(?:portfolio|website)[:\s]+(https?://[^\s,\n]+)",
            text,
            re.IGNORECASE,
        )
        return m.group(1).strip() if m else None

    _URL_RE = re.compile(r"https?://[^\s,\"'<>]+")

    def _extract_urls_from_text(self, text: str) -> list[str]:
        return list(dict.fromkeys(self._URL_RE.findall(text)))

    def _extract_url(self, text: str, platform: str) -> str | None:
        pattern = re.compile(
            rf"https?://(?:www\.)?{re.escape(platform)}\.com/[^\s,\"'<>]+",
            re.IGNORECASE,
        )
        m = pattern.search(text)
        return m.group(0) if m else None

    def _extract_skills(self, skills_text: str) -> list[RawField]:
        """Extract skills from labeled subsections or comma/bullet lists."""
        if not skills_text.strip():
            return []

        results: list[RawField] = []
        seen: set[str] = set()

        for raw_line in skills_text.splitlines():
            line = raw_line.strip().lstrip("•●▪◦- ")
            if not line:
                continue

            label_match = _SKILL_LABEL_RE.match(line)
            payload = label_match.group(2) if label_match else line
            tokens = re.split(r"[,|/]|(?<=\))\s+(?=[A-Z])", payload)

            for token in tokens:
                token = token.strip(" .:–—()")
                if not token or len(token) < 2 or len(token) > 60:
                    continue
                if _EMAIL_RE.search(token):
                    continue
                if self._looks_like_phone_token(token):
                    continue
                lower = token.lower()
                if lower in seen:
                    continue
                if _SKILL_LABEL_RE.match(token):
                    continue
                seen.add(lower)
                results.append(
                    RawField(
                        value=token,
                        source=SourceType.RESUME,
                        extraction_method=ExtractionMethod.REGEX,
                        raw_text=token,
                    )
                )

        return results

    def _looks_like_phone_token(self, token: str) -> bool:
        """Return True if token looks like a phone number, not a skill."""
        digits = sum(ch.isdigit() for ch in token)
        if digits >= 7 and re.search(r"[\d+\-().\s]", token):
            return True
        return False

    def _extract_experience(self, experience_text: str) -> list[RawField]:
        """Extract job entries from the EXPERIENCE section only."""
        if not experience_text.strip():
            return []

        entries: list[RawField] = []
        blocks = self._split_experience_blocks(experience_text)

        for block in blocks:
            entry = self._parse_experience_block(block)
            if entry and (entry.get("company") or entry.get("title")):
                entries.append(
                    RawField(
                        value=entry,
                        source=SourceType.RESUME,
                        extraction_method=ExtractionMethod.HEURISTIC,
                        raw_text=block[:200],
                    )
                )

        return entries

    def _extract_projects(self, projects_text: str) -> list[RawField]:
        """Extract project entries from the PROJECTS section."""
        if not projects_text.strip():
            return []

        entries: list[RawField] = []
        blocks = self._split_experience_blocks(projects_text)

        for block in blocks:
            entry = self._parse_project_block(block)
            if entry and entry.get("title"):
                entries.append(
                    RawField(
                        value=entry,
                        source=SourceType.RESUME,
                        extraction_method=ExtractionMethod.HEURISTIC,
                        raw_text=block[:200],
                    )
                )

        return entries

    def _extract_education(self, education_text: str) -> list[RawField]:
        """Extract education entries using institution-based block splitting."""
        if not education_text.strip():
            return []

        entries: list[RawField] = []
        blocks = self._split_education_blocks(education_text)

        for block in blocks:
            entry = self._parse_education_block(block)
            if entry and entry.get("institution"):
                entries.append(
                    RawField(
                        value=entry,
                        source=SourceType.RESUME,
                        extraction_method=ExtractionMethod.HEURISTIC,
                        raw_text=block[:200],
                    )
                )

        return entries

    # ------------------------------------------------------------------
    # Block splitting and parsing helpers
    # ------------------------------------------------------------------

    def _split_experience_blocks(self, text: str) -> list[str]:
        """Split experience/projects into role blocks."""
        text = text.strip()
        if not text:
            return []

        # Project-style: top-level bullet entries
        if re.search(r"^[•●▪]", text, re.MULTILINE):
            parts = re.split(r"\n(?=\s*[•●▪])", text)
            cleaned: list[str] = []
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                part = re.sub(r"^[•●▪]\s*", "", part)
                cleaned.append(part)
            return cleaned

        # Standard: blank-line separated blocks
        parts = re.split(r"\n{2,}", text)
        if len(parts) > 1:
            return [p.strip() for p in parts if p.strip()]

        # Single-newline jobs: Title / Company | Dates / Summary
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        blocks: list[str] = []
        current: list[str] = []

        for i, line in enumerate(lines):
            if current:
                next_line = lines[i + 1] if i + 1 < len(lines) else ""
                current_has_job = any(
                    "|" in ln or _DATE_RANGE_RE.search(ln) or _YEAR_RANGE_RE.search(ln)
                    for ln in current
                )
                starts_new_role = (
                    current_has_job
                    and "|" not in line
                    and not _DATE_RANGE_RE.search(line)
                    and not _YEAR_RANGE_RE.search(line)
                    and bool(next_line)
                    and (
                        "|" in next_line
                        or _DATE_RANGE_RE.search(next_line)
                        or _YEAR_RANGE_RE.search(next_line)
                    )
                )
                if starts_new_role:
                    blocks.append("\n".join(current))
                    current = [line]
                    continue

            current.append(line)

        if current:
            blocks.append("\n".join(current))

        return blocks if blocks else [text]

    def _education_block_has_institution(self, block_lines: list[str]) -> bool:
        for ln in block_lines:
            head = ln.split("|")[0].strip()
            if _INSTITUTION_RE.search(head):
                return True
        return False

    def _education_block_starts_with_degree(self, block_lines: list[str]) -> bool:
        if not block_lines:
            return False
        first = block_lines[0]
        head = first.split("|")[0].strip()
        return bool(_DEGREE_RE.search(first)) and not _INSTITUTION_RE.search(head)

    def _split_education_blocks(self, text: str) -> list[str]:
        """Split education by institution lines, not by embedded year ranges."""
        lines = [
            ln.strip()
            for ln in text.splitlines()
            if ln.strip() and not _BULLET_ONLY_RE.match(ln.strip())
        ]

        blocks: list[str] = []
        current: list[str] = []

        for line in lines:
            head = line.split("|")[0].strip()
            is_institution_line = bool(
                _INSTITUTION_RE.search(head)
                and not _DEGREE_RE.search(line)
                and not _YEAR_RANGE_RE.fullmatch(line.strip())
            )
            is_degree_line = bool(_DEGREE_RE.search(line)) and not is_institution_line

            if current:
                has_inst = self._education_block_has_institution(current)
                starts_degree = self._education_block_starts_with_degree(current)

                if is_degree_line and has_inst and starts_degree:
                    # Degree-first: new degree after a complete degree+institution pair
                    blocks.append("\n".join(current))
                    current = [line]
                elif is_institution_line and has_inst and not starts_degree:
                    # Institution-first: new institution after a complete block
                    blocks.append("\n".join(current))
                    current = [line]
                else:
                    current.append(line)
            else:
                current.append(line)

        if current:
            blocks.append("\n".join(current))

        if not blocks:
            return [text.strip()] if text.strip() else []

        return blocks

    def _looks_like_project_block(self, block: str) -> bool:
        first_line = block.splitlines()[0] if block.splitlines() else block
        if re.match(r"^[•●▪◦]", first_line.strip()):
            return True
        if "◦" in block:
            return True
        if re.search(r"\b(frontend|backend|database)\s*:", block, re.IGNORECASE):
            return True
        # Em dash in project titles (not date hyphens)
        if " – " in first_line and not re.search(r"\d{4}", first_line):
            return True
        return False

    def _parse_project_block(self, block: str) -> dict[str, Any]:
        """Parse a project block into a structured project entry."""
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        entry: dict[str, Any] = {
            "title": None,
            "summary": None,
            "url": None,
            "tech_stack": None,
        }

        if not lines:
            return entry

        entry["title"] = lines[0].lstrip("•●▪◦- ").strip()

        detail_lines: list[str] = []
        for ln in lines[1:]:
            cleaned = ln.lstrip("•●▪◦- ").strip()
            if re.search(r"\b(frontend|backend|database)\s*:", cleaned, re.IGNORECASE):
                entry["tech_stack"] = cleaned
                continue
            urls = self._extract_urls_from_text(cleaned)
            if urls and not entry["url"]:
                entry["url"] = urls[0]
            if cleaned and not _BULLET_ONLY_RE.match(cleaned):
                detail_lines.append(cleaned)

        if detail_lines:
            entry["summary"] = " ".join(detail_lines)[:400]

        if not entry["url"]:
            block_urls = self._extract_urls_from_text(block)
            if block_urls:
                entry["url"] = block_urls[0]

        return entry

    def _parse_experience_block(self, block: str) -> dict[str, Any]:
        """Extract company, title, start, end, summary from a text block."""
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        entry: dict[str, Any] = {
            "company": None,
            "title": None,
            "start": None,
            "end": None,
            "summary": None,
        }

        summary_parts: list[str] = []

        for ln in lines:
            if "|" in ln:
                company_part, _, meta_part = ln.partition("|")
                entry["company"] = company_part.strip() or entry["company"]
                date_text = meta_part.strip()
                dm = (
                    _DATE_RANGE_RE.search(date_text)
                    or _YEAR_RANGE_RE.search(date_text)
                    or _BROAD_YEAR_RANGE_RE.search(date_text)
                )
                if dm and not entry["start"]:
                    dp = re.split(
                        r"\s*[-–—to]+\s*",
                        dm.group(0),
                        maxsplit=1,
                        flags=re.IGNORECASE,
                    )
                    entry["start"] = dp[0].strip() if dp else None
                    entry["end"] = dp[1].strip() if len(dp) > 1 else None
                    if entry["end"] and is_present_marker(str(entry["end"])):
                        entry["end"] = None
                continue

            if (
                _DATE_RANGE_RE.search(ln)
                or _YEAR_RANGE_RE.search(ln)
                or _BROAD_YEAR_RANGE_RE.search(ln)
            ):
                dm = (
                    _DATE_RANGE_RE.search(ln)
                    or _YEAR_RANGE_RE.search(ln)
                    or _BROAD_YEAR_RANGE_RE.search(ln)
                )
                if dm and not entry["start"]:
                    dp = re.split(
                        r"\s*[-–—to]+\s*",
                        dm.group(0),
                        maxsplit=1,
                        flags=re.IGNORECASE,
                    )
                    entry["start"] = dp[0].strip() if dp else None
                    entry["end"] = dp[1].strip() if len(dp) > 1 else None
                    if entry["end"] and is_present_marker(str(entry["end"])):
                        entry["end"] = None
                continue

            if not entry["title"]:
                entry["title"] = ln
            else:
                summary_parts.append(ln)

        if summary_parts:
            entry["summary"] = " ".join(summary_parts)[:400]

        return entry

    def _parse_education_block(self, block: str) -> dict[str, Any]:
        """Extract institution, degree, field, start_year, end_year from a block."""
        lines = [
            ln.strip()
            for ln in block.splitlines()
            if ln.strip() and not _BULLET_ONLY_RE.match(ln.strip())
        ]
        entry: dict[str, Any] = {
            "institution": None,
            "degree": None,
            "field": None,
            "location": None,
            "start_year": None,
            "end_year": None,
        }

        year_range = _YEAR_RANGE_RE.search(block)
        if year_range:
            entry["start_year"] = year_range.group(1)
            end_part = year_range.group(2)
            if end_part and not is_present_marker(end_part):
                entry["end_year"] = end_part
        else:
            years = _SINGLE_YEAR_RE.findall(block)
            if years:
                entry["end_year"] = years[-1]

        for line in lines:
            line_no_years = _YEAR_RANGE_RE.sub("", line).strip()
            line_no_years = _SINGLE_YEAR_RE.sub("", line_no_years).strip(" ;,|")

            if _DEGREE_RE.search(line):
                degree_text = _YEAR_RANGE_RE.sub("", line).strip()
                degree_text = _SINGLE_YEAR_RE.sub("", degree_text).strip(" ;,|")
                entry["degree"] = degree_text or line
                self._maybe_set_degree_field(entry, degree_text)
            elif "|" in line and _INSTITUTION_RE.search(head := line.split("|")[0].strip()):
                inst_text = head.lstrip("•●▪◦- ").strip()
                inst, location = self._split_institution_location(inst_text)
                entry["institution"] = inst
                if location:
                    entry["location"] = location
                if not entry.get("end_year"):
                    year_after_pipe = _SINGLE_YEAR_RE.search(line.split("|", 1)[1])
                    if year_after_pipe:
                        entry["end_year"] = year_after_pipe.group(1)
            elif (
                not entry["institution"]
                and _INSTITUTION_RE.search(line)
                and not _DEGREE_RE.search(line)
            ):
                inst_text = line.split("|")[0].strip() if "|" in line else line_no_years
                inst_text = inst_text.lstrip("•●▪◦- ").strip()
                inst, location = self._split_institution_location(inst_text)
                entry["institution"] = inst
                if location:
                    entry["location"] = location

        if not entry["institution"]:
            for line in lines:
                if not _DEGREE_RE.search(line) and not _YEAR_RANGE_RE.fullmatch(line):
                    inst, location = self._split_institution_location(line)
                    if len(inst) > 5:
                        entry["institution"] = inst
                        if location:
                            entry["location"] = location
                        break

        return entry

    def _split_institution_location(self, line: str) -> tuple[str, str | None]:
        """
        Split 'National Institute of Technology, Delhi Delhi, India'
        into institution + location hint.
        """
        m = _LOCATION_SUFFIX_RE.match(line)
        if m:
            return m.group(1).strip(), f"{m.group(2).strip()}, {m.group(3).strip()}"

        if line.count(",") >= 2:
            parts = [p.strip() for p in line.split(",")]
            institution = ", ".join(parts[:-2]) if len(parts) > 2 else parts[0]
            location = ", ".join(parts[-2:])
            return institution, location

        return line, None

    def _maybe_set_degree_field(self, entry: dict[str, Any], degree_text: str) -> None:
        if "–" in degree_text:
            parts = degree_text.split("–", 1)
            if len(parts) == 2:
                entry["degree"] = parts[0].strip()
                if not entry.get("field"):
                    entry["field"] = parts[1].strip()
        elif " - " in degree_text:
            parts = degree_text.split(" - ", 1)
            if len(parts) == 2:
                entry["degree"] = parts[0].strip()
                if not entry.get("field"):
                    entry["field"] = parts[1].strip()

    def _make_field(self, value: str, method: ExtractionMethod) -> RawField:
        return RawField(
            value=value,
            source=SourceType.RESUME,
            extraction_method=method,
            raw_text=value,
        )
