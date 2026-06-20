"""Static-only audit (Check 2 + lightweight Check 1 surrogates) of all three
provers' released proofs. Runs without a Lean toolchain because every check
here is purely syntactic over the released source.

We report, per prover:
  - n total released proofs
  - n with explicit `sorry`/`admit`
  - n with `native_decide` (widens trusted base)
  - n with `decide` on Real-typed goals (potentially unsound)
  - n with `apply?` / `exact?` (interactive search — possible hidden metavar)
  - n with fresh `axiom` declarations
  - distribution of tactic findings

Output: reports/static_audit.json (machine-readable) + stdout summary.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from proofgate.checks.tactics import check_tactics
from proofgate.loaders import load_deepseek, load_goedel, load_kimina


PROVERS = [
    ("deepseek-prover-v2", "miniF2F-test",
     lambda: load_deepseek(Path("artifacts/deepseek-prover-v2/minif2f-solutions"), split="test")),
    ("deepseek-prover-v2", "miniF2F-valid",
     lambda: load_deepseek(Path("artifacts/deepseek-prover-v2/minif2f-solutions"), split="valid",
                           benchmark="miniF2F-valid")),
    ("kimina-prover-72b", "miniF2F-test",
     lambda: load_kimina(Path("artifacts/kimina-prover-72b/minif2f_test_solved/minif2f_test_solved/minif2f-test-solved.jsonl"))),
    ("goedel-prover-v2", "miniF2F-test",
     lambda: load_goedel(Path("artifacts/goedel-prover-v2/dataset/minif2f.jsonl"))),
]


def audit(prover: str, benchmark: str, items) -> dict:
    findings_by_tactic: Counter = Counter()
    findings_per_item: list[int] = []
    verdict_counts: Counter = Counter()
    sample_evidence: dict[str, list[dict]] = {}
    n_items = 0
    n_with_any_finding = 0

    for item in items:
        n_items += 1
        reps = check_tactics(item.lean_source, [item.theorem_name])
        rep = reps[0]
        verdict_counts[rep.verdict] += 1
        findings_per_item.append(len(rep.findings))
        if rep.findings:
            n_with_any_finding += 1
        for f in rep.findings:
            findings_by_tactic[f.tactic] += 1
            sample_evidence.setdefault(f.tactic, [])
            if len(sample_evidence[f.tactic]) < 3:
                sample_evidence[f.tactic].append({
                    "problem_id": item.problem_id,
                    "line": f.line,
                    "snippet": f.snippet[:140],
                })

    return {
        "prover": prover,
        "benchmark": benchmark,
        "n_items": n_items,
        "n_items_with_any_finding": n_with_any_finding,
        "pct_items_with_any_finding": round(100 * n_with_any_finding / n_items, 1) if n_items else 0.0,
        "verdict_counts": dict(verdict_counts),
        "findings_by_tactic": dict(findings_by_tactic),
        "sample_evidence": sample_evidence,
    }


def main():
    out = {}
    for prover, benchmark, loader in PROVERS:
        key = f"{prover}__{benchmark}"
        print(f"=== {key} ===")
        try:
            res = audit(prover, benchmark, loader())
            out[key] = res
            print(json.dumps({k: v for k, v in res.items() if k != "sample_evidence"}, indent=2))
            print()
        except Exception as e:
            print(f"  FAILED: {e}")
            out[key] = {"error": str(e)}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/static_audit.json").write_text(json.dumps(out, indent=2))
    print("Wrote reports/static_audit.json")


if __name__ == "__main__":
    main()
