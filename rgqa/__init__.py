"""retro-game-qa: deterministic replay tooling for retro-game test artifacts.

The package is deliberately dependency-light: manifest validation uses
jsonschema when available and falls back to a built-in structural check, so the
CI playback path never needs a model or a network.
"""

__all__ = ["manifest", "trace", "symbols", "adapters", "evidence", "runner"]

SCHEMA_VERSION = 1
