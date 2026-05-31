from litetoolllm import structured_completion

from code_reviewer.observability import trace_meta
from code_reviewer.schemas import ChangeSet
from code_reviewer.tools import git_diff, list_changed_files

MAX_FILES = 20

_SYSTEM = "Extract a concise structured summary of this git diff. Be factual and brief. It will be used as input for a code reviewing session."


def detect_changes(repo_path: str, base: str, branch: str, model: str) -> ChangeSet:
    files = list_changed_files(base=base, branch=branch)
    truncated = len(files) > MAX_FILES
    if truncated:
        files = files[:MAX_FILES]

    diff = git_diff(base=base, branch=branch)
    user = f"Files changed:\n{chr(10).join(files)}\n\nDiff:\n{diff}"

    response = structured_completion(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
        response_model=ChangeSet,
        max_recursion=2,
        metadata=trace_meta("detect", repo_path, branch),
    )
    result = response.content
    result.truncated = truncated
    return result
