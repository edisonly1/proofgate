-- Informal statement: "For every prime p > 2, p is odd."
-- Expected: MISALIGNED — the formal statement drops the `p > 2` hypothesis,
-- producing a false claim (`2` is prime and not odd). A prover that solves this
-- formal version gets credit for solving a different (and false) problem.
theorem misaligned_missing_hyp (p : Nat) (hp : Nat.Prime p) : Odd p := by
  sorry
