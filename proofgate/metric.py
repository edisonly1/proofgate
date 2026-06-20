"""Faithful-Pass: the headline metric the audit produces.

Faithful-Pass(P, B) := (1 / |B|) * Σ_i 1[item_i passes Checks 1, 2, AND its
                                       formal statement passes Checks 3, 4].

A single failed check disqualifies the item. ``pass-with-flag`` (the
native_decide case) is still a pass — the user can re-run with stricter
settings if they want.
"""
from __future__ import annotations

import dataclasses
import json
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from .checks import (
    AlignmentReport,
    AxiomReport,
    TacticReport,
    VacuityReport,
    check_alignment,
    check_axioms,
    check_tactics,
    check_vacuity,
)
from .kernel.lean_runner import LeanRunner
from .loaders import ProofItem


@dataclasses.dataclass
class AuditResult:
    item: ProofItem
    axiom: Optional[AxiomReport]
    tactic: Optional[TacticReport]
    vacuity: Optional[VacuityReport]
    alignment: Optional[AlignmentReport]

    @property
    def faithful_pass(self) -> bool:
        ok = True
        if self.axiom is not None:
            ok = ok and self.axiom.verdict in {"pass", "pass-with-flag"}
        if self.tactic is not None:
            ok = ok and self.tactic.verdict in {"pass", "flag"}
        if self.vacuity is not None:
            ok = ok and self.vacuity.verdict == "non-vacuous"
        if self.alignment is not None:
            ok = ok and self.alignment.verdict == "aligned"
        return ok

    def to_dict(self) -> dict:
        return {
            "prover": self.item.prover,
            "benchmark": self.item.benchmark,
            "problem_id": self.item.problem_id,
            "theorem": self.item.theorem_name,
            "faithful_pass": self.faithful_pass,
            "checks": {
                "axiom": {
                    "verdict": self.axiom.verdict,
                    "axioms": self.axiom.axioms,
                    "extra": self.axiom.extra,
                    "has_sorry": self.axiom.has_sorry,
                } if self.axiom else None,
                "tactic": {
                    "verdict": self.tactic.verdict,
                    "findings": [
                        {"tactic": f.tactic, "line": f.line, "snippet": f.snippet, "rationale": f.rationale}
                        for f in self.tactic.findings
                    ],
                } if self.tactic else None,
                "vacuity": {
                    "verdict": self.vacuity.verdict,
                    "note": self.vacuity.note,
                } if self.vacuity else None,
                "alignment": {
                    "verdict": self.alignment.verdict,
                    "score": self.alignment.score,
                    "backend": self.alignment.backend,
                    "judge_called": self.alignment.judge_called,
                } if self.alignment else None,
            },
        }


def _append_print_axioms(source: str, theorem_name: str) -> str:
    return source.rstrip() + f"\n\n#print axioms {theorem_name}\n"


def audit_item(
    item: ProofItem,
    *,
    runner: Optional[LeanRunner] = None,
    do_axioms: bool = True,
    do_tactics: bool = True,
    do_vacuity: bool = False,
    do_alignment: bool = False,
) -> AuditResult:
    """Run the requested subset of checks against one ``ProofItem``.

    Defaults skip vacuity and alignment because they require, respectively,
    a working kernel for the negation probe (Check 3 needs the same toolchain
    as the proof) and an alignment backend (Check 4 needs SBERT or an LLM
    judge). The CLI exposes flags to turn them on.
    """
    runner = runner or LeanRunner()

    axiom_rep: Optional[AxiomReport] = None
    if do_axioms:
        # Write the source + #print axioms to a tempfile and run.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".lean", delete=False
        ) as fh:
            fh.write(_append_print_axioms(item.lean_source, item.theorem_name))
            tmp = Path(fh.name)
        try:
            reps = check_axioms(tmp, [item.theorem_name], runner=runner)
            axiom_rep = reps[0] if reps else None
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass

    tactic_rep: Optional[TacticReport] = None
    if do_tactics:
        reps = check_tactics(item.lean_source, [item.theorem_name])
        tactic_rep = reps[0] if reps else None

    vacuity_rep: Optional[VacuityReport] = None
    if do_vacuity and item.formal_statement:
        vacuity_rep = check_vacuity(
            theorem_name=item.theorem_name,
            theorem_signature=item.formal_statement,
            runner=runner,
        )

    alignment_rep: Optional[AlignmentReport] = None
    if do_alignment and item.informal and item.formal_statement:
        alignment_rep = check_alignment(
            theorem_name=item.theorem_name,
            informal=item.informal,
            formal=item.formal_statement,
        )

    return AuditResult(
        item=item,
        axiom=axiom_rep,
        tactic=tactic_rep,
        vacuity=vacuity_rep,
        alignment=alignment_rep,
    )


@dataclasses.dataclass
class FaithfulPass:
    prover: str
    benchmark: str
    n_total: int
    n_faithful: int
    breakdown: dict[str, int]   # failure-mode counts

    @property
    def score(self) -> float:
        return self.n_faithful / self.n_total if self.n_total else 0.0

    def to_dict(self) -> dict:
        return {
            "prover": self.prover,
            "benchmark": self.benchmark,
            "n_total": self.n_total,
            "n_faithful": self.n_faithful,
            "faithful_pass": round(self.score, 4),
            "breakdown": self.breakdown,
        }


def aggregate(results: Iterable[AuditResult]) -> FaithfulPass:
    results = list(results)
    if not results:
        return FaithfulPass("?", "?", 0, 0, {})
    n_total = len(results)
    n_faithful = sum(1 for r in results if r.faithful_pass)
    breakdown = {
        "unfaithful_sorry": sum(1 for r in results if r.axiom and r.axiom.has_sorry),
        "unfaithful_extra_axiom": sum(
            1 for r in results if r.axiom and r.axiom.extra and not r.axiom.has_sorry
        ),
        "compiler_trusted_only": sum(
            1 for r in results if r.axiom and r.axiom.compiler_trusted
        ),
        "banned_tactic": sum(
            1 for r in results if r.tactic and r.tactic.verdict == "fail"
        ),
        "vacuous": sum(1 for r in results if r.vacuity and r.vacuity.vacuous),
        "misaligned": sum(
            1 for r in results if r.alignment and r.alignment.verdict == "misaligned"
        ),
    }
    return FaithfulPass(
        prover=results[0].item.prover,
        benchmark=results[0].item.benchmark,
        n_total=n_total,
        n_faithful=n_faithful,
        breakdown=breakdown,
    )


def write_jsonl(results: Iterable[AuditResult], out_path: Path) -> None:
    with Path(out_path).open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r.to_dict()) + "\n")
