from __future__ import annotations

"""Disciplinary calibration for the v1.3 contextual referee layer.

The first referee implementation correctly introduced incident types, referee
profiles, advantage, warnings, reactions and graded injuries, but an
outcome-blind 100-match diagnostic showed too many dismissals.  This adapter
keeps that architecture while making dismissal thresholds more realistic:
ordinary tactical/late fouls should usually be managed with warnings/yellows;
direct red is concentrated in DOGSO without a ball attempt, violent conduct
and genuinely excessive-force challenges.  A cautioned player also receives a
slightly higher practical threshold for a second yellow on ordinary offences,
while SPA, DOGSO and hard/reckless fouls retain strong sanction pressure.

This is disciplinary calibration only.  It has no access to or dependence on
match result, opponent identity or the official final seed.
"""

from typing import Optional

from engine import Band, Lane, PlayerState, Zone, clamp
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

        # Direct red is deliberately concentrated in genuinely send-off-level
        # conduct rather than being a small generic chance attached to every
        # foul.  Ordinary fouls can still become yellow/second-yellow through
        # the separate caution path.
        red = (
            0.0006
            + 0.34 * max(0.0, severity - 0.75)
            + 0.13 * float(violent)
            + 0.10 * float(dogso)
            + 0.020 * max(0.0, aggression - 0.72)
            - 0.012 * max(0.0, discipline - 0.72)
            + 0.030 * max(0.0, strict - 0.55)
        )
        if dogso and not ball_attempt:
            red += 0.18
        if zone.band == Band.BOX and dogso and ball_attempt:
            red -= 0.13
        if foul_type == "reckless_tackle" and severity >= 0.84:
            red += 0.07
        if foul_type == "elbow_or_forearm" and severity >= 0.78:
            red += 0.09
        red = clamp(red, 0.0004, 0.58)

        # Keep the established yellow logic, with only a modest upper cap. The
        # reduction in red frequency must not turn hard fouls into no-sanction
        # events.
        yellow = clamp(float(base["yellow"]), 0.015, 0.84)
        if severity >= 0.72 or incident.get("spa"):
            yellow = max(yellow, 0.40)
        if foul_type in {"reckless_tackle", "elbow_or_forearm"} and severity >= 0.70:
            yellow = max(yellow, 0.58)
        return {"yellow": yellow, "direct_red": red}

    @staticmethod
    def _second_yellow_factor(incident: dict) -> float:
        """Practical threshold modifier for a player already cautioned.

        Referees tend not to issue a second caution for every marginal repeat
        foul, but a promising-attack stop, DOGSO-level context or reckless
        challenge should erase most of that leniency.
        """
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
            # Hard fouls can provoke a reaction even when the generic reaction
            # draw was calm, but this remains a minority outcome.
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

        # Upgrade some genuinely hard-foul reactions from an appeal/protest to
        # face-to-face confrontation. Physical retaliation remains rare.
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

        # A confrontation may draw teammates, but mass confrontations remain
        # uncommon rather than being a scripted consequence of a hard foul.
        mass_p = clamp(
            0.025
            + 0.16 * max(0.0, severity - 0.68)
            + 0.07 * victim_aggression
            + 0.05 * defender.effective("aggression") / 100.0,
            0.02,
            0.18,
        )
        result["mass_confrontation"] = self.rng.random() < mass_p

        # If an appeal/protest had already generated a dissent caution, discard
        # that label and reassess under the actual confrontation behaviour.
        result["sanctions"] = [
            row for row in result.get("sanctions", []) if row.get("reason") != "dissent"
        ]
        dissent_pressure = 1.0 - self.referee.dissent_tolerance
        if reaction == "shove":
            # Retaliatory physical contact is sanctionable, but not every shove
            # is violent conduct.
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
