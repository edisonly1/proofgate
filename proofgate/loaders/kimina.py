"""Loader for Kimina-Prover-72B released proofs (JSONL form).

`minif2f-test-solved.jsonl` rows look like::

    {"uuid": "...", "name": "amc12_2000_p5", "cot": "...", "correct_proof": "<full lean source>"}

The `correct_proof` value is a full self-contained Lean source: imports,
opens, then the theorem.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from .types import ProofItem


_THEOREM_NAME_RE = re.compile(r"\btheorem\s+([\w'.]+)\b")


def _formal_statement(source: str) -> str | None:
    idx = source.find("theorem")
    if idx == -1:
        return None
    end = source.find(":=", idx)
    if end == -1:
        return None
    return source[idx : end + 2].strip()


def load_kimina(
    jsonl_path: Path,
    benchmark: str = "miniF2F-test",
) -> Iterator[ProofItem]:
    with Path(jsonl_path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            src = row.get("correct_proof") or row.get("proof") or ""
            n = _THEOREM_NAME_RE.search(src)
            yield ProofItem(
                prover="kimina-prover-72b",
                benchmark=benchmark,
                problem_id=row.get("name", row.get("uuid", "<unknown>")),
                theorem_name=n.group(1) if n else row.get("name", "<unknown>"),
                lean_source=src,
                informal=row.get("informal") or row.get("cot"),
                formal_statement=_formal_statement(src),
            )
