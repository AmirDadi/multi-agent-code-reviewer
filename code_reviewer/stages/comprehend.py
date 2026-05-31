from litetoolllm import structured_completion

from code_reviewer.observability import trace_meta
from code_reviewer.schemas import ChangeSet, FlowMap
from code_reviewer.tools import find_definition, find_references, read_file

_SYSTEM = """\
You build a flow model of how changed code fits into the broader codebase.
Use the provided tools to read changed files and trace callers/callees.

Reading priority — follow this order, stop when you have enough for the narrative:
1. Read each changed file in full.
2. Call find_references on each changed symbol to identify direct callers (blast radius).
3. Call find_definition on symbols the changed code calls into (downstream risk).
4. If documentation files exist (README.md, docs/), read them for domain context.
Do not exhaust the file cap on low-value reads — prioritise changed files and direct callers.

Narrative guidance:
Write 3-5 sentences covering:
(1) what the changed code does and why (infer from code if no description available),
(2) who calls it and what they expect — this is the blast radius,
(3) what the changed code depends on — downstream risk.
Be specific: name symbols and files. Do not write "the function" or "the module".

Confidence rubric:
- high: read all changed files and traced at least one caller or callee.
- medium: read all changed files but found no callers (symbol is new or unexported).
- low: could not read one or more changed files, or hit the file/recursion cap mid-trace.

Entry point definition:
An entry point is any changed symbol with no callers found in the repo — i.e. it is the
outermost callable: an HTTP handler, CLI command, publicly exported function, or scheduled job.
If no callers are found, treat the symbol itself as the entry point.

Rules:
- Trace at most 2 hops: direct callers and callees of changed symbols.
- Read at most 15 files total.
- If you hit any cap, set confidence="low" and return what you have.
"""


def comprehend(repo_path: str, base: str, branch: str, changeset: ChangeSet, model: str) -> FlowMap:
    user = (
        f"Branch: {branch} vs {base}\n"
        f"Changed files: {', '.join(changeset.files_changed)}\n"
        f"Summary: {changeset.summary}\n\n"
        "Trace how these changes flow through the codebase and return a FlowMap."
    )

    response = structured_completion(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
        response_model=FlowMap,
        tools=[read_file, find_references, find_definition],
        max_recursion=10,
        metadata=trace_meta("comprehend", repo_path, branch),
    )
    return response.content
