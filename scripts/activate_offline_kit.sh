#!/usr/bin/env bash
# Source this helper from a DSLM3 repository unpacked as:
#   <offline-root>/repo/dsl_manager-v3-main
# Override auto-detection with DSLM3_OFFLINE_ROOT=/path/to/offline-root.

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DSLM3_REPO_ROOT="$(cd "$_SCRIPT_DIR/.." && pwd)"
_DEFAULT_OFFLINE_ROOT="$(cd "$DSLM3_REPO_ROOT/../.." && pwd)"
export DSLM3_OFFLINE_ROOT="${DSLM3_OFFLINE_ROOT:-$_DEFAULT_OFFLINE_ROOT}"

if [[ ! -x "$DSLM3_OFFLINE_ROOT/venv/bin/python" ]]; then
  echo "DSLM3 offline venv not found: $DSLM3_OFFLINE_ROOT/venv" >&2
  if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then return 1; else exit 1; fi
fi

export VIRTUAL_ENV="$DSLM3_OFFLINE_ROOT/venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"
export PLAYWRIGHT_BROWSERS_PATH="$DSLM3_OFFLINE_ROOT/browsers/ms-playwright"

unset _SCRIPT_DIR _DEFAULT_OFFLINE_ROOT
