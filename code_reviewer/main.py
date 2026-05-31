import argparse
import asyncio
from pathlib import Path

import code_reviewer.tools as tool_module
from code_reviewer.config import FAST_MODEL, MID_MODEL, STRONG_MODEL, STRONGEST_MODEL
from code_reviewer.memory import load_codebase_profile, load_rejected_hashes
from code_reviewer.observability import setup_langfuse
from code_reviewer.schemas import ReviewReport
from code_reviewer.stages.comprehend import comprehend
from code_reviewer.stages.consolidate import consolidate
from code_reviewer.stages.detect import detect_changes
from code_reviewer.stages.specialists import run_specialists


def render_report(report: ReviewReport) -> str:
    lines = []

    if report.truncated:
        lines.append("> **Note:** diff was truncated — review covers a subset of changes.\n")

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    sorted_findings = sorted(report.findings, key=lambda f: severity_rank.get(f.severity, 9))

    if sorted_findings:
        lines.append("## Findings\n")
        for f in sorted_findings:
            loc = f.file
            if f.line_start:
                loc += f":{f.line_start}"
                if f.line_end and f.line_end != f.line_start:
                    loc += f"-{f.line_end}"
            lines.append(f"### [{f.severity.upper()}] {f.dimension} — `{loc}`")
            lines.append(f"**Issue:** {f.issue}  ")
            lines.append(f"**Suggestion:** {f.suggestion}\n")
    else:
        lines.append("## Findings\n\nNo issues found.\n")

    lines.append(f"## Positive Note\n\n{report.positive_note}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-agent code reviewer — review a branch before human review."
    )
    parser.add_argument("--repo", required=True, help="Path to the git repository to review")
    parser.add_argument("--branch", required=True, help="Branch to review")
    parser.add_argument("--base", default="main", help="Base branch (default: main)")
    parser.add_argument("--description", required=True, help="What this branch is intended to do")
    parser.add_argument("--out", help="Write markdown report to this file instead of stdout")
    args = parser.parse_args()

    setup_langfuse()
    tool_module.set_repo_root(args.repo)

    changeset = detect_changes(args.repo, args.base, args.branch, FAST_MODEL)
    flowmap = comprehend(args.repo, args.base, args.branch, changeset, STRONG_MODEL)
    profile = load_codebase_profile(args.repo)

    findings = asyncio.run(
        run_specialists(
            repo_path=args.repo,
            branch=args.branch,
            description=args.description,
            changeset=changeset,
            flowmap=flowmap,
            profile=profile,
            model=MID_MODEL,
        )
    )

    rejected = load_rejected_hashes(args.repo)
    report = consolidate(args.repo, args.branch, findings, rejected, changeset.truncated, STRONGEST_MODEL)

    md = render_report(report)

    if args.out:
        Path(args.out).write_text(md)
        print(f"Report written to {args.out}")
    else:
        print(md)


if __name__ == "__main__":
    main()
