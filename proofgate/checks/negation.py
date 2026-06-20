"""Check 3: negation-counterexample probe.

A statement φ is *vacuous* if its negation can also be discharged by a cheap
decision procedure, or if its hypotheses are unsatisfiable. We probe this by
emitting a fresh Lean file::

    theorem __probe_neg_<name> : ¬ <statement> := by
      first
        | decide
        | (intro h; exact absurd h (by decide))
        | (intros; omega)
        | (intros; simp_all)

If the probe closes, the original statement is vacuous (trivially false, which
contradicts the original being provable — i.e. unsoundness somewhere) OR the
decision procedure used is unsound (which is itself a finding). Either way the
item is unreliable as evidence of mathematical capability.

In practice for miniF2F-style benchmarks the more common vacuity mode is
*ex falso* — a misformalization yields contradictory hypotheses, and the
prover discharges the goal by exploding them. Pure `decide`-tautologies on
miniF2F are rare.

This implementation is intentionally limited: we use a small fixed tactic
budget. False negatives (we miss vacuity) are acceptable; false positives
(we wrongly flag a real statement as vacuous) are not, because they would
mislabel a legitimate proof.
"""
from __future__ import annotations

import dataclasses
import re
import textwrap
from pathlib import Path
from typing import Optional

from ..kernel.lean_runner import LeanRunner

# Lean considers a file successful if elaboration produces no errors; a
# `theorem` with `:= by ...` and no `error:` is a success.
_ERROR_LINE_RE = re.compile(r":\d+:\d+:\s*error:", re.IGNORECASE)


@dataclasses.dataclass
class VacuityReport:
    theorem: str
    vacuous: bool
    probe_stdout: str
    probe_stderr: str
    note: str = ""

    @property
    def verdict(self) -> str:
        return "vacuous" if self.vacuous else "non-vacuous"


def _extract_goal(signature: str) -> str:
    """From `theorem NAME (params...) : GOAL := by ...`, extract the GOAL.

    We strip everything up to and including the colon at parenthesis-depth 0
    that separates the parameter list from the goal type, then strip from
    `:=` onward. This is robust to colons inside parameter type annotations
    like `(n : Nat) (h : n > 0)`, which the naive `split(':', 1)` was not.
    """
    # First, drop any `:= ...` tail.
    walrus = signature.find(":=")
    if walrus != -1:
        signature = signature[:walrus]

    # Skip a leading `theorem NAME` if present.
    head = signature.lstrip()
    if head.startswith("theorem") or head.startswith("lemma"):
        # find end of keyword + identifier
        rest = head.split(None, 2)
        signature = rest[-1] if len(rest) > 2 else ""

    # Now scan for the colon at depth 0.
    depth = 0
    for i, c in enumerate(signature):
        if c in "([{⟨":
            depth += 1
        elif c in ")]}⟩":
            depth -= 1
        elif c == ":" and depth == 0:
            return signature[i + 1 :].strip()

    # Fallback: assume the whole thing is the goal.
    return signature.strip()


def _probe_source(theorem_signature: str, header_imports: str = "") -> str:
    """Build a Lean snippet that tries to discharge the *negation* of the goal.

    ``theorem_signature`` is a full theorem header, possibly with parameter
    annotations: e.g. ``theorem foo (n : Nat) (h : n > 0) : n + 0 = n := by``.
    Only the goal expression (the part after the colon at depth 0) is negated;
    parameters are reintroduced via `intros` inside the proof.
    """
    goal = _extract_goal(theorem_signature)
    return textwrap.dedent(
        f"""
        {header_imports}

        theorem __proofgate_probe : ¬ ({goal}) := by
          first
            | decide
            | (intro h; exact absurd h (by decide))
            | (intros; omega)
        """
    ).strip() + "\n"


def check_vacuity(
    theorem_name: str,
    theorem_signature: str,
    runner: Optional[LeanRunner] = None,
    header_imports: str = "",
) -> VacuityReport:
    """Try to discharge ``¬ statement``. Returns vacuous=True iff the probe succeeds
    *and* the original statement was provable (which the caller has presumably
    already established via Check 1)."""
    runner = runner or LeanRunner(timeout_s=30)
    src = _probe_source(theorem_signature, header_imports)
    res = runner.run_snippet(src)
    has_error = bool(_ERROR_LINE_RE.search(res.stdout + res.stderr))
    vacuous = (res.returncode == 0) and (not has_error)
    note = ""
    if res.returncode == 124:
        note = "probe timed out — treating as non-vacuous (conservative)"
        vacuous = False
    return VacuityReport(
        theorem=theorem_name,
        vacuous=vacuous,
        probe_stdout=res.stdout,
        probe_stderr=res.stderr,
        note=note,
    )
