"""Thin wrapper around the `lean` CLI used by every Check that needs the kernel.

We deliberately do NOT depend on a long-running Lean server. A subprocess per file
is slow relative to the Kimina Lean Server, but it has two advantages for an
audit tool:

  1. Each item is fully isolated. A misbehaving proof cannot leak state into the
     next one. For a credibility audit this matters more than throughput.
  2. The interface is reproducible from any machine with `lean` on PATH.

The class accepts an optional ``cwd`` so callers can run inside a lake project
that has mathlib on the search path (required for re-verifying released
prover artifacts; not required for the synthetic corpus).
"""
from __future__ import annotations

import dataclasses
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional


@dataclasses.dataclass
class LeanResult:
    returncode: int
    stdout: str
    stderr: str
    wall_seconds: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class LeanRunner:
    """Invoke `lean` on a file or snippet and capture stdout/stderr.

    Parameters
    ----------
    cwd:
        Working directory. If this points at a lake project, `lean` will see
        that project's `Mathlib` etc. on the search path. If ``None``, runs in
        the system temp directory and the snippet must be self-contained.
    timeout_s:
        Per-invocation wall-clock cap. Anything above this returns rc=124.
    lean_binary:
        Override the `lean` executable. Defaults to whatever `lean` resolves to
        on PATH (i.e. whatever elan has chosen).
    """

    def __init__(
        self,
        cwd: Optional[Path] = None,
        timeout_s: int = 120,
        lean_binary: Optional[str] = None,
    ) -> None:
        self.cwd = Path(cwd) if cwd is not None else None
        self.timeout_s = timeout_s
        self.lean_binary = lean_binary or shutil.which("lean") or "lean"

    def run_file(self, path: Path) -> LeanResult:
        return self._run([str(path)])

    def run_snippet(self, source: str, suffix: str = ".lean") -> LeanResult:
        """Write `source` to a tempfile and elaborate it. Returns the captured output."""
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, dir=self.cwd
        ) as fh:
            fh.write(source)
            tmp = Path(fh.name)
        try:
            return self._run([str(tmp)])
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass

    def _run(self, args: list[str]) -> LeanResult:
        t0 = time.monotonic()
        try:
            cp = subprocess.run(
                [self.lean_binary, *args],
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                cwd=str(self.cwd) if self.cwd else None,
            )
            rc, out, err = cp.returncode, cp.stdout, cp.stderr
        except subprocess.TimeoutExpired as e:
            rc, out, err = 124, e.stdout or "", (e.stderr or "") + "\n[proofgate] timeout"
        return LeanResult(returncode=rc, stdout=out, stderr=err, wall_seconds=time.monotonic() - t0)
