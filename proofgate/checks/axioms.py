"""Check 1: kernel-level axiom inspection.

Append `#print axioms <name>` after each released proof, elaborate, and parse
the resulting line. The trusted base follows the convention used by `mathlib`'s
`Mathlib.Util.AssertExists` and is what every published Lean 4 mathematics
paper takes for granted: propositional extensionality, the axiom of choice,
and `Quot.sound`.

`native_decide` introduces two additional axioms (`Lean.ofReduceBool` and
`Lean.trustCompiler`). These are sound *if* the user trusts the Lean compiler,
but they widen the trusted base meaningfully (an LLVM bug becomes a soundness
bug). We track them in ``COMPILER_TRUSTED_AXIOMS`` and report them as
``pass-with-flag`` rather than ``fail``: the user gets to decide whether to
include them in their notion of "faithful".
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Iterable, Optional

from ..kernel.lean_runner import LeanRunner


TRUSTED_AXIOMS: frozenset[str] = frozenset({
    "propext",
    "Classical.choice",
    "Quot.sound",
})


COMPILER_TRUSTED_AXIOMS: frozenset[str] = frozenset({
    "Lean.ofReduceBool",
    "Lean.trustCompiler",
})


# Anything ending in `sorryAx` (in any namespace) means a sorry/admit leaked in,
# possibly via an `apply?` suggestion the user accepted blindly. This is the
# canonical "implicit sorry" tell.
_SORRY_RE = re.compile(r"(^|\.)sorryAx$")


# Two output forms from `#print axioms`:
#   'foo' does not depend on any axioms
#   'foo' depends on axioms: [a, b.c, Lean.trustCompiler]
_AXIOM_LINE_RE = re.compile(
    r"'(?P<name>[^']+)' (?:does not depend on any axioms|depends on axioms: \[(?P<axs>[^\]]*)\])"
)


@dataclasses.dataclass
class AxiomReport:
    theorem: str
    axioms: list[str]
    trusted: bool
    compiler_trusted: bool   # True if the only extras are LLVM/Lean.trustCompiler
    has_sorry: bool
    extra: list[str]         # axioms outside both trusted sets
    raw_stdout: str
    raw_stderr: str

    @property
    def verdict(self) -> str:
        if self.has_sorry or self.extra:
            return "fail"
        if self.compiler_trusted:
            return "pass-with-flag"
        return "pass"


def _parse_axiom_lines(stdout: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for m in _AXIOM_LINE_RE.finditer(stdout):
        name = m.group("name")
        axs_raw = m.group("axs")
        if axs_raw is None:
            out[name] = []
        else:
            out[name] = [a.strip() for a in axs_raw.split(",") if a.strip()]
    return out


def check_axioms(
    proof_file: Path,
    theorem_names: Iterable[str],
    runner: Optional[LeanRunner] = None,
) -> list[AxiomReport]:
    """Run the kernel on ``proof_file`` (which must contain ``#print axioms`` for each
    name in ``theorem_names``) and return one ``AxiomReport`` per theorem.

    The caller is responsible for making sure the proof file is self-contained
    (imports its own mathlib, has its own `lean-toolchain` via being inside a
    lake project, etc.). For released prover artifacts this typically means
    invoking inside the prover's own lake project; see :mod:`proofgate.loaders`.
    """
    runner = runner or LeanRunner()
    res = runner.run_file(Path(proof_file))
    parsed = _parse_axiom_lines(res.stdout)

    reports: list[AxiomReport] = []
    for thm in theorem_names:
        axs = parsed.get(thm, [])
        has_sorry = any(_SORRY_RE.search(a) for a in axs)
        extras = [
            a for a in axs
            if a not in TRUSTED_AXIOMS
            and a not in COMPILER_TRUSTED_AXIOMS
            and not _SORRY_RE.search(a)
        ]
        compiler_trusted = (
            not has_sorry
            and not extras
            and any(a in COMPILER_TRUSTED_AXIOMS for a in axs)
        )
        trusted = (not has_sorry) and (not extras) and (not compiler_trusted)
        reports.append(
            AxiomReport(
                theorem=thm,
                axioms=axs,
                trusted=trusted,
                compiler_trusted=compiler_trusted,
                has_sorry=has_sorry,
                extra=extras,
                raw_stdout=res.stdout,
                raw_stderr=res.stderr,
            )
        )
    return reports
