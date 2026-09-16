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

        Routine low-severity repeat fouls receive materially more management
        room than SPA, DOGSO, reckless conduct or genuinely hard challenges.
        A second caution remains possible for the same marginal offence, but it
        should be a clearer threshold than a first yellow.  The canonical
        discipline adapter applies an additional guardrail to incidents created
        by the ordinary-contact extension.
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
            # Once booked, players and referees both manage routine marginal
            # repeats.  This acts only on second-caution conversion: first-yellow
            # frequency and all serious-card pathways are left untouched.
            factor *= 0.58
            return clamp(factor, 0.05, 0.30)

        return clamp(factor, 0.10, 0.55)


MatchEngine = MatchEngineV13Referee

__all__ = ["RefereeProfile", "MatchEngineV13Referee", "MatchEngine"]
