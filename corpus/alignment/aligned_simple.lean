-- Informal statement: "The sum of two even natural numbers is even."
-- Expected: aligned.
theorem aligned_simple (m n : Nat) (hm : ∃ k, m = 2 * k) (hn : ∃ k, n = 2 * k) :
    ∃ k, m + n = 2 * k := by
  obtain ⟨a, ha⟩ := hm
  obtain ⟨b, hb⟩ := hn
  exact ⟨a + b, by subst ha; subst hb; ring_nf⟩
