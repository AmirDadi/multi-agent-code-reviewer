from litetoolllm import structured_completion

from code_reviewer.memory import finding_hash
from code_reviewer.observability import trace_meta
from code_reviewer.schemas import Finding, ReviewReport
from code_reviewer.tools import find_definition, find_references, read_file

_SYSTEM = """\
You are the final code review consolidator.
You have access to the repository files — use them to verify, clarify, or add context to findings before making your final judgment.
Given findings from multiple specialist reviewers:
1. Use your tools to read relevant files and verify findings that need more context.
2. Deduplicate findings that describe the same issue in the same file.
3. Rank findings by severity: high → medium → low.
4. Add one genuine positive note about the change.
5. Return a ReviewReport.

Be specific. Do not invent findings that are not in the input.
"""


def consolidate(
    repo_path: str,
    branch: str,
    findings: list[Finding],
    rejected_hashes: set[str],
    truncated: bool,
    model: str,
) -> ReviewReport:
    # Drop previously-rejected findings before sending to LLM
    active = [f for f in findings if finding_hash(f) not in rejected_hashes]

    if active:
        findings_text = "\n".join(
            f"[{f.severity.upper()}] {f.dimension} | {f.file}:{f.line_start}-{f.line_end}\n"
            f"  Issue: {f.issue}\n"
            f"  Fix: {f.suggestion}"
            for f in active
        )
    else:
        findings_text = "none"

    response = structured_completion(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Findings:\n{findings_text}"},
        ],
        response_model=ReviewReport,
        tools=[read_file, find_references, find_definition],
        max_recursion=5,
        metadata=trace_meta("consolidate", repo_path, branch),
    )
    result = response.content
    result.truncated = truncated
    return result
