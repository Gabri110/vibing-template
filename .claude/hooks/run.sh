#!/usr/bin/env bash
# Runs a hook (or any helper script) with the first Python 3 this machine has.
#
#   run.sh <script.py | path/to/script.py> [args...]
#
# A bare name resolves next to this file; anything with a slash runs as given.
# `exec` hands stdin and the exit code straight to the interpreter, so a hook's
# JSON answer and a blocking exit code arrive untouched. The scripts themselves
# check for Python >= 3.11 and fail open when it is older.
set -u

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="${1:-}"
if [ -z "$script" ]; then
  echo "run.sh: missing script name" >&2
  exit 1
fi
shift
case "$script" in
  */*) ;;
  *) script="$here/$script" ;;
esac

# UTF-8 everywhere: on Windows, stdin would otherwise be read as cp1252 and an
# accented word in a prompt or a path would break the hook.
export PYTHONUTF8=1
export PYTHONDONTWRITEBYTECODE=1

case "$(uname -s 2>/dev/null)" in
  MINGW* | MSYS* | CYGWIN*) candidates=("py -3" "python" "python3") ;;
  *) candidates=("python3" "python") ;;
esac
if [ -n "${SKELETON_PYTHON:-}" ]; then
  candidates=("$SKELETON_PYTHON" "${candidates[@]}")
fi

for candidate in "${candidates[@]}"; do
  read -r -a parts <<<"$candidate"
  found="$(command -v "${parts[0]}" 2>/dev/null)" || continue
  # The Microsoft Store alias answers to `python` but runs nothing.
  case "$found" in *WindowsApps*) continue ;; esac
  exec "${parts[@]}" "$script" "$@"
done

# No interpreter: say it where someone will read it. SessionStart stdout reaches
# the model, which tells the person; for the rest a non-zero exit shows an error.
if [ "$(basename "$script")" = "session_start.py" ]; then
  echo "Los hooks del proyecto no encuentran Python 3: instala Python 3.11 o superior, o fija SKELETON_PYTHON."
  exit 0
fi
echo "run.sh: no Python 3 found for $(basename "$script"); set SKELETON_PYTHON" >&2
exit 1
