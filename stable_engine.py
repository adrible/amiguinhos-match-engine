from __future__ import annotations

"""Canonical stable entrypoint for the accepted Match Engine v1.2."""

from engine_experiment_v12 import MatchEngineV12, simulate_full_match_v12

ENGINE_VERSION = "1.2"

MatchEngine = MatchEngineV12
simulate_full_match = simulate_full_match_v12

__all__ = [
    "ENGINE_VERSION",
    "MatchEngine",
    "MatchEngineV12",
    "simulate_full_match",
    "simulate_full_match_v12",
]
