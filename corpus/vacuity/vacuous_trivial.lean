-- Expected: vacuous (statement is a propositional tautology — negation is
-- discharged by `decide` or `simp`, indicating no real mathematical content).
theorem vacuous_trivial : ∀ n : Nat, n = n := by intro n; rfl
#print axioms vacuous_trivial
