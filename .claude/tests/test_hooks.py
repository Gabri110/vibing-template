"""The hooks end to end: payload in through run.sh, decision out, in throwaway repos."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from _util import Sandbox, context_of


class Guard(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()

    def tearDown(self):
        self.box.close()

    def test_commit_on_the_integration_branch_is_refused(self):
        self.assertIn("rama de integración", self.box.bash("git commit -m x") or "")

    def test_commit_on_a_work_branch_passes_silently(self):
        self.box.git("switch", "-q", "-c", "fix/a")
        answer = self.box.hook(
            "pre_bash.py",
            {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}, "cwd": str(self.box.root)},
        )
        self.assertIsNone(answer)  # silent, never "allow": the ask rules of settings.json still apply

    def test_switching_first_in_the_same_command_counts(self):
        self.assertIsNone(self.box.bash("git switch -c fix/a && git commit -m x"))
        self.assertIsNotNone(self.box.bash("git switch -c fix/a && git switch main && git commit -m x"))

    def test_squash_flow(self):
        self.box.git("switch", "-q", "-c", "fix/a")
        self.box.commit_file("a.txt", "a\n")
        self.box.git("switch", "-q", "main")
        self.assertIsNone(self.box.bash("git merge --squash fix/a"))
        self.assertIsNotNone(self.box.bash("git merge fix/a"))
        self.assertIsNone(self.box.bash("git merge --no-ff fix/a"))
        self.box.git("merge", "--squash", "fix/a")
        self.assertIsNone(self.box.bash("git commit -m 'fix: a'"))

    def test_human_commit_policy(self):
        self.box.set_toml(".claude/project.toml", "human_commit = false", "human_commit = true")
        self.box.git("switch", "-q", "-c", "fix/a")
        self.box.commit_file("a.txt", "a\n")
        self.box.git("switch", "-q", "main")
        self.assertIsNone(self.box.bash("git merge --squash fix/a"))
        self.assertIsNotNone(self.box.bash("git merge --no-ff fix/a"))
        self.box.git("merge", "--squash", "fix/a")
        self.assertIn("lo hace una persona", self.box.bash("git commit -m x") or "")

    def test_moving_a_protected_branch_from_elsewhere(self):
        self.box.git("switch", "-q", "-c", "fix/a")
        for command in (
            "git branch -f main HEAD",
            "git branch -D main",
            "git update-ref refs/heads/main HEAD",
            "git fetch . fix/a:main",
            "git push . fix/a:main",
            "git checkout -B main",
        ):
            with self.subTest(command=command):
                self.assertIn("rama protegida", self.box.bash(command) or "")

    def test_history_commands_on_the_integration_branch(self):
        self.box.commit_file("b.txt", "b\n")
        self.assertIsNotNone(self.box.bash("git pull"))
        self.assertIsNone(self.box.bash("git pull --ff-only"))
        self.assertIsNotNone(self.box.bash("git rebase fix/x"))
        self.assertIsNotNone(self.box.bash("git reset --hard HEAD~1"))
        self.assertIsNone(self.box.bash("git reset --hard"))
        self.assertIsNone(self.box.bash("git merge --abort"))

    def test_powershell_and_accents(self):
        self.assertIsNotNone(self.box.bash('git commit -m "añade el índice"', tool="PowerShell"))
        self.assertIsNotNone(self.box.bash('git commit -m "añade el índice"'))

    def test_garbage_fails_open(self):
        result = self.box.run("bash", str(self.box.root / ".claude/hooks/run.sh"), "pre_bash.py", stdin="{no es json")
        self.assertEqual((result.returncode, result.stdout.strip()), (0, ""))
        self.assertIsNone(self.box.bash('git commit -m "sin cerrar'))

    def test_repos_outside_the_project_are_left_alone(self):
        other = self.box.tmp / "otro"
        other.mkdir()
        self.box.git("init", "-q", "-b", "main", cwd=other)
        self.assertIsNone(self.box.bash("git commit -m x", cwd=other))


class Release(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.box.write("scripts/release.toml", 'integration = "main"\nbranch = "entrega"\n')
        self.box.git("add", "scripts/release.toml")
        self.box.commit_file("VERSION", "0.1.0\n", "chore: version")
        self.box.git("branch", "entrega")
        self.box.remote()

    def tearDown(self):
        self.box.close()

    def test_delivery_branch_needs_seal_and_tag(self):
        self.box.git("switch", "-q", "entrega")
        self.assertIn("rama de entrega", self.box.bash("git commit -m x") or "")
        self.assertIn("verificación completa", self.box.bash("git push origin entrega") or "")
        self.assertEqual(self.box.python("scripts/check.py").returncode, 0)
        self.assertIn("v0.1.0", self.box.bash("git push origin entrega") or "")
        self.box.git("tag", "-a", "v0.1.0", "-m", "v0.1.0")
        self.assertIsNone(self.box.bash("git push origin entrega"))


class Push(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.box.remote()

    def tearDown(self):
        self.box.close()

    def test_work_branch_runs_the_fast_check(self):
        self.box.git("switch", "-q", "-c", "fix/a")
        self.assertIsNone(self.box.bash("git push -u origin fix/a"))
        self.box.write(
            "scripts/check.toml",
            '[[step]]\nname = "rompe"\ncmd = ["{python}", "-c", "import sys; sys.exit(3)"]\nfast = true\n',
        )
        self.assertIn("verificación rápida falla", self.box.bash("git push origin fix/a") or "")

    def test_protected_branch_needs_a_seal_of_that_exact_tree(self):
        self.assertIn("verificación completa", self.box.bash("git push origin main") or "")
        self.assertEqual(self.box.python("scripts/check.py").returncode, 0)
        self.assertIsNone(self.box.bash("git push origin main"))
        self.box.git("switch", "-q", "-c", "fix/a")
        self.box.commit_file("c.txt", "c\n")
        self.box.git("switch", "-q", "main")
        self.box.git("merge", "--squash", "fix/a")
        self.box.git("commit", "-q", "-m", "fix: c")
        self.assertIn("otro árbol", self.box.bash("git push origin main") or "")

    def test_force_and_allow_list(self):
        self.box.python("scripts/check.py")
        self.assertIn("No se fuerza", self.box.bash("git push --force origin main") or "")
        self.box.set_toml(".claude/project.toml", "push_allow = []", 'push_allow = ["main", "feature/*"]')
        self.box.git("switch", "-q", "-c", "fix/a")
        self.assertIn("solo se empujan", self.box.bash("git push origin fix/a") or "")


class Client(unittest.TestCase):
    """A code repo marked as the client's: strict policy, fails closed."""

    def setUp(self):
        self.box = Sandbox()
        self.code = self.box.tmp / "codigo-cliente"
        self.code.mkdir()
        self.box.git("init", "-q", "-b", "dev", cwd=self.code)
        self.box.commit_file("app.py", "print('hola')\n", "feat: app", cwd=self.code)
        self.box.git("config", "skeleton.role", "client", cwd=self.code)

    def tearDown(self):
        self.box.close()

    def test_commit_on_dev_is_for_a_person(self):
        self.assertIn("lo hace una persona", self.box.bash("git commit -m x", cwd=self.code) or "")

    def test_unknown_branch_refuses_only_here(self):
        self.box.git("checkout", "-q", "--detach", cwd=self.code)
        self.assertIn("No se sabe en qué rama", self.box.bash("git commit -m x", cwd=self.code) or "")
        self.box.git("checkout", "-q", "--detach")
        self.assertIsNone(self.box.bash("git commit -m x"))

    def test_policy_reaches_its_worktrees(self):
        tree = self.box.tmp / "wt"
        self.box.git("worktree", "add", "-q", "-b", "feature/x", str(tree), cwd=self.code)
        self.assertIsNone(self.box.bash("git commit -m x", cwd=tree))
        self.assertIn("solo se empujan", self.box.bash("git push origin otra-rama", cwd=tree) or "")

    def test_release_by_hand_and_unparseable(self):
        self.assertIn("una persona", self.box.bash("python3 scripts/release.py", cwd=self.code) or "")
        self.assertIsNone(self.box.bash("python3 scripts/release.py --dry-run", cwd=self.code))
        self.assertIsNotNone(self.box.bash('git commit -m "sin cerrar', cwd=self.code))
        self.assertIsNotNone(self.box.bash('git -C "$X" commit -m x', cwd=self.code))


class SessionStart(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()

    def tearDown(self):
        self.box.close()

    def start(self, cwd: Path | None = None) -> dict:
        return self.box.hook("session_start.py", {"cwd": str(cwd or self.box.root), "source": "startup"}) or {}

    def test_unconfigured_project_and_main_checkout(self):
        answer = self.start()
        self.assertIn("/configurar-proyecto", answer.get("systemMessage", ""))
        self.assertIn("checkout principal", context_of(answer))

    def test_worktree_with_default_branch_name(self):
        tree = self.box.root / ".claude" / "worktrees" / "tarea"
        self.box.git("worktree", "add", "-q", "-b", "worktree-tarea", str(tree))
        context = context_of(self.start(tree))
        self.assertIn("git branch -m", context)
        self.assertNotIn("checkout principal", context)


class Prompt(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()

    def tearDown(self):
        self.box.close()

    def ask(self, prompt: str) -> str:
        return context_of(self.box.hook("prompt.py", {"prompt": prompt, "session_id": "p"}))

    def test_names_only_skills_that_exist(self):
        self.box.write(".claude/skills/configurar-proyecto/SKILL.md", "---\nname: configurar-proyecto\n---\n")
        self.assertIn("`configurar-proyecto`", self.ask("Quiero configurar el proyecto desde cero"))
        self.box.run("rm", "-rf", str(self.box.root / ".claude/skills/configurar-proyecto"))
        self.assertEqual(self.ask("Quiero configurar el proyecto desde cero"), "")

    def test_short_prompts_are_ignored(self):
        self.assertEqual(self.ask("sí"), "")


class PostEdit(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.box.write("docs/manifest.toml", '[living."docs/guia.md"]\ncode = ["src/**"]\n')
        self.box.write("docs/guia.md", "# Guía\n")
        self.box.write("src/core/motor.py", "x = 1\n")

    def tearDown(self):
        self.box.close()

    def edit(self, rel: str, session: str = "e1") -> str:
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(self.box.root / rel)},
            "cwd": str(self.box.root),
            "session_id": session,
        }
        return context_of(self.box.hook("post_edit.py", payload))

    def test_code_names_its_document_once_per_session(self):
        self.assertIn("docs/guia.md", self.edit("src/core/motor.py"))
        self.assertEqual(self.edit("src/core/motor.py"), "")
        self.assertIn("docs/guia.md", self.edit("src/core/motor.py", session="otra"))

    def test_style_skill_reminder_says_when_it_is_missing(self):
        self.box.set_toml(".claude/project.toml", 'skill = ""', 'skill = "estilo-inexistente"')
        self.assertIn("no está instalada", self.edit("docs/guia.md"))
        self.box.set_toml(".claude/project.toml", 'skill = "estilo-inexistente"', 'skill = "humanizer:humanizer"')
        self.assertIn("humanizer:humanizer", self.edit("docs/guia.md", session="otra"))


if __name__ == "__main__":
    unittest.main()
