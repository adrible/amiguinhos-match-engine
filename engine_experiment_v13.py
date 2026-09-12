"""Canonical entrypoint for the current v1.3 candidate.

This is intentionally separate from frozen stable_engine.py (v1.2).
"""

from engine_experiment_v13_communication import MatchEngineV13Communication

ENGINE_VERSION = "1.3-candidate"
MatchEngine = MatchEngineV13Communication

__all__ = ["ENGINE_VERSION", "MatchEngine", "MatchEngineV13Communication"]
