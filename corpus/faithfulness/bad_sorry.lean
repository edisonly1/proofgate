-- Expected: unfaithful (depends on sorryAx)
theorem bad_sorry : 1 + 1 = 3 := by sorry
#print axioms bad_sorry
