"""Tests for ResumeAdapter — multi-format extraction."""

from pathlib import Path

import pytest

from src.adapters.resume import ResumeAdapter

ARJUN_RESUME = """\
Arjun Mehta
arjun.mehta@example.com | +91 98123 45678 | Bangalore, India
LinkedIn: linkedin.com/in/arjunmehta

SUMMARY
Senior backend engineer with 6+ years building scalable microservices.

EXPERIENCE
Senior Software Engineer
Globex Inc | Jan 2020 - Present
Led migration of monolith to Kubernetes-based microservices.

Software Engineer
Acme Corp | Jun 2018 - Dec 2019
Built REST APIs in Python and Go.

SKILLS
Python, Go, Kubernetes, Docker, PostgreSQL, ReactJS, AWS

EDUCATION
Bachelor of Technology - Computer Science
IIT Bombay | 2018
"""

NANDINI_STYLE = """\
Nandini
Email: nandinijeetkumar@gmail.com
Mobile: +91-734-7367-310
LinkedIn: nandini-nandini-a5b0b635b
LeetCode: https://leetcode.com/u/nandini123

Education
National Institute of Technology, Delhi Delhi, India
Bachelor of Technology – Computer Science and Engineering; CGPA: 8.99 2023 – 2027
Govt Model Sr. Sec School Chandigarh, India
Intermediate; Percentage: 95.8 2021 – 2023
Valley Public School Chandigarh, India
Class 10th; Percentage: 98 2021

Technical Skills and Interests
Programming Languages: C, C++, SQL, HTML, CSS, JavaScript, Python
Expertise: Web Development, Competitive Programming
Tools/Frameworks: MySQL, Raptor, VSCode, React
Soft Skills: Communication, Teamwork, Leadership

Projects
• Resolver – Incident & Task Management Mobile App
◦ Built RESTful APIs using Express.js for efficient communication between frontend and backend.
◦ Frontend: React Native Backend: Node.js, Express.js Database: MongoDB
• AI-Powered Mock Interview Platform
◦ Integrated Gemini API to generate dynamic interview questions.
"""


@pytest.fixture
def adapter() -> ResumeAdapter:
    return ResumeAdapter()


def _parse_text(adapter: ResumeAdapter, text: str):
    sections = adapter._detect_sections(text)
    from src.models.source_record import SourceRecord, SourceType

    record = SourceRecord(source_type=SourceType.RESUME, source_file="inline.txt")
    adapter._fill_record(record, text, sections)
    return record


class TestNameExtraction:
    def test_single_name_from_merged_header(self, adapter):
        record = _parse_text(adapter, NANDINI_STYLE)
        assert record.full_name is not None
        assert record.full_name.value == "Nandini"

    def test_multi_word_name(self, adapter):
        record = _parse_text(adapter, ARJUN_RESUME)
        assert record.full_name is not None
        assert record.full_name.value == "Arjun Mehta"


class TestProjectsSeparateFromExperience:
    def test_projects_not_in_experience(self, adapter):
        record = _parse_text(adapter, NANDINI_STYLE)
        assert record.experience_raw == []
        assert len(record.projects_raw) >= 2
        titles = [rf.value.get("title") for rf in record.projects_raw]
        assert any("Resolver" in (t or "") for t in titles)
        assert any("Mock Interview" in (t or "") for t in titles)

    def test_linkedin_and_leetcode_extracted(self, adapter):
        record = _parse_text(adapter, NANDINI_STYLE)
        assert record.linkedin_url is not None
        assert "linkedin.com/in/nandini-nandini" in record.linkedin_url.value
        assert record.leetcode_url is not None
        assert "leetcode.com" in record.leetcode_url.value


class TestEducationExtraction:
    def test_education_year_ranges(self, adapter):
        record = _parse_text(adapter, NANDINI_STYLE)
        assert len(record.education_raw) == 3

        nit = record.education_raw[0].value
        assert "National Institute of Technology" in nit["institution"]
        assert nit["start_year"] == "2023"
        assert nit["end_year"] == "2027"
        assert "Bachelor" in (nit["degree"] or "")

        school = record.education_raw[1].value
        assert school["start_year"] == "2021"
        assert school["end_year"] == "2023"

        tenth = record.education_raw[2].value
        assert tenth["end_year"] == "2021"
        assert "2023" not in (tenth["institution"] or "")


class TestDegreeFirstEducation:
    DEVESH_STYLE = """\
Devesh Nair
devesh.nair@example.com | +91 98123 45678

EDUCATION
Ph.D - Computer Science
IIT Madras | 2024

Master of Science - AI
IIT Madras | 2019

B.Tech - Information Technology
NIT Calicut | 2017
"""

    def test_multiple_degrees_same_institution(self, adapter):
        record = _parse_text(adapter, self.DEVESH_STYLE)
        assert len(record.education_raw) == 3

        phd = record.education_raw[0].value
        assert phd["institution"] == "IIT Madras"
        assert phd["degree"] == "Ph.D"
        assert phd["end_year"] == "2024"

        ms = record.education_raw[1].value
        assert ms["institution"] == "IIT Madras"
        assert ms["degree"] == "Master of Science"
        assert ms["end_year"] == "2019"

        btech = record.education_raw[2].value
        assert btech["institution"] == "NIT Calicut"
        assert btech["degree"] == "B.Tech"
        assert btech["end_year"] == "2017"
    def test_labeled_skills_section(self, adapter):
        record = _parse_text(adapter, NANDINI_STYLE)
        skill_names = {rf.value.lower() for rf in record.skills_raw}
        assert "python" in skill_names
        assert "react" in skill_names
        assert "programming languages:" not in skill_names


class TestEdgeCaseNamesAndSkills:
    def test_no_skills_name_not_treated_as_section(self, adapter):
        text = """No Skills
no.skills@example.com | +91 98123 45670

EXPERIENCE
Engineer
Acme | 2021 - Present
"""
        record = _parse_text(adapter, text)
        assert record.full_name is not None
        assert record.full_name.value == "No Skills"
        assert record.skills_raw == []

    def test_contact_only_name(self, adapter):
        text = """Contact Only
contact.only@example.com | +91 98123 45670
"""
        record = _parse_text(adapter, text)
        assert record.full_name is not None
        assert record.full_name.value == "Contact Only"

    def test_skills_exclude_contact_tokens(self, adapter):
        text = """Dup Skills
dup.skills@example.com | +91 98123 45670

SKILLS
Python, python, PYTHON, Django, AWS
"""
        record = _parse_text(adapter, text)
        assert record.full_name is not None
        assert record.full_name.value == "Dup Skills"
        assert {rf.value for rf in record.skills_raw} == {"Python", "Django", "AWS"}


class TestStandardExperienceResume:
    def test_experience_and_education(self, adapter):
        record = _parse_text(adapter, ARJUN_RESUME)
        assert len(record.experience_raw) == 2
        assert record.experience_raw[0].value.get("company") == "Globex Inc"
        assert len(record.education_raw) == 1


@pytest.mark.skipif(
    not Path("data/sample_inputs/resumes/Nandini_NIT_Delhi (3).pdf").exists(),
    reason="Nandini sample PDF not present",
)
class TestNandiniPdf:
    def test_pdf_name_and_projects(self, adapter):
        pdf = Path("data/sample_inputs/resumes/Nandini_NIT_Delhi (3).pdf")
        records = adapter.parse(pdf)
        assert len(records) == 1
        record = records[0]
        assert record.parse_errors == []
        assert record.full_name is not None
        assert record.full_name.value == "Nandini"
        assert record.experience_raw == []
        assert len(record.projects_raw) >= 2
        assert len(record.education_raw) == 3
        assert record.emails[0].value == "nandinijeetkumar@gmail.com"
        if record.linkedin_url:
            assert "linkedin" in record.linkedin_url.value.lower()


class TestDocxExtraction:
    def test_can_handle_docx(self, adapter):
        assert adapter.can_handle(Path("resume.docx"))
        assert adapter.can_handle(Path("resume.doc"))
        assert not adapter.can_handle(Path("resume.txt"))

    def test_parse_docx_file(self, adapter, tmp_path):
        from docx import Document

        docx_path = tmp_path / "arjun.docx"
        doc = Document()
        for line in ARJUN_RESUME.splitlines():
            doc.add_paragraph(line)
        doc.save(str(docx_path))

        record = adapter.parse(docx_path)[0]
        assert record.parse_errors == []
        assert record.full_name is not None
        assert record.full_name.value == "Arjun Mehta"
        assert record.emails[0].value == "arjun.mehta@example.com"
        assert len(record.experience_raw) == 2
        assert len(record.skills_raw) >= 5
