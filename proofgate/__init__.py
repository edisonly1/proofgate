"""ProofGate: audit faithfulness, alignment, and vacuity of Lean 4 proofs.

The public API is intentionally small. Most users want either
``proofgate audit`` from the CLI or :func:`audit_item` from Python.
"""
from .metric import AuditResult, FaithfulPass, audit_item

__all__ = ["AuditResult", "FaithfulPass", "audit_item"]
__version__ = "0.1.0"
