"""PostToolUse on Write, Edit and MultiEdit: what the edit leaves pending.

- Code that a living document describes (docs/manifest.toml): names the document,
  once per document and session.
- A document: names the writing-style skill set in .claude/project.toml
  ([style] skill), once per file and session, and says so when it is not
  installed instead of keeping quiet about it.

This is a convenience. The guarantee is the merge gate in pre_bash.py, which
refuses to integrate a branch that left a living document behind. Edits made
through the shell (sed, heredocs) do not reach this hook; they do reach the gate.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hooklib as lib  # noqa: E402

DOC_SUFFIXES = (".md", ".mdx", ".html", ".txt")


def _is_document(rel: str) -> bool:
    return rel.endswith(DOC_SUFFIXES) and (rel.startswith("docs/") or "/" not in rel)


def main() -> None:
    payload = lib.read_payload()
    if payload.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        return
    raw = (payload.get("tool_input") or {}).get("file_path") or ""
    if not raw:
        return
    path = Path(raw)
    if not path.is_absolute():
        path = Path(payload.get("cwd") or os.getcwd()) / path
    top = lib.toplevel(path.parent if path.parent.exists() else payload.get("cwd"))
    if top is None:
        return
    try:
        rel = path.resolve().relative_to(top.resolve()).as_posix()
    except ValueError:
        return
    session = payload.get("session_id") or ""
    lines = []

    living = lib.load_toml(top / "docs" / "manifest.toml").get("living", {})
    if rel not in living:
        for doc, entry in sorted(living.items()):
            if any(lib.glob_match(rel, g) for g in entry.get("code", [])) and lib.first_time(
                "doc-impact", session, f"{top}:{doc}"
            ):
                lines.append(
                    f"`{rel}` es código que describe `{doc}`: ese documento se pone al día en esta rama, o se "
                    "toca su línea «Revisado:» si sigue siendo cierto. La puerta del merge lo comprueba."
                )

    style = lib.project_config().get("style", {}).get("skill", "")
    if style and _is_document(rel) and lib.first_time("style", session, f"{top}:{rel}"):
        if lib.skill_installed(style) is False:
            lines.append(
                f"`{rel}` se ha editado. La skill de estilo configurada, `{style}`, no está instalada: se "
                "instala o se quita `[style] skill` de `.claude/project.toml`."
            )
        else:
            lines.append(f"`{rel}` se ha editado; la skill de estilo del proyecto para revisarlo es `{style}`.")

    if lines:
        lib.emit("PostToolUse", context="\n".join(lines))


if __name__ == "__main__":
    lib.run(main, "PostToolUse")
