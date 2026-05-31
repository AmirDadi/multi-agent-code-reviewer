import asyncio

from litetoolllm import astructured_completion

from code_reviewer.observability import trace_meta
from code_reviewer.schemas import ChangeSet, Finding, FindingList, FlowMap

_CONVENTIONS = """\
You are a code conventions reviewer.
Review the diff for: naming consistency, import ordering, formatting, and structural patterns.
Judge against the codebase profile when available; fall back to general best practices.
Return a FindingList with dimension="conventions". Return an empty list if nothing stands out.
"""

_DOMAIN = """\
You are a domain alignment reviewer.
Given the branch description and the FlowMap narrative, assess:
- Does the change accomplish what the description states?
- Are there missing edge cases or incomplete coverage of the stated intent?
- Is there scope creep beyond what was described?
- Is the change correctly wired into the execution flow (per FlowMap)?
Return a FindingList with dimension="domain".
"""

_SECURITY = """\
You are a security reviewer.
Look for: injection vulnerabilities, hardcoded secrets or credentials, unsafe function calls,
and unvalidated input arriving from upstream callers identified in the FlowMap.
Return a FindingList with dimension="security". Return an empty list if nothing stands out.
"""


def _context(changeset: ChangeSet, flowmap: FlowMap, profile: dict, description: str) -> str:
    upstream = [n.symbol for n in flowmap.upstream]
    downstream = [n.symbol for n in flowmap.downstream]
    return (
        f"Branch intent: {description}\n\n"
        f"Files changed: {', '.join(changeset.files_changed)}\n"
        f"Summary: {changeset.summary}\n\n"
        f"Flow narrative: {flowmap.narrative}\n"
        f"Upstream callers: {upstream}\n"
        f"Downstream callees: {downstream}\n\n"
        f"Codebase profile: {profile or 'not available — use general best practices'}"
    )


async def _run(system: str, user: str, model: str, dimension: str, repo: str, branch: str) -> list[Finding]:
    response = await astructured_completion(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_model=FindingList,
        max_recursion=2,
        metadata=trace_meta(f"specialist:{dimension}", repo, branch),
    )
    return response.content.findings if response.content else []


async def run_specialists(
    repo_path: str,
    branch: str,
    description: str,
    changeset: ChangeSet,
    flowmap: FlowMap,
    profile: dict,
    model: str,
) -> list[Finding]:
    user = _context(changeset, flowmap, profile, description)
    results = await asyncio.gather(
        _run(_CONVENTIONS, user, model, "conventions", repo_path, branch),
        _run(_DOMAIN, user, model, "domain", repo_path, branch),
        _run(_SECURITY, user, model, "security", repo_path, branch),
    )
    return [finding for batch in results for finding in batch]
