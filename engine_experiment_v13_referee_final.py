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
        """Practical management margin for a player who is already cautioned.

        A second caution should be materially harder to show than the first for
        an ordinary repeat foul. SPA, DOGSO, reckless conduct and high severity
        progressively remove that management margin, but even a serious
        cautionable offence remains distinct from the direct-red pathway.
        """
        severity = float(incident["severity"])
        factor = 0.05 + 0.14 * severity
        factor += 0.07 * float(bool(incident.get("spa")))
        factor += 0.12 * float(bool(incident.get("dogso")))
        if str(incident.get("type")) in {"reckless_tackle", "elbow_or_forearm"}:
            factor += 0.07
        if severity >= 0.80:
            factor += 0.05

        # Marginal repeats retain substantial referee-management room, while a
        # serious SPA/DOGSO or hard challenge can still produce a dismissal.
        # Direct-red probabilities are intentionally untouched by this layer.
        return clamp(factor, 0.10, 0.55)


MatchEngine = MatchEngineV13Referee

__all__ = ["RefereeProfile", "MatchEngineV13Referee", "MatchEngine"]
