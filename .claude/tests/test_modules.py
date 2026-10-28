"""The optional modules: living documentation, releases and the client boundary."""

from __future__ import annotations

import json
import shutil
import sys
import unittest

from _util import HAS_BOUNDARY, HAS_DOCS, HAS_RELEASE, Sandbox, context_of

MANIFEST = """record = ["docs/meeting-log.md"]

[living."docs/guia.md"]
code = ["src/**"]
"""

RELEASE_TOML = 'integration = "main"\nbranch = ""\nversion_file = "VERSION"\nchangelog = "CHANGELOG.md"\n'


@unittest.skipUnless(HAS_DOCS, "módulo de documentación viva retirado")
class LivingDocs(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox(commit=False)
        shutil.rmtree(self.box.root / "docs", ignore_errors=True)  # only this test's documents
        self.box.write("docs/manifest.toml", MANIFEST)
        self.box.write("docs/guia.md", "# Guía\n\nRevisado: 2026-10-27, versión inicial.\n")
        self.box.write("docs/meeting-log.md", "# Actas\n")
        self.box.write("src/motor.py", "x = 1\n")
        self.box.git("add", "-A")
        self.box.git("commit", "-q", "-m", "init")

    def tearDown(self):
        self.box.close()

    def docs(self, *args: str):
        return self.box.python("scripts/docs_impact.py", *args)

    def test_check_wants_every_document_classified(self):
        self.assertEqual(self.docs("--check").returncode, 0)
        self.box.write("docs/nuevo.md", "# Nuevo\n")
        result = self.docs("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/nuevo.md: sin clase", result.stdout)

    def test_check_catches_a_document_that_describes_nothing(self):
        self.box.write("docs/manifest.toml", MANIFEST.replace("src/**", "lib/**"))
        self.assertIn("no casa con ningún fichero", self.docs("--check").stdout)

    def test_gate_and_merge(self):
        self.box.git("switch", "-q", "-c", "fix/a")
        self.box.commit_file("src/motor.py", "x = 2\n", "fix: x")
        self.box.git("switch", "-q", "main")
        gate = self.docs("--gate", "fix/a", "--base", "main")
        self.assertEqual(gate.returncode, 1)
        self.assertIn("docs/guia.md", gate.stdout)
        self.assertIn("docs/guia.md", self.box.bash("git merge --squash fix/a") or "")

        self.box.git("switch", "-q", "fix/a")
        self.box.commit_file("docs/guia.md", "# Guía\n\nRevisado: 2026-10-28, x cambia y el texto sigue.\n", "docs: x")
        self.box.git("switch", "-q", "main")
        self.assertEqual(self.docs("--gate", "fix/a", "--base", "main").returncode, 0)
        self.assertIsNone(self.box.bash("git merge --squash fix/a"))

    def test_impact_lists_review_and_up_to_date(self):
        self.box.git("switch", "-q", "-c", "fix/b")
        self.box.write("src/motor.py", "x = 3\n")
        self.assertIn("REVISAR", self.docs("--impact", "--base", "main").stdout)
        self.box.write("docs/guia.md", "# Guía\n\nRevisado: hoy.\n")
        self.assertIn("AL DÍA", self.docs("--impact", "--base", "main").stdout)


@unittest.skipUnless(HAS_RELEASE, "módulo de releases retirado")
class Releases(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.box.write("scripts/release.toml", RELEASE_TOML)
        for name in ("VERSION", "CHANGELOG.md"):
            (self.box.root / name).unlink(missing_ok=True)
        self.assertEqual(self.box.python("scripts/release.py", "--init").returncode, 0)
        self.box.git("add", "-A")
        self.box.git("commit", "-q", "-m", "chore: release files")
        self.box.commit_file("a.txt", "a\n", "feat: primera función")

    def tearDown(self):
        self.box.close()

    def release(self, *args: str):
        return self.box.python("scripts/release.py", *args)

    def test_dry_run_touches_nothing(self):
        before = self.box.git("status", "--porcelain")
        result = self.release("--dry-run")
        self.assertIn("0.1.0 -> 0.1.0", result.stdout)
        self.assertIn("### Añadido", result.stdout)
        self.assertEqual(self.box.git("status", "--porcelain"), before)
        self.assertEqual(self.box.git("tag"), "")

    def test_release_then_bumps(self):
        self.assertEqual(self.release().returncode, 0)
        self.assertEqual(self.box.git("describe", "--tags"), "v0.1.0")
        self.assertIn("## v0.1.0", (self.box.root / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.box.commit_file("b.txt", "b\n", "fix: arreglo")
        self.assertIn("0.1.0 -> 0.1.1", self.release("--dry-run").stdout)
        self.box.commit_file("c.txt", "c\n", "feat(api)!: cambia la API")
        self.assertIn("0.1.0 -> 0.2.0", self.release("--dry-run").stdout)

    def test_refuses_a_dirty_tree_and_another_branch(self):
        self.box.write("sucio.txt", "x\n")
        self.assertIn("sin commitear", self.release().stdout)
        (self.box.root / "sucio.txt").unlink()
        self.box.git("switch", "-q", "-c", "fix/a")
        self.assertIn("sale de `main`", self.release().stdout)

    def test_delivery_branch_and_push(self):
        self.box.write("scripts/release.toml", 'integration = "main"\nbranch = "entrega"\n')
        self.box.git("add", "-A")
        self.box.git("commit", "-q", "-m", "chore: delivery branch")
        self.box.remote()
        self.assertEqual(self.release().returncode, 0)
        self.assertEqual(self.box.git("rev-parse", "entrega"), self.box.git("rev-parse", "main"))
        self.assertIsNone(self.box.bash("git push origin main entrega v0.1.0"))

    def test_manifest(self):
        out = self.box.tmp / "dist"
        self.assertEqual(self.release("manifest", str(out)).returncode, 0)
        data = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(data["version"], "0.1.0")
        self.assertTrue(data["commit"])


@unittest.skipUnless(HAS_BOUNDARY, "módulo de frontera con el cliente retirado")
class Boundary(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox(commit=False)
        self.box.write(".claude/skills/demo/SKILL.md", "---\nname: demo\ndescription: prueba\n---\n")
        self.box.write(".claude/rules/zona.md", '---\npaths:\n  - "src/**"\n---\n# Zona\n')
        self.box.write("AGENTS.md", "# Contrato\n\nRegla de prueba.\n")
        self.box.write("CLAUDE.md", "@AGENTS.md\n\n## Claude Code\n")
        self.box.git("add", "-A")
        self.box.git("commit", "-q", "-m", "init")
        self.code = self.box.tmp / "codigo-cliente"
        self.code.mkdir()
        self.box.git("init", "-q", "-b", "dev", cwd=self.code)
        self.box.commit_file("app.py", "print('hola')\n", "feat: app", cwd=self.code)

    def tearDown(self):
        self.box.close()

    def setup(self, *args: str):
        return self.box.python("scripts/boundary/setup_code_repo.py", str(self.code), *args)

    def test_wires_and_checks_and_repeats(self):
        self.assertEqual(self.setup().returncode, 0, self.setup().stdout)
        self.assertEqual(self.setup().returncode, 0)
        self.assertEqual(self.setup("--check").returncode, 0)
        self.assertEqual(self.box.git("config", "--get", "skeleton.role", cwd=self.code), "client")
        self.assertEqual(self.box.git("status", "--porcelain", cwd=self.code), "")
        settings = json.loads((self.code / ".claude/settings.local.json").read_text(encoding="utf-8"))
        command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertIn((self.box.root / ".claude/hooks/run.sh").as_posix(), command)
        self.assertEqual(settings["attribution"], {"commit": "", "pr": ""})
        allow = settings["permissions"]["allow"]
        self.assertEqual(len(allow), len(set(allow)))
        self.assertTrue((self.code / ".claude/skills/demo").is_symlink())
        self.assertIn("Regla de prueba", (self.code / "CLAUDE.local.md").read_text(encoding="utf-8"))
        self.assertNotIn("@AGENTS.md", (self.code / "CLAUDE.local.md").read_text(encoding="utf-8"))
        rule = (self.code / ".claude/rules/zona.md").read_text(encoding="utf-8")
        self.assertTrue(rule.startswith("---\npaths:"))

    def test_stale_copies_are_reported(self):
        self.setup()
        self.box.write("AGENTS.md", "# Contrato\n\nOtra regla.\n")
        result = self.setup("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("desfasada", result.stdout)
        answer = self.box.hook("session_start.py", {"cwd": str(self.code)})
        self.assertIn("desfasadas", context_of(answer))

    def test_git_hooks_are_the_guarantee(self):
        self.setup()
        (self.code / "leak.py").write_text("autor = 'Zeta'\n", encoding="utf-8")
        self.box.git("add", "leak.py", cwd=self.code)
        refused = self.box.run("git", "commit", "-m", "feat: x", cwd=self.code, check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("leak.py", refused.stdout + refused.stderr)

        self.box.git("reset", "-q", cwd=self.code)
        (self.code / "leak.py").unlink()
        self.box.git("switch", "-q", "-c", "feature/x", cwd=self.code)
        (self.code / "ok.py").write_text("x = 1\n", encoding="utf-8")
        self.box.git("add", "ok.py", cwd=self.code)
        message = "feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
        refused = self.box.run("git", "commit", "-m", message, cwd=self.code, check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(self.box.run("git", "commit", "-q", "-m", "feat: x", cwd=self.code, check=False).returncode, 0)

        hook = str(self.box.root / "scripts/boundary/githook.py")
        url = "https://example.com/cliente.git"
        out = self.box.run(sys.executable, hook, "pre-push", "origin", url, cwd=self.code, check=False,
                           stdin="refs/heads/otra abc refs/heads/otra def\n")
        self.assertEqual(out.returncode, 1)
        out = self.box.run(sys.executable, hook, "pre-push", "origin", url, cwd=self.code, check=False,
                           stdin="refs/heads/dev abc refs/heads/dev def\n")
        self.assertEqual(out.returncode, 0)

    def test_merge_gate_scans_the_branch(self):
        self.setup()
        self.box.git("switch", "-q", "-c", "feature/y", cwd=self.code)
        (self.code / "nota.md").write_text("Lo revisó Zeta.\n", encoding="utf-8")
        self.box.git("add", "nota.md", cwd=self.code)
        self.box.git("commit", "-q", "-m", "docs: nota", cwd=self.code)
        self.box.git("switch", "-q", "dev", cwd=self.code)
        self.assertIn("nota.md", self.box.bash("git merge --squash feature/y", cwd=self.code) or "")

    def test_foreign_hook_is_left_alone_and_remove_cleans_up(self):
        foreign = self.code / ".git/hooks/pre-commit"
        foreign.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        result = self.setup()
        self.assertEqual(result.returncode, 1)
        self.assertIn("ajeno", result.stdout)
        self.assertEqual(foreign.read_text(encoding="utf-8"), "#!/bin/sh\nexit 0\n")
        self.assertEqual(self.setup("--remove").returncode, 0)
        self.assertEqual(self.box.git("config", "--get", "skeleton.role", cwd=self.code, check=False), "")
        self.assertFalse((self.code / ".claude").exists())
        self.assertFalse((self.code / "CLAUDE.local.md").exists())
        self.assertFalse((self.code / ".git/hooks/commit-msg").exists())
        self.assertTrue(foreign.exists())
        self.assertNotIn("skeleton", (self.code / ".git/info/exclude").read_text(encoding="utf-8"))


@unittest.skipUnless(HAS_BOUNDARY, "módulo de frontera con el cliente retirado")
class Leaks(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()
        self.repo = self.box.tmp / "codigo"
        self.repo.mkdir()
        self.box.git("init", "-q", "-b", "dev", cwd=self.repo)

    def tearDown(self):
        self.box.close()

    def scan(self, *args: str):
        return self.box.python("scripts/boundary/leak_scan.py", "--repo", str(self.repo), *args)

    def test_finds_allows_and_masks(self):
        (self.repo / "notas.txt").write_text(
            "lo dijo Zeta\nclave de Zeta: api_key = 'abcdefghijklmnopqrstuvwx'\n", encoding="utf-8"
        )
        result = self.scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("notas.txt:1: [interno]", result.stdout)
        self.assertIn("notas.txt:2: [secreto]", result.stdout)
        self.assertNotIn("abcdefghijklmnop", result.stdout)
        rules = self.box.root / "scripts/boundary/leak_rules.toml"
        rules.write_text(rules.read_text(encoding="utf-8") + '"notas.txt" = ["*"]\n', encoding="utf-8")
        self.assertEqual(self.scan().returncode, 0)

    def test_text_mode(self):
        message = self.box.write("msg.txt", "feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
        self.assertEqual(self.box.python("scripts/boundary/leak_scan.py", "--text", str(message)).returncode, 1)
        self.assertEqual(
            self.box.python("scripts/boundary/leak_scan.py", "--text", str(message), "--skip", "herramienta").returncode, 0
        )


class Bootstrap(unittest.TestCase):
    def setUp(self):
        self.box = Sandbox()

    def tearDown(self):
        self.box.close()

    def test_adopt_copies_without_overwriting(self):
        dest = self.box.tmp / "existente"
        dest.mkdir()
        self.box.git("init", "-q", "-b", "main", cwd=dest)
        (dest / "CLAUDE.md").write_text("# Mío\n", encoding="utf-8")
        (dest / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        result = self.box.python("scripts/bootstrap.py", "adopt", str(dest))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((dest / "CLAUDE.md").read_text(encoding="utf-8"), "# Mío\n")
        self.assertIn("- CLAUDE.md", result.stdout)
        self.assertTrue((dest / ".claude/hooks/pre_bash.py").exists())
        self.assertTrue((dest / "docs/esqueleto.md").exists())
        ignore = (dest / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("node_modules/", ignore)
        self.assertIn(".claude/worktrees/", ignore)
        again = self.box.python("scripts/bootstrap.py", "adopt", str(dest))
        self.assertNotIn("líneas añadidas", again.stdout)
        self.assertEqual(ignore, (dest / ".gitignore").read_text(encoding="utf-8"))

    def test_doctor_runs_clean(self):
        result = self.box.python("scripts/bootstrap.py", "doctor")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("✔ pre_bash.py responde", result.stdout)
        self.assertIn("⚠ proyecto configurado", result.stdout)


if __name__ == "__main__":
    unittest.main()
