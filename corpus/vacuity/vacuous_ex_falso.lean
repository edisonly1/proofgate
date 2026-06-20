-- Expected: vacuous (hypotheses are unsatisfiable; the statement is provable
-- ex falso and the prover gets credit for "solving" nothing).
theorem vacuous_ex_falso (h : 0 = 1) : 17 = 42 := by
  exact absurd h (by decide)
#print axioms vacuous_ex_falso
