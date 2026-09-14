"""Canonical entrypoint for the current v1.3 candidate.

This is intentionally separate from frozen stable_engine.py (v1.2).
"""

from engine_experiment_v13_adaptation_inertia import MatchEngineV13AdaptationInertia

ENGINE_VERSION = "1.3-candidate"
MatchEngine = MatchEngineV13AdaptationInertia

__all__ = ["ENGINE_VERSION", "MatchEngine", "MatchEngineV13AdaptationInertia"]
