-- Expected: faithful (Classical.choice is in trusted base)
open Classical in
theorem good_classical (p : Prop) : p ∨ ¬ p := em p
#print axioms good_classical
