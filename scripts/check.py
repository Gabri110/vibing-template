"""The project's single verification: every step, or only the fast ones.

    python3 scripts/check.py           every step; on green, writes the seal
    python3 scripts/check.py --fast    the fast steps only (seconds); no seal
    python3 scripts/check.py --list    the steps, in order

"Done" means this command came back green, with its output at hand. The steps
live in scripts/check.toml, run in order and stop at the first failure; wrappers
(.sh, .bat) only find an interpreter and call this file, so the steps exist in
one place.

The seal is what a push to a protected branch asks for: it records the exact
tree (tracked and untracked files) that a full green run saw, and it is written
only if nothing changed while the run lasted. It lives in the git directory,
one per worktree, and is never committed. Format, shared with
.claude/hooks/_hooklib.py: {"tree", "head", "written", "written_epoch"}.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "scripts" / "check.toml"
SEAL_NAME = "check-seal.json"
CONTRACT_MAX_LINES = 200
DESCRIPTION_MAX = 1536
MARKER = "RELLENAR"
TOML_FILES = (
    ".claude/project.toml",
    "scripts/check.toml",
    "scripts/release.toml",
    "docs/manifest.toml",
    "scripts/boundary/leak_rules.toml",
)
JSON_FILES = (".claude/settings.json", ".claude/settings.local.json")
PY_DIRS = (".claude/hooks", ".claude/tests", "scripts")


def git(*args: str, env: dict | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env
        )
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def secs(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " s"


# --- built-in steps ------------------------------------------------------------


def frontmatter(path: Path) -> dict | None:
    """The YAML header of a SKILL.md, read just far enough: `key: value` and folded `>` blocks."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    meta: dict[str, str] = {}
    key = None
    for line in text[3:end].splitlines():
        if not line.strip():
            continue
        if line[0] in " \t" and key:
            meta[key] = (meta[key] + " " + line.strip()).strip()
            continue
        name, _, value = line.partition(":")
        key = name.strip()
        value = value.strip()
        meta[key] = "" if value in (">", "|", ">-", "|-") else value.strip("\"'")
    return meta


def check_config() -> list[str]:
    """Configuration that parses, a contract that fits, skills the harness can list."""
    import tomllib

    problems: list[str] = []
    parsed: dict[str, dict] = {}
    for name in TOML_FILES:
        path = ROOT / name
        if path.exists():
            try:
                parsed[name] = tomllib.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                problems.append(f"{name}: TOML inválido ({exc})")
    for name in JSON_FILES:
        path = ROOT / name
        if path.exists():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                problems.append(f"{name}: JSON inválido ({exc})")

    project = parsed.get(".claude/project.toml", {})
    configured = project.get("skeleton", {}).get("configured", True)
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = ROOT / name
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > CONTRACT_MAX_LINES:
            problems.append(
                f"{name}: {len(lines)} líneas. El contrato se queda por debajo de {CONTRACT_MAX_LINES}; "
                "lo que solo aplica a una parte del repo va a .claude/rules/."
            )
        if configured and any(MARKER in line for line in lines):
            problems.append(f"{name}: quedan marcas {MARKER} y .claude/project.toml dice configured = true.")

    for skill in sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")):
        where = skill.relative_to(ROOT).as_posix()
        meta = frontmatter(skill)
        if meta is None:
            problems.append(f"{where}: sin cabecera YAML entre líneas ---")
            continue
        if meta.get("name") != skill.parent.name:
            problems.append(f"{where}: name debe ser el nombre de su carpeta, {skill.parent.name}")
        description = meta.get("description", "")
        if not description:
            problems.append(f"{where}: sin description; es lo que usa el modelo para elegirla")
        elif len(description) + len(meta.get("when_to_use", "")) > DESCRIPTION_MAX:
            problems.append(f"{where}: description más when_to_use pasan de {DESCRIPTION_MAX} caracteres y se cortan")

    release = parsed.get("scripts/release.toml", {})
    ours = project.get("branches", {}).get("integration")
    if release.get("integration") and ours and release["integration"] != ours:
        problems.append(
            f"La rama de integración no coincide: {ours} en .claude/project.toml y "
            f"{release['integration']} en scripts/release.toml."
        )
    return problems


def check_compat() -> list[str]:
    """Every script still parses as Python 3.11, the oldest the hooks support."""
    problems = []
    for folder in PY_DIRS:
        for path in sorted((ROOT / folder).rglob("*.py")):
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 11))
            except SyntaxError as exc:
                problems.append(f"{path.relative_to(ROOT).as_posix()}:{exc.lineno}: no es Python 3.11 ({exc.msg})")
    return problems


BUILTINS = {"config": check_config, "compat": check_compat}


# --- running the steps -----------------------------------------------------------


def run_step(step: dict, fast: bool) -> tuple[str, str]:
    """Return (status, output): status is ok, FALLA or omitido."""
    if "builtin" in step:
        problems = BUILTINS[step["builtin"]]()
        return ("FALLA", "\n".join(problems)) if problems else ("ok", "")
    when = step.get("when")
    if when and not (ROOT / when).exists():
        return "omitido", ""
    cmd = [sys.executable if part == "{python}" else part for part in step["cmd"]]
    timeout = step.get("timeout", 120 if fast else 1800)
    try:
        result = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
        )
    except FileNotFoundError:
        return "FALLA", f"No se encuentra `{cmd[0]}`: ¿está instalado y en el PATH? (en Windows, npm es npm.cmd)"
    except subprocess.TimeoutExpired:
        return "FALLA", f"Pasó de {timeout} s."
    output = (result.stdout + result.stderr).strip()
    return ("ok", output) if result.returncode == 0 else ("FALLA", output)


def working_tree() -> str | None:
    """The tree of the working copy, untracked files included, without touching the real index."""
    if git("rev-parse", "--git-dir") is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        if git("rev-parse", "--verify", "--quiet", "HEAD") is not None and git("read-tree", "HEAD", env=env) is None:
            return None
        if git("add", "-A", env=env) is None:
            return None
        return git("write-tree", env=env)


def write_seal(tree: str) -> Path | None:
    where = git("rev-parse", "--git-path", SEAL_NAME)
    if not where:
        return None
    path = Path(where) if Path(where).is_absolute() else ROOT / where
    now = datetime.now(timezone.utc)
    seal = {
        "tree": tree,
        "head": git("rev-parse", "--verify", "--quiet", "HEAD"),
        "written": now.isoformat(timespec="seconds"),
        "written_epoch": now.timestamp(),
    }
    path.write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="La verificación única del proyecto.")
    parser.add_argument("--fast", action="store_true", help="solo los pasos rápidos; no deja sello")
    parser.add_argument("--list", action="store_true", help="enseña los pasos y sale")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        print(f"check.py necesita Python 3.11 o superior; este es {sys.version.split()[0]}.")
        return 2
    import tomllib

    steps = tomllib.loads(CONFIG.read_text(encoding="utf-8")).get("step", [])
    selected = [s for s in steps if s.get("fast") or not args.fast]
    if args.list:
        for i, step in enumerate(steps, 1):
            print(f"{i}. {step['name']}{' (rápido)' if step.get('fast') else ''}")
        return 0

    before = None if args.fast else working_tree()
    start = time.monotonic()
    for i, step in enumerate(selected, 1):
        t0 = time.monotonic()
        status, output = run_step(step, args.fast)
        print(f"[{i}/{len(selected)}] {step['name']}: {status} ({secs(time.monotonic() - t0)})", flush=True)
        if status == "FALLA":
            lines = output.splitlines()
            print("\n".join(lines[-200:]))
            print(f"\nFalla «{step['name']}»: no está hecho.")
            return 1
    total = secs(time.monotonic() - start)
    if args.fast:
        print(f"Rápida en verde ({len(selected)} pasos, {total}). Antes de integrar o de empujar a una rama protegida, la completa.")
        return 0
    if before is None:
        print(f"Todo en verde ({len(selected)} pasos, {total}). Sin repo git, sin sello.")
    elif working_tree() == before and (path := write_seal(before)):
        print(f"Todo en verde ({len(selected)} pasos, {total}). Sello en {path}: cubre este árbol exacto durante 24 h.")
    else:
        print(f"Todo en verde ({len(selected)} pasos, {total}), pero el árbol cambió mientras corría: sin sello.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
