"""Canonical entrypoint for the current v1.3 candidate.

This is intentionally separate from frozen stable_engine.py (v1.2).
"""

from engine_experiment_v13_keeper_crosses import MatchEngineV13KeeperCrosses
from engine_experiment_v13_restarts import MatchEngineV13Restarts
from engine_experiment_v13_rebounds import MatchEngineV13Rebounds
from engine_experiment_v13_injuries import MatchEngineV13Injuries
from engine_experiment_v13_roles import MatchEngineV13Roles
from engine_experiment_v13_corners import MatchEngineV13Corners
from engine_experiment_v13_throwins import MatchEngineV13ThrowIns
from engine_experiment_v13_positions import MatchEngineV13Positions
from engine_experiment_v13_substitution_strategy import MatchEngineV13SubstitutionStrategy
from engine_experiment_v13_rotations import MatchEngineV13Rotations
from engine_experiment_v13_instructions import MatchEngineV13IndividualInstructions
from engine_experiment_v13_ratings import MatchEngineV13Ratings
from engine_experiment_v13_environment import MatchEngineV13Environment
from engine_experiment_v13_game_management import MatchEngineV13GameManagement
from engine_experiment_v13_set_piece_routines import MatchEngineV13SetPieceRoutines
from engine_experiment_v13_leadership import MatchEngineV13Leadership
from engine_experiment_v13_awards import MatchEngineV13Awards
from engine_experiment_v13_tournament import MatchEngineV13TournamentContext

ENGINE_VERSION = "1.3-candidate"
MatchEngine = MatchEngineV13TournamentContext

__all__ = [
    "ENGINE_VERSION",
    "MatchEngine",
    "MatchEngineV13KeeperCrosses",
    "MatchEngineV13Restarts",
    "MatchEngineV13Rebounds",
    "MatchEngineV13Injuries",
    "MatchEngineV13Roles",
    "MatchEngineV13Corners",
    "MatchEngineV13ThrowIns",
    "MatchEngineV13Positions",
    "MatchEngineV13SubstitutionStrategy",
    "MatchEngineV13Rotations",
    "MatchEngineV13IndividualInstructions",
    "MatchEngineV13Ratings",
    "MatchEngineV13Environment",
    "MatchEngineV13GameManagement",
    "MatchEngineV13SetPieceRoutines",
    "MatchEngineV13Leadership",
    "MatchEngineV13Awards",
    "MatchEngineV13TournamentContext",
]
