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

        Routine low/moderate repeat fouls receive materially more management
        room than SPA, DOGSO, reckless conduct or genuinely hard challenges.
        A second caution remains possible for the same ordinary infringement,
        but its threshold is deliberately clearer than the first caution. The
        canonical discipline adapter applies an even narrower conversion route
        to incidents created by the ordinary-contact extension.
        """
        severity = float(incident["severity"])
        spa = bool(incident.get("spa"))
        dogso = bool(incident.get("dogso"))
        hard_type = str(incident.get("type")) in {"reckless_tackle", "elbow_or_forearm"}

        # A routine repeat is managed behaviourally rather than by giving every
        # minor foul another full yellow-card lottery.  SPA retains more sanction
        # pressure, while DOGSO/reckless/hard incidents stay on the serious path.
        if not dogso and not hard_type and severity < 0.66:
            if spa:
                return clamp(0.052 + 0.050 * severity, 0.055, 0.090)
            return clamp(0.024 + 0.034 * severity, 0.028, 0.050)

        factor = 0.05 + 0.14 * severity
        factor += 0.07 * float(spa)
        factor += 0.12 * float(dogso)
        if hard_type:
            factor += 0.07
        if severity >= 0.80:
            factor += 0.05
        return clamp(factor, 0.10, 0.55)


MatchEngine = MatchEngineV13Referee

__all__ = ["RefereeProfile", "MatchEngineV13Referee", "MatchEngine"]
