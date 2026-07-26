"""Dimwit — the WANEFALL-specific autonomous asset engine.

A separate variant of the Blunder recursive proof engine, specialized for game ASSET creation,
import, validation, mutation, and human-review packaging. Dimwit inherits Blunder's CONCEPTS
(proof ledger, task queue, mock-before-execute, bounded recursion, fail-closed human gate, lesson
promotion) but keeps ALL of its mutable state separate. Dimwit never writes into Blunder's ledger,
queue, memory, or artifact root.

Stdlib-only. All writes are confined to the Dimwit workspace root.
"""

__all__ = ["core", "engine", "review"]
__role__ = "WANEFALL-specific autonomous asset/build operator"
__canonical_name__ = "Dimwit"
__version__ = "1.0.0-foundation"
