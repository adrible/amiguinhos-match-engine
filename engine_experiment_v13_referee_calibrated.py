from __future__ import annotations

"""Disciplinary calibration for the v1.3 contextual referee layer.

Direct dismissal is driven by dismissal-level facts: excessive force, violent
conduct or DOGSO. Referee strictness, aggression and discipline can influence a
credible red-card incident, but cannot by themselves turn a routine low-severity
contact into a straight red. This matters once ordinary foul generation is
realistic: increasing the number of genuine minor fouls must not linearly create
extra straight-red lottery tickets.
"""

from typing import Optional

from engine import Band, PlayerState, Zone, clamp
from engine_experiment_v13_referee_ordering import (
    MatchEngineV13Referee as _OrderingReferee,
    RefereeProfile,
)


class MatchEngineV13Referee(_OrderingReferee):
    """Final v1.3 referee calibration layer."""

    def _card_probabilities(
        self,
        defending_team: int,
        defender: PlayerState,
        incident: dict,
        zone: Zone,
        foul_count_after: int,
    ) -> dict:
        base = super()._card_probabilities(
            defending_team, defender, incident, zone, foul_count_after
        )
        severity = float(incident["severity"])
        aggression = defender.effective("aggression") / 100.0
        discipline = defender.effective("discipline") / 100.0
        strict = self.referee.strictness
        foul_type = str(incident.get("type", "trip"))
        dogso = bool(incident.get("dogso"))
        violent = bool(incident.get("violent"))
        ball_attempt = bool(incident.get("attempt_to_play_ball"))

        # Context can only amplify an incident that already carries a credible
        # dismissal signal. A strict referee should show more reds for serious
        # conduct, not manufacture straight reds from ordinary trips/holds.
        severe_signal = clamp((severity - 0.66) / 0.34)
        dismissal_signal = max(
            severe_signal,
            1.0 if dogso else 0.0,
            1.0 if violent else 0.0,
        )
        context_modifier = dismissal_signal * (
            0.016 * max(0.0, aggression - 0.72)
            - 0.010 * max(0.0, discipline - 0.72)
            + 0.020 * max(0.0, strict - 0.55)
        )
        red = (
            0.00025
            + 0.34 * max(0.0, severity - 0.75)
            + 0.13 * float(violent)
            + 0.10 * float(dogso)
            + context_modifier
        )
        if dogso and not ball_attempt:
            red += 0.18
        # The DOGSO ball-challenge exception never discounts an independent
        # violent-conduct ground for dismissal.
        if zone.band == Band.BOX and dogso and ball_attempt and not violent:
            red -= 0.13
        if foul_type == "reckless_tackle" and severity >= 0.84:
            red += 0.07
        if foul_type == "elbow_or_forearm" and severity >= 0.78:
            red += 0.09
        red = clamp(red, 0.0002, 0.58)

        # Preserve first-yellow behaviour while isolating sanction consistency
        # from population-dependent calibration of overall caution frequency.
        yellow = clamp(float(base["yellow"]), 0.015, 0.84)
        if severity >= 0.72 or incident.get("spa"):
            yellow = max(yellow, 0.40)
        if foul_type in {"reckless_tackle", "elbow_or_forearm"} and severity >= 0.70:
            yellow = max(yellow, 0.58)
        return {"yellow": yellow, "direct_red": red}

    @staticmethod
    def _second_yellow_factor(incident: dict) -> float:
        """Legacy base factor; the final adapter applies the active refinement."""
        severity = float(incident["severity"])
        factor = 0.36 + 0.32 * severity
        factor += 0.18 * float(bool(incident.get("spa")))
        factor += 0.20 * float(bool(incident.get("dogso")))
        if str(incident.get("type")) in {"reckless_tackle", "elbow_or_forearm"}:
            factor += 0.14
        if severity >= 0.80:
            factor += 0.10
        return clamp(factor, 0.44, 1.0)

    def _decide_card(
        self,
        defending_team: int,
        defender: PlayerState,
        incident: dict,
        zone: Zone,
        foul_count_after: int,
    ) -> tuple[Optional[str], dict]:
        probs = self._card_probabilities(
            defending_team, defender, incident, zone, foul_count_after
        )
        if self.config.direct_red_enabled and self.rng.random() < probs["direct_red"]:
            return "direct_red", probs

        yellow_p = float(probs["yellow"])
        if defender.yellow:
            yellow_p *= self._second_yellow_factor(incident)
        if self.rng.random() >= yellow_p:
            return None, {**probs, "effective_yellow": yellow_p}
        return (
            "second_yellow_red" if defender.yellow else "yellow",
            {**probs, "effective_yellow": yellow_p},
        )

    def _hard_foul_reaction_upgrade(
        self,
        attacking_team: int,
        attacker: PlayerState,
        defending_team: int,
        defender: PlayerState,
        incident: dict,
        result: Optional[dict],
    ) -> Optional[dict]:
        severity = float(incident["severity"])
        if severity < 0.67:
            return result

        victim_aggression = attacker.effective("aggression") / 100.0
        victim_composure = attacker.effective("composure") / 100.0
        determination = getattr(attacker.player, "determination", 50.0) / 100.0
        heat = clamp(
            0.05
            + 0.52 * max(0.0, severity - 0.64)
            + 0.20 * victim_aggression
            + 0.08 * determination
            - 0.17 * victim_composure,
            0.03,
            0.42,
        )

        if result is None:
            if self.rng.random() >= heat * 0.65:
                return None
            result = {
                "reaction": "verbal_protest",
                "aggressor_response": "walks_away",
                "mass_confrontation": False,
                "sanctions": [],
            }

        if result["reaction"] not in {"appeal_to_referee", "verbal_protest"}:
            return result
        if self.rng.random() >= heat:
            return result

        shove_p = clamp(
            0.015
            + 0.10 * max(0.0, severity - 0.78)
            + 0.05 * max(0.0, victim_aggression - 0.75)
            - 0.04 * victim_composure,
            0.005,
            0.08,
        )
        reaction = "shove" if self.rng.random() < shove_p else "confront"
        result["reaction"] = reaction

        mass_p = clamp(
            0.025
            + 0.16 * max(0.0, severity - 0.68)
            + 0.07 * victim_aggression
            + 0.05 * defender.effective("aggression") / 100.0,
            0.02,
            0.18,
        )
        result["mass_confrontation"] = self.rng.random() < mass_p
        result["sanctions"] = [
            row for row in result.get("sanctions", []) if row.get("reason") != "dissent"
        ]
        dissent_pressure = 1.0 - self.referee.dissent_tolerance
        if reaction == "shove":
            red_p = clamp(
                0.015
                + 0.08 * max(0.0, severity - 0.78)
                + 0.06 * victim_aggression
                - 0.05 * victim_composure,
                0.005,
                0.12,
            )
            result["sanctions"].append(
                {
                    "team": attacking_team,
                    "player": attacker,
                    "reason": "retaliation",
                    "card": "direct_red" if self.rng.random() < red_p else "yellow",
                }
            )
        else:
            confrontation_yellow_p = clamp(
                0.06
                + 0.10 * dissent_pressure
                + 0.06 * victim_aggression
                + 0.05 * max(0.0, severity - 0.70),
                0.04,
                0.24,
            )
            if self.rng.random() < confrontation_yellow_p:
                result["sanctions"].append(
                    {
                        "team": attacking_team,
                        "player": attacker,
                        "reason": "confrontation",
                        "card": "yellow",
                    }
                )
        return result

    def _reaction_outcome(
        self,
        attacking_team: int,
        attacker: PlayerState,
        defending_team: int,
        defender: PlayerState,
        incident: dict,
    ) -> Optional[dict]:
        result = super()._reaction_outcome(
            attacking_team, attacker, defending_team, defender, incident
        )
        return self._hard_foul_reaction_upgrade(
            attacking_team,
            attacker,
            defending_team,
            defender,
            incident,
            result,
        )


MatchEngine = MatchEngineV13Referee

__all__ = ["RefereeProfile", "MatchEngineV13Referee", "MatchEngine"]
