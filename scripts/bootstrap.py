"""Puts the skeleton to work: checks a machine and a project, or adopts it into an existing repo.

    python3 scripts/bootstrap.py doctor            what this machine and project need, checked
    python3 scripts/bootstrap.py adopt ../mi-repo  copies the skeleton into a repo, never overwriting

`doctor` is what to run first on a new machine, and after updating Claude Code:
hooks that cannot find their interpreter fail open, in silence, and this is
where that shows. `adopt` copies what is missing and lists what has to be merged
by hand; after it, the guided configuration (/configurar-proyecto) does the rest.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_CLAUDE = (2, 1, 277)

# Owned by the skeleton: replaced as a whole when the skeleton is updated, never edited per project.
SKELETON_OWNED = [
    ".claude/hooks",
    ".claude/tests",
    ".claude/skills/configurar-proyecto",
    ".claude/skills/verificar",
    ".claude/skills/cerrar-tarea",
    ".claude/skills/revision-periodica",
    ".claude/skills/sincronizar-docs",
    "scripts/check.py",
    "scripts/docs_impact.py",
    "scripts/release.py",
    "scripts/bootstrap.py",
    "scripts/boundary/leak_scan.py",
    "scripts/boundary/githook.py",
    "scripts/boundary/setup_code_repo.py",
    "docs/practicas.md",
]
# Owned by the project: copied when missing, merged by hand when they already exist.
PROJECT_OWNED = [
    "AGENTS.md",
    "CLAUDE.md",
    ".claude/settings.json",
    ".claude/project.toml",
    ".claude/skills/README.md",
    ".claude/rules/ejemplo-ruta.md",
    "scripts/check.toml",
    "scripts/release.toml",
    "scripts/boundary/leak_rules.toml",
    "docs/manifest.toml",
    "docs/meeting-log.md",
    "docs/backlog.md",
    ".gitattributes",
    ".worktreeinclude",
]


def run(*cmd: str, stdin: str | None = None, cwd: Path = ROOT) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            list(cmd), cwd=cwd, input=stdin, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None


# --- doctor -------------------------------------------------------------------------


def doctor() -> int:
    results: list[tuple[str, str, str]] = []  # (mark, what, detail)

    def report(ok: bool | None, what: str, detail: str = "") -> None:
        results.append(("✔" if ok else "⚠" if ok is None else "✘", what, detail))

    report(sys.version_info >= (3, 11), "Python de este comando", sys.version.split()[0])

    git = run("git", "--version")
    version = tuple(int(n) for n in re.findall(r"\d+", git.stdout)[:2]) if git and git.returncode == 0 else ()
    report(bool(version) and version >= (2, 31), "git 2.31 o superior", git.stdout.strip() if git else "no está")

    bash = shutil.which("bash")
    report(bool(bash), "bash para lanzar los hooks", bash or "no está: en Windows, Git Bash")

    run_sh = ROOT / ".claude" / "hooks" / "run.sh"
    report(b"\r\n" not in run_sh.read_bytes(), "run.sh con finales de línea LF", "CRLF rompe bash" if b"\r\n" in run_sh.read_bytes() else "")
    if bash:
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / "probe.py"
            probe.write_text("import sys; print('%d.%d.%d' % sys.version_info[:3])\n", encoding="utf-8")
            picked = run("bash", str(run_sh), str(probe))
        found = picked.stdout.strip() if picked and picked.returncode == 0 else ""
        numbers = tuple(int(n) for n in found.split(".")) if found else ()
        report(bool(numbers) and numbers >= (3, 11), "Python que eligen los hooks (run.sh)",
               found or "ninguno: los hooks fallarán abiertos; se fija SKELETON_PYTHON")

    claude = run("claude", "--version") if shutil.which("claude") else None
    if claude and claude.returncode == 0:
        numbers = tuple(int(n) for n in re.findall(r"\d+", claude.stdout)[:3])
        report(numbers >= MIN_CLAUDE, f"Claude Code {'.'.join(map(str, MIN_CLAUDE))} o superior", claude.stdout.strip())
    else:
        report(None, "Claude Code en el PATH", "no se encuentra: la comprobación de versión se salta")

    settings_path = ROOT / ".claude" / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        report(True, ".claude/settings.json se lee")
    except (OSError, ValueError) as exc:
        settings = {}
        report(False, ".claude/settings.json se lee", str(exc))
    for event, groups in settings.get("hooks", {}).items():
        for group in groups:
            for hook in group.get("hooks", []):
                script = hook.get("command", "").split()[-1]
                exists = (ROOT / ".claude" / "hooks" / script).is_file()
                report(exists, f"hook de {event}: {script}", "" if exists else "no existe el fichero")

    if bash:
        samples = {
            "session_start.py": {"cwd": str(ROOT), "source": "startup"},
            "pre_bash.py": {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(ROOT)},
            "prompt.py": {"prompt": "una prueba del doctor", "session_id": "doctor"},
            "post_edit.py": {"tool_name": "Edit", "tool_input": {"file_path": str(ROOT / "README.md")},
                             "cwd": str(ROOT), "session_id": "doctor"},
        }
        for name, payload in samples.items():
            answer = run("bash", str(run_sh), name, stdin=json.dumps(payload))
            ok = bool(answer) and answer.returncode == 0
            if ok and answer.stdout.strip():
                try:
                    json.loads(answer.stdout)
                except ValueError:
                    ok = False
            report(ok, f"{name} responde", "" if ok else (answer.stderr.strip()[-200:] if answer else "no corre"))

    try:
        import tomllib

        project = tomllib.loads((ROOT / ".claude" / "project.toml").read_text(encoding="utf-8"))
        configured = project.get("skeleton", {}).get("configured", True)
        report(True if configured else None, "proyecto configurado", "" if configured else "falta: /configurar-proyecto")
    except (OSError, ValueError, ModuleNotFoundError) as exc:
        report(False, ".claude/project.toml se lee", str(exc))

    for mark, what, detail in results:
        print(f"{mark} {what}" + (f": {detail}" if detail else ""))
    return 1 if any(mark == "✘" for mark, _, _ in results) else 0


# --- adopt --------------------------------------------------------------------------


def adopt(dest: Path) -> int:
    dest = dest.resolve()
    if not dest.is_dir():
        print(f"{dest} no existe.")
        return 1
    if dest == ROOT:
        print("Ese es el propio esqueleto.")
        return 1
    copied, same, merge = [], [], []
    # The skeleton's guide is README.md until /configurar-proyecto moves it to docs/esqueleto.md.
    guide = "docs/esqueleto.md" if (ROOT / "docs" / "esqueleto.md").exists() else "README.md"
    plan = [(p, p) for p in SKELETON_OWNED + PROJECT_OWNED] + [(guide, "docs/esqueleto.md")]
    for source_rel, target_rel in plan:
        source, target = ROOT / source_rel, dest / target_rel
        if not source.exists():
            continue
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(source, target)
            copied.append(target_rel)
        elif source.is_file() and filecmp.cmp(source, target, shallow=False):
            same.append(target_rel)
        else:
            merge.append(target_rel)

    gitignore = dest / ".gitignore"
    ours = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    theirs = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    missing = [line for line in ours if line.strip() and not line.startswith("#") and line not in theirs]
    if missing:
        text = "\n".join(theirs).rstrip("\n")
        block = "\n".join(["# Claude Code (esqueleto)", *missing])
        gitignore.write_text((text + "\n\n" if text else "") + block + "\n", encoding="utf-8")

    print(f"Esqueleto adoptado en {dest}")
    print(f"  copiados: {len(copied)}" + (f" ({', '.join(copied[:6])}{', ...' if len(copied) > 6 else ''})" if copied else ""))
    if same:
        print(f"  ya iguales: {len(same)}")
    if missing:
        print(f"  .gitignore: {len(missing)} líneas añadidas")
    if merge:
        print("  ya existían y se fusionan a mano (no se ha tocado nada):")
        for rel in merge:
            print(f"    - {rel}")
        if ".claude/settings.json" in merge:
            print("    En settings.json lo que hay que llevarse es el bloque hooks, worktree.baseRef y las listas de permisos.")
    if run("git", "rev-parse", "--git-dir", cwd=dest) is None or run("git", "rev-parse", "--git-dir", cwd=dest).returncode != 0:
        print("  aviso: no es un repo git; sin git no hay ramas, worktrees ni puertas de push (git init).")
    print("Siguiente paso: abrir Claude Code en esa carpeta y escribir /configurar-proyecto.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pone a trabajar el esqueleto.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="comprueba esta máquina y este proyecto")
    adopt_parser = sub.add_parser("adopt", help="copia el esqueleto a un repo existente sin pisar nada")
    adopt_parser.add_argument("dest", type=Path)
    args = parser.parse_args(argv)
    return doctor() if args.command == "doctor" else adopt(args.dest)


if __name__ == "__main__":
    sys.exit(main())
