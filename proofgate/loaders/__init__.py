"""Loaders for each prover's released artifact format.

Every loader yields ``ProofItem`` records that the audit pipeline can consume
uniformly. Each prover ships a different format; the differences are:

  - DeepSeek-Prover-V2: one .lean file per problem; theorem name = filename stem.
  - Kimina-Prover-72B: JSONL with {uuid, correct_proof, cot, name}.
  - Goedel-Prover-V2:  JSONL with {name, informal_prefix, formal_statement,
                                   split, lean4_code, problem_id}.

Adding a new prover means writing one ~30 LOC loader; nothing else changes.
"""
from .types import ProofItem
from .deepseek import load_deepseek
from .kimina import load_kimina
from .goedel import load_goedel

__all__ = ["ProofItem", "load_deepseek", "load_kimina", "load_goedel"]
