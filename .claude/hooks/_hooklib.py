"""Shared helpers for the project's hooks: read the payload, answer, ask git.

Every hook prints at most one JSON object and fails open by default: a hook
that crashes must never block work it could not check. The one place that fails
closed (the client's code repo, in pre_bash.py) says so where it does it.

Messages are written as facts, not as orders: the official documentation warns
that imperative, system-like text in a hook's context can trip the model's
prompt-injection defences.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = HOOKS_DIR.parent.parent  # the repo that holds these hooks
MIN_PYTHON = (3, 11)
SEAL_NAME = "check-seal.json"
SEAL_MAX_AGE = 24 * 3600


def python_ok() -> bool:
    return sys.version_info >= MIN_PYTHON


def read_payload() -> dict:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def emit(event: str, *, context: str = "", deny: str = "", system: str = "") -> None:
    """Print the hook's single JSON answer; print nothing when there is nothing to say.

    A guard that lets a call through stays silent instead of answering "allow",
    so the ask and deny rules of settings.json still apply.
    """
    specific: dict = {}
    if deny:
        specific["permissionDecision"] = "deny"
        specific["permissionDecisionReason"] = deny
    if context:
        specific["additionalContext"] = context
    out: dict = {}
    if specific:
        out["hookSpecificOutput"] = {"hookEventName": event, **specific}
    if system:
        out["systemMessage"] = system
    if out:
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")


def run(main, event: str) -> None:
    """Run a hook's main(); a crash or an old Python lets the action through."""
    if not python_ok():
        found = sys.version.split()[0]
        print(f"hook {event}: needs Python 3.11+, found {found}", file=sys.stderr)
        return
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - a hook must never break the session
        print(f"hook {event} failed open: {exc!r}", file=sys.stderr)


# --- git -------------------------------------------------------------------


def git(*args: str, cwd: str | os.PathLike | None = None, timeout: float = 5) -> str | None:
    """Run git; return stripped stdout, or None when it fails or times out."""
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=off", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def toplevel(cwd: str | os.PathLike | None) -> Path | None:
    out = git("rev-parse", "--show-toplevel", cwd=cwd)
    return Path(out) if out else None


def git_dir(cwd: str | os.PathLike | None) -> Path | None:
    out = git("rev-parse", "--absolute-git-dir", cwd=cwd)
    return Path(out) if out else None


def common_dir(cwd: str | os.PathLike | None) -> Path | None:
    out = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=cwd)
    return Path(out).resolve() if out else None


def current_branch(cwd: str | os.PathLike | None) -> str | None:
    """The checked-out branch, also before the first commit; None when detached."""
    return git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=cwd)


def role(cwd: str | os.PathLike | None) -> str:
    """'client' in a code repo wired by scripts/boundary/setup_code_repo.py."""
    return git("config", "--get", "skeleton.role", cwd=cwd) or ""


_project_common: list[Path | None] = []


def in_project(cwd: str | os.PathLike | None) -> bool:
    """True when cwd is this project's repo or one of its worktrees."""
    if not _project_common:
        _project_common.append(common_dir(PROJECT_DIR))
    mine = _project_common[0]
    return mine is not None and common_dir(cwd) == mine


# --- configuration ----------------------------------------------------------


def load_toml(path: Path) -> dict:
    """Parse a TOML file; {} when it is missing or broken (check.py reports broken ones)."""
    try:
        import tomllib
    except ModuleNotFoundError:
        return {}
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except (OSError, ValueError):
        return {}


def project_config() -> dict:
    return load_toml(PROJECT_DIR / ".claude" / "project.toml")


def release_config(top: Path | None) -> dict:
    return load_toml(top / "scripts" / "release.toml") if top else {}


def policy(cwd: str | os.PathLike | None) -> dict | None:
    """Branch rules for the repo a command runs in; None for repos the project does not own."""
    cfg = project_config()
    top = toplevel(cwd)
    release = release_config(top).get("branch", "")
    if role(cwd) == "client":
        b = cfg.get("boundary", {})
        return {
            "client": True,
            "integration": b.get("integration", "dev"),
            "release": release or b.get("release", ""),
            "human_commit": True,
            "allow_no_ff": False,
            "push_allow": list(b.get("push_allow", [])),
        }
    if not in_project(cwd):
        return None
    b = cfg.get("branches", {})
    return {
        "client": False,
        "integration": b.get("integration", "main"),
        "release": release,
        "human_commit": bool(b.get("human_commit", False)),
        "allow_no_ff": bool(b.get("allow_no_ff", True)),
        "push_allow": list(b.get("push_allow", [])),
    }


def skill_installed(name: str) -> bool | None:
    """True or False for project and personal skills; None for plugin skills (`plugin:skill`)."""
    if ":" in name:
        return None
    for base in (PROJECT_DIR / ".claude" / "skills", Path.home() / ".claude" / "skills"):
        if (base / name / "SKILL.md").is_file():
            return True
    return False


# --- small utilities ----------------------------------------------------------


def first_time(namespace: str, session_id: str, key: str) -> bool:
    """True the first time `key` shows up in this session; remembered in a temp file."""
    folder = Path(tempfile.gettempdir()) / f"claude-skeleton-{namespace}"
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "no-session")
    marker = folder / f"{safe}.txt"
    try:
        seen = set(marker.read_text(encoding="utf-8").splitlines())
    except OSError:
        seen = set()
    if key in seen:
        return False
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with marker.open("a", encoding="utf-8") as fh:
            fh.write(key + "\n")
    except OSError:
        pass
    return True


def prune_markers(max_age_days: int = 7) -> None:
    """Delete the once-per-session markers of sessions older than a week."""
    limit = time.time() - max_age_days * 86400
    for folder in Path(tempfile.gettempdir()).glob("claude-skeleton-*"):
        for marker in folder.glob("*.txt"):
            try:
                if marker.stat().st_mtime < limit:
                    marker.unlink()
            except OSError:
                pass


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`**` crosses folders, `*` and `?` stay inside one: the manifest's glob dialect."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def glob_match(path: str, pattern: str) -> bool:
    return bool(glob_to_regex(pattern).match(path))


def seal_covers(cwd: str | os.PathLike | None, commit: str) -> tuple[bool, str]:
    """Whether a full green `scripts/check.py` run saw exactly this commit's tree.

    check.py writes the seal (git dir / check-seal.json) only when the working
    tree did not change during the run; this reads it. Same format on both sides:
    {"tree": <sha>, "head": <sha or null>, "written": <iso>, "written_epoch": <s>}.
    """
    where = git("rev-parse", "--git-path", SEAL_NAME, cwd=cwd)
    if not where:
        return False, "no se encuentra el directorio de git"
    path = Path(where)
    if not path.is_absolute():
        path = Path(cwd or ".") / path
    try:
        seal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "no hay sello de una verificación completa en verde"
    age = time.time() - float(seal.get("written_epoch", 0))
    if age > SEAL_MAX_AGE or age < -300:
        return False, "el sello tiene más de 24 horas"
    tree = git("rev-parse", f"{commit}^{{tree}}", cwd=cwd)
    if not tree or tree != seal.get("tree"):
        return False, "el sello es de otro árbol: algo cambió después de la verificación completa"
    return True, ""
