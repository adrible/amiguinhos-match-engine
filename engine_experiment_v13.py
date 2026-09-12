"""Canonical entrypoint for the current v1.3 candidate.

This is intentionally separate from frozen stable_engine.py (v1.2).
"""

from engine_experiment_v13_determination import MatchEngineV13Determination

ENGINE_VERSION = "1.3-candidate"
MatchEngine = MatchEngineV13Determination

__all__ = ["ENGINE_VERSION", "MatchEngine", "MatchEngineV13Determination"]
