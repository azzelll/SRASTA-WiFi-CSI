#!/usr/bin/env bash
# Compatibility entry point: selected model and isolated simulator database.
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
exec bash "$repo_dir/scripts/run_local.sh" simulator "$@"
