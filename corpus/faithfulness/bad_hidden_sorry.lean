-- Expected: unfaithful (sorry hidden inside a `have`; outer goal type-checks fine,
-- but #print axioms reveals sorryAx). This is the failure mode the proposal calls
-- "implicit sorry attacks" — common when `apply?`/`exact?` are silently accepted.
theorem bad_hidden_sorry : 2 + 2 = 4 := by
  have h : 0 = 1 := sorry
  exact (by rfl)
#print axioms bad_hidden_sorry
