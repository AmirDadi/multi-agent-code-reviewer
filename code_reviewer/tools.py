import re
import shutil
import subprocess
from pathlib import Path

_GREP = shutil.which("grep") or "grep"

MAX_FILE_LINES = 500
MAX_DIFF_KB = 100
MAX_GREP_RESULTS = 50
MAX_GREP_CONTEXT_LINES = 30  # hard cap on context_lines arg
MAX_GREP_OUTPUT_LINES = 150  # hard cap on grep_context total output
MAX_BATCH_FILES = 5
MAX_BATCH_COMBINED_LINES = 300

_repo_root: Path | None = None
_branch: str | None = None


def set_repo_root(path: str) -> None:
    global _repo_root
    _repo_root = Path(path).resolve()


def set_branch(branch: str) -> None:
    global _branch
    _branch = branch


def _safe_path(path: str) -> Path:
    """Resolve path and raise if it escapes the repo root."""
    resolved = (_repo_root / path).resolve()
    if not str(resolved).startswith(str(_repo_root)):
        raise PermissionError(f"Path escapes repo root: {path}")
    return resolved


def _symbol_variants(symbol: str) -> set[str]:
    """Return camelCase, snake_case, and PascalCase variants of a symbol."""
    words = re.split(r"[_\s]+|(?<=[a-z])(?=[A-Z])", symbol)
    words = [w for w in words if w]
    snake = "_".join(w.lower() for w in words)
    camel = words[0].lower() + "".join(w.capitalize() for w in words[1:])
    pascal = "".join(w.capitalize() for w in words)
    return {symbol, snake, camel, pascal}


def _read_text(path: str) -> str | None:
    """Read text from filesystem or the reviewed branch, returning None if not found."""
    full_path = _safe_path(path)
    if full_path.exists():
        return full_path.read_text(errors="replace")
    if _branch:
        result = subprocess.run(
            ["git", "show", f"{_branch}:{path}"],
            cwd=str(_repo_root),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout
    return None


def git_diff(base: str = "main", branch: str = "HEAD", context_lines: int = 3) -> str:
    """Return unified diff between base and branch, capped at MAX_DIFF_KB.

    context_lines controls how many surrounding lines are shown per hunk (default 3).
    Use context_lines=30 to pre-load ±30 lines of context around each change.
    """
    result = subprocess.run(
        ["git", "diff", f"-U{context_lines}", f"{base}...{branch}"],
        cwd=str(_repo_root),
        capture_output=True,
        text=True,
    )
    output = result.stdout
    max_bytes = MAX_DIFF_KB * 1024
    if len(output.encode()) > max_bytes:
        output = output.encode()[:max_bytes].decode(errors="replace") + "\n[diff truncated]"
    return output


def list_changed_files(base: str = "main", branch: str = "HEAD") -> list[str]:
    """List files changed between base and branch."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{branch}"],
        cwd=str(_repo_root),
        capture_output=True,
        text=True,
    )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def read_file(path: str) -> str:
    """Read a single file within the repo root, capped at MAX_FILE_LINES lines.

    Falls back to git show <branch>:<path> when the file only exists on the
    reviewed branch and not the current checkout.
    Prefer grep_context() when you only need a specific section of a file.
    """
    full_path = _safe_path(path)
    if full_path.is_dir():
        return f"'{path}' is a directory. Use list_directory('{path}') to see its contents."
    text = _read_text(path)
    if text is None:
        return f"File not found: {path}"
    lines = text.splitlines()
    if len(lines) > MAX_FILE_LINES:
        lines = lines[:MAX_FILE_LINES]
        lines.append(f"[truncated at {MAX_FILE_LINES} lines]")
    return "\n".join(lines)


def read_files(paths: list[str]) -> str:
    """Read multiple small files in one call (max 5 files, 300 combined lines).

    Use this for config/doc files where you need several at once.
    Files not found on disk are fetched from the reviewed branch via git show.
    """
    results = []
    total_lines = 0
    for path in paths[:MAX_BATCH_FILES]:
        try:
            full_path = _safe_path(path)
            if full_path.is_dir():
                results.append(f"=== {path} ===\n(directory)")
                continue
            text = _read_text(path)
            if text is None:
                results.append(f"=== {path} ===\n(not found)")
                continue
            available = MAX_BATCH_COMBINED_LINES - total_lines
            if available <= 0:
                results.append(f"=== {path} ===\n[skipped — combined line cap reached]")
                continue
            lines = text.splitlines()[:available]
            total_lines += len(lines)
            results.append(f"=== {path} ===\n" + "\n".join(lines))
        except PermissionError:
            results.append(f"=== {path} ===\n(access denied)")
    return "\n\n".join(results) if results else "No files read."


def grep_context(pattern: str, context_lines: int = 20) -> str:
    """Search for a pattern and return matches with ±context_lines of surrounding code.

    Use this instead of read_file when you only need the area around a specific
    symbol, function, or pattern — avoids loading an entire file into context.
    context_lines is capped at 30.
    """
    context_lines = min(context_lines, MAX_GREP_CONTEXT_LINES)
    result = subprocess.run(
        [_GREP, "-r", "-n", "-E",
         f"-A{context_lines}", f"-B{context_lines}",
         pattern, str(_repo_root)],
        capture_output=True,
        text=True,
    )
    lines = result.stdout.splitlines()[:MAX_GREP_OUTPUT_LINES]
    return "\n".join(lines) if lines else "No matches found."


def list_directory(path: str = ".") -> str:
    """List files and subdirectories at path within the repo root."""
    full_path = _safe_path(path)
    if not full_path.is_dir():
        return f"'{path}' is not a directory. Use read_file('{path}') to read it."
    entries = sorted(full_path.iterdir())
    lines = [f"{'dir ' if e.is_dir() else 'file'} {e.relative_to(_repo_root)}" for e in entries]
    return "\n".join(lines) if lines else "(empty directory)"


def find_references(symbol: str) -> str:
    """Find lines in the repo that reference the symbol (all case variants)."""
    variants = _symbol_variants(symbol)
    pattern = "|".join(re.escape(v) for v in variants if v)
    result = subprocess.run(
        [_GREP, "-r", "-n", "-E", pattern, str(_repo_root)],
        capture_output=True,
        text=True,
    )
    lines = result.stdout.splitlines()[:MAX_GREP_RESULTS]
    return "\n".join(lines) if lines else "No references found."


def find_definition(symbol: str) -> str:
    """Find the definition site of a symbol using a declaration-pattern heuristic."""
    variants = _symbol_variants(symbol)
    sym_pattern = "|".join(re.escape(v) for v in variants if v)
    pattern = rf"(def|class|const|function|=)\s+({sym_pattern})|({sym_pattern})\s*[=:(]"
    result = subprocess.run(
        [_GREP, "-r", "-n", "-E", pattern, str(_repo_root)],
        capture_output=True,
        text=True,
    )
    lines = result.stdout.splitlines()[:20]
    return "\n".join(lines) if lines else "No definition found."
