from __future__ import annotations

"""Experimental v1.3 layer: complete candidate persistence.

The stable engine already serializes the match, players, tactics, event log and
RNG state.  v1.3 adds persistent relationship/adaptation state that must also
survive a save/restore boundary or a restored match could make a different
next decision despite having the same visible snapshot.

This layer keeps the stable v1.2 format readable.  Old states without a ``v13``
section restore with neutral/default candidate state.
"""

from copy import deepcopy

from engine_experiment_v13_adaptation import MatchEngineV13Adaptation


VERSION = (
    "1.3-candidate-spatial-creativity-boldness-offball-body-defense-"
    "marking-cover-communication-offside-overload-errors-chemistry-"
    "adaptation-persistence"
)
STATE_VERSION = 3


class MatchEngineV13Persistence(MatchEngineV13Adaptation):
    """Candidate engine with JSON-safe v1.3 private-state persistence."""

    def _v13_state_to_dict(self) -> dict:
        pair_store = getattr(self, "_v13_pair_familiarity", None)
        pairs = []
        if isinstance(pair_store, dict):
            for key, value in sorted(pair_store.items(), key=lambda row: row[0]):
                if not isinstance(key, tuple) or len(key) != 3:
                    continue
                team, first, second = key
                pairs.append({
                    "team": int(team),
                    "first": str(first),
                    "second": str(second),
                    "value": float(value),
                })

        history = getattr(self, "_v13_adaptation_history", None)
        adaptation_history = deepcopy(history) if isinstance(history, list) else []

        last_error = getattr(self, "_v13_last_defensive_error", None)
        last_profile = getattr(self, "_v13_last_defensive_error_profile", None)

        return {
            "pair_familiarity": pairs,
            "adaptation_history": adaptation_history,
            # These are diagnostic rather than causal between steps, but keeping
            # them makes save/restore introspection faithful as well.
            "last_defensive_error": deepcopy(last_error) if isinstance(last_error, dict) else None,
            "last_defensive_error_profile": deepcopy(last_profile) if isinstance(last_profile, dict) else None,
        }

    def export_state(self) -> dict:
        data = super().export_state()
        data["version"] = STATE_VERSION
        data["engine_version"] = VERSION
        data["v13"] = self._v13_state_to_dict()
        return data

    @classmethod
    def from_state_dict(cls, data: dict) -> "MatchEngineV13Persistence":
        obj = super().from_state_dict(data)
        candidate = data.get("v13", {})
        if not isinstance(candidate, dict):
            candidate = {}

        pair_store = {}
        rows = candidate.get("pair_familiarity", [])
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    team = int(row["team"])
                    first = str(row["first"])
                    second = str(row["second"])
                    value = float(row["value"])
                except (KeyError, TypeError, ValueError):
                    continue
                pair_store[obj._pair_key(team, first, second)] = value
        obj._v13_pair_familiarity = pair_store

        history = candidate.get("adaptation_history", [])
        obj._v13_adaptation_history = deepcopy(history) if isinstance(history, list) else []

        last_error = candidate.get("last_defensive_error")
        obj._v13_last_defensive_error = deepcopy(last_error) if isinstance(last_error, dict) else None
        last_profile = candidate.get("last_defensive_error_profile")
        obj._v13_last_defensive_error_profile = deepcopy(last_profile) if isinstance(last_profile, dict) else None

        # Error-window draws never span public step() boundaries. Restoring them
        # as inactive prevents a stale diagnostic roll from leaking into the
        # next live action.
        obj._v13_error_window_depth = 0
        obj._v13_error_window_roll = None
        obj._v13_error_window_realized = None
        return obj


MatchEngine = MatchEngineV13Persistence
