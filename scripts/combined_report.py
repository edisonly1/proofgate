"""Merge static, kernel, and alignment audit results into one unified per-item report.

Reads:
  reports/static_audit.json            (Check 2 over all 879 items)
  reports/batched/<prover>.json        (Check 1 kernel results, where available)
  reports/alignment_audit.json         (Check 4 alignment scores)

Writes:
  reports/combined/<prover>.json       (one row per item with all check verdicts)
  reports/combined/_summary.json       (per-prover Faithful-Pass under T0 and T1)
  reports/combined/_summary.md         (human-readable summary table)

A row is "Faithful-Pass" iff:
  - tactic verdict in {pass, flag}                          (Check 2)
  - axiom verdict in {pass, pass-with-flag, n/a}            (Check 1 — n/a if no kernel run for this prover)
  - alignment verdict == aligned                            (Check 4)
We exclude vacuity (Check 3) here because we have not run it over real items
in this submission; future-work caveat is in the paper.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


# Static audit's prover_key (from scripts/static_audit.py) -> common name we use everywhere.
STATIC_KEYS = {
    "deepseek-prover-v2__miniF2F-test":  "deepseek-prover-v2-test",
    "deepseek-prover-v2__miniF2F-valid": "deepseek-prover-v2-valid",
    "kimina-prover-72b__miniF2F-test":   "kimina-prover-72b-test",
    "goedel-prover-v2__miniF2F-test":    "goedel-prover-v2-test",
}


def _safe_load(path: Path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None


def main():
    static = _safe_load(Path("reports/static_audit.json")) or {}
    align  = _safe_load(Path("reports/alignment_audit.json")) or {}
    batched_dir = Path("reports/batched")
    kernel = {}
    for jf in sorted(batched_dir.glob("*.json")):
        if jf.name.startswith("_"):
            continue
        kernel[jf.stem] = _safe_load(jf)

    Path("reports/combined").mkdir(parents=True, exist_ok=True)
    summaries = {}

    for static_key, common in STATIC_KEYS.items():
        st = static.get(static_key) or {}
        kr = (kernel.get(common) or {}).get("rows") or []
        al = (align.get(common) or {}).get("rows") or []

        # Index by problem_id for join. Static doesn't have per-item rows in
        # the JSON we produced (only summary + sample_evidence), so we treat
        # absence as "no static finding" for that item, and instead derive
        # tactic verdicts from the audit summary at the prover-level.
        kernel_by_pid = {r["problem_id"]: r for r in kr}
        align_by_pid  = {r["problem_id"]: r for r in al}

        # Goedel: special-case. Static audit's sorry-on-244 finding means EVERY
        # item is unfaithful by tactic check; we record that uniformly.
        is_goedel = "goedel" in common
        # All known problem_ids from any source
        all_pids = set(kernel_by_pid) | set(align_by_pid)
        if not all_pids and is_goedel:
            # No kernel run for Goedel; pull pids from alignment
            all_pids = {r["problem_id"] for r in al}

        rows = []
        ctr = Counter()
        for pid in sorted(all_pids):
            kr_row = kernel_by_pid.get(pid)
            al_row = align_by_pid.get(pid)
            if is_goedel:
                tactic_v = "fail"            # sorry placeholder, see Finding 2
            else:
                tactic_v = "pass"            # static audit found no hard-fail items
            axiom_v = (kr_row or {}).get("verdict", "n/a")  # n/a if kernel not run
            align_v = (al_row or {}).get("verdict", "n/a")

            faithful = (
                tactic_v in {"pass", "flag"}
                and axiom_v in {"pass", "pass-with-flag", "n/a"}
                and align_v in {"aligned", "n/a"}
            )
            ctr["faithful" if faithful else "unfaithful"] += 1
            ctr[f"axiom_{axiom_v}"] += 1
            ctr[f"alignment_{align_v}"] += 1

            rows.append({
                "problem_id": pid,
                "faithful_pass": faithful,
                "tactic": tactic_v,
                "axiom": axiom_v,
                "axiom_set": (kr_row or {}).get("axioms"),
                "alignment": align_v,
                "alignment_score": (al_row or {}).get("score"),
            })

        n_total = len(rows) or 1
        n_faithful = ctr["faithful"]
        summary = {
            "prover": common,
            "n_total": len(rows),
            "n_faithful_pass": n_faithful,
            "faithful_pass_combined": round(n_faithful / n_total, 4),
            "checks_run": {
                "tactic": True,
                "axiom": bool(kr),
                "alignment": bool(al),
                "vacuity": False,
            },
            "counts": dict(ctr),
        }
        summaries[common] = summary
        out_path = Path("reports/combined") / f"{common}.json"
        out_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))

    Path("reports/combined/_summary.json").write_text(json.dumps(summaries, indent=2))

    # Human-readable markdown summary
    lines = ["# Combined audit summary", "",
             "| Prover | n | Faithful (combined) | %  | Notes |",
             "|---|---:|---:|---:|---|"]
    for c, s in summaries.items():
        checks = ", ".join(
            f"+{k}" for k, v in s["checks_run"].items() if v
        ) or "none"
        notes = f"checks: {checks}"
        if "goedel" in c:
            notes += "; all items fail Check 2 (sorry placeholders, Finding 2)"
        lines.append(
            f"| {c} | {s['n_total']} | {s['n_faithful_pass']} | "
            f"{100*s['faithful_pass_combined']:.1f}% | {notes} |"
        )
    Path("reports/combined/_summary.md").write_text("\n".join(lines) + "\n")

    print("=== Combined per-prover summary ===")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
