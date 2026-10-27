#!/usr/bin/env bash
# Runs the harness inside the toolchain image, the same Python and LLVM the app
# uses. Paths are relative to the repository root.
#
#   scripts/harness.sh check content/exercises/<id> content/exercises/<id>/solution.py
#   scripts/harness.sh run   content/exercises/<id> content/exercises/<id>/solution.py
set -euo pipefail
cd "$(dirname "$0")/.."
mode="$1"; exercise="$2"; submission="$3"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
cp "$submission" "$scratch/submission.py"
cp "$exercise/tests.py" "$scratch/tests.py"
exec docker run --rm --network none --memory 768m -e PYTHONDONTWRITEBYTECODE=1 --user "$(id -u):$(id -g)" \
  -v "$PWD/backend/app/runner:/runner:ro" -v "$PWD/$exercise:/exercise:ro" -v "$scratch:/work" \
  -w /work cpu-toolchain:local python3 /runner/harness.py "$mode" /exercise /work/submission.py
