#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for review_python in "$project_dir/.venv/bin/python" "$project_dir/venv/bin/python"; do
    if [[ -x "$review_python" ]]; then
        exec "$review_python" "$project_dir/review.py" "$@"
    fi
done

printf 'No project virtual environment found. See %s/README.md for installation.\n' "$project_dir" >&2
exit 1
