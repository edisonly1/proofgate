"""ProofGate command-line interface.

    proofgate audit deepseek --root <path> --split test --out reports/ds.jsonl
    proofgate audit kimina   --jsonl <path>             --out reports/km.jsonl
    proofgate audit goedel   --jsonl <path>             --out reports/gd.jsonl
    proofgate audit-corpus   --root corpus/             --out reports/corpus.jsonl
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

import click
from tqdm import tqdm

from .kernel.lean_runner import LeanRunner
from .loaders import ProofItem, load_deepseek, load_goedel, load_kimina
from .metric import aggregate, audit_item, write_jsonl
from .report import text_summary


def _run(
    items: Iterable[ProofItem],
    out_path: Path,
    runner: LeanRunner,
    do_vacuity: bool,
    do_alignment: bool,
    limit: int | None,
) -> int:
    items = list(items)
    if limit:
        items = items[:limit]
    results = []
    for item in tqdm(items, desc="auditing"):
        results.append(audit_item(
            item, runner=runner,
            do_vacuity=do_vacuity, do_alignment=do_alignment,
        ))
    write_jsonl(results, out_path)
    fp = aggregate(results)
    click.echo(text_summary(fp, results))
    summary_path = out_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(fp.to_dict(), indent=2))
    click.echo(f"\nWrote per-item report to {out_path}\nWrote summary to {summary_path}")
    return 0


@click.group()
def main() -> None:
    """ProofGate: audit Lean 4 proofs for faithfulness, alignment, vacuity."""


def _shared_opts(f):
    f = click.option("--out", type=click.Path(path_type=Path), required=True)(f)
    f = click.option("--lean-cwd", type=click.Path(exists=True, file_okay=False, path_type=Path), default=None,
                     help="Run lean in this directory (e.g. a lake project that bundles mathlib).")(f)
    f = click.option("--timeout", type=int, default=180, help="Per-file kernel timeout in seconds.")(f)
    f = click.option("--vacuity/--no-vacuity", default=False, help="Run Check 3 (negation probe).")(f)
    f = click.option("--alignment/--no-alignment", default=False, help="Run Check 4 (alignment).")(f)
    f = click.option("--limit", type=int, default=None, help="Audit only the first N items (smoke-test).")(f)
    return f


@main.command()
@click.option("--root", required=True, type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--split", default="test", show_default=True)
@_shared_opts
def deepseek(root, split, out, lean_cwd, timeout, vacuity, alignment, limit):
    """Audit DeepSeek-Prover-V2 released proofs."""
    runner = LeanRunner(cwd=lean_cwd, timeout_s=timeout)
    items = load_deepseek(root, split=split, benchmark=f"miniF2F-{split}")
    sys.exit(_run(items, out, runner, vacuity, alignment, limit))


@main.command()
@click.option("--jsonl", required=True, type=click.Path(exists=True, path_type=Path))
@_shared_opts
def kimina(jsonl, out, lean_cwd, timeout, vacuity, alignment, limit):
    """Audit Kimina-Prover-72B released proofs."""
    runner = LeanRunner(cwd=lean_cwd, timeout_s=timeout)
    items = load_kimina(jsonl)
    sys.exit(_run(items, out, runner, vacuity, alignment, limit))


@main.command()
@click.option("--jsonl", required=True, type=click.Path(exists=True, path_type=Path))
@_shared_opts
def goedel(jsonl, out, lean_cwd, timeout, vacuity, alignment, limit):
    """Audit Goedel-Prover-V2 released proofs."""
    runner = LeanRunner(cwd=lean_cwd, timeout_s=timeout)
    items = load_goedel(jsonl)
    sys.exit(_run(items, out, runner, vacuity, alignment, limit))


@main.command("audit-corpus")
@click.option("--root", required=True, type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--out", required=True, type=click.Path(path_type=Path))
@click.option("--timeout", type=int, default=60)
def audit_corpus(root, out, timeout):
    """Run all 4 checks against the synthetic adversarial corpus and compare to manifest.json."""
    from .corpus_runner import run_corpus
    sys.exit(run_corpus(root, out, timeout))
