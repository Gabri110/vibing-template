"""Leak scanner: terms that must never reach the client's code repo.

    python3 scripts/boundary/leak_scan.py --repo PATH                    working tree (tracked and untracked)
    python3 scripts/boundary/leak_scan.py --repo PATH --ref BRANCH [--base dev]   a branch as git has it
    python3 scripts/boundary/leak_scan.py --repo PATH --staged           what the next commit carries
    python3 scripts/boundary/leak_scan.py --text FILE                    one text, e.g. a commit message

With --base, or --staged, only the files that change are read, so an older
finding someone accepted does not stop every merge. The rules live in
leak_rules.toml next to this file, in the internal repo, never in the client's;
findings that are fine on purpose go in its [allow] table, with the reason.
Exit 1 when something is found.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RULES = Path(__file__).resolve().parent / "leak_rules.toml"


@dataclass
class Rule:
    name: str
    why: str
    regexes: list[re.Pattern[str]]
    mask: bool

    def search(self, text: str) -> re.Match[str] | None:
        return next((m for r in self.regexes if (m := r.search(text))), None)


def load_rules(path: Path) -> tuple[list[Rule], dict[str, list[str]]]:
    import tomllib

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    rules = []
    for raw in data.get("rule", []):
        regexes = []
        if terms := [re.escape(t) for t in raw.get("terms", []) if t]:
            regexes.append(re.compile("|".join(terms), re.IGNORECASE))
        if words := [re.escape(w) for w in raw.get("words", []) if w]:
            regexes.append(re.compile(r"\b(?:" + "|".join(words) + r")\b"))
        if raw.get("pattern"):
            regexes.append(re.compile(raw["pattern"]))
        if regexes:
            rules.append(Rule(raw["name"], raw.get("why", ""), regexes, bool(raw.get("mask"))))
    return rules, data.get("allow", {})


def git(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    result = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=repo, input=data, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout


def _blobs(repo: Path, entries: list[tuple[str, str]]) -> list[tuple[str, bytes]]:
    """(path, sha) pairs to (path, content), in one `git cat-file --batch`."""
    if not entries:
        return []
    out = git(repo, "cat-file", "--batch", data="".join(f"{sha}\n" for _, sha in entries).encode())
    files, pos = [], 0
    for path, _ in entries:
        header_end = out.index(b"\n", pos)
        size = int(out[pos:header_end].split()[2])
        files.append((path, out[header_end + 1 : header_end + 1 + size]))
        pos = header_end + 1 + size + 1
    return files


def from_ref(repo: Path, ref: str, base: str | None) -> list[tuple[str, bytes]]:
    listing = git(repo, "ls-tree", "-r", "-z", ref).decode("utf-8", "replace")
    entries = []
    for item in filter(None, listing.split("\0")):
        meta, path = item.split("\t", 1)
        _, kind, sha = meta.split()
        if kind == "blob":
            entries.append((path, sha))
    if base:
        changed = set(filter(None, git(repo, "diff", "--name-only", "-z", f"{base}...{ref}").decode().split("\0")))
        entries = [e for e in entries if e[0] in changed]
    return _blobs(repo, entries)


def staged(repo: Path) -> list[tuple[str, bytes]]:
    changed = set(filter(None, git(repo, "diff", "--cached", "--name-only", "-z").decode().split("\0")))
    listing = git(repo, "ls-files", "-s", "-z").decode("utf-8", "replace")
    entries = []
    for item in filter(None, listing.split("\0")):
        meta, path = item.split("\t", 1)
        _, sha, _ = meta.split()
        if path in changed:
            entries.append((path, sha))
    return _blobs(repo, entries)


def working_tree(repo: Path) -> list[tuple[str, bytes]]:
    names = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard").decode("utf-8", "replace")
    files = []
    for path in filter(None, names.split("\0")):
        try:
            files.append((path, (repo / path).read_bytes()))
        except OSError:
            continue
    return files


def allowed(path: str, rule: str, allow: dict[str, list[str]]) -> bool:
    return any(fnmatch.fnmatchcase(path, glob) and (rule in rules or "*" in rules) for glob, rules in allow.items())


def scan(files: list[tuple[str, bytes]], rules: list[Rule], allow: dict[str, list[str]]) -> list[str]:
    findings = []
    for path, content in files:
        if b"\0" in content[:8000]:
            continue  # binary
        text = content.decode("utf-8", "replace")
        for rule in rules:
            if rule.search(path) and not allowed(path, rule.name, allow):
                findings.append(f"{path}: [{rule.name}] el nombre del fichero ({rule.why})")
        for number, line in enumerate(text.splitlines(), 1):
            hits = [rule for rule in rules if rule.search(line) and not allowed(path, rule.name, allow)]
            if not hits:
                continue
            excerpt = line.strip()
            for rule in rules:  # a secret stays masked whichever rule reports the line
                if rule.mask:
                    for regex in rule.regexes:
                        excerpt = regex.sub(lambda m: m.group(0)[:4] + "…", excerpt)
            findings.extend(f"{path}:{number}: [{rule.name}] {excerpt[:120]}" for rule in hits)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Busca material interno que no puede llegar al repo del cliente.")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repo que se revisa (por defecto, el actual)")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--ref", help="rama o commit, tal como lo tiene git")
    source.add_argument("--staged", action="store_true", help="lo preparado para el siguiente commit")
    source.add_argument("--text", type=Path, help="un texto suelto, como un mensaje de commit")
    parser.add_argument("--base", help="con --ref, solo los ficheros que cambian frente a esta rama")
    parser.add_argument("--rules", type=Path, default=RULES)
    parser.add_argument("--skip", action="append", default=[], metavar="REGLA", help="regla que no se aplica esta vez")
    args = parser.parse_args(argv)
    try:
        rules, allow = load_rules(args.rules)
        rules = [r for r in rules if r.name not in args.skip]
        if args.text:
            files = [(args.text.name, args.text.read_bytes())]
        elif args.ref:
            files = from_ref(args.repo, args.ref, args.base)
        elif args.staged:
            files = staged(args.repo)
        else:
            files = working_tree(args.repo)
    except (OSError, RuntimeError, ValueError, re.error) as exc:
        print(f"No se pudo revisar: {exc}")
        return 2
    findings = scan(files, rules, allow)
    if findings:
        print("Material interno que no puede llegar al repo del cliente:")
        print("\n".join(f"  {f}" for f in findings))
        print("\nSe quita del cambio o, si es correcto a propósito, va a [allow] de leak_rules.toml con su motivo.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
