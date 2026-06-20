-- Expected: unfaithful (introduces a fresh axiom outside the trusted base)
axiom magic_lemma : ∀ n : Nat, n = n + 1
theorem bad_fresh_axiom : 0 = 1 := magic_lemma 0
#print axioms bad_fresh_axiom
