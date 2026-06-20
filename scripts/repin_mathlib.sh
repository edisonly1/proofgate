#!/usr/bin/env bash
# Re-pin each lake project's mathlib to the prover-specific revision.
#
# The first version of setup_lake_projects.sh did a `sed` against a string that
# the modern `lake init` no longer writes, so all three projects ended up on
# whatever mathlib commit was master at provision time. This script fixes them:
# rewrites each lakefile.{lean,toml}, deletes lake-manifest.json so lake
# re-resolves, then runs `lake exe cache get && lake build`.
#
# Disk: incremental; depending on how different the new rev is from current.
# Time: 10-30 min per project if mathlib cache hits; 60+ min if it has to build.
#
# Usage:  bash scripts/repin_mathlib.sh [LAKE_PROJECTS_DIR]
set -euo pipefail

LAKE="${1:-./lake-projects}"

repin() {
  local NAME="$1"
  local URL="$2"        # which mathlib4 git URL
  local REV="$3"        # commit hash, tag, or branch
  local TOOLCHAIN="$4"  # leanprover/lean4:vX.Y.Z (must match the mathlib rev's era)
  local DIR="$LAKE/$NAME"
  if [[ ! -d "$DIR" ]]; then
    echo "  [$NAME] SKIP (directory missing)"
    return
  fi
  echo "=== [$NAME] re-pinning mathlib to $URL @ $REV (toolchain $TOOLCHAIN) ==="
  cd "$DIR"

  # CRITICAL: set lean-toolchain BEFORE any lake operations. lake init has a
  # tendency to write the latest installed toolchain into this file; if it
  # doesn't match the mathlib pin's era, the older mathlib's lakefile will use
  # Lake APIs that modern Lake cannot parse, and you'll see errors like
  # "Function expected at BuildJob" coming out of proofwidgets/lakefile.lean.
  echo "$TOOLCHAIN" > lean-toolchain
  echo "  set lean-toolchain to $TOOLCHAIN"
  echo "  ensuring elan has $TOOLCHAIN installed (may auto-download ~2 min first time)..."
  elan toolchain install "$TOOLCHAIN" 2>&1 | tail -3 || true

  if [[ -f lakefile.toml ]]; then
    python3 - <<PY
import re, pathlib
p = pathlib.Path("lakefile.toml")
text = p.read_text()
if 'name = "mathlib"' not in text:
    raise SystemExit("no mathlib require block found in lakefile.toml")
def fix(block: str) -> str:
    if 'name = "mathlib"' not in block: return block
    # Set git URL
    if re.search(r'^\s*git\s*=', block, flags=re.M):
        block = re.sub(r'^\s*git\s*=\s*".*"', f'git = "${URL}"', block, count=1, flags=re.M)
    # Set rev
    if re.search(r'^\s*rev\s*=', block, flags=re.M):
        block = re.sub(r'^\s*rev\s*=\s*".*"', f'rev = "${REV}"', block, count=1, flags=re.M)
    else:
        block = block.rstrip() + f'\nrev = "${REV}"\n'
    return block
parts = re.split(r'(?=^\[\[require\]\])', text, flags=re.M)
parts = [fix(p) for p in parts]
p.write_text(''.join(parts))
print("  updated lakefile.toml")
PY
  elif [[ -f lakefile.lean ]]; then
    python3 - <<PY
import re, pathlib
p = pathlib.Path("lakefile.lean")
text = p.read_text()
new = re.sub(
    r'require\s+mathlib\s+from\s+git\s+"[^"]+"(\s*@\s*"[^"]+")?',
    f'require mathlib from git "${URL}" @ "${REV}"',
    text,
    count=1,
)
if new == text:
    raise SystemExit("no mathlib require line found in lakefile.lean")
p.write_text(new)
print("  updated lakefile.lean")
PY
  else
    echo "  [$NAME] ERROR: no lakefile.lean or lakefile.toml"
    return
  fi

  rm -f lake-manifest.json
  echo "  lake update mathlib..."
  lake update mathlib 2>&1 | tail -5 || true
  echo "  lake exe cache get..."
  lake exe cache get 2>&1 | tail -5 || true
  echo "  lake build..."
  lake build 2>&1 | tail -3 || true
  cd - >/dev/null
  echo "  [$NAME] done."
  echo
}

MAINLINE="https://github.com/leanprover-community/mathlib4.git"

# Kimina pins to a specific commit on mainline mathlib (Lean 4.15 release window).
repin "kimina-v4.15"  "$MAINLINE" "9837ca9d65d9de6fad1ef4381750ca688774e608" "leanprover/lean4:v4.15.0"

# DeepSeek ships no explicit pin; their proofs use plain `import Mathlib`. We use
# the mathlib tag matching the closest plausible toolchain (Lean 4.9.0 release).
repin "deepseek-v4.9" "$MAINLINE" "v4.9.0" "leanprover/lean4:v4.9.0"

# Goedel pinned to a FORK (xinhjBrant/mathlib4) at a commit we can't fetch from
# mainline. We deliberately skip building a Goedel lake project: Goedel ships
# zero proofs (only benchmark-input statements with `:= by sorry`), so there is
# nothing for the kernel audit to verify. The static linter already establishes
# the "no auditable proofs" finding without a lake project.
echo "=== [goedel-v4.9] SKIP: Goedel ships no proofs to audit (see paper Section 5, Finding 2)."
echo

echo "All projects re-pinned. Verify with:"
echo "  for d in $LAKE/*/; do echo \"--- \$d ---\"; python3 -c 'import json; m=json.load(open(\"'\"\$d\"'lake-manifest.json\")); [print(p[\"name\"], p[\"rev\"]) for p in m[\"packages\"] if \"mathlib\" in p[\"name\"]]'; done"
