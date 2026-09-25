#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -x "$python_path" ]]; then
  echo "Virtual environment not found. Follow the WSL setup in README.md." >&2
  exit 1
fi

cd "$project_dir"
python app.py

