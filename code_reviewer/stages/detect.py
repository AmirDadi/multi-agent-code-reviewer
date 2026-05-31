from litetoolllm import structured_completion

from code_reviewer.observability import trace_meta
from code_reviewer.schemas import ChangeSet
from code_reviewer.tools import git_diff, list_changed_files

MAX_FILES = 20

_SYSTEM = """\
You extract a structured summary of a git diff for use in a code review pipeline.

Field guidance:
- files_changed: list files exactly as shown in the diff header, relative paths only.
- summary: 2-4 sentences. Name the key symbols added, removed, or modified.
  Describe the apparent behaviour change — not just which files were touched.
  Include any obvious risks or side effects visible in the diff (e.g. a deleted validation, \
a new DB query, a changed function signature).
- truncated: set true only when told the diff was cut off; otherwise false.

--- Example 1: new feature ---
Diff adds calculate_score() to scoring.py; main.py updated to call it.

Output:
{
  "files_changed": ["scoring.py", "main.py"],
  "summary": "Adds calculate_score() to scoring.py, which computes a weighted signal score \
from input features. main.py is updated to call calculate_score() inside the main processing \
loop, replacing the previous hardcoded sort. No existing public interfaces are removed or renamed.",
  "truncated": false
}

--- Example 2: API endpoint change ---
Diff modifies /listings route to accept an optional filter param; serializer updated; tests added.

Output:
{
  "files_changed": ["api/routes.py", "api/serializers.py", "tests/test_api.py"],
  "summary": "Extends the /listings endpoint in routes.py to accept an optional status filter \
query parameter. serializers.py adds the filter field to the response schema. Two test cases are \
added in test_api.py. The change is additive — existing callers with no filter parameter are unaffected.",
  "truncated": false
}
"""


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
