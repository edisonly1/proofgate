"""Render audit results as a human-readable summary."""
from __future__ import annotations

from typing import Iterable

from .metric import AuditResult, FaithfulPass


def text_summary(fp: FaithfulPass, results: Iterable[AuditResult]) -> str:
    results = list(results)
    lines = [
        f"=== ProofGate audit ===",
        f"Prover:     {fp.prover}",
        f"Benchmark:  {fp.benchmark}",
        f"Items:      {fp.n_total}",
        f"Faithful:   {fp.n_faithful} ({100*fp.score:.1f}%)",
        "",
        "Failure-mode breakdown:",
    ]
    for k, v in fp.breakdown.items():
        lines.append(f"  {k:25s} {v}")

    fails = [r for r in results if not r.faithful_pass]
    if fails:
        lines.append("")
        lines.append(f"First {min(10, len(fails))} failing items:")
        for r in fails[:10]:
            why = []
            if r.axiom and r.axiom.has_sorry:
                why.append("sorry")
            if r.axiom and r.axiom.extra:
                why.append(f"axioms={r.axiom.extra}")
            if r.tactic and r.tactic.verdict == "fail":
                bad = [f.tactic for f in r.tactic.findings]
                why.append(f"tactics={bad}")
            if r.vacuity and r.vacuity.vacuous:
                why.append("vacuous")
            if r.alignment and r.alignment.verdict == "misaligned":
                why.append(f"misaligned(score={r.alignment.score:.2f})")
            lines.append(f"  - {r.item.problem_id}: {', '.join(why)}")
    return "\n".join(lines)
