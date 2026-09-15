"""Canonical entrypoint for the current v1.3 candidate.

This is intentionally separate from frozen stable_engine.py (v1.2).
"""

from engine_experiment_v13_keeper_crosses import MatchEngineV13KeeperCrosses
from engine_experiment_v13_restarts import MatchEngineV13Restarts
from engine_experiment_v13_rebounds import MatchEngineV13Rebounds
from engine_experiment_v13_injuries import MatchEngineV13Injuries
from engine_experiment_v13_roles import MatchEngineV13Roles

ENGINE_VERSION = "1.3-candidate"
MatchEngine = MatchEngineV13Roles

__all__ = [
    "ENGINE_VERSION",
    "MatchEngine",
    "MatchEngineV13KeeperCrosses",
    "MatchEngineV13Restarts",
    "MatchEngineV13Rebounds",
    "MatchEngineV13Injuries",
    "MatchEngineV13Roles",
]
