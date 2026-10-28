"""UserPromptSubmit: names the project skill that fits the prompt, before the model reads it.

Choosing a skill by its description alone is probabilistic, and the documentation
says so; in the project this comes from, four of six skills were never picked on
their own in a week. This hook adds one line of context per match and leaves the
decision to the model. It only names skills that exist, so a missing one shows up
as a missing folder, not as a request nobody can fulfil.

The keyword table is [[skills.trigger]] in .claude/project.toml.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hooklib as lib  # noqa: E402


def main() -> None:
    prompt = lib.read_payload().get("prompt") or ""
    if len(prompt.strip()) < 8:
        return
    triggers = lib.project_config().get("skills", {}).get("trigger", [])
    lines = []
    for trigger in triggers:
        skill, pattern = trigger.get("skill"), trigger.get("pattern")
        if not skill or not pattern or lib.skill_installed(skill) is False:
            continue
        try:
            if not re.search(pattern, prompt, re.IGNORECASE):
                continue
        except re.error:
            continue
        note = trigger.get("note", "")
        lines.append(f"- `{skill}`: {note}" if note else f"- `{skill}`")
    if lines:
        lib.emit(
            "UserPromptSubmit",
            context="Skills del proyecto relacionadas con este mensaje (se invocan con la herramienta Skill "
            "si encajan):\n" + "\n".join(lines),
        )


if __name__ == "__main__":
    lib.run(main, "UserPromptSubmit")
