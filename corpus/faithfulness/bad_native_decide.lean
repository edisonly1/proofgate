-- Expected: linter flag (native_decide introduces Lean.ofReduceBool / Lean.trustCompiler
-- into the axiom set — the kernel trusts the compiled decision procedure rather
-- than re-checking it. Faithful by Check 1's permissive trusted base, but Check 2
-- flags it for review.
theorem bad_native_decide : (List.range 100).length = 100 := by native_decide
#print axioms bad_native_decide
