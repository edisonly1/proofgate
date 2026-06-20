"""Batched, parallel-per-prover kernel audit.

For each prover, concatenates all released proofs into a single Lean file
(each in its own namespace), appends `#print axioms` to each, runs `lake env
lean` ONCE inside the prover's lake project, then parses the combined output
back into per-item reports.

Why: a per-file subprocess pays the mathlib-load tax (~20-40s) every
invocation. 879 invocations = ~7h. Batching reduces it to one mathlib load
per prover, then ~1-3s elaboration per proof = ~10 min wall-time for the
whole audit when all three provers run in parallel.

Usage:
    python scripts/batch_audit.py --smoke      # 5 items each, ~3 min
    python scripts/batch_audit.py --parallel   # full audit, ~10 min wall
    python scripts/batch_audit.py --prover kimina-prover-72b-test
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Make the package importable when running from the project root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from proofgate.checks.axioms import (  # noqa: E402
    _AXIOM_LINE_RE,
    _SORRY_RE,
    COMPILER_TRUSTED_AXIOMS,
    TRUSTED_AXIOMS,
)
from proofgate.loaders import (  # noqa: E402
    load_deepseek,
    load_goedel,
    load_kimina,
)


# Shared header for every batched file. We intentionally use `maxHeartbeats 0`
# (no timeout) because the original prover proofs were generated under the
# same setting; re-verifying with a stricter heartbeat budget would falsely
# disqualify proofs that the original prover accepted.
HEADER = """\
import Mathlib
import Aesop

-- The released prover proofs were generated under `maxHeartbeats 0` (unlimited).
-- We must match it: a smaller budget would force Lean to insert `sorry` mid-proof
-- on heavy `nlinarith`/`polyrith` calls, producing false-positive `sorryAx`
-- findings that have nothing to do with the prover's faithfulness.
set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat
"""


def _sanitize_namespace(s: str) -> str:
    """Lean identifiers allow letters, digits, underscores. Replace anything else."""
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


def _extract_theorem_body(src: str) -> str:
    """Strip imports/opens/set_option preamble; keep the theorem (and its docstring).

    Heuristic: scan line-by-line, drop lines that begin with `import `,
    `set_option `, or a bare `open ` (one not followed by `in`). Keep everything
    starting from the first line that looks like a docstring or theorem header.
    """
    lines = src.split("\n")
    start = 0
    for i, raw in enumerate(lines):
        line = raw.lstrip()
        if line.startswith("/--") or line.startswith("/-!"):
            start = i
            break
        if line.startswith("theorem ") or line.startswith("lemma ") or line.startswith("example "):
            start = i
            break
    kept = []
    for line in lines[start:]:
        s = line.lstrip()
        if s.startswith("import "):
            continue
        if s.startswith("set_option "):
            continue
        # Drop top-level `open X Y Z` (no `in`), but keep `open X in theorem ...`.
        if s.startswith("open ") and " in " not in line:
            continue
        kept.append(line)
    return "\n".join(kept)


def build_batched_file(items) -> tuple[str, dict[str, str]]:
    """Returns (lean_source, name_map). name_map maps qualified Lean name back to problem_id."""
    parts = [HEADER]
    name_map: dict[str, str] = {}
    for item in items:
        ns = "Audit_" + _sanitize_namespace(item.problem_id)
        body = _extract_theorem_body(item.lean_source)
        parts.append(f"\n-- ===== {item.problem_id} =====")
        parts.append(f"namespace {ns}")
        parts.append(body.rstrip())
        parts.append(f"#print axioms {item.theorem_name}")
        parts.append(f"end {ns}")
        # Qualified form Lean will print: "Audit_xxx.theorem_name"
        name_map[f"{ns}.{item.theorem_name}"] = item.problem_id
    return "\n".join(parts), name_map


def run_lean_in_project(project_dir: Path, lean_file: Path, timeout_s: int = 7200):
    t0 = time.monotonic()
    try:
        cp = subprocess.run(
            ["lake", "env", "lean", str(lean_file)],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return cp.returncode, cp.stdout, cp.stderr, time.monotonic() - t0
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or ""), (e.stderr or "") + "\n[batch_audit] timeout", time.monotonic() - t0


def parse_axiom_output(stdout: str, name_map: dict[str, str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for m in _AXIOM_LINE_RE.finditer(stdout):
        qual = m.group("name")
        axs_raw = m.group("axs")
        axs = [a.strip() for a in axs_raw.split(",") if a.strip()] if axs_raw else []
        pid = name_map.get(qual, qual)
        out[pid] = axs
    return out


def verdict_for(axioms: list[str] | None) -> tuple[str, bool, bool, list[str]]:
    if axioms is None:
        return "no-output", False, False, []
    has_sorry = any(_SORRY_RE.search(a) for a in axioms)
    extras = [
        a for a in axioms
        if a not in TRUSTED_AXIOMS
        and a not in COMPILER_TRUSTED_AXIOMS
        and not _SORRY_RE.search(a)
    ]
    compiler = (
        not has_sorry
        and not extras
        and any(a in COMPILER_TRUSTED_AXIOMS for a in axioms)
    )
    if has_sorry or extras:
        return "fail", has_sorry, compiler, extras
    if compiler:
        return "pass-with-flag", has_sorry, compiler, extras
    return "pass", has_sorry, compiler, extras


def audit_prover_batched(name: str, benchmark: str, loader_fn, lake_cwd: Path,
                         out_path: Path, limit: int | None = None,
                         keep_lean_file: bool = True) -> dict:
    items = list(loader_fn())
    if limit:
        items = items[:limit]
    log = lambda m: print(f"[{name}] {m}", flush=True)
    log(f"{len(items)} items, lake={lake_cwd}")

    source, name_map = build_batched_file(items)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lean_file = out_path.parent / f"_{name}_batch.lean"
    lean_file.write_text(source, encoding="utf-8")
    log(f"wrote batched source ({len(source)} chars) to {lean_file}")

    log("invoking lake env lean (mathlib load + per-proof elaboration)...")
    # IMPORTANT: pass absolute path. `lake env lean` resolves relative paths
    # against the lake project's cwd, not the caller's cwd.
    rc, stdout, stderr, elapsed = run_lean_in_project(lake_cwd, lean_file.resolve())
    log(f"lean returned rc={rc} in {elapsed:.1f}s")

    parsed = parse_axiom_output(stdout, name_map)
    rows = []
    counts = {"pass": 0, "pass-with-flag": 0, "fail": 0, "no-output": 0}
    failure_modes = {"sorry": 0, "extra_axiom": 0}
    for item in items:
        axs = parsed.get(item.problem_id)
        verdict, has_sorry, compiler, extras = verdict_for(axs)
        counts[verdict] += 1
        if has_sorry:
            failure_modes["sorry"] += 1
        if extras:
            failure_modes["extra_axiom"] += 1
        rows.append({
            "problem_id": item.problem_id,
            "theorem_name": item.theorem_name,
            "axioms": axs,
            "verdict": verdict,
            "has_sorry": has_sorry,
            "compiler_trusted_only": compiler,
            "extra_axioms": extras,
        })

    summary = {
        "prover": name,
        "benchmark": benchmark,
        "n_total": len(items),
        "verdict_counts": counts,
        "failure_modes": failure_modes,
        "wall_seconds": round(elapsed, 1),
        "lean_returncode": rc,
        "faithful_pass_T0": (counts["pass"]) / max(1, len(items)),
        "faithful_pass_T1": (counts["pass"] + counts["pass-with-flag"]) / max(1, len(items)),
    }

    payload = {"summary": summary, "rows": rows}
    out_path.write_text(json.dumps(payload, indent=2))
    # Lean emits elaboration errors on stdout (not stderr) so we save both.
    (out_path.with_suffix(".stderr.txt")).write_text(stderr)
    (out_path.with_suffix(".stdout.txt")).write_text(stdout)
    log(f"pass={counts['pass']}  pass-with-flag={counts['pass-with-flag']}  "
        f"fail={counts['fail']}  no-output={counts['no-output']}  "
        f"Faithful-Pass[T0]={summary['faithful_pass_T0']:.3f}  "
        f"Faithful-Pass[T1]={summary['faithful_pass_T1']:.3f}")
    log(f"per-item report -> {out_path}")
    log(f"lean stderr     -> {out_path.with_suffix('.stderr.txt')}")
    if not keep_lean_file:
        try:
            lean_file.unlink()
        except OSError:
            pass
    return summary


PROVERS = [
    {
        "name": "deepseek-prover-v2-test",
        "benchmark": "miniF2F-test",
        "loader": lambda: load_deepseek(Path("artifacts/deepseek-prover-v2/minif2f-solutions"), split="test"),
        "lake": Path("lake-projects/deepseek-v4.9"),
    },
    {
        "name": "deepseek-prover-v2-valid",
        "benchmark": "miniF2F-valid",
        "loader": lambda: load_deepseek(Path("artifacts/deepseek-prover-v2/minif2f-solutions"), split="valid", benchmark="miniF2F-valid"),
        "lake": Path("lake-projects/deepseek-v4.9"),
    },
    {
        "name": "kimina-prover-72b-test",
        "benchmark": "miniF2F-test",
        "loader": lambda: load_kimina(Path("artifacts/kimina-prover-72b/minif2f_test_solved/minif2f_test_solved/minif2f-test-solved.jsonl")),
        "lake": Path("lake-projects/kimina-v4.15"),
    },
    # Goedel intentionally omitted from kernel audit: their public release contains
    # 0 proofs (only benchmark-input statements with `:= by sorry`), so the static
    # linter already establishes the audit's verdict. See paper Section 5, Finding 2.
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prover", choices=[p["name"] for p in PROVERS] + ["all"], default="all")
    ap.add_argument("--parallel", action="store_true",
                    help="Run all selected provers in parallel (one thread each).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Smoke-test: audit only the first N items per prover.")
    ap.add_argument("--smoke", action="store_true",
                    help="Equivalent to --limit 5 --parallel (fast end-to-end check).")
    ap.add_argument("--out-dir", type=Path, default=Path("reports/batched"))
    args = ap.parse_args()

    if args.smoke:
        args.limit = 5
        args.parallel = True

    selected = PROVERS if args.prover == "all" else [p for p in PROVERS if p["name"] == args.prover]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    def runone(p):
        return audit_prover_batched(
            p["name"], p["benchmark"], p["loader"], p["lake"],
            args.out_dir / f"{p['name']}.json",
            limit=args.limit,
        )

    t0 = time.monotonic()
    if args.parallel and len(selected) > 1:
        with ThreadPoolExecutor(max_workers=len(selected)) as ex:
            summaries = list(ex.map(runone, selected))
    else:
        summaries = [runone(p) for p in selected]
    total = time.monotonic() - t0

    print()
    print(f"=== Audit complete in {total:.1f}s total wall time ===")
    print()
    for s in summaries:
        print(f"  {s['prover']:32s}  n={s['n_total']:4d}  "
              f"pass={s['verdict_counts']['pass']:4d}  "
              f"flag={s['verdict_counts']['pass-with-flag']:4d}  "
              f"fail={s['verdict_counts']['fail']:4d}  "
              f"no-out={s['verdict_counts']['no-output']:4d}  "
              f"FP[T0]={s['faithful_pass_T0']:.3f}  "
              f"FP[T1]={s['faithful_pass_T1']:.3f}")

    combined_path = args.out_dir / "_combined_summary.json"
    combined_path.write_text(json.dumps(summaries, indent=2))
    print(f"\nCombined summary -> {combined_path}")


if __name__ == "__main__":
    main()
