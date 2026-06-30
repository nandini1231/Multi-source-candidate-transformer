"""
main.py — CLI entry point using argparse.

Usage:
  python main.py --resume path/to/resume.pdf
  python main.py --resume-dir path/to/resumes/
  python main.py --recruiter-csv path/to/data.csv
  python main.py --resume path/to/resume.pdf --recruiter-csv path/to/data.csv

All business logic lives in src/. This file only:
  1. Parses arguments
  2. Validates paths
  3. Invokes the existing Pipeline
  4. Prints a human-readable summary
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ── Default paths ────────────────────────────────────────────────────────────
_DEFAULT_PROJECTION = Path("config/projection_config.json")
_DEFAULT_ENGINE_CFG = Path("config/engine_config.json")
_DEFAULT_OUTPUT     = Path("data/sample_outputs/output.json")

_SEP = "=" * 57


# ── Argument parser ───────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Multi-source candidate data transformer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --resume data/sample_inputs/resumes/candidate.pdf
  python main.py --recruiter-csv data/sample_inputs/candidates.csv
  python main.py --resume path/to/resume.pdf --recruiter-csv path/to/data.csv \\
                 --output output/result.json
        """,
    )
    parser.add_argument(
        "--resume",
        type=Path,
        default=None,
        metavar="FILE",
        help="Single resume file (PDF or DOCX). Omit to process CSV only.",
    )
    parser.add_argument(
        "--resume-dir",
        type=Path,
        default=None,
        dest="resume_dir",
        metavar="DIR",
        help="Directory of resume files (PDF/DOCX). Processes all supported files.",
    )
    parser.add_argument(
        "--recruiter-csv",
        type=Path,
        default=None,
        dest="recruiter_csv",
        metavar="FILE",
        help="Recruiter CSV file. Omit to process resume only.",
    )
    parser.add_argument(
        "--projection",
        type=Path,
        default=None,
        metavar="FILE",
        help=f"Projection config JSON. Default: {_DEFAULT_PROJECTION}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="FILE_OR_DIR",
        help=f"Output JSON path. Default: {_DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--engine-config",
        type=Path,
        default=_DEFAULT_ENGINE_CFG,
        dest="engine_config",
        metavar="FILE",
        help=f"Engine config JSON. Default: {_DEFAULT_ENGINE_CFG}",
    )
    return parser


# ── Path resolution & validation ─────────────────────────────────────────────

def _resolve_paths(args: argparse.Namespace) -> dict:
    """
    Determine final file paths from args + defaults.
    Validates that every supplied path actually exists.
    Returns a dict with keys: csv_path, resume_files, projection, engine_config, output.
    """
    errors: list[str] = []
    resolved: dict = {}

    # --- Recruiter CSV (only when explicitly provided) ---
    if args.recruiter_csv is not None:
        if not args.recruiter_csv.exists():
            errors.append(f"Recruiter CSV not found: {args.recruiter_csv}")
        elif not args.recruiter_csv.is_file():
            errors.append(f"Recruiter CSV path is not a file: {args.recruiter_csv}")
        else:
            resolved["csv_path"] = args.recruiter_csv
    else:
        resolved["csv_path"] = None

    # --- Resume file or directory (mutually exclusive) ---
    if args.resume is not None and args.resume_dir is not None:
        errors.append("Pass only one of --resume or --resume-dir, not both")
        resolved["resume_files"] = None
        resolved["resume_dir"] = None
    elif args.resume is not None:
        if not args.resume.exists():
            errors.append(f"Resume file not found: {args.resume}")
        elif not args.resume.is_file():
            errors.append(f"Resume path is not a file: {args.resume}")
        else:
            resolved["resume_files"] = [args.resume]
            resolved["resume_dir"] = None
    elif args.resume_dir is not None:
        if not args.resume_dir.exists():
            errors.append(f"Resume directory not found: {args.resume_dir}")
        elif not args.resume_dir.is_dir():
            errors.append(f"Resume path is not a directory: {args.resume_dir}")
        else:
            resolved["resume_files"] = None
            resolved["resume_dir"] = args.resume_dir
    else:
        resolved["resume_files"] = None
        resolved["resume_dir"] = None

    has_resume_input = bool(resolved.get("resume_files") or resolved.get("resume_dir"))
    if resolved.get("csv_path") is None and not has_resume_input:
        errors.append(
            "No input provided — pass at least one of --resume, --resume-dir, or --recruiter-csv"
        )

    # --- Projection config ---
    projection = args.projection if args.projection is not None else _DEFAULT_PROJECTION
    if projection is not None and not projection.exists():
        errors.append(f"Projection config not found: {projection}")
    else:
        resolved["projection"] = projection

    # --- Engine config ---
    if args.engine_config and not args.engine_config.exists():
        errors.append(f"Engine config not found: {args.engine_config}")
    else:
        resolved["engine_config"] = args.engine_config

    # --- Output path ---
    output = args.output if args.output is not None else _DEFAULT_OUTPUT
    # If output is a directory, auto-name the file inside it
    if output.suffix == "" or output.is_dir():
        output = output / "candidate_output.json"
    resolved["output"] = output

    if errors:
        print("\nError — the following paths could not be found:")
        for e in errors:
            print(f"  ✗  {e}")
        sys.exit(1)

    return resolved


# ── Console summary printer ───────────────────────────────────────────────────

def _print_summary(
    paths: dict,
    output: "PipelineOutput",  # noqa: F821
) -> None:
    """Print a clean, human-readable execution summary to the terminal."""
    from src.models.canonical import CandidateStatus

    profiles  = output.profiles
    summary   = output.summary
    decisions = output.decision_results

    # ── aggregate stats ──────────────────────────────────────────────────────
    total_conflicts = summary.total_conflicts
    validation_ok   = summary.validation_failures == 0
    n_candidates    = summary.total

    print()
    print(_SEP)
    print("  Candidate Processing Summary")
    print(_SEP)

    # Input files
    csv_used    = paths.get("csv_path")
    resume_used = paths.get("resume_dir") or (paths.get("resume_files") or [None])[0]
    print(f"\nResume:")
    print(f"  {resume_used or '(none)'}")
    print(f"\nRecruiter CSV:")
    print(f"  {csv_used or '(none)'}")
    print(f"\nProjection Config:")
    print(f"  {paths.get('projection')}")

    # ── Per-candidate details ─────────────────────────────────────────────────
    for idx, (profile, decision) in enumerate(zip(profiles, decisions), start=1):
        label = f"Candidate {idx}" if n_candidates > 1 else "Candidate"
        print(f"\n{'─' * 57}")
        print(f"  {label}: {profile.full_name or profile.candidate_id}")
        print(f"{'─' * 57}")

        # Status
        status_str = (
            "AUTO_APPROVED"
            if profile.status == CandidateStatus.ACTIVE
            else "MANUAL_REVIEW"
        )
        status_icon = "✓" if profile.status == CandidateStatus.ACTIVE else "⚠"
        print(f"\nStatus:")
        print(f"  {status_icon}  {status_str}")

        # Confidence + Quality
        print(f"\nOverall Confidence:")
        print(f"  {round(profile.overall_confidence * 100)}%")
        print(f"\nQuality Score:")
        print(f"  {round(profile.data_quality_score * 100)}%")

        # Candidate match
        keys = decision.match_keys_used
        if "single_source" in keys or not keys:
            match_desc = "Single source — no cross-source matching required"
        else:
            readable = {
                "email":        "Email",
                "phone":        "Phone",
                "name_company": "Name + Company",
            }
            parts = [readable.get(k, k) for k in keys]
            match_desc = "Matched using " + " + ".join(parts)
        print(f"\nCandidate Match:")
        print(f"  {match_desc}")

        # Normalization
        print(f"\nNormalization:")
        if summary.normalized_phones > 0:
            print(f"  ✓  Phone converted to E.164 ({summary.normalized_phones} phone(s))")
        elif profile.phones:
            print(f"  ✓  Phone already in E.164 format")
        else:
            print(f"  –  No phone present")

        if summary.normalized_skills:
            for example in summary.normalized_skills[:5]:  # show up to 5 examples
                print(f"  ✓  {example}")
        else:
            print(f"  ✓  Skills already in canonical form (or no skills)")

        # Validation
        print(f"\nValidation:")
        if profile.emails:
            print(f"  ✓  Email Valid")
        else:
            print(f"  ✗  Email Not found")

        if profile.phones:
            print(f"  ✓  Phone Valid")
        else:
            print(f"  ✗  Phone Not found or invalid")

        rejections = summary.validation_rejections
        if not rejections:
            print(f"  ✓  No validation rejections")
        else:
            print(f"  ⚠  {len(rejections)} validation rejection(s):")
            for rej in rejections:
                code = rej.get("reason_code", "UNKNOWN")
                reason = rej.get("reason", "")
                field = rej.get("field", "?")
                raw = rej.get("raw_value")
                if raw:
                    print(f"      • {field}: {code} — {reason} (value: {raw})")
                else:
                    print(f"      • {field}: {code} — {reason}")

        # Conflicts resolved
        n_conflicts = len(profile.conflict_log)
        print(f"\nConflicts Resolved:")
        print(f"  {n_conflicts}")

        # Decision explanations
        if profile.field_decisions:
            print(f"\nDecision:")
            shown: set[str] = set()
            for fd in profile.field_decisions:
                if fd.reason_code in ("NO_VALUE", "UNION_DEDUPE"):
                    continue
                msg = fd.reason_human
                if msg not in shown:
                    shown.add(msg)
                    print(f"  ✓  {msg}")
                if len(shown) >= 4:
                    break

        # Review reasons
        if profile.review_reasons:
            print(f"\nReview Reasons:")
            for reason in profile.review_reasons:
                print(f"  ⚠  {reason}")

    # ── Output ───────────────────────────────────────────────────────────────
    print(f"\n{'─' * 57}")
    print(f"\nOutput Saved To:")
    print(f"  {paths['output']}")
    print()
    print(_SEP)
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()
    paths  = _resolve_paths(args)

    # Lazy import — keeps CLI startup fast
    from src.pipeline import Pipeline

    pipeline = Pipeline(
        engine_config_path=paths["engine_config"],
        projection_config_path=paths["projection"],
    )

    result = pipeline.run(
        csv_path=paths.get("csv_path"),
        resume_dir=paths.get("resume_dir"),
        resume_files=paths.get("resume_files"),
    )

    pipeline.write_output(result, output_path=paths["output"], pretty=True)

    _print_summary(paths, result)


if __name__ == "__main__":
    main()
