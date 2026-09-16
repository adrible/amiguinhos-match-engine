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
        """Practical management margin for a player already cautioned.

        Routine low-severity repeat fouls get more management room than SPA,
        DOGSO, reckless conduct or genuinely hard challenges. The canonical
        discipline adapter applies the additional ordinary-contact guardrail.
        """
        severity = float(incident["severity"])
        spa = bool(incident.get("spa"))
        dogso = bool(incident.get("dogso"))
        hard_type = str(incident.get("type")) in {"reckless_tackle", "elbow_or_forearm"}

        factor = 0.05 + 0.14 * severity
        factor += 0.07 * float(spa)
        factor += 0.12 * float(dogso)
        if hard_type:
            factor += 0.07
        if severity >= 0.80:
            factor += 0.05

        if not spa and not dogso and not hard_type and severity < 0.55:
            factor *= 0.82
            return clamp(factor, 0.07, 0.40)

        return clamp(factor, 0.10, 0.55)


MatchEngine = MatchEngineV13Referee

__all__ = ["RefereeProfile", "MatchEngineV13Referee", "MatchEngine"]
