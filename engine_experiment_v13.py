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
from engine_experiment_v13_stoppage import MatchEngineV13Stoppage
from engine_experiment_v13_clock_behaviour import MatchEngineV13ClockBehaviour
from engine_experiment_v13_mental_state import MatchEngineV13MentalState
from engine_experiment_v13_tactical_fouls import MatchEngineV13TacticalFouls
from engine_experiment_v13_mismatches import MatchEngineV13Mismatches
from engine_experiment_v13_micro_adjustments import MatchEngineV13MicroAdjustments
from engine_experiment_v13_second_balls import MatchEngineV13SecondBalls
from engine_experiment_v13_set_piece_defense import MatchEngineV13SetPieceDefense
from engine_experiment_v13_offensive_communication import MatchEngineV13OffensiveCommunication
from engine_experiment_v13_numerical_advantage import MatchEngineV13NumericalAdvantage
from engine_experiment_v13_load_injuries import MatchEngineV13LoadInjuries
from engine_experiment_v13_gk_one_v_one import MatchEngineV13GoalkeeperOneVOne
from engine_experiment_v13_penalties import MatchEngineV13Penalties
from engine_experiment_v13_match_flow_realism import MatchEngineV13MatchFlowRealism

ENGINE_VERSION = "1.3-candidate"
MatchEngine = MatchEngineV13MatchFlowRealism

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
    "MatchEngineV13Stoppage",
    "MatchEngineV13ClockBehaviour",
    "MatchEngineV13MentalState",
    "MatchEngineV13TacticalFouls",
    "MatchEngineV13Mismatches",
    "MatchEngineV13MicroAdjustments",
    "MatchEngineV13SecondBalls",
    "MatchEngineV13SetPieceDefense",
    "MatchEngineV13OffensiveCommunication",
    "MatchEngineV13NumericalAdvantage",
    "MatchEngineV13LoadInjuries",
    "MatchEngineV13GoalkeeperOneVOne",
    "MatchEngineV13Penalties",
    "MatchEngineV13MatchFlowRealism",
]
