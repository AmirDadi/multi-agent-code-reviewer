from litetoolllm import structured_completion

from code_reviewer.memory import finding_hash
from code_reviewer.observability import trace_meta
from code_reviewer.schemas import Finding, ReviewReport
from code_reviewer.tools import find_definition, find_references, list_directory, read_file

_SYSTEM = """\
You are the final code review consolidator.
You have access to repository files — use them to verify findings before making your final judgment.

Workflow:
1. For every HIGH severity finding, read the referenced file at the flagged lines to confirm
   the issue is real. Downgrade or drop the finding if the surrounding code already handles it.
2. Deduplicate: merge findings that describe the same root cause at the same location,
   even if worded differently by different specialists. Keep the most informative wording.
3. Adjust severity where reading the file reveals a different picture.
4. Rank final findings: high → medium → low.
5. Add one specific positive note — name a concrete design decision, pattern, or risk that
   was handled well. Not a generic compliment like "the code is clean".
6. Return a ReviewReport.

Deduplication examples:
  Input findings:
    [MEDIUM] security  | auth.py:42 — unvalidated user input passed to DB query
    [MEDIUM] conventions | auth.py:42 — missing input sanitisation before DB call
  → Same root cause, same location. Keep the security finding, drop the conventions duplicate.

  Input findings:
    [LOW] domain | api.py:80 — new endpoint not documented
    [LOW] conventions | api.py:80 — missing docstring on new route handler
  → Same gap described from two angles. Merge into one finding with the clearest wording.

Severity adjustment examples:
  Finding: [HIGH] hardcoded secret in config.py:10
  After reading config.py:10 — value is the string "YOUR_API_KEY_HERE", a placeholder.
  → Downgrade to LOW (template value, not a real secret).

  Finding: [MEDIUM] missing null check on user.id in handler.py:55
  After reading handler.py:50-65 — user.id is dereferenced 3 lines above the check and the
  handler is reachable from an unauthenticated endpoint.
  → Upgrade to HIGH (exploitable without auth).

Be specific. Do not invent findings not in the input.
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
        tools=[read_file, list_directory, find_references, find_definition],
        max_recursion=5,
        metadata=trace_meta("consolidate", repo_path, branch),
    )
    result = response.content
    result.truncated = truncated
    return result
