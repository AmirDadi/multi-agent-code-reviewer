import asyncio

from litetoolllm import astructured_completion

from code_reviewer.observability import trace_meta
from code_reviewer.schemas import ChangeSet, Finding, FindingList, FlowMap
from code_reviewer.tools import (
    find_definition,
    find_references,
    git_diff,
    grep_context,
    list_directory,
    read_file,
    read_files,
)

_CONVENTIONS = """\
You are a code conventions reviewer.
The changed code is pre-loaded in the user message — review it directly.

Step 1 — discover project conventions (one batch call):
  read_files(["pyproject.toml", "setup.cfg", ".flake8", ".eslintrc.json", ".prettierrc"])
  Stop after this one call. Extract active rules from whatever was found.
  If nothing found, infer from the codebase profile or the language's standard style guide.

Step 2 — review the pre-loaded diff:
  Judge against the conventions from Step 1.
  Check: naming, import ordering, formatting, structural patterns, error handling, clean code.
  Only flag deviations from established conventions — not personal preferences.
  Use grep_context(pattern) if you need to see how a pattern is used elsewhere for comparison.
  Do not read files unrelated to the change.

Return a FindingList with dimension="conventions". Return an empty list if nothing stands out.
"""

_DOMAIN = """\
You are a domain/business alignment code reviewer.
The changed code is pre-loaded in the user message — review it directly.

Assess:
- Does the change accomplish what the description states?
- Are there missing edge cases or incomplete coverage of the stated intent?
- Is there scope creep — behaviour modified beyond what was described?
- Is the change correctly wired into the execution flow (per FlowMap narrative)?
- Backward compatibility:
    * Public interfaces: signatures, return types, or raised exceptions changed in a breaking way?
    * Database: schema changes (new columns, renamed columns, dropped constraints)?
- If no description is provided, infer intent from the summary and FlowMap narrative.

Use grep_context(symbol, context_lines=20) to check how a specific symbol is used or expected
by callers — only when the pre-loaded diff is not enough to answer a specific question.
Do not read files unrelated to alignment with the stated intent.

Return a FindingList with dimension="domain".
"""

_SECURITY = """\
You are a security reviewer.
The changed code is pre-loaded in the user message — review it directly.

Look for:
- Injection: SQL, shell command, path traversal, template injection.
- Hardcoded secrets, credentials, API keys, or tokens.
- Unsafe function calls (eval, exec, pickle, unsafe deserialisation).
- Unvalidated input: for each upstream caller in the FlowMap, check whether input is
  validated before reaching the changed code. Flag the first unguarded use.
- Auth gaps: new endpoints or data-access paths not protected by existing auth checks.
- Sensitive data in logs: passwords, tokens, session IDs, PII, auth headers, full request bodies.

Use grep_context(pattern, context_lines=20) to inspect how input flows into a suspicious call
or to check if an auth guard exists nearby — only when the pre-loaded diff is insufficient.
Do not read files unrelated to the security surface of this change.

Return a FindingList with dimension="security". Return an empty list if nothing stands out.
"""


def _context(
    changeset: ChangeSet,
    flowmap: FlowMap,
    profile: dict,
    description: str,
    base: str,
    branch: str,
) -> str:
    upstream = [n.symbol for n in flowmap.upstream]
    downstream = [n.symbol for n in flowmap.downstream]
    preloaded = git_diff(base=base, branch=branch, context_lines=30)
    return (
        f"Branch intent: {description}\n"
        f"Base: {base}  Branch: {branch}\n\n"
        f"Files changed: {', '.join(changeset.files_changed)}\n"
        f"Summary: {changeset.summary}\n\n"
        f"Flow narrative: {flowmap.narrative}\n"
        f"Upstream callers (blast radius): {upstream}\n"
        f"Downstream callees (dependencies): {downstream}\n\n"
        f"Codebase profile: {profile or 'not available — use general best practices'}\n\n"
        f"--- Pre-loaded diff (±30 lines context around each change) ---\n"
        f"{preloaded}\n"
        f"--- End of pre-loaded diff ---\n\n"
        f"Available tools:\n"
        f"- grep_context(pattern, context_lines=20): search with surrounding lines — prefer over read_file\n"
        f"- read_files(paths): read small config files in one call (max 5)\n"
        f"- read_file(path): read a full file only when absolutely necessary\n"
        f"- find_references(symbol) / find_definition(symbol): trace symbol usage\n"
        f"Do not read files not relevant to your review dimension."
    )


async def _run(
    system: str,
    user: str,
    model: str,
    dimension: str,
    repo: str,
    branch: str,
) -> list[Finding]:
    response = await astructured_completion(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_model=FindingList,
        tools=[grep_context, read_files, find_references, find_definition, read_file, list_directory],
        max_recursion=6,
        model_capabilities={"function_calling": True, "json_mode": False},
        metadata=trace_meta(f"specialist:{dimension}", repo, branch),
    )
    return response.content.findings if response.content else []


async def run_specialists(
    repo_path: str,
    base: str,
    branch: str,
    description: str,
    changeset: ChangeSet,
    flowmap: FlowMap,
    profile: dict,
    model: str,
    security_model: str | None = None,
) -> list[Finding]:
    user = _context(changeset, flowmap, profile, description, base, branch)
    sec_model = security_model or model
    results = await asyncio.gather(
        _run(_CONVENTIONS, user, model, "conventions", repo_path, branch),
        _run(_DOMAIN, user, model, "domain", repo_path, branch),
        _run(_SECURITY, user, sec_model, "security", repo_path, branch),
    )
    return [finding for batch in results for finding in batch]
