from litetoolllm import structured_completion

from code_reviewer.observability import trace_meta
from code_reviewer.schemas import ChangeSet, FlowMap
from code_reviewer.tools import find_definition, find_references, read_file

_SYSTEM = """\
You build a flow model of how changed code fits into the broader codebase.
Use the provided tools to read changed files and trace callers/callees.
Try to follow the code to understand the domain and execution flow implications of the change.
If any README or documentation files are present (e.g. README.md, docs/), read them to understand project context.
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
