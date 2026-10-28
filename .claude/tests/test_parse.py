"""The command-line reader of pre_bash.py: what it sees as separate commands and git calls."""

from __future__ import annotations

import os
import sys
import unittest

from _util import HOOKS

sys.path.insert(0, str(HOOKS))
import pre_bash  # noqa: E402

COMMIT_HEREDOC = """git commit -m "$(cat <<'EOF'
fix: cierra el paréntesis (y otro)

Cuerpo con ) suelto y un apóstrofo: it's fine.
EOF
)" """


class SplitCommands(unittest.TestCase):
    def split(self, line: str, powershell: bool = False) -> list[list[str]]:
        return pre_bash.split_commands(line, powershell)

    def test_separators(self):
        self.assertEqual(
            self.split("git status && git commit -m x || echo no; ls | wc -l & true"),
            [["git", "status"], ["git", "commit", "-m", "x"], ["echo", "no"], ["ls"], ["wc", "-l"], ["true"]],
        )

    def test_newlines_separate_commands(self):
        self.assertEqual(self.split("git add -A\ngit commit -m x"), [["git", "add", "-A"], ["git", "commit", "-m", "x"]])

    def test_separators_inside_quotes_are_text(self):
        self.assertEqual(self.split('git commit -m "a; b && c"'), [["git", "commit", "-m", "a; b && c"]])
        self.assertEqual(self.split("echo 'git commit'"), [["echo", "git commit"]])

    def test_commit_message_from_a_heredoc_is_one_word(self):
        commands = self.split(COMMIT_HEREDOC)
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][:3], ["git", "commit", "-m"])
        self.assertIn("it's fine", commands[0][3])

    def test_heredoc_body_is_not_run(self):
        line = "cat > notas.txt <<EOF\ngit commit -m peligro\nEOF\ngit status"
        self.assertEqual(self.split(line), [["cat"], ["git", "status"]])

    def test_redirections_are_dropped(self):
        self.assertEqual(
            self.split("git push origin main 2>&1 | tail -5"), [["git", "push", "origin", "main"], ["tail", "-5"]]
        )
        self.assertEqual(self.split("git log > out.txt 2> /dev/null"), [["git", "log"]])

    def test_open_quote_is_an_error(self):
        with self.assertRaises(ValueError):
            self.split('git commit -m "sin cerrar')

    def test_powershell_keeps_backslashes(self):
        self.assertEqual(
            self.split('cd C:\\repo\\x; git commit -m "a"', powershell=True),
            [["cd", "C:\\repo\\x"], ["git", "commit", "-m", "a"]],
        )


class GitCalls(unittest.TestCase):
    def calls(self, line: str, cwd: str = "/work/repo"):
        return pre_bash.git_calls(pre_bash.split_commands(line), cwd)

    def test_cd_and_dash_c_move_the_repo(self):
        calls = self.calls("cd ../otro && git commit -m x && git -C /tmp/tercero push")
        self.assertEqual([c.sub for c in calls], ["commit", "push"])
        self.assertEqual(calls[0].cwd, os.path.normpath("/work/otro"))
        self.assertEqual(calls[1].cwd, os.path.normpath("/tmp/tercero"))

    def test_env_assignments_and_global_options(self):
        calls = self.calls("GIT_EDITOR=true git -c core.x=1 --no-pager commit --amend")
        self.assertEqual((calls[0].sub, calls[0].args), ("commit", ["--amend"]))

    def test_unfollowable_paths_are_marked(self):
        self.assertTrue(self.calls('git -C "$REPO" commit')[0].unresolved)
        self.assertTrue(self.calls("cd $X && git commit")[0].unresolved)
        self.assertTrue(self.calls("git --git-dir=/x/.git commit")[0].unresolved)

    def test_git_inside_a_string_is_not_a_call(self):
        self.assertEqual(self.calls('echo "git commit -m x"'), [])


if __name__ == "__main__":
    unittest.main()
