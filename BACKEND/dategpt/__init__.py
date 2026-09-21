"""Core runtime primitives for DateGPT.

The engine deliberately keeps game policy in prompt bundles and scenario packs.
This package provides only stable runtime capabilities: rooted file access,
session workspaces, controls, and per-turn context snapshots.
"""

from .host import RuntimeHost, TurnContext

__all__ = ["RuntimeHost", "TurnContext"]
