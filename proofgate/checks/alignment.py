"""Check 4: alignment score.

We compute a dual-direction backtranslation score in the spirit of
FormalAlign (Lu et al., ICLR 2025): the informal statement φ is paired with
its formal counterpart φ̂, and we measure whether a competent reader can
recover one from the other. Disagreements are escalated to an LLM judge.

The implementation here exposes a clean interface and ships with a
*deterministic* default backend (cosine similarity over a small SBERT model
if available; otherwise a token-overlap heuristic). The LLM-judge path is
behind a flag and stubs cleanly. Production audits should swap in either
FormalAlign's released checkpoint or a local llama.cpp model — see the
README for the contract.

The point of keeping this module standalone is so users running the audit
without internet access still get *some* alignment signal, even if it's the
weaker fallback. The audit pipeline reports which backend was used so
results are reproducible.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Callable, Optional, Protocol


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


class AlignmentBackend(Protocol):
    """Anything that maps two strings to a similarity in [0, 1]."""

    name: str

    def similarity(self, informal: str, formal: str) -> float: ...


class TokenOverlapBackend:
    """Jaccard-ish overlap on lowercased identifier tokens, after stripping
    obvious Lean syntax. Deterministic, no dependencies, weak signal — useful
    as a smoke-test backend and a tiebreaker, not a primary signal."""

    name = "token-overlap"

    _LEAN_KEYWORDS = {
        "theorem", "lemma", "def", "by", "have", "show", "let", "fun",
        "intro", "intros", "exact", "apply", "refine", "rfl", "trivial",
        "Prop", "Type", "Nat", "Int", "Real", "Set", "True", "False",
    }

    def _bag(self, s: str) -> set[str]:
        return {
            t.lower()
            for t in _TOKEN_RE.findall(s)
            if t.lower() not in self._LEAN_KEYWORDS
        }

    def similarity(self, informal: str, formal: str) -> float:
        a, b = self._bag(informal), self._bag(formal)
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)


class SbertBackend:
    """Wrapper around a sentence-transformers model. Imports lazily so the
    base package has no torch/transformers dependency."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore

        self._model = SentenceTransformer(model_name)
        self.name = f"sbert:{model_name}"

    def similarity(self, informal: str, formal: str) -> float:
        emb = self._model.encode([informal, formal], normalize_embeddings=True)
        return float((emb[0] * emb[1]).sum())


def default_backend() -> AlignmentBackend:
    try:
        return SbertBackend()
    except Exception:
        return TokenOverlapBackend()


@dataclasses.dataclass
class AlignmentReport:
    theorem: str
    informal: str
    formal: str
    score: float
    threshold: float
    backend: str
    judge_called: bool = False
    judge_verdict: Optional[str] = None

    @property
    def verdict(self) -> str:
        if self.score >= self.threshold:
            return "aligned"
        if self.judge_verdict == "aligned":
            return "aligned"
        return "misaligned"


def check_alignment(
    theorem_name: str,
    informal: str,
    formal: str,
    backend: Optional[AlignmentBackend] = None,
    threshold: float = 0.50,
    judge: Optional[Callable[[str, str], str]] = None,
) -> AlignmentReport:
    """Score the (informal, formal) pair. If below threshold, optionally call
    a stronger judge to break ties.

    ``judge`` is any callable returning ``"aligned"`` or ``"misaligned"``.
    Production callers point it at a local LLM via llama.cpp; tests can pass a
    pure-Python stub.
    """
    backend = backend or default_backend()
    score = backend.similarity(informal, formal)
    judge_verdict: Optional[str] = None
    judge_called = False
    if score < threshold and judge is not None:
        judge_called = True
        try:
            judge_verdict = judge(informal, formal)
        except Exception:
            judge_verdict = None
    return AlignmentReport(
        theorem=theorem_name,
        informal=informal,
        formal=formal,
        score=score,
        threshold=threshold,
        backend=backend.name,
        judge_called=judge_called,
        judge_verdict=judge_verdict,
    )
