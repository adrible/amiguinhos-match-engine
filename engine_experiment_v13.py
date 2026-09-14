"""Canonical entrypoint for the current v1.3 candidate.

This is intentionally separate from frozen stable_engine.py (v1.2).
"""

from engine_experiment_v13_collective import MatchEngineV13Collective

ENGINE_VERSION = "1.3-candidate"
MatchEngine = MatchEngineV13Collective

__all__ = ["ENGINE_VERSION", "MatchEngine", "MatchEngineV13Collective"]
