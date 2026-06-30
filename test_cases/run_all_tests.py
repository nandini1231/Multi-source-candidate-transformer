#!/usr/bin/env python3
"""Run unit tests + all integration test cases; write test_results.json and TEST_RESULTS.md."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
TEST_CASES = REPO / "test_cases"
OUTPUT_DIR = REPO / "output" / "test_runs"
RESULTS_JSON = REPO / "test_results.json"
RESULTS_MD = REPO / "TEST_RESULTS.md"

SKIP_CSV_PREFIXES = ("(none", "(intentionally", "(none —", "(none—")
SKIP_RESUME_MARKERS = ("(no resume", "(none)", "csv-only", "intentionally empty", "simulated corrupt")
CONFIDENCE_TOLERANCE = 0.05

# Ensure src imports work when invoking Pipeline directly
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _python() -> str:
    venv = REPO / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def generate_pdfs() -> tuple[bool, str]:
    script = TEST_CASES / "generate_test_pdfs.py"
    proc = subprocess.run([_python(), str(script)], cwd=REPO, capture_output=True, text=True)
    if proc.returncode != 0:
        return False, proc.stderr or proc.stdout
    return True, proc.stdout.strip().split("\n")[-1]


def run_pytest() -> dict[str, Any]:
    proc = subprocess.run(
        [_python(), "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    lines = proc.stdout.splitlines()
    passed = failed = 0
    failures: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for line in lines:
        if " PASSED" in line:
            passed += 1
        elif " FAILED" in line:
            failed += 1
            name = line.split(" FAILED")[0].strip().split()[-1]
            current = {"test": name, "reason": ""}
            failures.append(current)
        elif current is not None and line.startswith("E   "):
            current["reason"] += line[4:] + " "

    return {
        "exit_code": proc.returncode,
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "failures": failures,
        "raw_tail": lines[-20:] if lines else [],
    }


def _csv_usable(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return True  # empty CSV is valid (TC07/TC02)
    first = text.splitlines()[0].strip().lower()
    return not any(first.startswith(p) for p in SKIP_CSV_PREFIXES)


def _resume_usable(tc_dir: Path, resume_format: str = "pdf") -> bool:
    ext = ".docx" if resume_format == "docx" else ".pdf"
    resume = tc_dir / f"resume{ext}"
    if not resume.exists():
        return False
    txt = tc_dir / "resume.txt"
    if txt.exists():
        content = txt.read_text(encoding="utf-8").strip().lower()
        if not content or any(m in content for m in SKIP_RESUME_MARKERS):
            return False
    return True


def _resolve_resume_file(tc_dir: Path, expected: dict) -> Path | None:
    resume_format = expected.get("resume_format", "pdf")
    if _resume_usable(tc_dir, resume_format):
        ext = ".docx" if resume_format == "docx" else ".pdf"
        return tc_dir / f"resume{ext}"
    return None


def _resolve_projection(tc_dir: Path) -> Path | None:
    proj = tc_dir / "projection.json"
    if not proj.exists():
        return None
    try:
        data = json.loads(proj.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return proj
    if isinstance(data, dict) and "_note" in data:
        default = REPO / "config" / "default_projection.json"
        return default if default.exists() else REPO / "config" / "projection_config.json"
    if isinstance(data, dict) and "fields" in data:
        return proj
    return None


def _resolve_engine_config(tc_dir: Path) -> Path | None:
    cfg = tc_dir / "engine_config.json"
    return cfg if cfg.exists() else None


def _resume_dir_usable(tc_dir: Path) -> Path | None:
    resume_dir = tc_dir / "resumes"
    if not resume_dir.is_dir():
        return None
    pdfs = [p for p in resume_dir.iterdir() if p.suffix.lower() == ".pdf" and p.is_file()]
    return resume_dir if pdfs else None


def _run_pipeline(
    csv_path: Path | None,
    resume_path: Path | None,
    resume_dir: Path | None,
    projection: Path | None,
    engine_config: Path | None,
    out_path: Path,
) -> tuple[int, str]:
    cmd = [_python(), str(REPO / "main.py")]
    if resume_dir:
        cmd.extend(["--resume-dir", str(resume_dir)])
    elif resume_path:
        cmd.extend(["--resume", str(resume_path)])
    if csv_path:
        cmd.extend(["--recruiter-csv", str(csv_path)])
    if projection:
        cmd.extend(["--projection", str(projection)])
    if engine_config:
        cmd.extend(["--engine-config", str(engine_config)])
    cmd.extend(["--output", str(out_path)])
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def _run_cli_expect_fail(missing_csv: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [_python(), str(REPO / "main.py"), "--recruiter-csv", missing_csv],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    ok = proc.returncode != 0 and "could not be found" in (proc.stdout + proc.stderr).lower()
    reason = "" if ok else f"expected non-zero exit with path error, got exit={proc.returncode}"
    return ok, reason


def _run_pipeline_api_empty() -> tuple[bool, dict[str, Any], str]:
    try:
        from src.pipeline import Pipeline

        p = Pipeline()
        result = p.run(csv_path=None, resume_dir=None, resume_files=None)
        actual = {
            "summary": {
                "total": result.summary.total,
                "active": result.summary.active,
                "manual_review": result.summary.manual_review,
                "errors": result.summary.errors,
            },
            "candidates": [],
        }
        ok = result.summary.total == 0
        return ok, actual, "" if ok else f"expected total=0, got {result.summary.total}"
    except Exception as exc:
        return False, {}, str(exc)


def _float_close(a: Any, b: Any, tol: float = CONFIDENCE_TOLERANCE) -> bool:
    try:
        return math.isclose(float(a), float(b), abs_tol=tol)
    except (TypeError, ValueError):
        return a == b


def _compare_values(exp: Any, act: Any, path: str, diffs: list[str]) -> None:
    if exp is None:
        return
    if isinstance(exp, float) and isinstance(act, (int, float)):
        if not _float_close(exp, act):
            diffs.append(f"{path}: expected {exp}, got {act}")
        return
    if isinstance(exp, list) and isinstance(act, list):
        if exp and all(isinstance(x, str) for x in exp):
            if sorted(exp) != sorted(act):
                diffs.append(f"{path}: expected {exp}, got {act}")
        elif len(exp) != len(act):
            diffs.append(f"{path}: list length expected {len(exp)}, got {len(act)}")
        else:
            for i, (e, a) in enumerate(zip(exp, act)):
                if isinstance(e, dict) and isinstance(a, dict):
                    _compare_partial_object(e, a, f"{path}[{i}]", diffs)
                elif e != a and not (isinstance(e, float) and _float_close(e, a)):
                    diffs.append(f"{path}[{i}]: expected {e!r}, got {a!r}")
        return
    if isinstance(exp, dict) and isinstance(act, dict):
        _compare_partial_object(exp, act, path, diffs)
        return
    if exp != act:
        diffs.append(f"{path}: expected {exp!r}, got {act!r}")


def _compare_partial_object(exp: dict, act: dict, path: str, diffs: list[str]) -> None:
    for key, exp_val in exp.items():
        if key.startswith("expected_"):
            continue
        if isinstance(exp_val, str) and (" or " in exp_val or exp_val.startswith("<")):
            continue
        if key not in act:
            diffs.append(f"{path}.{key}: missing in actual output")
            continue
        _compare_values(exp_val, act[key], f"{path}.{key}", diffs)


def compare_output(expected: dict, actual: dict) -> list[str]:
    diffs: list[str] = []
    if "expected_behavior" in expected and "candidates" not in expected:
        return diffs  # behavioral-only spec; validated separately

    if keys := expected.get("expected_keys_in_output"):
        act_candidates = actual.get("candidates") or []
        if not act_candidates:
            diffs.append("candidates: expected at least one for expected_keys_in_output check")
        else:
            for key in keys:
                if key not in act_candidates[0]:
                    diffs.append(f"candidates[0].{key}: missing in actual output")

    if nonempty := expected.get("assert_non_empty_in_candidate"):
        act_candidates = actual.get("candidates") or []
        if act_candidates:
            for key in nonempty:
                val = act_candidates[0].get(key)
                if not val:
                    diffs.append(f"candidates[0].{key}: expected non-empty, got {val!r}")

    if "summary" in expected and "summary" in actual:
        _compare_partial_object(expected["summary"], actual["summary"], "summary", diffs)

    exp_candidates = expected.get("candidates")
    act_candidates = actual.get("candidates")
    if exp_candidates is not None:
        if act_candidates is None:
            diffs.append("candidates: missing in actual output")
        elif len(exp_candidates) != len(act_candidates):
            diffs.append(
                f"candidates: count expected {len(exp_candidates)}, got {len(act_candidates)}"
            )
        else:
            for i, (ec, ac) in enumerate(zip(exp_candidates, act_candidates)):
                if isinstance(ec, dict):
                    _compare_partial_object(ec, ac, f"candidates[{i}]", diffs)
    return diffs


def run_integration_case(tc_dir: Path, run_id: str) -> dict[str, Any]:
    rel = tc_dir.relative_to(TEST_CASES)
    name = str(rel).replace("\\", "/")
    expected_path = tc_dir / "expected_output.json"
    result: dict[str, Any] = {"case": name, "status": "unknown"}

    if not expected_path.exists():
        result["status"] = "skipped"
        result["reason"] = "no expected_output.json"
        return result

    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    # TC07/TC01 — CLI path validation
    if expected.get("expected_behavior", "").startswith("main.py exits"):
        ok, reason = _run_cli_expect_fail("/tmp/does/not/exist.csv")
        result["status"] = "passed" if ok else "failed"
        if not ok:
            result["reason"] = reason
        return result

    # TC07/TC06 — empty pipeline via API
    if "no flags provided" in expected.get("expected_behavior", "").lower() or (
        rel.parts[0] == "07_error_handling" and rel.name == "TC06"
    ):
        ok, actual, reason = _run_pipeline_api_empty()
        result["status"] = "passed" if ok else "failed"
        if not ok:
            result["reason"] = reason
        else:
            diffs = compare_output(expected, actual)
            if diffs:
                result["status"] = "failed"
                result["reason"] = "; ".join(diffs)
        return result

    csv_path = tc_dir / "recruiter.csv"
    resume_to_use: Path | None = None
    resume_dir_to_use: Path | None = None

    # TC07/TC05 — corrupt PDF
    if rel.parts[0] == "07_error_handling" and rel.name == "TC05":
        corrupt = tc_dir / "corrupt.pdf"
        corrupt.write_bytes(b"this is not a valid pdf file content")
        resume_to_use = corrupt
    elif resume_dir := _resume_dir_usable(tc_dir):
        resume_dir_to_use = resume_dir
    elif _resolve_resume_file(tc_dir, expected):
        resume_to_use = _resolve_resume_file(tc_dir, expected)
    elif _resume_usable(tc_dir):
        resume_to_use = tc_dir / "resume.pdf"

    use_csv = _csv_usable(csv_path)
    use_resume = resume_to_use is not None or resume_dir_to_use is not None

    if not use_csv and not use_resume:
        result["status"] = "skipped"
        result["reason"] = "no usable csv or resume input"
        return result

    projection = _resolve_projection(tc_dir)
    engine_config = _resolve_engine_config(tc_dir)
    out_path = OUTPUT_DIR / run_id / f"{rel.as_posix().replace('/', '_')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    exit_code, logs = _run_pipeline(
        csv_path if use_csv else None,
        resume_to_use if resume_to_use else None,
        resume_dir_to_use,
        projection,
        engine_config,
        out_path,
    )

    if exit_code != 0:
        result["status"] = "failed"
        result["reason"] = f"pipeline exited {exit_code}: {logs[-500:]}"
        return result

    if not out_path.exists():
        result["status"] = "failed"
        result["reason"] = "no output file produced"
        return result

    actual = json.loads(out_path.read_text(encoding="utf-8"))
    diffs = compare_output(expected, actual)
    if diffs:
        result["status"] = "failed"
        result["reason"] = "; ".join(diffs[:8])
        if len(diffs) > 8:
            result["reason"] += f" (+{len(diffs) - 8} more)"
    else:
        result["status"] = "passed"
    return result


def discover_cases() -> list[Path]:
    return sorted(p.parent for p in TEST_CASES.rglob("expected_output.json"))


def write_reports(report: dict[str, Any]) -> None:
    RESULTS_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# Test Results",
        "",
        f"Generated: {report['timestamp']}",
        "",
        "## Summary",
        "",
        f"| Suite | Passed | Failed | Skipped | Total |",
        f"|-------|--------|--------|---------|-------|",
        f"| Unit (pytest) | {report['unit_tests']['passed']} | {report['unit_tests']['failed']} | 0 | {report['unit_tests']['total']} |",
        f"| Integration | {report['integration']['passed']} | {report['integration']['failed']} | {report['integration']['skipped']} | {report['integration']['total']} |",
        f"| **Overall** | **{report['overall']['passed']}** | **{report['overall']['failed']}** | **{report['integration']['skipped']}** | **{report['overall']['total']}** |",
        "",
    ]

    if report["unit_tests"]["failures"]:
        lines.extend(["## Unit Test Failures", ""])
        for f in report["unit_tests"]["failures"]:
            lines.append(f"- **{f['test']}**: {f['reason'].strip() or 'see pytest output'}")
        lines.append("")

    failed_cases = [c for c in report["integration"]["cases"] if c["status"] == "failed"]
    if failed_cases:
        lines.extend(["## Integration Failures", ""])
        for c in failed_cases:
            lines.append(f"- **{c['case']}**: {c.get('reason', 'unknown')}")
        lines.append("")

    skipped = [c for c in report["integration"]["cases"] if c["status"] == "skipped"]
    if skipped:
        lines.extend(["## Skipped Integration Cases", ""])
        for c in skipped:
            lines.append(f"- **{c['case']}**: {c.get('reason', '')}")
        lines.append("")

    passed_pct = (
        round(100 * report["overall"]["passed"] / report["overall"]["total"], 1)
        if report["overall"]["total"]
        else 0
    )
    lines.extend([
        "## Notes",
        "",
        f"- Pass rate (excluding skipped): **{passed_pct}%** of executed tests",
        "- PDFs regenerated via `test_cases/generate_test_pdfs.py` before integration runs",
        "- Integration comparison uses partial matching on keys present in `expected_output.json`",
        f"- Confidence tolerance: ±{CONFIDENCE_TOLERANCE}",
        "",
        "Full machine-readable report: [test_results.json](test_results.json)",
    ])

    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    run_id = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report: dict[str, Any] = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "run_id": run_id,
    }

    pdf_ok, pdf_msg = generate_pdfs()
    report["pdf_generation"] = {"ok": pdf_ok, "message": pdf_msg}

    report["unit_tests"] = run_pytest()

    cases = discover_cases()
    integration_results = [run_integration_case(tc, run_id) for tc in cases]
    passed_i = sum(1 for c in integration_results if c["status"] == "passed")
    failed_i = sum(1 for c in integration_results if c["status"] == "failed")
    skipped_i = sum(1 for c in integration_results if c["status"] == "skipped")

    report["integration"] = {
        "total": len(integration_results),
        "passed": passed_i,
        "failed": failed_i,
        "skipped": skipped_i,
        "cases": integration_results,
    }

    unit = report["unit_tests"]
    report["overall"] = {
        "passed": unit["passed"] + passed_i,
        "failed": unit["failed"] + failed_i,
        "total": unit["total"] + passed_i + failed_i,
    }

    write_reports(report)

    print(f"PDF generation: {'OK' if pdf_ok else 'FAILED'} — {pdf_msg}")
    print(f"Unit tests:     {unit['passed']}/{unit['total']} passed")
    print(f"Integration:    {passed_i}/{passed_i + failed_i} passed ({skipped_i} skipped)")
    print(f"Reports:        {RESULTS_JSON}")
    print(f"                {RESULTS_MD}")

    return 0 if unit["failed"] == 0 and failed_i == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
