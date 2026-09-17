#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
if [ ! -x .venv/bin/python ]; then
  echo 'Eseguire prima bash installa.sh.' >&2
  exit 1
fi
exec .venv/bin/python -m dslm3 --workspace "$PWD/workspace" serve "$@"
