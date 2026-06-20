# ProofGate

> Reproducible audit of faithfulness, alignment, and vacuity in state-of-the-art Lean 4 theorem provers.

ProofGate re-verifies released proofs from neural theorem provers under a hardened Lean 4 kernel configuration, and reports a single dimensionless metric — **Faithful-Pass** — that strips out unfaithful, vacuous, and misaligned solutions.

## The four checks

| # | Check | What it catches |
|---|---|---|
| 1 | Kernel-level axiom inspection | `sorry`/`admit` (explicit or hidden), fresh `axiom` declarations, compiler-trust axioms from `native_decide` |
| 2 | Banned-tactic linter | `sorry`, `admit`, bare `apply?`/`exact?`, `decide` on real-typed goals, fresh `axiom` declarations |
| 3 | Negation-counterexample probe | Vacuous statements (tautologies, ex-falso, misformalizations whose negation is also closable) |
| 4 | Alignment score | Informal/formal mismatches (missing hypotheses, swapped quantifiers, type errors that change the problem) |

A single failed check disqualifies the item from Faithful-Pass.

## Quickstart

```bash
pip install -e .
# Validate the pipeline against a synthetic corpus (10 items, ~5 seconds):
python -m proofgate audit-corpus --root corpus --out reports/synthetic.json
```

To audit released artifacts:

```bash
bash scripts/download_artifacts.sh           # ~5 MB total, three provers
bash scripts/setup_lake_projects.sh           # ~3-5 GB per prover, one-time
bash scripts/run_audit.sh                     # ~3-6 h depending on caches
```

## Trusted axiom base

We follow the de facto Lean 4 mathematics convention:

- `propext` (propositional extensionality)
- `Classical.choice` (axiom of choice)
- `Quot.sound`

`Lean.ofReduceBool` and `Lean.trustCompiler` (introduced by `native_decide`) are tracked separately and reported as `pass-with-flag` — sound under the assumption that the user trusts the Lean compiler, but a strictly larger trusted base than the conventional one.

## Citation

If you use ProofGate in academic work, please cite the workshop paper (see `paper/proofgate.pdf`).

## License

MIT.
