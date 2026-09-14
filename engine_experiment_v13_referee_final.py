from __future__ import annotations

"""Final second-yellow threshold refinement for the v1.3 referee model."""

from engine import clamp
from engine_experiment_v13_referee_calibrated import (
    MatchEngineV13Referee as _CalibratedReferee,
    RefereeProfile,
)


class MatchEngineV13Referee(_CalibratedReferee):
    @staticmethod
    def _second_yellow_factor(incident: dict) -> float:
        """Higher practical threshold for a player's dismissal by second caution.

        A marginal repeat trip is not treated as if it carried the same caution
        likelihood as the player's first booking.  SPA, DOGSO, reckless conduct
        and high severity progressively remove that referee-management margin.
        """
        severity = float(incident["severity"])
        factor = 0.22 + 0.24 * severity
        factor += 0.16 * float(bool(incident.get("spa")))
        factor += 0.22 * float(bool(incident.get("dogso")))
        if str(incident.get("type")) in {"reckless_tackle", "elbow_or_forearm"}:
            factor += 0.12
        if severity >= 0.80:
            factor += 0.12
        return clamp(factor, 0.28, 1.0)


MatchEngine = MatchEngineV13Referee

__all__ = ["RefereeProfile", "MatchEngineV13Referee", "MatchEngine"]
