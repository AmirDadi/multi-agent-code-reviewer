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

Step 1 — read existing sibling files to extract actual project conventions:
  Use list_directory to find files in the same package/directory as the changed files.
  Read 1-2 existing source files (not the changed ones) to observe:
    - Naming style: snake_case vs camelCase for functions, variables, classes
    - Indentation: 2 spaces vs 4 spaces (count carefully)
    - Type hints: are function signatures annotated or not?
    - Docstrings: present or absent? what format (Google, NumPy, plain)?
    - Import style: one import per line vs combined (import a, b)
    - File headers: is there a comment at the top of each file?
  This is the ground truth — config files often don't capture these patterns.

Step 2 — check linter/formatter config (one batch call):
  read_files("pyproject.toml, setup.cfg, .flake8, .eslintrc.json, .prettierrc")
  Extract any active rules that add to what you found in Step 1.

Step 3 — compare the pre-loaded diff against the conventions from Steps 1-2:
  For each convention you observed, check if the changed code follows it.
  Naming, indentation, type hints, docstrings, imports, file headers — check them all.
  Use grep_context(pattern) to verify a pattern before flagging it as a deviation.
  Only flag clear deviations — not stylistic preferences absent from the project.

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

Mitigation-first rule (critical):
Before flagging ANY finding, read the surrounding code in the diff carefully and check
whether a mitigation already exists — sanitization, validation, auth guard, context manager, etc.
If a mitigation is present and correct, do NOT flag the issue.
If you are unsure, use grep_context to see the actual lines before deciding.

Look for:
- Injection: SQL, shell command, path traversal, template injection.
  For path traversal: check if basename(), resolve(), normpath(), or similar is already applied.
  os.path.basename() correctly strips traversal sequences — if present, it is a valid mitigation.
- Hardcoded secrets, credentials, API keys, or tokens.
- Unsafe function calls (eval, exec, pickle, unsafe deserialisation).
- Unvalidated input: check whether the input is sanitized before use, not just whether
  a parameter exists. Flag only if validation is absent.
- Auth gaps: new endpoints or data-access paths not protected by existing auth checks.
- Sensitive data in logs: flag only actual secrets/PII — local file paths are LOW at most,
  not MEDIUM or HIGH.

Severity calibration:
- HIGH: exploitable with no mitigation present.
- MEDIUM: real risk but partially mitigated or requires specific conditions.
- LOW: style/practice issue (missing context manager, missing encoding, etc.).
A local file path in a print() is LOW, not MEDIUM.

Use grep_context(pattern, context_lines=20) to verify a suspicious pattern before flagging.
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
        f"- read_files('path1, path2, ...'): read small config files in one call (max 5)\n"
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
        max_recursion=8,
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
