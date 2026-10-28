"""Wires a client's code repo to this internal repo, without versioning anything in it.

    python3 scripts/boundary/setup_code_repo.py ../codigo-cliente            wire it (safe to repeat)
    python3 scripts/boundary/setup_code_repo.py ../codigo-cliente --check    what is missing or stale (exit 1)
    python3 scripts/boundary/setup_code_repo.py ../codigo-cliente --remove   undo it

What it writes in the code repo, and why git there never sees any of it:

    git config skeleton.role client     marks the repo: the hooks apply [boundary] and fail closed
    .git/info/exclude                   keeps .claude/, CLAUDE.local.md and .remember/ out of git
    .claude/settings.local.json         this repo's hooks by absolute path, its permissions, attribution
    .claude/skills/<name>               one link per skill of this repo
    .claude/rules/*.md                  copies: a rule linked from outside the project does not load
    CLAUDE.local.md                     a copy of AGENTS.md and CLAUDE.md: an import from outside the
                                        project waits for an approval dialog that may never show
    hooks/pre-commit, commit-msg, pre-push   shims calling githook.py here: the real guarantee
    .claude/.skeleton-copies.json       what was copied from where, so --check and the session start
                                        can tell when a copy is stale
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

INTERNAL = Path(__file__).resolve().parents[2]
HOOK_NAMES = ("pre-commit", "commit-msg", "pre-push")
MARK = "skeleton-githook"
GENERATED = "Copia generada por setup_code_repo.py"
EXCLUDE_BEGIN, EXCLUDE_END = "# >>> skeleton (setup_code_repo.py)", "# <<< skeleton"
EXCLUDED = (".claude/", "CLAUDE.local.md", ".remember/")
COPIES = Path(".claude") / ".skeleton-copies.json"
MANAGED_KEYS = ("hooks", "worktree", "attribution")


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8")
    if check and result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip() if result.returncode == 0 else ""


def digest(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for path in paths:
        h.update(path.read_bytes())
    return h.hexdigest()


def is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def make_link(source: Path, link: Path) -> None:
    try:
        link.symlink_to(source, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        import _winapi  # a junction needs no admin rights or developer mode

        _winapi.CreateJunction(str(source), str(link))


def remove_link(link: Path) -> None:
    if link.is_symlink():
        link.unlink()
    else:
        os.rmdir(link)  # a junction: removes the link, never its target


def load_toml(path: Path) -> dict:
    import tomllib

    return tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


class Wiring:
    def __init__(self, target: Path) -> None:
        if not target.is_dir():
            raise SystemExit(f"{target} no existe.")
        common = Path(git(target, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
        if common == Path(git(INTERNAL, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve():
            raise SystemExit("Ese es el propio repo interno: se cablea el repo de código del cliente.")
        self.top = common.parent if common.name == ".git" else Path(git(target, "rev-parse", "--show-toplevel"))
        self.common = common
        hooks_path = git(self.top, "config", "--get", "core.hooksPath", check=False)
        self.hooks_dir = (self.top / hooks_path).resolve() if hooks_path else common / "hooks"
        self.boundary = load_toml(INTERNAL / ".claude" / "project.toml").get("boundary", {})
        self.claude = self.top / ".claude"
        self.state = self._load_state()

    # -- what gets written --------------------------------------------------

    def _load_state(self) -> dict:
        try:
            return json.loads((self.top / COPIES).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"copies": {}, "managed": {}}

    def skills(self) -> list[Path]:
        return sorted(p for p in (INTERNAL / ".claude" / "skills").iterdir() if (p / "SKILL.md").is_file())

    def rules(self) -> list[Path]:
        return sorted((INTERNAL / ".claude" / "rules").glob("*.md"))

    def contract_sources(self) -> list[Path]:
        return [p for p in (INTERNAL / "AGENTS.md", INTERNAL / "CLAUDE.md") if p.exists()]

    def rule_copy(self, source: Path) -> str:
        text = source.read_text(encoding="utf-8")
        note = f"<!-- {GENERATED} desde {source.as_posix()}: se edita allí, no aquí. -->\n"
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end >= 0:
                cut = text.find("\n", end + 4)
                cut = len(text) if cut < 0 else cut + 1
                return text[:cut] + note + text[cut:]
        return note + text

    def contract_copy(self) -> str:
        parts = [
            f"<!-- {GENERATED} desde {INTERNAL.as_posix()}: el contrato se edita allí, en AGENTS.md y "
            "CLAUDE.md, y se vuelve a pasar el setup. -->\n"
        ]
        for source in self.contract_sources():
            lines = [line for line in source.read_text(encoding="utf-8").splitlines() if line.strip() != "@AGENTS.md"]
            parts.append("\n".join(lines).strip() + "\n")
        return "\n".join(parts)

    def settings(self, existing: dict) -> tuple[dict, dict[str, list[str]]]:
        ours = json.loads((INTERNAL / ".claude" / "settings.json").read_text(encoding="utf-8"))
        run_sh = (INTERNAL / ".claude" / "hooks" / "run.sh").as_posix()
        hooks = json.loads(json.dumps(ours.get("hooks", {})).replace("${CLAUDE_PROJECT_DIR}/.claude/hooks/run.sh", run_sh))
        merged = {**existing, "hooks": hooks, "worktree": ours.get("worktree", {"baseRef": "head"})}
        if not self.boundary.get("attribution", False):
            merged["attribution"] = {"commit": "", "pr": ""}
        permissions = dict(existing.get("permissions", {}))
        added: dict[str, list[str]] = {}
        for kind in ("allow", "ask", "deny"):
            current = list(permissions.get(kind, []))
            for rule in ours.get("permissions", {}).get(kind, []):
                if rule not in current:
                    current.append(rule)
                    added.setdefault(kind, []).append(rule)
            if current:
                permissions[kind] = current
        merged["permissions"] = permissions
        return merged, added

    def shim(self, name: str) -> str:
        internal = INTERNAL.as_posix()
        return (
            "#!/bin/sh\n"
            f"# {MARK}: escrito por setup_code_repo.py desde {internal}; se quita con --remove\n"
            f"internal='{internal}'\n"
            'if [ ! -f "$internal/scripts/boundary/githook.py" ]; then\n'
            '  echo "skeleton: falta $internal; este hook rechaza hasta que vuelva o se quite con '
            'setup_code_repo.py --remove" >&2\n'
            "  exit 1\n"
            "fi\n"
            f'exec bash "$internal/.claude/hooks/run.sh" "$internal/scripts/boundary/githook.py" {name} "$@"\n'
        )

    # -- apply, check, remove -------------------------------------------------

    def _exclude(self, present: bool) -> None:
        path = self.common / "info" / "exclude"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if EXCLUDE_BEGIN in text:
            head, _, rest = text.partition(EXCLUDE_BEGIN)
            _, _, tail = rest.partition(EXCLUDE_END)
            text = head.rstrip("\n") + ("\n" if head.strip() else "") + tail.lstrip("\n")
        if present:
            text = text.rstrip("\n") + ("\n" if text.strip() else "") + "\n".join([EXCLUDE_BEGIN, *EXCLUDED, EXCLUDE_END]) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def apply(self) -> int:
        problems: list[str] = []
        if self.claude.is_symlink():
            raise SystemExit(f"{self.claude} es un enlace: Claude Code no crea worktrees así. Tiene que ser una carpeta.")
        git(self.top, "config", "--local", "skeleton.role", "client")
        git(self.top, "config", "--local", "skeleton.home", INTERNAL.as_posix())
        self._exclude(present=True)
        self.claude.mkdir(exist_ok=True)

        settings_path = self.claude / "settings.local.json"
        existing = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
        merged, added = self.settings(existing)
        settings_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        previous = self.state.get("managed", {}).get("permissions", {})
        for kind, rules in previous.items():
            added[kind] = sorted(set(added.get(kind, [])) | set(rules))

        links = []
        (self.claude / "skills").mkdir(exist_ok=True)
        for source in self.skills():
            link = self.claude / "skills" / source.name
            if is_link(link):
                remove_link(link)
            elif link.exists():
                problems.append(f"{link}: ya hay una skill propia con ese nombre; se deja como está.")
                continue
            make_link(source, link)
            links.append(link.relative_to(self.top).as_posix())

        copies: dict[str, dict] = {}

        def write_copy(target: Path, text: str, sources: list[Path]) -> None:
            if target.exists() and GENERATED not in target.read_text(encoding="utf-8", errors="replace"):
                problems.append(f"{target}: ya existe y no es una copia nuestra; no se toca.")
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            copies[target.relative_to(self.top).as_posix()] = {
                "sources": [s.as_posix() for s in sources],
                "sha256": digest(sources),
            }

        for source in self.rules():
            write_copy(self.claude / "rules" / source.name, self.rule_copy(source), [source])
        if self.contract_sources():
            write_copy(self.top / "CLAUDE.local.md", self.contract_copy(), self.contract_sources())

        hooks = []
        self.hooks_dir.mkdir(parents=True, exist_ok=True)
        for name in HOOK_NAMES:
            path = self.hooks_dir / name
            if path.exists() and MARK not in path.read_text(encoding="utf-8", errors="replace"):
                problems.append(f"{path}: ya hay un hook {name} ajeno; se fusiona a mano llamando a githook.py {name}.")
                continue
            path.write_bytes(self.shim(name).encode("utf-8"))
            path.chmod(0o755)
            hooks.append(path.as_posix())

        state = {"copies": copies, "managed": {"permissions": added, "links": links, "hooks": hooks}}
        (self.top / COPIES).write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Repo del cliente cableado: {self.top}")
        for problem in problems:
            print(f"  aviso: {problem}")
        return 1 if problems else 0

    def check(self) -> int:
        issues = []
        if git(self.top, "config", "--get", "skeleton.role", check=False) != "client":
            issues.append("falta la marca skeleton.role = client")
        exclude = self.common / "info" / "exclude"
        if not exclude.exists() or EXCLUDE_BEGIN not in exclude.read_text(encoding="utf-8"):
            issues.append("falta el bloque de .git/info/exclude")
        settings = self.claude / "settings.local.json"
        run_sh = (INTERNAL / ".claude" / "hooks" / "run.sh").as_posix()
        if not settings.exists() or run_sh not in settings.read_text(encoding="utf-8"):
            issues.append("settings.local.json no llama a los hooks de este repo interno")
        for source in self.skills():
            if not is_link(self.claude / "skills" / source.name):
                issues.append(f"falta el enlace de la skill {source.name}")
        expected = {(self.claude / "rules" / s.name) for s in self.rules()}
        if self.contract_sources():
            expected.add(self.top / "CLAUDE.local.md")
        copies = self.state.get("copies", {})
        for target in sorted(expected):
            rel = target.relative_to(self.top).as_posix()
            info = copies.get(rel)
            if not target.exists() or info is None:
                issues.append(f"falta {rel}")
            elif digest([Path(s) for s in info["sources"] if Path(s).exists()]) != info["sha256"]:
                issues.append(f"{rel} está desfasada: su original cambió")
        for name in HOOK_NAMES:
            path = self.hooks_dir / name
            if not path.exists() or MARK not in path.read_text(encoding="utf-8", errors="replace"):
                issues.append(f"falta el hook de git {name}")
        if issues:
            print(f"{self.top}:")
            print("\n".join(f"  ✘ {issue}" for issue in issues))
            print("Se arregla volviendo a pasar setup_code_repo.py sin opciones.")
            return 1
        print(f"{self.top}: cableado y al día.")
        return 0

    def remove(self) -> int:
        git(self.top, "config", "--local", "--unset", "skeleton.role", check=False)
        git(self.top, "config", "--local", "--unset", "skeleton.home", check=False)
        self._exclude(present=False)
        managed = self.state.get("managed", {})
        settings_path = self.claude / "settings.local.json"
        if settings_path.exists():
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            for key in MANAGED_KEYS:
                data.pop(key, None)
            permissions = data.get("permissions", {})
            for kind, rules in managed.get("permissions", {}).items():
                kept = [r for r in permissions.get(kind, []) if r not in rules]
                if kept:
                    permissions[kind] = kept
                else:
                    permissions.pop(kind, None)
            if not permissions:
                data.pop("permissions", None)
            if data:
                settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            else:
                settings_path.unlink()
        for rel in managed.get("links", []):
            if is_link(self.top / rel):
                remove_link(self.top / rel)
        for rel in self.state.get("copies", {}):
            path = self.top / rel
            if path.exists() and GENERATED in path.read_text(encoding="utf-8", errors="replace"):
                path.unlink()
        for name in HOOK_NAMES:
            path = self.hooks_dir / name
            if path.exists() and MARK in path.read_text(encoding="utf-8", errors="replace"):
                path.unlink()
        (self.top / COPIES).unlink(missing_ok=True)
        for folder in (self.claude / "rules", self.claude / "skills", self.claude):
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        print(f"Cableado quitado de {self.top}.")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cablea el repo de código del cliente a este repo interno.")
    parser.add_argument("repo", type=Path, help="carpeta del repo de código del cliente")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="dice qué falta o está desfasado (sale con 1)")
    mode.add_argument("--remove", action="store_true", help="lo deshace todo")
    args = parser.parse_args(argv)
    wiring = Wiring(args.repo.resolve())
    if args.check:
        return wiring.check()
    if args.remove:
        return wiring.remove()
    return wiring.apply()


if __name__ == "__main__":
    sys.exit(main())
