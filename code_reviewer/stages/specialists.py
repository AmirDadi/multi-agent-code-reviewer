import asyncio

from litetoolllm import astructured_completion

from code_reviewer.observability import trace_meta
from code_reviewer.schemas import ChangeSet, Finding, FindingList, FlowMap
from code_reviewer.tools import find_definition, find_references, git_diff, list_directory, read_file

_CONVENTIONS = """\
You are a code conventions reviewer.

Step 1 — discover project conventions:
Use read_file to look for style configuration files. Check in this order:
  pyproject.toml, setup.cfg, .flake8, .pylintrc, tox.ini,
  .eslintrc, .eslintrc.js, .eslintrc.json, .prettierrc, .editorconfig
Extract any active rules (line length, quote style, naming rules, import order, etc.).
If none exist, infer conventions from the codebase profile. Fall back to the language's
standard style guide only when no project conventions can be found.

Step 2 — review the changed code:
Judge only against the conventions discovered in Step 1.
Check: naming (variables, functions, classes, files), import ordering, formatting,
structural patterns, error handling style, and clean code practices.
Do not flag personal style preferences or rules that are not established in this project.

Return a FindingList with dimension="conventions". Return an empty list if nothing stands out.
"""

_DOMAIN = """\
You are a domain/business alignment code reviewer.
Given the branch description and the FlowMap narrative, assess:
- Does the change accomplish what the description states?
- Are there missing edge cases or incomplete coverage of the stated intent?
- Is there scope creep — behaviour modified beyond what was described?
- Is the change correctly wired into the execution flow (per FlowMap)?
- Backward compatibility:
    * Public interfaces: are function signatures, return types, or raised exceptions changed
      in a way that would break existing callers listed in the FlowMap?
    * Database: are there schema changes (new columns, renamed columns, dropped constraints)
      that could break existing queries or require a migration?
- If no description is provided, infer the intent from the change summary and FlowMap narrative.

Return a FindingList with dimension="domain".
"""

_SECURITY = """\
You are a security reviewer.
Look for:
- Injection vulnerabilities: SQL, shell command, path traversal, template injection.
- Hardcoded secrets, credentials, API keys, or tokens in source or config files.
- Unsafe or deprecated function calls (e.g. eval, exec, pickle, unsafe deserialisation).
- Unvalidated input: for each upstream caller in the FlowMap, check whether input is
  validated before reaching the changed code. Flag the first unguarded use.
- Authentication and authorisation gaps: does the change introduce new endpoints, actions,
  or data-access paths that are not protected by existing auth checks? Would an unauthenticated
  or lower-privilege caller be able to reach the new code?
- Sensitive data in logs or error responses: flag any logging of passwords, tokens, session IDs,
  full request bodies, auth headers, or PII. Error messages should not reveal internal stack
  traces or system paths to the caller.

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
    return (
        f"Branch intent: {description}\n"
        f"Base: {base}  Branch: {branch}\n\n"
        f"Files changed: {', '.join(changeset.files_changed)}\n"
        f"Summary: {changeset.summary}\n\n"
        f"Flow narrative: {flowmap.narrative}\n"
        f"Upstream callers (blast radius): {upstream}\n"
        f"Downstream callees (dependencies): {downstream}\n\n"
        f"Codebase profile: {profile or 'not available — use general best practices'}\n\n"
        f"Tools available:\n"
        f"- read_file(path): read any file in the repo\n"
        f"- git_diff(base='{base}', branch='{branch}'): get the raw diff if you need exact changed lines\n"
        f"- find_references(symbol): find callers of a symbol\n"
        f"- find_definition(symbol): find where a symbol is defined"
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
        tools=[read_file, list_directory, git_diff, find_references, find_definition],
        max_recursion=5,
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
) -> list[Finding]:
    user = _context(changeset, flowmap, profile, description, base, branch)
    results = await asyncio.gather(
        _run(_CONVENTIONS, user, model, "conventions", repo_path, branch),
        _run(_DOMAIN, user, model, "domain", repo_path, branch),
        _run(_SECURITY, user, model, "security", repo_path, branch),
    )
    return [finding for batch in results for finding in batch]
