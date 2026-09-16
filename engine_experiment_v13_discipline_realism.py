from __future__ import annotations

"""Disciplinary guardrails for the causal ordinary-contact layer.

The real-match benchmark showed that adding missing ordinary-contact fouls fixed
foul/yellow frequency but exposed too many dismissals.  This adapter is narrow:
it only changes sanctions for incidents explicitly tagged ``ordinary_contact``.
Hard/reckless fouls, DOGSO, violent conduct, tactical fouls and reaction cards
continue through the established referee model unchanged.

The layer does not read benchmark targets, team identity, scoreline or desired
result.  First cautions remain governed by the existing yellow-card model.
"""

from engine import PlayerState, Zone, clamp
from engine_experiment_v13_match_flow_realism import MatchEngineV13MatchFlowRealism

VERSION = "1.3-candidate-discipline-realism"


class MatchEngineV13DisciplineRealism(MatchEngineV13MatchFlowRealism):
    def _card_probabilities(
        self,
        defending_team: int,
        defender: PlayerState,
        incident: dict,
        zone: Zone,
        foul_count_after: int,
    ) -> dict:
        probs = super()._card_probabilities(
            defending_team,
            defender,
            incident,
            zone,
            foul_count_after,
        )
        if not bool(incident.get("ordinary_contact")):
            return probs

        # Ordinary contact in this layer is explicitly bounded to low/moderate
        # severity and never DOGSO/violent.  It should therefore not inherit a
        # meaningful residual direct-red chance merely from aggression or referee
        # strictness.  First-yellow probability is deliberately untouched.
        direct_red = min(float(probs.get("direct_red", 0.0)), 0.0008)
        return {**probs, "direct_red": direct_red}

    def _second_yellow_factor(self, incident: dict) -> float:
        base = float(super()._second_yellow_factor(incident))
        if not bool(incident.get("ordinary_contact")):
            return base

        severity = clamp(float(incident.get("severity", 0.0)))
        spa = bool(incident.get("spa"))

        # A booked player can still be dismissed for a repeat ordinary foul, but
        # the same marginal contact should require a clearer second-caution
        # threshold.  SPA removes much of that management margin.  This changes
        # only the second-caution conversion after a foul has actually occurred.
        if spa:
            factor = base * (0.48 + 0.12 * severity)
            return clamp(factor, 0.055, 0.125)
        factor = base * (0.30 + 0.10 * severity)
        return clamp(factor, 0.030, 0.060)


MatchEngine = MatchEngineV13DisciplineRealism

__all__ = ["MatchEngineV13DisciplineRealism", "MatchEngine", "VERSION"]
