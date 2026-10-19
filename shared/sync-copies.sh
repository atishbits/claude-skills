#!/usr/bin/env bash
# Copy the shared scripts into every skill that uses them. A skill opts in to
# drive_sync.py by shipping scripts/drive-sync.json. Each skill gets its own
# copy so it works wherever it is installed, including on its own; the
# pre-commit hook refuses a copy that differs from the master here.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
for cfg in skills/*/scripts/drive-sync.json; do
  [ -e "$cfg" ] || continue
  dst="$(dirname "$cfg")/drive_sync.py"
  if ! cmp -s shared/scripts/drive_sync.py "$dst"; then
    cp shared/scripts/drive_sync.py "$dst"
    echo "updated $dst"
  fi
done
