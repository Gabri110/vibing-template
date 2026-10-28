"""SessionStart: says where the session stands. It reports and never touches anything.

A short line for the person (systemMessage) and the detail for the model
(additionalContext). No `git fetch` and no `git pull`: a pull at start-up either
fails or merges something nobody chose, and a fetch can hang on a proxy, so the
report uses local refs and says how old they are.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hooklib as lib  # noqa: E402


def _age(path: Path) -> str:
    try:
        seconds = time.time() - path.stat().st_mtime
    except OSError:
        return "sin fetch previo"
    if seconds < 3600:
        return f"de hace {int(seconds // 60)} min"
    if seconds < 86400:
        return f"de hace {int(seconds // 3600)} h"
    return f"de hace {int(seconds // 86400)} días"


def _stale_copies(top: Path) -> list[str]:
    """Files that setup_code_repo.py copied into a client repo and whose source changed since."""
    manifest = top / ".claude" / ".skeleton-copies.json"
    try:
        copies = json.loads(manifest.read_text(encoding="utf-8")).get("copies", {})
    except (OSError, ValueError, AttributeError):
        return []
    stale = []
    for target, info in copies.items():
        digest = hashlib.sha256()
        try:
            for source in info["sources"]:
                digest.update(Path(source).read_bytes())
        except (OSError, KeyError, TypeError):
            stale.append(target)
            continue
        if digest.hexdigest() != info.get("sha256"):
            stale.append(target)
    return stale


def main() -> None:
    payload = lib.read_payload()
    cwd = payload.get("cwd") or os.getcwd()
    lib.prune_markers()
    facts: list[str] = []  # for the model
    notes: list[str] = []  # for the person

    cfg = lib.project_config()
    if cfg.get("skeleton", {}).get("configured") is False:
        facts.append(
            "El proyecto está sin configurar (`configured = false` en `.claude/project.toml`): la skill "
            "`configurar-proyecto` guía esa primera conversación (objetivos, idiomas, stack, ramas, "
            "coautoría, verificación y módulos)."
        )
        notes.append("Proyecto sin configurar: /configurar-proyecto")

    top = lib.toplevel(cwd)
    if top is None:
        facts.append("La carpeta no es un repo git: sin git no hay ramas, worktrees ni puertas de push.")
        notes.append("sin repo git")
        lib.emit("SessionStart", context="\n".join(facts), system=" · ".join(notes))
        return

    branch = lib.current_branch(cwd)
    has_commits = lib.git("rev-parse", "--verify", "--quiet", "HEAD", cwd=cwd) is not None
    status = lib.git("status", "--porcelain", cwd=cwd, timeout=3)
    dirty = "estado sin comprobar" if status is None else f"{len(status.splitlines())} cambios sin commitear"
    where = branch or "HEAD separado"
    facts.append(f"Repo `{top.name}`, rama `{where}`{'' if has_commits else ' (sin commits todavía)'}, {dirty}.")
    notes.append(f"{where} · {dirty}")

    in_worktree = (top / ".git").is_file()
    rules = lib.policy(cwd) or {}
    if not in_worktree:
        facts.append(
            "La sesión está en el checkout principal, no en un worktree. Para una tarea que cambie "
            "ficheros: `EnterWorktree` (o `claude -w <nombre>` desde fuera) y, ya dentro, "
            "`git branch -m <prefijo>/<nombre>`. Una tarea de una frase puede quedarse aquí."
        )
        notes.append("checkout principal")
    if branch and branch.startswith("worktree-"):
        facts.append(f"La rama `{branch}` conserva el nombre por defecto: `git branch -m fix/<nombre>` (o feature/, docs/).")

    upstream = lib.git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", cwd=cwd)
    if upstream:
        counts = lib.git("rev-list", "--left-right", "--count", f"HEAD...{upstream}", cwd=cwd)
        common = lib.common_dir(cwd)
        age = _age(common / "FETCH_HEAD") if common else "sin fetch previo"
        if counts:
            ahead, behind = counts.split()
            facts.append(f"Frente a `{upstream}`: {ahead} por delante y {behind} por detrás (referencias {age}).")
            if behind != "0":
                notes.append(f"{behind} por detrás de {upstream}")

    worktrees = lib.git("worktree", "list", "--porcelain", cwd=cwd) or ""
    extra = sum(1 for line in worktrees.splitlines() if line.startswith("worktree ")) - 1
    if extra >= 1:
        hint = ": conviene borrar los que ya estén integrados" if extra >= 3 else ""
        facts.append(f"Hay {extra} worktrees abiertos además del principal{hint}.")

    integration, release = rules.get("integration"), rules.get("release")
    if integration and release and has_commits:
        behind = lib.git("rev-list", "--count", f"{integration}..{release}", cwd=cwd)
        if behind and behind != "0":
            facts.append(
                f"`{release}` lleva {behind} commits que `{integration}` no tiene: se traen hoy a "
                f"`{integration}`, o la siguiente entrega los pisa."
            )
            notes.append(f"{release} adelanta a {integration}")

    if rules.get("client"):
        stale = _stale_copies(top)
        if stale:
            facts.append(
                "Las copias del contrato y las reglas en este repo del cliente están desfasadas "
                f"({', '.join(stale)}): `scripts/boundary/setup_code_repo.py` del repo interno las rehace."
            )
            notes.append("copias del contrato desfasadas")

    lib.emit("SessionStart", context="\n".join(facts), system=" · ".join(notes))


if __name__ == "__main__":
    if not lib.python_ok():
        print(
            f"Los hooks del proyecto necesitan Python 3.11 o superior y han encontrado "
            f"{sys.version.split()[0]}: las puertas de commit y push no actúan hasta que se instale."
        )
    else:
        lib.run(main, "SessionStart")
