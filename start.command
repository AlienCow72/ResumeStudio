#!/bin/zsh
cd "$(dirname "$0")" || exit 1
python_bin=python3
bundled_python="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
if [[ -x "$bundled_python" ]]; then python_bin="$bundled_python"; fi
exec "$python_bin" src/launch.py
