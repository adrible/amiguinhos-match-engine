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

        A second caution remains available, but routine low-severity repeat
        contact gets more management room than SPA, DOGSO, reckless conduct or
        genuinely hard challenges. This is a contextual threshold, not immunity.
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

        # Ordinary-contact expansion creates many real but marginal fouls. A
        # booked defender should manage those contacts more cautiously and the
        # referee normally needs a clearer repeat offence for dismissal.
        ordinary = bool(incident.get("ordinary_contact"))
        if ordinary and not spa and not dogso and not hard_type and severity < 0.60:
            factor *= 0.60
            return clamp(factor, 0.055, 0.30)

        # Other marginal non-SPA repeats also retain a little more management
        # room now that the engine produces a realistic foul population.
        if not spa and not dogso and not hard_type and severity < 0.55:
            factor *= 0.82
            return clamp(factor, 0.07, 0.40)

        return clamp(factor, 0.10, 0.55)


MatchEngine = MatchEngineV13Referee

__all__ = ["RefereeProfile", "MatchEngineV13Referee", "MatchEngine"]
