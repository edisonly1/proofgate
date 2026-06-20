#!/usr/bin/env bash
# Download the publicly released proof artifacts for the three provers ProofGate audits.
#
# Usage: bash scripts/download_artifacts.sh [DEST_DIR]
#
# DEST_DIR defaults to ./artifacts/.  No HF token required — every URL is public
# at the time of writing.  All sizes are <1MB except the mathlib caches if you
# choose to build the lake projects locally.
#
# Tested commits (record what we audited against in your `Reproducibility` section):
#   DeepSeek-Prover-V2:  e598a57ea3284997d4a2a168a069fdd5064afbc8
#   Kimina-Prover-72B:   7abd61a5d9861bf5c15b195c216c1bb233ac32e4
#   Goedel-Prover-V2:    2e9036e118464aa96a8bebaf9f5b9d091aa3585c
set -euo pipefail

DEST="${1:-./artifacts}"
mkdir -p "$DEST"

echo "[1/3] DeepSeek-Prover-V2 (miniF2F-test + miniF2F-valid, 440 .lean files)"
DS_DIR="$DEST/deepseek-prover-v2"
mkdir -p "$DS_DIR"
if [[ ! -d "$DS_DIR/.git" ]]; then
  git clone --depth 1 https://github.com/deepseek-ai/DeepSeek-Prover-V2.git "$DS_DIR"
fi
( cd "$DS_DIR" && \
  git checkout e598a57ea3284997d4a2a168a069fdd5064afbc8 -- minif2f-solutions.zip 2>/dev/null || true && \
  unzip -oq minif2f-solutions.zip -d minif2f-solutions/ )
echo "  -> $DS_DIR/minif2f-solutions/{test,valid}/"

echo "[2/3] Kimina-Prover-72B (miniF2F-test, JSONL, 197 entries + filtered 0710)"
KM_DIR="$DEST/kimina-prover-72b"
mkdir -p "$KM_DIR"
if [[ ! -d "$KM_DIR/.git" ]]; then
  git clone --depth 1 https://github.com/MoonshotAI/Kimina-Prover-Preview.git "$KM_DIR"
fi
( cd "$KM_DIR" && \
  for z in minif2f_test_solved.zip minif2f_test_solved_filtered_0710.zip; do
    [[ -f "$z" ]] && unzip -oq "$z" -d "${z%.zip}/" || true
  done )
echo "  -> $KM_DIR/minif2f_test_solved/minif2f-test-solved.jsonl"

echo "[3/3] Goedel-Prover-V2 (miniF2F-test, JSONL, 244 entries)"
GD_DIR="$DEST/goedel-prover-v2"
mkdir -p "$GD_DIR"
if [[ ! -d "$GD_DIR/.git" ]]; then
  git clone --depth 1 https://github.com/Goedel-LM/Goedel-Prover-V2.git "$GD_DIR"
fi
echo "  -> $GD_DIR/dataset/minif2f.jsonl"

echo
echo "Done. To audit:"
echo "  python -m proofgate deepseek --root  $DS_DIR/minif2f-solutions --split test --out reports/deepseek-test.jsonl"
echo "  python -m proofgate kimina   --jsonl $KM_DIR/minif2f_test_solved/minif2f-test-solved.jsonl --out reports/kimina-test.jsonl"
echo "  python -m proofgate goedel   --jsonl $GD_DIR/dataset/minif2f.jsonl --out reports/goedel-test.jsonl"
echo
echo "NOTE: For miniF2F re-verification you must supply a lake project that bundles"
echo "      mathlib at the prover's pinned revision (Kimina v4.15, Goedel v4.9)."
echo "      Pass it via --lean-cwd <project-dir>."
