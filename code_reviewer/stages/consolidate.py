from litetoolllm import structured_completion

from code_reviewer.memory import finding_hash
from code_reviewer.observability import trace_meta
from code_reviewer.schemas import Finding, ReviewReport

_SYSTEM = """\
You are the final code review consolidator.
Given findings from multiple specialist reviewers:
1. Deduplicate findings that describe the same issue in the same file.
2. Rank findings by severity: high → medium → low.
3. Add one genuine positive note about the change.
4. Return a ReviewReport.

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
        max_recursion=2,
        metadata=trace_meta("consolidate", repo_path, branch),
    )
    result = response.content
    result.truncated = truncated
    return result
