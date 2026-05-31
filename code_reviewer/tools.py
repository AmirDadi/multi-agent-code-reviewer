import re
import shutil
import subprocess
from pathlib import Path

_GREP = shutil.which("grep") or "grep"

MAX_FILE_LINES = 500
MAX_DIFF_KB = 100
MAX_GREP_RESULTS = 50

_repo_root: Path | None = None


def set_repo_root(path: str) -> None:
    global _repo_root
    _repo_root = Path(path).resolve()


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


def git_diff(base: str = "main", branch: str = "HEAD") -> str:
    """Return unified diff between base and branch, capped at MAX_DIFF_KB."""
    result = subprocess.run(
        ["git", "diff", f"{base}...{branch}"],
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
    """Read a file within the repo root, capped at MAX_FILE_LINES lines."""
    full_path = _safe_path(path)
    if full_path.is_dir():
        return f"'{path}' is a directory. Use list_directory('{path}') to see its contents."
    lines = full_path.read_text(errors="replace").splitlines()
    if len(lines) > MAX_FILE_LINES:
        lines = lines[:MAX_FILE_LINES]
        lines.append(f"[truncated at {MAX_FILE_LINES} lines]")
    return "\n".join(lines)


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
