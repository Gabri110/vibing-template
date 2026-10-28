"""One version per delivery: version, changelog, tag and, if there is one, the delivery branch.

    python3 scripts/release.py --init          creates VERSION and CHANGELOG.md when they are missing
    python3 scripts/release.py --dry-run       the next version and its changelog, touching nothing
    python3 scripts/release.py                 the release; it prints the push and never runs it
    python3 scripts/release.py manifest OUT    writes OUT/manifest.json (version, commit, date)

The next version comes from the conventional commits since the last tag: `feat`
raises the minor, `fix` and `perf` the patch, a `!` or BREAKING CHANGE the major
(the minor while the version is 0.x). The release runs from the integration
branch with a clean tree: verification (the seal if it covers HEAD, the full
check otherwise), VERSION and the `also_update` files, a CHANGELOG.md section,
commit `chore(release): vX.Y.Z`, annotated tag, and a fast-forward of the
delivery branch. Since only version files changed after a green run, it seals
the new tree too, so the push it prints passes the gate.

manifest.json goes inside the package: with it the app can show "v1.4.0 · 2026-10-27"
and anyone can tell, months later, which code a delivery came from.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "scripts" / "release.toml"
SEAL_NAME = "check-seal.json"
SUBJECT = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?: (?P<desc>.+)$")
SECTIONS = (("feat", "Añadido"), ("fix", "Corregido"), ("perf", "Rendimiento"))


class ReleaseError(Exception):
    pass


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip() if result.returncode == 0 else ""


def config() -> dict:
    import tomllib

    defaults = {"integration": "main", "branch": "", "version_file": "VERSION", "changelog": "CHANGELOG.md",
                "tag_prefix": "v", "also_update": []}
    if CONFIG.exists():
        defaults.update(tomllib.loads(CONFIG.read_text(encoding="utf-8")))
    return defaults


# --- versions and commits ---------------------------------------------------------


def parse_version(text: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"\s*(\d+)\.(\d+)\.(\d+)\s*", text)
    if not match:
        raise ReleaseError(f"La versión «{text.strip()}» no es X.Y.Z.")
    return int(match[1]), int(match[2]), int(match[3])


def last_tag(prefix: str) -> str | None:
    return git("describe", "--tags", "--abbrev=0", "--match", f"{prefix}[0-9]*", check=False) or None


def commits_since(tag: str | None) -> list[dict]:
    span = f"{tag}..HEAD" if tag else "HEAD"
    raw = git("log", "--format=%s%x1f%b%x1e", span, check=False)
    commits = []
    for record in filter(None, (r.strip() for r in raw.split("\x1e"))):
        subject, _, body = record.partition("\x1f")
        match = SUBJECT.match(subject)
        kind = match["type"].lower() if match else "other"
        if kind == "chore" and match and match["scope"] == "release":
            continue
        commits.append({
            "type": kind,
            "scope": match["scope"] if match else None,
            "desc": match["desc"] if match else subject,
            "breaking": bool(match and match["bang"]) or "BREAKING CHANGE" in body,
        })
    return commits


def next_version(current: tuple[int, int, int], commits: list[dict]) -> tuple[int, int, int]:
    major, minor, patch = current
    if any(c["breaking"] for c in commits):
        return (major, minor + 1, 0) if major == 0 else (major + 1, 0, 0)
    if any(c["type"] == "feat" for c in commits):
        return major, minor + 1, 0
    return major, minor, patch + 1


def changelog_section(tag: str, commits: list[dict]) -> str:
    lines = [f"## {tag} ({date.today().isoformat()})", ""]
    groups = {title: [] for _, title in SECTIONS}
    others = []
    for c in commits:
        entry = f"- {c['desc']}" + (f" ({c['scope']})" if c["scope"] else "")
        title = dict(SECTIONS).get(c["type"])
        (groups[title] if title else others).append(entry)
    for title, entries in [*groups.items(), ("Otros", others)]:
        if entries:
            lines += [f"### {title}", "", *entries, ""]
    return "\n".join(lines)


# --- the seal -----------------------------------------------------------------------


def seal_path() -> Path:
    where = git("rev-parse", "--git-path", SEAL_NAME)
    return Path(where) if Path(where).is_absolute() else ROOT / where


def seal_covers_head() -> bool:
    try:
        seal = json.loads(seal_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    fresh = time.time() - float(seal.get("written_epoch", 0)) < 24 * 3600
    return fresh and seal.get("tree") == git("rev-parse", "HEAD^{tree}")


def write_seal() -> None:
    now = datetime.now(timezone.utc)
    seal = {
        "tree": git("rev-parse", "HEAD^{tree}"),
        "head": git("rev-parse", "HEAD"),
        "written": now.isoformat(timespec="seconds"),
        "written_epoch": now.timestamp(),
        "derived": "release: only version files changed after a green check",
    }
    seal_path().write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")


# --- commands ---------------------------------------------------------------------------


def init(cfg: dict) -> int:
    for name, text in ((cfg["version_file"], "0.1.0\n"), (cfg["changelog"], "# Changelog\n")):
        path = ROOT / name
        if path.exists():
            print(f"{name} ya existe.")
        else:
            path.write_text(text, encoding="utf-8")
            print(f"{name} creado.")
    return 0


def plan(cfg: dict) -> tuple[str, str, str, list[dict]]:
    version_path = ROOT / cfg["version_file"]
    if not version_path.exists():
        raise ReleaseError(f"No hay {cfg['version_file']}: `release.py --init` lo crea.")
    current = version_path.read_text(encoding="utf-8").strip()
    tag = last_tag(cfg["tag_prefix"])
    commits = commits_since(tag)
    if not commits:
        raise ReleaseError(f"No hay commits desde {tag or 'el principio'}: nada que entregar.")
    parse_version(current)
    # The first release ships the version VERSION already says; later ones bump it.
    new = current if tag is None else ".".join(map(str, next_version(parse_version(current), commits)))
    return current, new, cfg["tag_prefix"] + new, commits


def preflight(cfg: dict) -> None:
    branch = git("symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if branch != cfg["integration"]:
        raise ReleaseError(f"La release sale de `{cfg['integration']}` y estás en `{branch or 'HEAD separado'}`.")
    if git("status", "--porcelain"):
        raise ReleaseError("El árbol tiene cambios sin commitear: la release sale de un árbol limpio.")
    if (Path(git("rev-parse", "--absolute-git-dir")) / "index.lock").exists():
        raise ReleaseError("Hay un .git/index.lock: otro proceso de git está en marcha.")
    delivery = cfg["branch"]
    if delivery and git("rev-parse", "--verify", "--quiet", f"refs/heads/{delivery}", check=False):
        behind = git("rev-list", "--count", f"{cfg['integration']}..{delivery}")
        if behind != "0":
            raise ReleaseError(
                f"`{delivery}` lleva {behind} commits que `{cfg['integration']}` no tiene: se traen antes."
            )


def bump_files(cfg: dict, old: str, new: str) -> list[str]:
    touched = [cfg["version_file"]]
    (ROOT / cfg["version_file"]).write_text(new + "\n", encoding="utf-8")
    for name in cfg["also_update"]:
        path = ROOT / name
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        for i, line in enumerate(lines):
            if "version" in line.lower() and old in line:
                lines[i] = line.replace(old, new, 1)
                break
        else:
            raise ReleaseError(f"{name}: no se encuentra una línea de versión con {old}.")
        path.write_text("".join(lines), encoding="utf-8")
        touched.append(name)
    return touched


def release(cfg: dict) -> int:
    preflight(cfg)
    old, new, tag, commits = plan(cfg)
    if not seal_covers_head():
        print("El sello no cubre HEAD: corre la verificación completa.", flush=True)
        if subprocess.run([sys.executable, str(ROOT / "scripts" / "check.py")], cwd=ROOT).returncode != 0:
            raise ReleaseError("La verificación falla: no hay release.")
    touched = bump_files(cfg, old, new)
    changelog = ROOT / cfg["changelog"]
    text = changelog.read_text(encoding="utf-8") if changelog.exists() else "# Changelog\n"
    head, _, rest = text.partition("\n")
    changelog.write_text(f"{head}\n\n{changelog_section(tag, commits)}\n{rest.lstrip()}", encoding="utf-8")
    git("add", *touched, cfg["changelog"])
    git("commit", "-q", "-m", f"chore(release): {tag}")
    git("tag", "-a", tag, "-m", tag)
    write_seal()
    refs = [cfg["integration"]]
    delivery = cfg["branch"]
    if delivery:
        if git("rev-parse", "--verify", "--quiet", f"refs/heads/{delivery}", check=False):
            git("fetch", "-q", ".", f"{cfg['integration']}:{delivery}")  # refuses anything but a fast-forward
        else:
            git("branch", delivery)
        refs.append(delivery)
    print(f"Release {tag} hecha: commit, tag{' y ' + delivery + ' adelantada' if delivery else ''}.")
    print("Falta el push, que lo lanza una persona después de mirarlo:")
    print(f"  git push origin {' '.join(refs)} {tag}")
    return 0


def dry_run(cfg: dict) -> int:
    old, new, tag, commits = plan(cfg)
    print(f"{old} -> {new} ({len(commits)} commits desde {last_tag(cfg['tag_prefix']) or 'el principio'})\n")
    print(changelog_section(tag, commits))
    return 0


def manifest(cfg: dict, out: Path) -> int:
    version_path = ROOT / cfg["version_file"]
    data = {
        "version": version_path.read_text(encoding="utf-8").strip() if version_path.exists() else None,
        "commit": git("rev-parse", "--short", "HEAD", check=False) or None,
        "dirty": bool(git("status", "--porcelain", check=False)),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"{out / 'manifest.json'}: {data}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Una versión por entrega.")
    parser.add_argument("--init", action="store_true", help="crea VERSION y CHANGELOG.md si faltan")
    parser.add_argument("--dry-run", action="store_true", help="enseña la versión y el changelog sin tocar nada")
    parser.add_argument("command", nargs="?", choices=["manifest"], help="manifest OUT: escribe OUT/manifest.json")
    parser.add_argument("out", nargs="?", type=Path)
    args = parser.parse_args(argv)
    cfg = config()
    try:
        if args.init:
            return init(cfg)
        if args.command == "manifest":
            return manifest(cfg, args.out or ROOT / "dist")
        return dry_run(cfg) if args.dry_run else release(cfg)
    except ReleaseError as exc:
        print(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
