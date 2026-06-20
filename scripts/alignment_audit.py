"""Run Check 4 (alignment) over all released items that ship an (informal, formal) pair.

For each prover, we iterate the loaders, extract:
  - informal text:    DeepSeek docstring  / Kimina `cot` / Goedel `informal_prefix`
  - formal statement: parsed `theorem NAME : ... :=` skeleton

We then score each pair with the SBERT backend and report counts above and below
the calibrated threshold. Items lacking either side are reported separately so
the counts add up correctly.

Output: reports/alignment_audit.json plus a stdout summary.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from proofgate.checks.alignment import SbertBackend, TokenOverlapBackend  # noqa: E402
from proofgate.loaders import load_deepseek, load_goedel, load_kimina  # noqa: E402


PROVERS = [
    ("deepseek-prover-v2-test", "miniF2F-test",
     lambda: load_deepseek(Path("artifacts/deepseek-prover-v2/minif2f-solutions"), split="test")),
    ("deepseek-prover-v2-valid", "miniF2F-valid",
     lambda: load_deepseek(Path("artifacts/deepseek-prover-v2/minif2f-solutions"), split="valid",
                           benchmark="miniF2F-valid")),
    ("kimina-prover-72b-test", "miniF2F-test",
     lambda: load_kimina(Path("artifacts/kimina-prover-72b/minif2f_test_solved/minif2f_test_solved/minif2f-test-solved.jsonl"))),
    ("goedel-prover-v2-test", "miniF2F-test",
     lambda: load_goedel(Path("artifacts/goedel-prover-v2/dataset/minif2f.jsonl"))),
]


def main():
    print("Loading SBERT backend (one-time, ~5s)...", flush=True)
    try:
        backend = SbertBackend()
        print(f"  backend: {backend.name}")
    except Exception as e:
        print(f"  SBERT failed ({e!r}); falling back to token-overlap")
        backend = TokenOverlapBackend()

    THRESHOLD = 0.40   # see Section 3.4 of the paper for the calibration story
    Path("reports").mkdir(exist_ok=True)
    out: dict[str, dict] = {}

    for name, benchmark, loader in PROVERS:
        items = list(loader())
        n_total = len(items)
        rows: list[dict] = []
        counts: Counter = Counter()
        scores: list[float] = []
        t0 = time.monotonic()
        for item in items:
            informal = (item.informal or "").strip()
            formal = (item.formal_statement or "").strip()
            if not informal or not formal:
                counts["missing_pair"] += 1
                rows.append({
                    "problem_id": item.problem_id,
                    "verdict": "missing_pair",
                    "score": None,
                    "informal_present": bool(informal),
                    "formal_present": bool(formal),
                })
                continue
            score = backend.similarity(informal, formal)
            scores.append(score)
            verdict = "aligned" if score >= THRESHOLD else "misaligned"
            counts[verdict] += 1
            rows.append({
                "problem_id": item.problem_id,
                "verdict": verdict,
                "score": round(score, 4),
                "informal_present": True,
                "formal_present": True,
            })
        elapsed = time.monotonic() - t0
        summary = {
            "prover": name,
            "benchmark": benchmark,
            "backend": backend.name,
            "threshold": THRESHOLD,
            "n_total": n_total,
            "n_aligned": counts["aligned"],
            "n_misaligned": counts["misaligned"],
            "n_missing_pair": counts["missing_pair"],
            "frac_aligned": round(counts["aligned"] / n_total, 4) if n_total else 0.0,
            "frac_misaligned": round(counts["misaligned"] / n_total, 4) if n_total else 0.0,
            "median_score": round(sorted(scores)[len(scores) // 2], 4) if scores else None,
            "min_score": round(min(scores), 4) if scores else None,
            "max_score": round(max(scores), 4) if scores else None,
            "wall_seconds": round(elapsed, 1),
        }
        # List the lowest-scoring items so a human can sanity-check the threshold.
        sorted_rows = sorted(
            [r for r in rows if r["score"] is not None],
            key=lambda r: r["score"],
        )
        summary["lowest_scoring_items"] = [
            {"problem_id": r["problem_id"], "score": r["score"], "verdict": r["verdict"]}
            for r in sorted_rows[:10]
        ]
        out[name] = {"summary": summary, "rows": rows}
        print(f"[{name}] aligned={counts['aligned']}/{n_total}  "
              f"misaligned={counts['misaligned']}/{n_total}  "
              f"missing_pair={counts['missing_pair']}/{n_total}  "
              f"wall={elapsed:.1f}s")
        if sorted_rows:
            print(f"  lowest 3 scores: " + ", ".join(
                f"{r['problem_id']}={r['score']}" for r in sorted_rows[:3]
            ))

    Path("reports/alignment_audit.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote reports/alignment_audit.json")


if __name__ == "__main__":
    main()
