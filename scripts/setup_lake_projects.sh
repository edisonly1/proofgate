#!/usr/bin/env bash
# Build the per-prover lake projects ProofGate needs for re-verification.
#
# Each prover pinned a different mathlib; you cannot audit them all against
# one toolchain. This script provisions a fresh lake project per prover with
# the right `lean-toolchain` and `mathlib` rev, then pulls the cache so that
# the first `lake build` is fast.
#
# Disk: ~3-5 GB per project (mostly cached mathlib olean files).
# Time: ~10-15 min per project on a warm cache, ~60 min if you have to build
#       mathlib from source (cache miss).
set -euo pipefail

DEST="${1:-./lake-projects}"
mkdir -p "$DEST"

provision() {
  local NAME="$1"
  local LEAN_TC="$2"
  local MATHLIB_REV="$3"
  local DIR="$DEST/$NAME"
  echo "=== Provisioning $NAME (lean=$LEAN_TC mathlib=$MATHLIB_REV) ==="
  if [[ -d "$DIR" ]]; then
    echo "  Already exists at $DIR, skipping init."
  else
    mkdir -p "$DIR" && pushd "$DIR" >/dev/null
    echo "$LEAN_TC" > lean-toolchain
    lake init proofgate_audit math
    sed -i.bak 's|@ "main"|@ "'"$MATHLIB_REV"'"|' lakefile.lean || true
    lake exe cache get || true
    lake build || true
    popd >/dev/null
  fi
  echo "  Done. Use with: --lean-cwd $DIR"
}

provision "kimina-v4.15"  "leanprover/lean4:v4.15.0" "9837ca9d65d9de6fad1ef4381750ca688774e608"
provision "goedel-v4.9"   "leanprover/lean4:v4.9.0"  "2f65ba7f1a9144b20c8e7358513548e317d26de1"
# DeepSeek-Prover-V2 doesn't pin; v4.9 matches its imports.
provision "deepseek-v4.9" "leanprover/lean4:v4.9.0"  "2f65ba7f1a9144b20c8e7358513548e317d26de1"
