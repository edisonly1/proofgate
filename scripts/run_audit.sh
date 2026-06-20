#!/usr/bin/env bash
# Run ProofGate against all three provers and produce a single summary table.
# Run after scripts/download_artifacts.sh and scripts/setup_lake_projects.sh.
#
# Estimated wall time: ~3-6h depending on whether mathlib caches are warm.
set -euo pipefail

ART="${ARTIFACTS:-./artifacts}"
LAKE="${LAKE_PROJECTS:-./lake-projects}"
OUT="${OUT_DIR:-./reports}"
mkdir -p "$OUT"

run() {
  local NAME="$1"; shift
  echo "=== $NAME ==="
  python -m proofgate "$@" --out "$OUT/${NAME}.jsonl"
}

run deepseek-test deepseek \
  --root "$ART/deepseek-prover-v2/minif2f-solutions" \
  --split test \
  --lean-cwd "$LAKE/deepseek-v4.9" \
  --vacuity --alignment

run kimina-test kimina \
  --jsonl "$ART/kimina-prover-72b/minif2f_test_solved/minif2f-test-solved.jsonl" \
  --lean-cwd "$LAKE/kimina-v4.15" \
  --vacuity --alignment

run goedel-test goedel \
  --jsonl "$ART/goedel-prover-v2/dataset/minif2f.jsonl" \
  --lean-cwd "$LAKE/goedel-v4.9" \
  --vacuity --alignment

echo
echo "Summary tables:"
for f in "$OUT"/*.summary.json; do
  echo "--- $f ---"
  cat "$f"
done
