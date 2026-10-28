"""PreToolUse on Bash and PowerShell: branch guard, push gate and merge gate.

Checks run cheapest first and stop at the first refusal:

1. Guard. On the integration branch only a prepared squash (or, if allowed, a
   --no-ff merge) gets committed; on the delivery branch nothing does, by hand.
   Commands that move or delete a protected branch from elsewhere are refused.
2. Push. Allowed refs; a push to a protected branch needs the seal of a full
   green check of that exact tree; a push to the delivery branch needs its
   release tag; any other push runs `scripts/check.py --fast` first.
3. Merge. Integrating a branch runs the living-docs gate and, in the client's
   code repo, the leak scanner.

It fails open (a crash lets the command through), except in a code repo marked
`skeleton.role = client`, where an unchecked command could leave something in
the client's history that cannot be taken back: there it fails closed.

Rules live in .claude/project.toml ([branches], and [boundary] for the client
repo) and scripts/release.toml (the delivery branch).
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hooklib as lib  # noqa: E402

HISTORY = {"commit", "merge", "pull", "rebase", "cherry-pick", "revert", "am"}
WRAPPERS = {"command", "exec", "time", "nohup", "env"}
CD_NAMES = {"cd", "chdir", "pushd", "set-location", "sl"}
FAST_TIMEOUT = 150


# --- reading a command line ---------------------------------------------------


def _read_word(line: str, i: int) -> tuple[int, str]:
    """Skip blanks, then read one word (quotes removed). Returns (index after, word)."""
    n = len(line)
    while i < n and line[i] in " \t":
        i += 1
    out = []
    while i < n and line[i] not in " \t\n;&|<>()":
        c = line[i]
        if c in "'\"":
            j = line.find(c, i + 1)
            if j < 0:
                raise ValueError("unterminated quote")
            out.append(line[i + 1 : j])
            i = j + 1
        else:
            out.append(c)
            i += 1
    return i, "".join(out)


def _skip_heredoc(line: str, i: int, delim: str, strip_tabs: bool) -> int:
    """From the start of a line, skip a here-document body up to its delimiter line."""
    n = len(line)
    while i < n:
        end = line.find("\n", i)
        end = n if end < 0 else end
        text = line[i:end]
        if (text.lstrip("\t") if strip_tabs else text) == delim:
            return end + 1
        i = end + 1
    return n


def _read_double(line: str, i: int, powershell: bool) -> tuple[int, str]:
    """From an opening double quote to its closing one, `$( )` included."""
    escape = "`" if powershell else "\\"
    out, j, n = [], i + 1, len(line)
    while j < n:
        c = line[j]
        if c == escape and j + 1 < n:
            out.append(line[j + 1])
            j += 2
        elif c == "$" and line.startswith("$(", j):
            j, text = _read_balanced(line, j, powershell)
            out.append(text)
        elif c == '"':
            return j + 1, "".join(out)
        else:
            out.append(c)
            j += 1
    raise ValueError("unterminated double quote")


def _read_balanced(line: str, i: int, powershell: bool) -> tuple[int, str]:
    """From `$(` to its matching `)`, skipping quotes and here-documents inside."""
    depth, j, n = 0, i + 1, len(line)
    pending: list[tuple[str, bool]] = []
    while j < n:
        c = line[j]
        if c == "\\" and not powershell:
            j += 2
            continue
        if c == "'":
            k = line.find("'", j + 1)
            if k < 0:
                raise ValueError("unterminated quote")
            j = k + 1
            continue
        if c == '"':
            j, _ = _read_double(line, j, powershell)
            continue
        if line.startswith("<<", j) and not line.startswith("<<<", j):
            strip = line.startswith("<<-", j)
            j, delim = _read_word(line, j + (3 if strip else 2))
            pending.append((delim, strip))
            continue
        if c == "\n" and pending:
            j += 1
            while pending:
                delim, strip = pending.pop(0)
                j = _skip_heredoc(line, j, delim, strip)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j + 1, line[i : j + 1]
        j += 1
    raise ValueError("unterminated $(")


def split_commands(line: str, powershell: bool = False) -> list[list[str]]:
    """Split a command line into simple commands, each a list of words.

    Understands quotes, escapes, the separators && || | |& ; & and newlines,
    `$( )` and backticks kept inside one word, redirections (dropped with their
    target) and here-documents (skipped). Raises ValueError on an open quote.
    """
    commands: list[list[str]] = []
    words: list[str] = []
    word: list[str] = []
    in_word = False
    heredocs: list[tuple[str, bool]] = []
    i, n = 0, len(line)

    def end_word() -> None:
        nonlocal in_word
        if in_word:
            words.append("".join(word))
            word.clear()
            in_word = False

    def end_command() -> None:
        end_word()
        if words:
            commands.append(words.copy())
            words.clear()

    while i < n:
        c = line[i]
        if c == "\\" and not powershell:
            if line.startswith("\\\n", i):
                i += 2
            elif i + 1 < n:
                word.append(line[i + 1])
                in_word = True
                i += 2
            else:
                i += 1
        elif c == "'":
            j = line.find("'", i + 1)
            if j < 0:
                raise ValueError("unterminated single quote")
            word.append(line[i + 1 : j])
            in_word = True
            i = j + 1
        elif c == '"':
            i, text = _read_double(line, i, powershell)
            word.append(text)
            in_word = True
        elif line.startswith("$(", i):
            i, text = _read_balanced(line, i, powershell)
            word.append(text)
            in_word = True
        elif c == "`" and not powershell:
            j = line.find("`", i + 1)
            if j < 0:
                raise ValueError("unterminated backtick")
            word.append(line[i : j + 1])
            in_word = True
            i = j + 1
        elif c == "\n":
            end_command()
            i += 1
            while heredocs:
                delim, strip = heredocs.pop(0)
                i = _skip_heredoc(line, i, delim, strip)
        elif c in " \t\r":
            end_word()
            i += 1
        elif line.startswith("&>", i):
            end_word()
            i, _ = _read_word(line, i + 2 + (line[i + 2 : i + 3] == ">"))
        elif c in "&|;":
            op = line[i : i + 2] if line[i : i + 2] in ("&&", "||", "|&", ";;") else c
            end_command()
            i += len(op)
        elif c in "<>":
            if in_word and "".join(word).isdigit():  # the 2 of 2>&1
                word.clear()
                in_word = False
            else:
                end_word()
            if line.startswith("<<<", i):
                i, _ = _read_word(line, i + 3)
            elif line.startswith("<<", i):
                strip = line.startswith("<<-", i)
                i, delim = _read_word(line, i + (3 if strip else 2))
                heredocs.append((delim, strip))
            else:
                j = i + 1
                while j < n and line[j] in "<>|&":
                    j += 1
                i, _ = _read_word(line, j)
        else:
            word.append(c)
            in_word = True
            i += 1
    end_command()
    return commands


# --- the git calls in a command -------------------------------------------------


@dataclass
class GitCall:
    cwd: str  # where git runs, after any cd and -C
    sub: str  # subcommand: commit, push...
    args: list[str]
    unresolved: bool = False  # a cd, -C or --git-dir that can't be followed


def _parse_git(rest: list[str], here: str, lost: bool) -> GitCall:
    path, unresolved, i = here, lost, 0
    while i < len(rest):
        w = rest[i]
        if w == "-C" and i + 1 < len(rest):
            target = rest[i + 1]
            unresolved = unresolved or "$" in target or "%" in target
            path = os.path.normpath(os.path.join(path, os.path.expanduser(target)))
            i += 2
        elif w in ("-c", "--exec-path", "--namespace", "--config-env") and i + 1 < len(rest):
            i += 2
        elif w in ("--git-dir", "--work-tree"):
            unresolved = True
            i += 2
        elif w.startswith(("--git-dir=", "--work-tree=")):
            unresolved = True
            i += 1
        elif w.startswith("-"):
            i += 1
        else:
            break
    sub = rest[i] if i < len(rest) else ""
    return GitCall(path, sub, rest[i + 1 :], unresolved)


def git_calls(commands: list[list[str]], cwd: str) -> list[GitCall]:
    """Every git invocation, with the directory it runs in (following cd and -C)."""
    calls: list[GitCall] = []
    here, lost = cwd, False
    for words in commands:
        k = 0
        while k < len(words) and (
            words[k] in WRAPPERS or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[k])
        ):
            k += 1
        if k >= len(words):
            continue
        name = os.path.basename(words[k]).lower()
        rest = words[k + 1 :]
        if name in CD_NAMES:
            target = next((w for w in rest if not w.startswith("-")), None)
            if target is None:
                here = str(Path.home())
            elif target == "-" or "$" in target or "%" in target:
                lost = True
            else:
                here = os.path.normpath(os.path.join(here, os.path.expanduser(target)))
        elif name in ("git", "git.exe"):
            calls.append(_parse_git(rest, here, lost))
    return calls


# --- repo state ------------------------------------------------------------------


@dataclass
class Repo:
    top: Path | None
    gitdir: Path | None
    branch: str | None
    rules: dict | None


_repos: dict[str, Repo] = {}


def repo_at(path: str) -> Repo:
    if path not in _repos:
        _repos[path] = Repo(lib.toplevel(path), lib.git_dir(path), lib.current_branch(path), lib.policy(path))
    return _repos[path]


def _positional(args: list[str], with_value: set[str] = frozenset()) -> list[str]:
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a == "--":
            break
        elif a in with_value:
            skip = True
        elif not a.startswith("-"):
            out.append(a)
    return out


def _local_branch(name: str, cwd: str) -> bool:
    return lib.git("rev-parse", "--verify", "--quiet", f"refs/heads/{name}", cwd=cwd) is not None


def switched_to(call: GitCall) -> str | None:
    """The branch a checkout or switch leaves checked out, if it changes it."""
    args = call.args
    for flag in ("-b", "-B", "-c", "-C", "--create", "--force-create"):
        if flag in args and args.index(flag) + 1 < len(args):
            return args[args.index(flag) + 1]
    if "--detach" in args:
        return None
    for name in _positional(args):
        if _local_branch(name, call.cwd):
            return name
        break
    return None


# --- 1. guard --------------------------------------------------------------------


def _aborting(args: list[str]) -> bool:
    return "--abort" in args or "--quit" in args


def _resets_elsewhere(args: list[str], cwd: str) -> bool:
    target = next(iter(_positional(args)), None)
    if target is None:
        return False
    commit = lib.git("rev-parse", "--verify", "--quiet", f"{target}^{{commit}}", cwd=cwd)
    if commit is None:  # a path, not a commit
        return False
    return commit != lib.git("rev-parse", "--verify", "--quiet", "HEAD", cwd=cwd)


def _moves_protected(call: GitCall, protected: set[str]) -> str | None:
    sub, args = call.sub, call.args

    def hit(ref: str) -> str | None:
        name = ref.lstrip("+").removeprefix("refs/heads/")
        return name if name in protected else None

    found = None
    if sub == "branch":
        flags = {a for a in args if a.startswith("-")}
        pos = _positional(args)
        if flags & {"-f", "--force", "-m", "-M", "--move", "-d", "-D", "--delete"}:
            found = next((h for p in pos if (h := hit(p))), None)
        elif flags & {"-c", "-C", "--copy"} and pos:
            found = hit(pos[-1])
    elif sub in ("checkout", "switch"):
        for flag in ("-B", "-C", "--force-create"):
            if flag in args and args.index(flag) + 1 < len(args):
                found = found or hit(args[args.index(flag) + 1])
    elif sub == "update-ref":
        found = next((h for p in _positional(args) if (h := hit(p))), None)
    elif sub in ("fetch", "push"):
        pos = _positional(args)
        if pos and pos[0] == ".":
            found = next((h for s in pos[1:] if ":" in s and (h := hit(s.split(":", 1)[1]))), None)
    if found:
        return (
            f"Ese comando mueve o borra `{found}`, que es una rama protegida, sin pasar por ella. "
            "Las ramas protegidas solo avanzan integrando una rama de trabajo, o con scripts/release.py "
            "si es la de entrega."
        )
    return None


def guard(call: GitCall, repo: Repo, branch: str | None) -> str | None:
    rules = repo.rules or {}
    integration, release = rules.get("integration", ""), rules.get("release", "")
    protected = {b for b in (integration, release) if b}
    if moved := _moves_protected(call, protected):
        return moved
    sub, args = call.sub, call.args
    if branch is None:
        if rules.get("client") and (sub in HISTORY or sub == "reset"):
            return (
                "No se sabe en qué rama corre este comando, y en el repo del cliente eso deniega. "
                "Se repite con la ruta escrita entera, sin cd ni variables."
            )
        return None
    if _aborting(args):
        return None
    if release and branch == release:
        if sub in HISTORY or (sub == "reset" and _resets_elsewhere(args, call.cwd)):
            return (
                f"`{release}` es la rama de entrega: solo avanza con scripts/release.py, por avance "
                "rápido desde la de integración. Nada se commitea, fusiona ni reescribe en ella a mano."
            )
        return None
    if branch != integration:
        return None
    if sub == "commit":
        if rules.get("human_commit"):
            return (
                f"En `{integration}` el commit lo hace una persona. Lo que toca es dejarlo preparado con "
                "`git merge --squash <rama>`, enseñar el resumen del diff, pedir la revisión de forma "
                "explícita y proponer un mensaje de una línea."
            )
        if not _finishing_merge(repo):
            return (
                f"`git commit` directo en `{integration}`, la rama de integración. Aquí solo entra lo que "
                "viene de una rama de trabajo: la tarea va en su rama (`git switch -c fix/<nombre>`) o en "
                f"un worktree, y se integra desde aquí con `git merge --squash <rama>` y su commit."
            )
    elif sub == "merge":
        if "--squash" in args:
            return None
        if "--no-ff" in args and rules.get("allow_no_ff") and not rules.get("human_commit"):
            return None
        extra = "" if rules.get("human_commit") else (
            ", o `git merge --no-ff <rama>` si es una rama de varios días cuyos commits valen por sí solos"
        )
        return f"En `{integration}` una rama entra con `git merge --squash <rama>`{extra}."
    elif sub == "pull":
        if "--ff-only" not in args:
            return f"En `{integration}`, `git pull --ff-only`: un pull que fusiona crea un commit que nadie pidió."
    elif sub in ("rebase", "cherry-pick", "revert", "am"):
        return f"`git {sub}` cambia la historia de `{integration}`, que es una rama protegida: va en una rama de trabajo."
    elif sub == "reset" and _resets_elsewhere(args, call.cwd):
        return f"Ese `git reset` mueve `{integration}` a otra referencia, y es una rama protegida."
    return None


def _finishing_merge(repo: Repo) -> bool:
    gd = repo.gitdir
    return bool(gd and ((gd / "SQUASH_MSG").exists() or (gd / "MERGE_HEAD").exists()))


# --- 2. push ---------------------------------------------------------------------

PUSH_WITH_VALUE = {"--repo", "-o", "--push-option", "--receive-pack", "--exec"}


def _fast_check(top: Path, client: bool) -> str | None:
    script = top / "scripts" / "check.py"
    if not script.is_file():
        return None
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--fast"],
            cwd=top,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=FAST_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        if client:
            return f"La verificación rápida no pudo correr ({exc!r}), y en el repo del cliente eso deniega."
        print(f"pre_bash: fast check could not run: {exc!r}", file=sys.stderr)
        return None
    if result.returncode == 0:
        return None
    tail = (result.stdout + result.stderr)[-3000:]
    return f"La verificación rápida falla, así que no se empuja:\n\n{tail}"


def _release_tag_gate(repo: Repo, commit: str, cwd: str) -> str | None:
    rel = lib.release_config(repo.top)
    version_file = rel.get("version_file", "VERSION")
    version = lib.git("show", f"{commit}:{version_file}", cwd=cwd)
    if not version:
        return f"El commit no trae `{version_file}`: la rama de entrega solo recibe lo que sale de scripts/release.py."
    tag = rel.get("tag_prefix", "v") + version.strip()
    if tag not in (lib.git("tag", "--points-at", commit, cwd=cwd) or "").split():
        return (
            f"El commit no lleva el tag `{tag}`: a la rama de entrega solo llega lo que etiqueta "
            "scripts/release.py (con `--dry-run` enseña la versión sin tocar nada)."
        )
    return None


def push_gate(call: GitCall, repo: Repo, branch: str | None) -> str | None:
    rules = repo.rules or {}
    client = bool(rules.get("client"))
    flags = [a for a in call.args if a.startswith("-")]
    pos = _positional(call.args, PUSH_WITH_VALUE)
    if any(f in ("--all", "--mirror", "--branches") for f in flags):
        return "Un push con --all o --mirror no se puede verificar: cada rama se empuja por su nombre."
    if pos and pos[0] == ".":
        return None  # local ref moves: the guard already looked at them
    force = any(f in ("-f", "--force") or f.startswith(("--force-with-lease", "--force-if-includes")) for f in flags)
    targets: list[tuple[str | None, str, bool]] = []
    for spec in pos[1:]:
        plus, spec = spec.startswith("+"), spec.lstrip("+")
        if spec.startswith(":"):
            targets.append((None, spec[1:], plus))
        elif ":" in spec:
            src, dst = spec.split(":", 1)
            targets.append((src, dst, plus))
        else:
            targets.append((spec, spec, plus))
    if not pos[1:] and "--tags" not in flags:
        if branch is None:
            return "No se sabe qué rama se empuja: se escribe el destino, `git push origin <rama>`." if client else None
        targets.append((branch, branch, False))

    protected = {b for b in (rules.get("integration"), rules.get("release")) if b}
    allow = rules.get("push_allow") or []
    needs_fast = False
    for src, dst, plus in targets:
        is_tag = dst.startswith("refs/tags/") or (
            lib.git("rev-parse", "--verify", "--quiet", f"refs/tags/{dst}", cwd=call.cwd) is not None
            and not _local_branch(dst, call.cwd)
        )
        name = dst.removeprefix("refs/heads/").removeprefix("refs/tags/")
        if allow and not any(fnmatch.fnmatchcase(name, p) for p in allow):
            return f"Desde este repo solo se empujan {', '.join(f'`{p}`' for p in allow)}; `{name}` no está en la lista."
        if name in protected and not is_tag:
            if force or plus:
                return f"No se fuerza un push a `{name}`: la historia compartida no se reescribe, se arregla hacia delante."
            if src is None:
                return f"`{name}` es una rama protegida y no se borra en el remoto."
            commit = lib.git("rev-parse", "--verify", "--quiet", f"{src}^{{commit}}", cwd=call.cwd)
            if not commit:
                return f"No se resuelve `{src}`, así que no se puede comprobar el push a `{name}`."
            ok, why = lib.seal_covers(call.cwd, commit)
            if not ok:
                return (
                    f"Empujar a `{name}` exige una verificación completa en verde de ese mismo árbol: {why}. "
                    "Se corre `python3 scripts/check.py` (la completa) y se vuelve a empujar."
                )
            if name == rules.get("release") and (reason := _release_tag_gate(repo, commit, call.cwd)):
                return reason
        elif not is_tag:
            needs_fast = True
    if needs_fast and repo.top:
        return _fast_check(repo.top, client)
    return None


# --- 3. merge ----------------------------------------------------------------------

MERGE_WITH_VALUE = {"-m", "-s", "-X", "-F", "--file", "--strategy", "--strategy-option", "--into-name"}


def _run_tool(cmd: list[str], top: Path, what: str) -> str | None:
    """Run a gate tool. Exit 1 is a refusal with its output; anything else is "could not check"."""
    try:
        result = subprocess.run(
            cmd, cwd=top, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"No se pudo comprobar {what} ({exc!r}); el merge espera a que se pueda."
    if result.returncode == 0:
        return None
    output = (result.stdout + result.stderr).strip()[-3000:]
    if result.returncode == 1:
        return output
    return f"No se pudo comprobar {what} (código {result.returncode}):\n{output}"


def merge_gate(call: GitCall, repo: Repo, branch: str | None) -> str | None:
    rules = repo.rules or {}
    if _aborting(call.args) or "--continue" in call.args or branch != rules.get("integration") or not repo.top:
        return None
    target = next(iter(_positional(call.args, MERGE_WITH_VALUE)), None)
    if not target or not _local_branch(target, call.cwd):
        return None
    # From here the command closes a branch: a check that can't run refuses (fails closed).
    reasons = []
    docs_tool = repo.top / "scripts" / "docs_impact.py"
    if docs_tool.is_file() and (repo.top / "docs" / "manifest.toml").is_file():
        cmd = [sys.executable, str(docs_tool), "--gate", target, "--base", branch]
        if out := _run_tool(cmd, repo.top, "la documentación viva"):
            reasons.append(out)
    if rules.get("client"):
        leak_tool = lib.PROJECT_DIR / "scripts" / "boundary" / "leak_scan.py"
        cmd = [sys.executable, str(leak_tool), "--repo", str(repo.top), "--ref", target, "--base", branch]
        if out := _run_tool(cmd, repo.top, "las fugas al repo del cliente"):
            reasons.append(out)
    return "\n\n".join(reasons) or None


# --- the whole command ---------------------------------------------------------------


def _release_by_hand(commands: list[list[str]]) -> bool:
    for words in commands:
        if any(w.endswith(("release.py", "release.sh", "release.bat")) for w in words) and "--dry-run" not in words:
            return True
    return False


def evaluate(command: str, cwd: str, powershell: bool) -> str | None:
    client_here = lib.role(cwd) == "client"
    try:
        commands = split_commands(command, powershell)
    except ValueError:
        if client_here and "git" in command:
            return "No se puede analizar el comando, y en el repo del cliente eso deniega. Se repite sin comillas abiertas."
        return None
    if client_here and _release_by_hand(commands):
        return (
            "En el repo del cliente la release la lanza una persona desde su terminal; "
            "`--dry-run` enseña la versión y el changelog sin tocar nada."
        )
    tracked: dict[str, str | None] = {}
    for call in git_calls(commands, cwd):
        if call.unresolved:
            if client_here or lib.role(call.cwd) == "client":
                return "El comando lleva un cd, -C o --git-dir que no se puede seguir, y en el repo del cliente eso deniega."
            continue
        repo = repo_at(call.cwd)
        if repo.rules is None:
            continue
        key = str(repo.top)
        branch = tracked.get(key, repo.branch)
        if reason := guard(call, repo, branch):
            return reason
        if call.sub in ("checkout", "switch"):
            tracked[key] = switched_to(call) or branch
        elif call.sub == "push" and (reason := push_gate(call, repo, branch)):
            return reason
        elif call.sub == "merge" and (reason := merge_gate(call, repo, branch)):
            return reason
    return None


def main() -> None:
    payload = lib.read_payload()
    tool = payload.get("tool_name")
    if tool not in ("Bash", "PowerShell"):
        return
    command = (payload.get("tool_input") or {}).get("command") or ""
    if "git" not in command and "release" not in command:
        return
    cwd = payload.get("cwd") or os.getcwd()
    try:
        reason = evaluate(command, cwd, tool == "PowerShell")
    except Exception as exc:  # noqa: BLE001
        if lib.role(cwd) != "client":
            raise
        reason = f"No se pudo comprobar el comando ({exc!r}), y en el repo del cliente eso deniega."
    if reason:
        lib.emit("PreToolUse", deny=reason)


if __name__ == "__main__":
    lib.run(main, "PreToolUse")
