"""Helpers for the skeleton's tests: throwaway projects with an isolated git, hooks run through run.sh.

Every sandbox is a copy of this skeleton in a temp folder, with its own HOME and
no global or system git configuration, so the tests never read or touch the
person's settings. Hooks run exactly as Claude Code runs them: `bash run.sh
<hook>` with the JSON payload on stdin.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKELETON = Path(__file__).resolve().parents[2]
HOOKS = SKELETON / ".claude" / "hooks"

# Modules a project may have retired: their tests skip themselves when the files are gone.
HAS_DOCS = (SKELETON / "scripts" / "docs_impact.py").exists()
HAS_RELEASE = (SKELETON / "scripts" / "release.py").exists()
HAS_BOUNDARY = all((SKELETON / "scripts" / "boundary" / n).exists() for n in ("setup_code_repo.py", "leak_scan.py", "githook.py"))

# The policy the tests assume, whatever the project chose in its own .claude/project.toml.
TEST_PROJECT = """
[skeleton]
version = "test"
configured = false

[branches]
integration = "main"
human_commit = false
allow_no_ff = true
push_allow = []

[style]
skill = ""

[boundary]
integration = "dev"
push_allow = ["dev", "master", "v*"]
attribution = false

[[skills.trigger]]
skill = "configurar-proyecto"
pattern = "configur\\\\w* (el |del )?proyecto"
note = "prueba"
"""

TEST_LEAK_RULES = """
[[rule]]
name = "herramienta"
why = "rastros de la herramienta"
terms = ["co-authored-by: claude", "generated with claude code"]

[[rule]]
name = "secreto"
why = "claves"
pattern = '''(?i)(api[_-]?key|secret|token|password)\\s*[:=]\\s*['"][A-Za-z0-9_\\-]{16,}['"]'''
mask = true

[[rule]]
name = "interno"
why = "nombres del equipo"
words = ["Zeta"]

[allow]
"""

# A check.toml with one fast and one full step that always pass: the real one runs
# these very tests, and a sandbox must not start another round of sandboxes.
QUICK_CHECK = """
[[step]]
name = "rápido"
cmd = ["{python}", "-c", "pass"]
fast = true

[[step]]
name = "completo"
cmd = ["{python}", "-c", "pass"]
"""


def isolated_env(home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        HOME=str(home),
        USERPROFILE=str(home),
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="Test",
        GIT_AUTHOR_EMAIL="test@example.com",
        GIT_COMMITTER_NAME="Test",
        GIT_COMMITTER_EMAIL="test@example.com",
        SKELETON_PYTHON=sys.executable,
        PYTHONDONTWRITEBYTECODE="1",
    )
    return env


class Sandbox:
    """A temporary project made from this skeleton, with its own repo and HOME."""

    def __init__(self, commit: bool = True, quick_check: bool = True) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="skeleton-test-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.root = self.tmp / "project"
        shutil.copytree(
            SKELETON,
            self.root,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "worktrees", "settings.local.json"),
            symlinks=True,
        )
        if quick_check:
            (self.root / "scripts" / "check.toml").write_text(QUICK_CHECK, encoding="utf-8")
        (self.root / ".claude" / "project.toml").write_text(TEST_PROJECT, encoding="utf-8")
        (self.root / "docs" / "manifest.toml").unlink(missing_ok=True)  # tests that need one write their own
        if (self.root / "scripts" / "boundary").is_dir():
            (self.root / "scripts" / "boundary" / "leak_rules.toml").write_text(TEST_LEAK_RULES, encoding="utf-8")
        self.env = isolated_env(self.home)
        self.git("init", "-q", "-b", "main")
        if commit:
            self.git("add", "-A")
            self.git("commit", "-q", "-m", "init")

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- running things ------------------------------------------------------

    def run(self, *cmd: str, cwd: Path | None = None, check: bool = True, stdin: str | None = None):
        return subprocess.run(
            list(cmd),
            cwd=cwd or self.root,
            env=self.env,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=check,
            timeout=300,
        )

    def git(self, *args: str, cwd: Path | None = None, check: bool = True) -> str:
        return self.run("git", *args, cwd=cwd, check=check).stdout.strip()

    def python(self, script: str, *args: str, cwd: Path | None = None, check: bool = False):
        return self.run(sys.executable, str(self.root / script), *args, cwd=cwd, check=check)

    def hook(self, name: str, payload: dict) -> dict | None:
        result = self.run("bash", str(self.root / ".claude" / "hooks" / "run.sh"), name, stdin=json.dumps(payload))
        out = result.stdout.strip()
        return json.loads(out) if out else None

    def bash(self, command: str, cwd: Path | None = None, tool: str = "Bash", session: str = "s1") -> str | None:
        """Run pre_bash.py on a command; the deny reason, or None when it lets it through."""
        payload = {
            "tool_name": tool,
            "tool_input": {"command": command},
            "cwd": str(cwd or self.root),
            "session_id": session,
        }
        return deny_reason(self.hook("pre_bash.py", payload))

    # -- shaping the project ---------------------------------------------------

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def commit_file(self, rel: str, text: str, message: str = "change", cwd: Path | None = None) -> None:
        base = cwd or self.root
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.git("add", rel, cwd=base)
        self.git("commit", "-q", "-m", message, cwd=base)

    def set_toml(self, rel: str, old: str, new: str) -> None:
        path = self.root / rel
        text = path.read_text(encoding="utf-8")
        assert old in text, f"{old!r} not in {rel}"
        path.write_text(text.replace(old, new), encoding="utf-8")

    def remote(self) -> Path:
        """A bare repo as origin, with main pushed to it."""
        bare = self.tmp / "origin.git"
        self.git("init", "-q", "--bare", "-b", "main", str(bare))
        self.git("remote", "add", "origin", str(bare))
        self.git("push", "-q", "origin", "main")
        return bare


def deny_reason(answer: dict | None) -> str | None:
    if not answer:
        return None
    specific = answer.get("hookSpecificOutput", {})
    if specific.get("permissionDecision") == "deny":
        return specific.get("permissionDecisionReason", "")
    return None


def context_of(answer: dict | None) -> str:
    if not answer:
        return ""
    return answer.get("hookSpecificOutput", {}).get("additionalContext", "")
