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
        """Clear caution grounds are independent of an existing booking.

        Behavioural caution is modelled before contact. Referee management only
        applies to marginal routine contact, not SPA, DOGSO or dangerous acts.
        The source/generator of an incident is not a disciplinary ground.
        """
        severity = float(incident["severity"])
        clear_ground = (
            bool(incident.get("spa")) or bool(incident.get("dogso"))
            or bool(incident.get("violent"))
            or str(incident.get("type")) in {"reckless_tackle", "elbow_or_forearm"}
            or severity >= 0.66
        )
        if clear_ground:
            return 1.0
        return clamp(0.024 + 0.034 * severity, 0.028, 0.050)



MatchEngine = MatchEngineV13Referee

__all__ = ["RefereeProfile", "MatchEngineV13Referee", "MatchEngine"]
