"""Loader for Goedel-Prover-V2 released proofs.

`dataset/minif2f.jsonl` rows::

    {"name": "...", "informal_prefix": "...", "formal_statement": "...",
     "split": "test", "lean4_code": "<full lean source>", "problem_id": "..."}

`formal_statement` is the bare `theorem name : ... := by` skeleton; `lean4_code`
is the full file (imports + statement + proof). We use `lean4_code` as the
``lean_source`` for the audit.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .types import ProofItem


def load_goedel(
    jsonl_path: Path,
    benchmark: str = "miniF2F-test",
) -> Iterator[ProofItem]:
    with Path(jsonl_path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "lean4_code" not in row or not row["lean4_code"]:
                continue
            yield ProofItem(
                prover="goedel-prover-v2",
                benchmark=benchmark,
                problem_id=row.get("problem_id") or row.get("name", "<unknown>"),
                theorem_name=row.get("name", "<unknown>"),
                lean_source=row["lean4_code"],
                informal=row.get("informal_prefix"),
                formal_statement=row.get("formal_statement"),
            )
