"""Check 2: banned-tactic linter.

A purely *syntactic* check on the proof source. Cheap, fast, and conservative:
we flag occurrences of tactics that have been observed in the wild to mask
unsoundness or to widen the trusted base without the user noticing. The check
is advisory in the sense that an occurrence does not by itself fail the proof
(``native_decide`` on a `Decidable Bool` goal is fine) — but every occurrence
goes into the audit report so a human can decide.

What we flag:
  - bare ``apply?``, ``exact?`` (interactive search tactics; in some versions
    they could complete with a hidden metavariable / sorry — see the Lean Zulip
    discussion the proposal references)
  - ``sorry`` / ``admit`` anywhere in the source
  - any new ``axiom`` declaration in the same file as the proof
  - ``native_decide`` and ``decide`` on (textual) `Real`-typed goals, which is
    a heuristic for "decision procedure may be unsound for this goal type"
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Iterable

# We strip Lean line- and block-comments before scanning, so a quote in a
# comment doesn't trip the linter. We replace comment bodies with whitespace
# of the same width (preserving newlines) so that match offsets and reported
# line numbers stay consistent with the original source.
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/-(?:(?!-/).)*?-/", re.DOTALL)


def _blank_preserving(match: "re.Match[str]") -> str:
    s = match.group(0)
    # Replace every non-newline character with a space so byte offsets and
    # line numbers from `scan` map to the same positions in the original.
    return "".join(" " if c != "\n" else "\n" for c in s)


BANNED_TACTICS: dict[str, str] = {
    # tactic name -> short rationale
    "sorry": "explicit incomplete proof",
    "admit": "alias for sorry",
    "apply?": "interactive search; can succeed with a hidden metavariable",
    "exact?": "interactive search; can succeed with a hidden metavariable",
}


_AXIOM_DECL_RE = re.compile(r"^\s*axiom\s+(\w+)\b", re.MULTILINE)
_NATIVE_DECIDE_RE = re.compile(r"\bnative_decide\b")
_DECIDE_RE = re.compile(r"(?<!\w)decide\b")
# Crude but effective: if `Real` appears in the same statement as `decide`, flag.
_REAL_TOKEN_RE = re.compile(r"\bReal\b")


@dataclasses.dataclass
class TacticFinding:
    tactic: str
    rationale: str
    line: int                 # 1-indexed
    snippet: str              # the offending line, stripped


@dataclasses.dataclass
class TacticReport:
    theorem: str
    findings: list[TacticFinding]

    @property
    def verdict(self) -> str:
        # Any banned tactic or fresh axiom => fail. native_decide => flag-only.
        hard_fail = {"sorry", "admit", "apply?", "exact?", "fresh axiom"}
        if any(f.tactic in hard_fail for f in self.findings):
            return "fail"
        if self.findings:
            return "flag"
        return "pass"


def _strip_comments(src: str) -> str:
    return _LINE_COMMENT.sub(_blank_preserving, _BLOCK_COMMENT.sub(_blank_preserving, src))


def _line_of(src: str, offset: int) -> int:
    return src.count("\n", 0, offset) + 1


def _enclosing_line(src: str, offset: int) -> str:
    start = src.rfind("\n", 0, offset) + 1
    end = src.find("\n", offset)
    if end == -1:
        end = len(src)
    return src[start:end].strip()


def check_tactics(
    proof_source: str | Path,
    theorem_names: Iterable[str],
) -> list[TacticReport]:
    """Lint each named theorem's body. Returns one ``TacticReport`` per theorem.

    The current implementation reports findings *per file* rather than carefully
    slicing per theorem; for the audit this is conservative (a finding in any
    theorem in the file is attributed to all theorems in that file). For
    released prover artifacts where each proof is in its own file this is
    exact.
    """
    src = (
        proof_source.read_text(encoding="utf-8")
        if isinstance(proof_source, Path)
        else proof_source
    )
    scan = _strip_comments(src)

    findings: list[TacticFinding] = []

    for tac, why in BANNED_TACTICS.items():
        # Use a non-regex search so `apply?` etc. work without escaping.
        idx = 0
        while True:
            i = scan.find(tac, idx)
            if i == -1:
                break
            # word-boundary check (cheap): make sure this isn't part of a longer ident
            left_ok = (i == 0) or not (scan[i - 1].isalnum() or scan[i - 1] == "_")
            right_pos = i + len(tac)
            right_ok = (right_pos >= len(scan)) or not (
                scan[right_pos].isalnum() or scan[right_pos] == "_"
            )
            if left_ok and right_ok:
                findings.append(
                    TacticFinding(
                        tactic=tac,
                        rationale=why,
                        line=_line_of(src, i),
                        snippet=_enclosing_line(src, i),
                    )
                )
            idx = i + len(tac)

    for m in _AXIOM_DECL_RE.finditer(scan):
        findings.append(
            TacticFinding(
                tactic="fresh axiom",
                rationale=f"new `axiom` declaration `{m.group(1)}` outside trusted base",
                line=_line_of(src, m.start()),
                snippet=_enclosing_line(src, m.start()),
            )
        )

    for m in _NATIVE_DECIDE_RE.finditer(scan):
        findings.append(
            TacticFinding(
                tactic="native_decide",
                rationale="widens trusted base to Lean.ofReduceBool / Lean.trustCompiler",
                line=_line_of(src, m.start()),
                snippet=_enclosing_line(src, m.start()),
            )
        )

    for m in _DECIDE_RE.finditer(scan):
        line = _enclosing_line(src, m.start())
        if _REAL_TOKEN_RE.search(line):
            findings.append(
                TacticFinding(
                    tactic="decide-on-real",
                    rationale="`decide` on a real-typed goal: unsound if no Decidable instance",
                    line=_line_of(src, m.start()),
                    snippet=line,
                )
            )

    return [TacticReport(theorem=thm, findings=list(findings)) for thm in theorem_names]
