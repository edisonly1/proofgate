"""Loader for DeepSeek-Prover-V2 released proofs.

Layout (from `minif2f-solutions.zip` in the official repo):

    test/<problem_id>.lean
    valid/<problem_id>.lean

Each file is self-contained: it imports Mathlib + Aesop, opens the usual
namespaces, contains a docstring with the informal statement, and ends with a
single `theorem <problem_id> ... := by ...` block.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from .types import ProofItem


# Capture an optional /-! ... -/ or /-- ... -/ docstring as the informal,
# then the theorem name.
_DOCSTRING_RE = re.compile(r"/--?\s*(.*?)\s*-/", re.DOTALL)
_THEOREM_NAME_RE = re.compile(r"\btheorem\s+([\w'.]+)\b")


def _split_informal(source: str) -> tuple[str | None, str | None]:
    m = _DOCSTRING_RE.search(source)
    informal = m.group(1).strip() if m else None
    n = _THEOREM_NAME_RE.search(source)
    name = n.group(1) if n else None
    return informal, name


def _formal_statement(source: str) -> str | None:
    """Return `theorem name : ... :=` with the proof body stripped, if findable."""
    idx = source.find("theorem")
    if idx == -1:
        return None
    end = source.find(":=", idx)
    if end == -1:
        return None
    return source[idx : end + 2].strip()


def load_deepseek(
    root: Path,
    split: str = "test",
    benchmark: str = "miniF2F-test",
) -> Iterator[ProofItem]:
    """Yield one ``ProofItem`` per .lean file in ``root/<split>/``.

    ``root`` should be the directory containing ``test/`` and ``valid/`` from
    the unzipped artifact.
    """
    split_dir = Path(root) / split
    if not split_dir.is_dir():
        raise FileNotFoundError(f"DeepSeek split directory not found: {split_dir}")
    for path in sorted(split_dir.glob("*.lean")):
        src = path.read_text(encoding="utf-8")
        informal, name = _split_informal(src)
        yield ProofItem(
            prover="deepseek-prover-v2",
            benchmark=benchmark,
            problem_id=path.stem,
            theorem_name=name or path.stem,
            lean_source=src,
            informal=informal,
            formal_statement=_formal_statement(src),
        )
