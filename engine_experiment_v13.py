"""Canonical entrypoint for the current v1.3 candidate.

This is intentionally separate from frozen stable_engine.py (v1.2).
"""

from engine_experiment_v13_errors import MatchEngineV13Errors

ENGINE_VERSION = "1.3-candidate"
MatchEngine = MatchEngineV13Errors

__all__ = ["ENGINE_VERSION", "MatchEngine", "MatchEngineV13Errors"]
