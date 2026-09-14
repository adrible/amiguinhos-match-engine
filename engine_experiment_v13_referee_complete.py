from __future__ import annotations

"""Integrity adapter for the extended v1.3 referee model.

Keeps special incidents from mutating play when no decision is made, makes a
head/concussion protocol stop play, and counts sanctioned handballs as team
fouls.  Separated as an adapter so the previous referee layers remain auditable.
"""

from typing import Optional

from engine import Band, Event, EventType, Lane, PendingAction, PlayerState, Zone
from engine_experiment_v13_referee_extended import (
    MatchEngineV13RefereeExtended as _ExtendedReferee,
    RefereeProfile,
)


VERSION = "1.3-candidate-referee-complete"


class MatchEngineV13RefereeComplete(_ExtendedReferee):
    def _advantage_probability(
        self,
        attacking_team,
        attacker,
        zone,
        incident,
        card,
        injury,
    ) -> float:
        # Any suspected head impact requiring protocol assessment stops play.
        if injury and injury.get("concussion_protocol"):
            return 0.0
        return super()._advantage_probability(
            attacking_team, attacker, zone, incident, card, injury
        )

    def _record_handball_foul(self, defending_team: int) -> None:
        self.stats[defending_team].fouls += 1
        self._ref_team_fouls[defending_team] += 1

    def _commit_handball(
        self,
        pending: PendingAction,
        defender: PlayerState,
        incident: dict,
        *,
        force_referee_call: Optional[bool] = None,
        force_var_intervention: Optional[bool] = None,
    ) -> Optional[Event]:
        self._special_referee_counts["handball_contacts"] += 1
        if not incident.get("offence"):
            return None
        self._special_referee_counts["handball_offences"] += 1

        attacking_team = int(pending.team)
        defending_team = 1 - attacking_team
        called_p = self._handball_referee_call_probability(incident)
        called = (
            self.rng.random() < called_p
            if force_referee_call is None
            else bool(force_referee_call)
        )
        in_box = pending.zone.band == Band.BOX
        certainty = float(incident["certainty"])
        var_p = min(
            0.82,
            max(
                0.0,
                0.20
                + 0.52 * self.referee.consistency
                + 0.20 * max(0.0, certainty - 0.72),
            ),
        )
        var_intervenes = (
            in_box
            and not called
            and certainty >= 0.76
            and (
                self.rng.random() < var_p
                if force_var_intervention is None
                else bool(force_var_intervention)
            )
        )

        # Crucial invariant: if neither referee nor VAR acts, the football play
        # remains untouched and the ordinary pending-action resolver continues.
        if not called and not var_intervenes:
            return None

        self.state.pending = None
        self.state.transition_boost = 0.0
        self.state.phase = "restart"

        if var_intervenes:
            self._special_referee_counts["var_interventions"] += 1
            self._review_queue.append(
                {
                    "kind": "award_handball_penalty",
                    "team": attacking_team,
                    "defending_team": defending_team,
                    "defender": defender.player.name,
                    "incident": dict(incident),
                }
            )
            self.state.restart = None
            self.state.restart_team = None
            self.state.restart_zone = None
            return self._emit(
                EventType.INFO,
                attacking_team,
                4,
                "var_check_missed_handball",
                defender=defender.player.name,
                certainty=round(certainty, 4),
                arm_position=incident["arm_position"],
            )

        self._record_handball_foul(defending_team)
        card = self._handball_card(defending_team, defender, incident)
        if in_box:
            self.state.restart = "penalty"
            self.state.restart_team = attacking_team
            self.state.restart_zone = Zone(Band.BOX, Lane.CENTER)
            primary = self._emit(
                EventType.PENALTY,
                attacking_team,
                5,
                "penalty_for_handball",
                defender=defender.player.name,
                arm_position=incident["arm_position"],
                movement_to_ball=bool(incident["movement_to_ball"]),
                certainty=round(certainty, 4),
                spa=bool(incident["spa"]),
                dogso=bool(incident["dogso"]),
                card=card,
                foul_type="handball",
            )
        else:
            self.state.restart = "free_kick"
            self.state.restart_team = attacking_team
            self.state.restart_zone = pending.zone
            primary = self._emit(
                EventType.FOUL,
                attacking_team,
                3 if card else 2,
                "handball_offence",
                defender=defender.player.name,
                arm_position=incident["arm_position"],
                movement_to_ball=bool(incident["movement_to_ball"]),
                certainty=round(certainty, 4),
                spa=bool(incident["spa"]),
                dogso=bool(incident["dogso"]),
                card=card,
                foul_type="handball",
            )
        if card is not None:
            self._queue_event(
                EventType.CARD,
                defending_team,
                4 if card != "yellow" else 2,
                "card_for_handball",
                player=defender.player.name,
                card=card,
                reason="handball_dogso" if incident.get("dogso") else "handball_spa",
            )
        return primary

    def _emit_review_resolution(self) -> Event:
        if not self._review_queue or self._review_queue[0].get("kind") != "award_handball_penalty":
            return super()._emit_review_resolution()

        row = self._review_queue.pop(0)
        attacking_team = int(row["team"])
        defending_team = int(row["defending_team"])
        defender_name = str(row["defender"])
        defender = self.teams[defending_team].by_name(defender_name)
        incident = dict(row["incident"])

        self._record_handball_foul(defending_team)
        card = self._handball_card(defending_team, defender, incident)
        self.state.restart = "penalty"
        self.state.restart_team = attacking_team
        self.state.restart_zone = Zone(Band.BOX, Lane.CENTER)
        self.state.phase = "restart"
        event = Event(
            round(self.minute, 2),
            attacking_team,
            EventType.PENALTY,
            5,
            "var_awards_penalty_handball",
            {
                "defender": defender_name,
                "arm_position": incident["arm_position"],
                "card": card,
                "foul_type": "handball",
            },
        )
        self.state.event_log.append(event)
        if card is not None:
            self._queue_event(
                EventType.CARD,
                defending_team,
                4 if card != "yellow" else 2,
                "card_for_handball",
                player=defender_name,
                card=card,
                reason="handball_dogso" if incident.get("dogso") else "handball_spa",
            )
        return event


MatchEngine = MatchEngineV13RefereeComplete

__all__ = [
    "RefereeProfile",
    "MatchEngineV13RefereeComplete",
    "MatchEngine",
    "VERSION",
]
