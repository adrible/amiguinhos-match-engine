"""Canonical entrypoint for the current v1.3 candidate.

This is intentionally separate from frozen stable_engine.py (v1.2).
"""

from engine_experiment_v13_keeper_crosses import MatchEngineV13KeeperCrosses
from engine_experiment_v13_restarts import MatchEngineV13Restarts

ENGINE_VERSION = "1.3-candidate"
MatchEngine = MatchEngineV13Restarts

__all__ = [
    "ENGINE_VERSION",
    "MatchEngine",
    "MatchEngineV13KeeperCrosses",
    "MatchEngineV13Restarts",
]
