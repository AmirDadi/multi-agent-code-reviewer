from litetoolllm import structured_completion

from code_reviewer.observability import trace_meta
from code_reviewer.schemas import ChangeSet, FlowMap
from code_reviewer.tools import (
    find_definition,
    find_references,
    git_diff,
    grep_context,
    list_directory,
    read_file,
    read_files,
)

_SYSTEM = """\
You build a flow model of how changed code fits into the broader codebase.
The changed code (±30 lines context around each hunk) is pre-loaded in the user message.
Do NOT re-read the changed files — that context is already available above.

Tool use rules:
- grep_context(pattern, context_lines=20): use this first when you need to see a specific
  symbol or pattern in context. Much cheaper than read_file — prefer it.
- find_references(symbol): find who calls a changed symbol (blast radius).
- find_definition(symbol): find what the changed code depends on (downstream risk).
- read_files(paths): read small config/doc files (max 5 at once).
- read_file(path): only for files not already in the pre-loaded diff context.
- list_directory(path): explore unfamiliar directory structure.
- Do NOT read files that are not directly related to understanding the change.
- Stop exploring as soon as you have enough for a confident narrative.
- After your last tool call, immediately return the FlowMap.

Narrative guidance:
Write 3-5 sentences covering:
(1) what the changed code does and why,
(2) who calls it and what they expect — blast radius,
(3) what the changed code depends on — downstream risk.
Name symbols and files specifically. Do not write "the function" or "the module".

Confidence rubric:
- high: pre-loaded diff understood + traced at least one caller or callee.
- medium: pre-loaded diff understood but no callers found (new/unexported symbol).
- low: hit recursion cap or could not understand the change from the diff.

Entry point: any changed symbol with no callers in the repo — HTTP handler, CLI command,
exported function, or scheduled job. If no callers found, treat the symbol as entry point.

Tracing rules:
- Trace at most 2 hops: direct callers and callees only.
- Read at most 5 additional files beyond the pre-loaded diff.
- If you hit any cap, set confidence="low" and return what you have.
"""


def _preload_diff(base: str, branch: str) -> str:
    """Return the diff with ±30 lines of context around each change."""
    return git_diff(base=base, branch=branch, context_lines=30)


def comprehend(repo_path: str, base: str, branch: str, changeset: ChangeSet, model: str) -> FlowMap:
    preloaded = _preload_diff(base, branch)
    user = (
        f"Branch: {branch} vs {base}\n"
        f"Changed files: {', '.join(changeset.files_changed)}\n"
        f"Summary: {changeset.summary}\n\n"
        f"--- Pre-loaded diff (±30 lines context) ---\n"
        f"{preloaded}\n"
        f"--- End of pre-loaded diff ---\n\n"
        "The changed code above is already in your context.\n"
        "Use tools only to trace callers/callees and read related files.\n"
        "Return a FlowMap."
    )

    response = structured_completion(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
        response_model=FlowMap,
        tools=[grep_context, find_references, find_definition, read_files, read_file, list_directory],
        max_recursion=10,
        model_capabilities={"function_calling": True, "json_mode": False},
        metadata=trace_meta("comprehend", repo_path, branch),
    )
    return response.content
