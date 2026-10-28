"""Living documentation: which documents describe the code a branch touched.

    python3 scripts/docs_impact.py --check                   the manifest holds up (fast step of check.py)
    python3 scripts/docs_impact.py --impact [--base main]    what this branch and the working tree affect
    python3 scripts/docs_impact.py --gate BRANCH --base main refuses (exit 1) while a REVIEW is pending

docs/manifest.toml sorts documents in two classes. `record` documents are dated
(minutes, plans, the backlog) and never go stale. `living` documents must be
true today, and each lists the code it describes in `code` (globs: `**` crosses
folders, `*` does not). When a branch changes that code and not the document,
the document is in REVIEW: the branch updates it, or touches its "Revisado:"
line to say it was read and still holds. Either way the document ends up in the
branch's diff, which is all the gate looks at: no state lives anywhere else.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "manifest.toml"
DOC_SUFFIXES = (".md", ".mdx", ".html")


def git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=off", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def glob_to_regex(pattern: str) -> re.Pattern[str]:
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


def matches(path: str, patterns: list[str]) -> bool:
    return any(glob_to_regex(p).match(path) for p in patterns)


def load_manifest() -> dict:
    import tomllib

    with open(MANIFEST, "rb") as fh:
        return tomllib.load(fh)


def repo_files() -> list[str]:
    out = git("ls-files", "-z", "--cached", "--others", "--exclude-standard") or ""
    return [p for p in out.split("\0") if p]


def changed_between(base: str, head: str) -> set[str] | None:
    out = git("diff", "--name-only", "--no-renames", "-z", f"{base}...{head}")
    return None if out is None else {p for p in out.split("\0") if p}


def changed_in_worktree() -> set[str]:
    out = git("status", "--porcelain", "-z", "--untracked-files=all", "--no-renames") or ""
    return {entry[3:] for entry in out.split("\0") if len(entry) > 3}


def reviews(living: dict, changed: set[str]) -> list[tuple[str, str, list[str]]]:
    """(document, status, code that moved) for every living document the change set reaches."""
    rows = []
    for doc, entry in sorted(living.items()):
        hits = sorted(f for f in changed if f != doc and matches(f, entry.get("code", [])))
        if hits:
            rows.append((doc, "AL DÍA" if doc in changed else "REVISAR", hits))
    return rows


def check() -> int:
    manifest = load_manifest()
    living, record = manifest.get("living", {}), manifest.get("record", [])
    files = repo_files()
    problems = []
    for path in files:
        if path.startswith("docs/") and path.endswith(DOC_SUFFIXES) and path not in living and not matches(path, record):
            problems.append(f"{path}: sin clase. Va a docs/manifest.toml como living (con su code) o en record.")
    for doc, entry in sorted(living.items()):
        if doc not in files:
            problems.append(f"{doc}: está en el manifiesto como living y no existe.")
        if "code" not in entry:
            problems.append(f"{doc}: living sin `code`; un índice sin código lleva `code = []`.")
            continue
        for pattern in entry["code"]:
            if not any(glob_to_regex(pattern).match(f) for f in files):
                problems.append(f"{doc}: `{pattern}` no casa con ningún fichero; el documento describe algo que ya no está.")
    for problem in problems:
        print(problem)
    return 1 if problems else 0


def impact(base: str) -> int:
    changed = changed_between(base, "HEAD")
    if changed is None:
        print(f"No se puede comparar con `{base}`: ¿existe esa rama?")
        return 2
    rows = reviews(load_manifest().get("living", {}), changed | changed_in_worktree())
    if not rows:
        print(f"Ningún documento vivo describe lo que cambia frente a `{base}`.")
    for doc, status, hits in rows:
        print(f"{status:8} {doc}  (por {', '.join(hits[:4])}{', ...' if len(hits) > 4 else ''})")
    return 0


def gate(branch: str, base: str) -> int:
    changed = changed_between(base, branch)
    if changed is None:
        print(f"No se puede comparar `{branch}` con `{base}`.")
        return 2
    pending = [row for row in reviews(load_manifest().get("living", {}), changed) if row[1] == "REVISAR"]
    if not pending:
        return 0
    print(f"La rama `{branch}` cambia código que describen estos documentos y no los toca:")
    for doc, _, hits in pending:
        print(f"  - {doc} (por {', '.join(hits[:3])}{', ...' if len(hits) > 3 else ''})")
    print(
        "\nTres salidas, en la rama: ponerlo al día; pasar la skill sincronizar-docs; o, si sigue siendo "
        "cierto, tocar su línea «Revisado: AAAA-MM-DD, motivo». Después, el merge otra vez."
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Documentación viva: qué documentos describen lo que cambia.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="el manifiesto se sostiene")
    mode.add_argument("--impact", action="store_true", help="lo que afecta esta rama y el árbol de trabajo")
    mode.add_argument("--gate", metavar="RAMA", help="deniega mientras quede un REVISAR")
    parser.add_argument("--base", default="main", help="rama contra la que se compara (por defecto, main)")
    args = parser.parse_args(argv)
    if not MANIFEST.exists():
        print("No hay docs/manifest.toml: el módulo de documentación viva no está activo.")
        return 0
    if args.check:
        return check()
    if args.impact:
        return impact(args.base)
    return gate(args.gate, args.base)


if __name__ == "__main__":
    sys.exit(main())
