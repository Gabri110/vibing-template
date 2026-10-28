"""Git hooks of the client's code repo; setup_code_repo.py installs small shims that call this.

    githook.py pre-commit            on that repo's protected branches: leak scan of what is staged
    githook.py commit-msg FILE       no tool traces when [boundary] attribution = false, and no leaks
    githook.py pre-push REMOTE URL   only the refs in [boundary] push_allow leave

These are the boundary's guarantee: git runs them on every commit and push in
that repo, made by Claude or by a person, whatever opened the session. The
Claude hooks only see what goes through Claude.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INTERNAL = HERE.parent.parent
TRACE = re.compile(r"(?im)^\s*co-authored-by:.*(claude|anthropic)|generated with .*claude|\U0001F916")


def load_toml(path: Path) -> dict:
    import tomllib

    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def boundary() -> dict:
    return load_toml(INTERNAL / ".claude" / "project.toml").get("boundary", {})


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.stdout.strip() if result.returncode == 0 else ""


def scan(*args: str) -> int:
    return subprocess.run([sys.executable, str(HERE / "leak_scan.py"), *args]).returncode


def pre_commit() -> int:
    top = Path(git("rev-parse", "--show-toplevel") or ".")
    branch = git("symbolic-ref", "--quiet", "--short", "HEAD")
    release = load_toml(top / "scripts" / "release.toml").get("branch", "")
    protected = {b for b in (boundary().get("integration", "dev"), release) if b}
    if branch not in protected:
        return 0
    return 0 if scan("--repo", str(top), "--staged") == 0 else 1


def commit_msg(path: str) -> int:
    attribution = bool(boundary().get("attribution", False))
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    if not attribution and TRACE.search(body):
        print("El mensaje lleva rastros de la herramienta (coautoría o «generated with»): en este repo, no.", file=sys.stderr)
        return 1
    skip = ["--skip", "herramienta"] if attribution else []
    return 0 if scan("--text", path, *skip) == 0 else 1


def _local(url: str) -> bool:
    if url.startswith("file://"):
        return True
    if "://" in url or re.match(r"^[^/\\]+@[^/\\]+:", url) or re.match(r"^[A-Za-z0-9.-]{2,}:", url):
        return False
    return True


def pre_push(remote: str, url: str) -> int:
    allow = boundary().get("push_allow", [])
    if not allow or _local(url):
        return 0
    refused = []
    for line in sys.stdin:
        parts = line.split()
        if len(parts) == 4:
            name = parts[2].removeprefix("refs/heads/").removeprefix("refs/tags/")
            if not any(fnmatch.fnmatchcase(name, p) for p in allow):
                refused.append(name)
    if refused:
        print(f"Desde este repo solo salen {', '.join(allow)}; no sale: {', '.join(refused)}.", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print("githook.py pre-commit | commit-msg FILE | pre-push REMOTE URL", file=sys.stderr)
        return 2
    name, args = argv[0], argv[1:]
    if name == "pre-commit":
        return pre_commit()
    if name == "commit-msg" and args:
        return commit_msg(args[0])
    if name == "pre-push" and len(args) >= 2:
        return pre_push(args[0], args[1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
