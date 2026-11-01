from __future__ import annotations

"""Disciplinary guardrails for the causal ordinary-contact layer.

This top adapter owns the *additional* sanction management for incidents tagged
``ordinary_contact``. The lower referee layers remain responsible for general
fouls, DOGSO, violent/reckless conduct, tactical fouls and reaction cards. First
cautions are deliberately unchanged; only straight-red
conversion for genuinely marginal contact is constrained.
"""

from engine import PlayerState, Zone
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

        severity = float(incident.get("severity", 0.0))
        dogso = bool(incident.get("dogso"))
        violent = bool(incident.get("violent"))
        if dogso or violent or severity >= 0.66:
            return probs

        # The ordinary-contact generator is bounded to low/moderate incidents.
        # It may still produce a yellow, but cannot gain a meaningful straight-
        # red lottery merely from referee strictness or player aggression.
        direct_red = min(float(probs.get("direct_red", 0.0)), 0.00035)
        return {**probs, "direct_red": direct_red}



MatchEngine = MatchEngineV13DisciplineRealism

__all__ = ["MatchEngineV13DisciplineRealism", "MatchEngine", "VERSION"]
