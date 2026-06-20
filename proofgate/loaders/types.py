from __future__ import annotations

import dataclasses
from typing import Optional


@dataclasses.dataclass
class ProofItem:
    """One (formal statement, proof) pair to audit."""
    prover: str               # "deepseek-prover-v2" | "kimina-prover-72b" | "goedel-prover-v2"
    benchmark: str            # "miniF2F-test" | ...
    problem_id: str           # e.g. "mathd_algebra_478"
    theorem_name: str         # the Lean identifier as released
    lean_source: str          # full self-contained Lean source (imports + theorem + proof)
    informal: Optional[str]   # natural-language statement if released, else None
    formal_statement: Optional[str]  # `theorem name : ... := by` (proof stripped)
