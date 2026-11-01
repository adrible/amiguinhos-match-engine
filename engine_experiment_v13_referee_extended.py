from __future__ import annotations

"""Extended v1.3 refereeing realism.

Adds the remaining referee-adjacent mechanics without touching frozen v1.2:
- second cautions for dissent/confrontation are harder than first cautions;
- contextual handball decisions, including SPA/DOGSO consequences;
- rare simulation/diving attempts and referee detection;
- head-impact / concussion protocol on relevant foul incidents;
- match-temperature memory shared symmetrically by both teams;
- limited VAR intervention only where this layer has an explicit factual basis
  (clear missed handball or a wrongly awarded penalty after simulation).

None of these systems reads team identity, desired result, score target or the
official final seed.  They operate on player attributes and current match state.
"""

from typing import Optional

from engine import Band, Event, EventType, Lane, PendingAction, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_referee_final import (
    MatchEngineV13Referee as _FinalReferee,
    RefereeProfile,
)


VERSION = "1.3-candidate-referee-extended"


class MatchEngineV13RefereeExtended(_FinalReferee):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._match_heat = 0.0
        self._last_heat_minute = self.minute
        self._special_referee_counts = {
            "handball_contacts": 0,
            "handball_offences": 0,
            "simulation_attempts": 0,
            "simulation_detected": 0,
            "simulation_fooled_referee": 0,
            "managed_second_caution": 0,
            "concussion_checks": 0,
            "var_interventions": 0,
        }
        self._review_queue: list[dict] = []

    # ------------------------- persistence / diagnostics -------------------------

    @classmethod
    def from_state_dict(cls, data: dict) -> "MatchEngineV13RefereeExtended":
        obj = super().from_state_dict(data)
        obj._match_heat = float(data.get("match_heat", 0.0))
        obj._last_heat_minute = float(data.get("last_heat_minute", obj.minute))
        counts = data.get("special_referee_counts", {})
        defaults = {
            "handball_contacts": 0,
            "handball_offences": 0,
            "simulation_attempts": 0,
            "simulation_detected": 0,
            "simulation_fooled_referee": 0,
            "managed_second_caution": 0,
            "concussion_checks": 0,
            "var_interventions": 0,
        }
        obj._special_referee_counts = {
            key: int(counts.get(key, value)) for key, value in defaults.items()
        }
        obj._review_queue = [dict(row) for row in data.get("referee_review_queue", [])]
        return obj

    def export_state(self) -> dict:
        data = super().export_state()
        data["engine_version"] = VERSION
        data["match_heat"] = self._match_heat
        data["last_heat_minute"] = self._last_heat_minute
        data["special_referee_counts"] = dict(self._special_referee_counts)
        data["referee_review_queue"] = [dict(row) for row in self._review_queue]
        return data

    def referee_diagnostic(self) -> dict:
        data = super().referee_diagnostic()
        data["match_heat"] = round(self._match_heat, 4)
        data["special_counts"] = dict(self._special_referee_counts)
        data["pending_reviews"] = len(self._review_queue)
        return data

    # ------------------------- second-caution management -------------------------

    @staticmethod
    def _second_behavior_yellow_factor(reason: str) -> float:
        """Second cautions for behaviour require a clearer threshold.

        A booked player is not immune, but ordinary dissent receives materially
        more referee-management margin than a first caution. Physical retaliation
        remains the least protected behaviour.
        """
        return {
            "dissent": 0.34,
            "confrontation": 0.52,
            "simulation": 0.44,
            "retaliation": 0.76,
        }.get(str(reason), 0.48)

    def _apply_reaction_sanctions(self, sanctions: list[dict]) -> list[dict]:
        applied: list[dict] = []
        for row in sanctions:
            team = int(row["team"])
            player: PlayerState = row["player"]
            proposed = str(row["card"])
            reason = str(row["reason"])
            if player.red:
                continue

            actual = proposed
            if proposed == "yellow" and player.yellow:
                if self.rng.random() >= self._second_behavior_yellow_factor(reason):
                    self._special_referee_counts["managed_second_caution"] += 1
                    continue
                actual = "second_yellow_red"

            self._apply_card_state(team, player, actual)
            applied.append(
                {
                    "team": team,
                    "player": player.player.name,
                    "card": actual,
                    "reason": reason,
                }
            )
        return applied

    def _apply_unsporting_caution(
        self,
        team: int,
        player: PlayerState,
        reason: str,
    ) -> Optional[str]:
        if player.red:
            return None
        if not player.yellow:
            self._apply_card_state(team, player, "yellow")
            return "yellow"
        if self.rng.random() < self._second_behavior_yellow_factor(reason):
            self._apply_card_state(team, player, "second_yellow_red")
            return "second_yellow_red"
        self._special_referee_counts["managed_second_caution"] += 1
        return None

    # ------------------------- match temperature -------------------------

    def _decay_match_heat(self) -> None:
        now = self.minute
        elapsed = max(0.0, now - self._last_heat_minute)
        if elapsed:
            self._match_heat = clamp(self._match_heat - 0.018 * elapsed)
            self._last_heat_minute = now

    def _update_match_heat(self, event: Event) -> None:
        self._decay_match_heat()
        add = 0.0
        if event.type in {EventType.FOUL, EventType.PENALTY}:
            severity = float(event.data.get("severity", 0.0) or 0.0)
            add += 0.025 + 0.10 * max(0.0, severity - 0.55)
        if event.type == EventType.CARD:
            card = str(event.data.get("card", ""))
            add += 0.045 if card == "yellow" else 0.10
        if event.text_key == "mass_confrontation":
            add += 0.16
        elif event.text_key == "player_reaction_to_foul" and event.data.get("reaction") in {"confront", "shove"}:
            add += 0.07
        if event.type == EventType.INJURY and event.data.get("grade") in {"moderate", "severe"}:
            add += 0.04
        self._match_heat = clamp(self._match_heat + add)

    def _card_probabilities(self, defending_team, defender, incident, zone, foul_count_after):
        probs = super()._card_probabilities(
            defending_team, defender, incident, zone, foul_count_after
        )
        heat = self._match_heat
        yellow = clamp(float(probs["yellow"]) + 0.055 * heat, 0.015, 0.86)
        red = float(probs["direct_red"])
        if float(incident.get("severity", 0.0)) >= 0.76:
            red = clamp(red + 0.012 * heat, 0.0004, 0.58)
        return {"yellow": yellow, "direct_red": red}

    def _reaction_outcome(self, attacking_team, attacker, defending_team, defender, incident):
        result = super()._reaction_outcome(
            attacking_team, attacker, defending_team, defender, incident
        )
        heat = self._match_heat
        severity = float(incident.get("severity", 0.0))
        if result is None and heat >= 0.58 and severity >= 0.48:
            extra = clamp(0.035 + 0.10 * heat + 0.05 * max(0.0, severity - 0.55), 0.03, 0.16)
            if self.rng.random() < extra:
                result = {
                    "reaction": "verbal_protest",
                    "aggressor_response": "walks_away",
                    "mass_confrontation": False,
                    "sanctions": [],
                }
        elif result is not None and not result.get("mass_confrontation") and heat >= 0.70:
            if result.get("reaction") in {"confront", "shove"} and self.rng.random() < 0.08 * heat:
                result["mass_confrontation"] = True
        return result

    # ------------------------- concussion / head checks -------------------------

    def _injury_outcome(self, defender, attacker, incident):
        result = super()._injury_outcome(defender, attacker, incident)
        foul_type = str(incident.get("type", ""))
        if foul_type != "elbow_or_forearm":
            return result

        severity = float(incident.get("severity", 0.0))
        head_check_p = clamp(0.12 + 0.48 * severity, 0.16, 0.62)
        if result is None:
            if self.rng.random() >= head_check_p:
                return None
            self._special_referee_counts["concussion_checks"] += 1
            return {
                "grade": "head_check",
                "body_area": "head_or_face",
                "impact": round(clamp(0.45 + 0.42 * severity), 4),
                "probability": round(head_check_p, 4),
                "forced_off": False,
                "concussion_protocol": True,
                "suspected_concussion": False,
            }

        if result.get("body_area") != "head_or_face":
            return result

        self._special_referee_counts["concussion_checks"] += 1
        impact = float(result.get("impact", severity))
        suspected_p = clamp(
            0.05 + 0.34 * max(0.0, impact - 0.55) + 0.20 * max(0.0, severity - 0.72),
            0.03,
            0.32,
        )
        suspected = self.rng.random() < suspected_p
        result["concussion_protocol"] = True
        result["suspected_concussion"] = suspected
        if suspected:
            result["grade"] = "moderate"
            result["forced_off"] = True
            attacker.injured = True
            attacker.energy = max(0.18, attacker.energy - 0.08)
        return result

    # ------------------------- handball -------------------------

    def _handball_contact_probability(self, pending: PendingAction, defender: PlayerState) -> float:
        if pending.kind != "shoot":
            return 0.0
        origin_bonus = 0.0055 if pending.origin in {"cross", "cutback", "corner", "free_kick"} else 0.0015
        box_bonus = 0.0030 if pending.zone.band == Band.BOX else 0.0005
        positioning = defender.effective("positioning") / 100.0
        discipline = defender.effective("discipline") / 100.0
        return clamp(
            0.0012
            + origin_bonus
            + box_bonus
            + 0.0035 * (1.0 - positioning)
            + 0.0025 * (1.0 - discipline)
            + 0.0020 * clamp(pending.pressure),
            0.0008,
            0.018,
        )

    def _build_handball_incident(
        self,
        pending: PendingAction,
        defender: PlayerState,
        *,
        forced: Optional[dict] = None,
    ) -> dict:
        if forced is not None:
            incident = dict(forced)
            incident.setdefault("arm_position", "extended")
            incident.setdefault("movement_to_ball", False)
            incident.setdefault("offence", True)
            incident.setdefault("certainty", 0.82)
            incident.setdefault("spa", pending.danger >= 0.58)
            incident.setdefault("dogso", pending.danger >= 0.84)
            return incident

        discipline = defender.effective("discipline") / 100.0
        positioning = defender.effective("positioning") / 100.0
        arm_position = weighted_choice(
            self.rng,
            [
                ("supporting_arm", 0.17 + 0.05 * positioning),
                ("natural", 0.43 + 0.08 * discipline),
                ("extended", 0.26 + 0.09 * (1.0 - discipline)),
                ("above_shoulder", 0.07 + 0.06 * (1.0 - discipline)),
            ],
        )
        movement_p = clamp(0.03 + 0.12 * (1.0 - discipline) + 0.04 * pending.danger, 0.03, 0.18)
        movement = self.rng.random() < movement_p
        offence = arm_position in {"extended", "above_shoulder"} or movement
        certainty = {
            "supporting_arm": 0.22,
            "natural": 0.40,
            "extended": 0.78,
            "above_shoulder": 0.91,
        }[str(arm_position)]
        if movement:
            certainty = max(certainty, 0.82)
        spa = bool(pending.danger >= 0.60)
        dogso = bool(pending.danger >= 0.86 and pending.zone.band == Band.BOX)
        return {
            "arm_position": str(arm_position),
            "movement_to_ball": movement,
            "offence": offence,
            "certainty": round(certainty, 4),
            "spa": spa,
            "dogso": dogso,
        }

    def _handball_referee_call_probability(self, incident: dict) -> float:
        certainty = float(incident["certainty"])
        return clamp(
            0.30
            + 0.40 * self.referee.consistency
            + 0.10 * self.referee.strictness
            - 0.06 * self.referee.contact_tolerance
            + 0.18 * (certainty - 0.50),
            0.42,
            0.94,
        )

    def _handball_card(self, team: int, defender: PlayerState, incident: dict) -> Optional[str]:
        if incident.get("dogso"):
            self._apply_card_state(team, defender, "direct_red")
            return "direct_red"
        if not incident.get("spa"):
            return None
        first_p = 0.58
        if not defender.yellow:
            if self.rng.random() < first_p:
                self._apply_card_state(team, defender, "yellow")
                return "yellow"
            return None
        pseudo = {
            "type": "handball",
            "severity": 0.58,
            "spa": True,
            "dogso": False,
        }
        if self.rng.random() < first_p * self._second_yellow_factor(pseudo):
            self._apply_card_state(team, defender, "second_yellow_red")
            return "second_yellow_red"
        self._special_referee_counts["managed_second_caution"] += 1
        return None

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
        called = self.rng.random() < called_p if force_referee_call is None else bool(force_referee_call)
        in_box = pending.zone.band == Band.BOX
        certainty = float(incident["certainty"])

        # A clear missed penalty-area handball can be picked up by VAR.
        var_p = clamp(0.20 + 0.52 * self.referee.consistency + 0.20 * max(0.0, certainty - 0.72), 0.0, 0.82)
        var_intervenes = (
            in_box and not called and certainty >= 0.76 and
            (self.rng.random() < var_p if force_var_intervention is None else bool(force_var_intervention))
        )

        self.state.pending = None
        self.state.transition_boost = 0.0
        self.state.phase = "restart"

        if not called and not var_intervenes:
            # No whistle/intervention: let the original attacking action resolve.
            return None

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

    # ------------------------- simulation -------------------------

    def _simulation_probability(self, actor: PlayerState, pending: PendingAction) -> float:
        if pending.kind != "dribble" or pending.zone.band not in {Band.ATT, Band.BOX}:
            return 0.0
        discipline = actor.effective("discipline") / 100.0
        composure = actor.effective("composure") / 100.0
        boldness = float(getattr(actor.player, "boldness", 50.0)) / 100.0
        score_diff = self.stats[pending.team].goals - self.stats[1 - pending.team].goals
        late_need = 1.0 if self.minute >= 70.0 and score_diff <= 0 else 0.0
        return clamp(
            0.0008
            + 0.0085 * (1.0 - discipline)
            + 0.0035 * boldness
            + 0.0025 * (1.0 - composure)
            + 0.0035 * float(pending.zone.band == Band.BOX)
            + 0.0020 * late_need,
            0.0005,
            0.022,
        )

    def _commit_simulation(
        self,
        pending: PendingAction,
        actor: PlayerState,
        *,
        force_detected: Optional[bool] = None,
        force_fooled: Optional[bool] = None,
        force_var_overturn: Optional[bool] = None,
    ) -> Event:
        self._special_referee_counts["simulation_attempts"] += 1
        attacking_team = int(pending.team)
        defending_team = 1 - attacking_team
        detection_p = clamp(
            0.38 + 0.34 * self.referee.consistency + 0.12 * self.referee.game_management,
            0.48,
            0.82,
        )
        detected = self.rng.random() < detection_p if force_detected is None else bool(force_detected)
        fooled_p = clamp(
            0.04
            + 0.18 * (1.0 - self.referee.consistency)
            + 0.08 * (1.0 - self.referee.game_management),
            0.03,
            0.18,
        )
        fooled = False if detected else (
            self.rng.random() < fooled_p if force_fooled is None else bool(force_fooled)
        )

        self.state.pending = None
        self.state.transition_boost = 0.0
        self.state.phase = "restart"

        if detected:
            self._special_referee_counts["simulation_detected"] += 1
            card = self._apply_unsporting_caution(attacking_team, actor, "simulation")
            self.state.restart = "free_kick"
            self.state.restart_team = defending_team
            self.state.restart_zone = pending.zone.mirror()
            primary = self._emit(
                EventType.FOUL,
                defending_team,
                3 if card else 2,
                "simulation_detected",
                player=actor.player.name,
                card=card,
                detection_probability=round(detection_p, 4),
            )
            if card is not None:
                self._queue_event(
                    EventType.CARD,
                    attacking_team,
                    4 if card != "yellow" else 2,
                    "card_for_simulation",
                    player=actor.player.name,
                    card=card,
                    reason="simulation",
                )
            return primary

        if fooled:
            self._special_referee_counts["simulation_fooled_referee"] += 1
            if pending.zone.band == Band.BOX:
                var_p = clamp(0.44 + 0.40 * self.referee.consistency, 0.58, 0.82)
                var_overturn = (
                    self.rng.random() < var_p
                    if force_var_overturn is None
                    else bool(force_var_overturn)
                )
                if var_overturn:
                    self._special_referee_counts["var_interventions"] += 1
                    self._review_queue.append(
                        {
                            "kind": "overturn_simulation_penalty",
                            "team": attacking_team,
                            "defending_team": defending_team,
                            "player": actor.player.name,
                        }
                    )
                    self.state.restart = None
                    self.state.restart_team = None
                    self.state.restart_zone = None
                else:
                    self.state.restart = "penalty"
                    self.state.restart_team = attacking_team
                    self.state.restart_zone = Zone(Band.BOX, Lane.CENTER)
                return self._emit(
                    EventType.PENALTY,
                    attacking_team,
                    5,
                    "penalty_awarded_after_simulation",
                    player=actor.player.name,
                    var_review_pending=bool(var_overturn),
                )

            self.state.restart = "free_kick"
            self.state.restart_team = attacking_team
            self.state.restart_zone = pending.zone
            return self._emit(
                EventType.FOUL,
                attacking_team,
                2,
                "free_kick_awarded_after_simulation",
                player=actor.player.name,
            )

        # Referee is not fooled but also does not caution: play dies and the
        # defending side takes over without an invented foul.
        self.state.restart = "free_kick"
        self.state.restart_team = defending_team
        self.state.restart_zone = pending.zone.mirror()
        return self._emit(
            EventType.INFO,
            defending_team,
            1,
            "simulation_no_call",
            player=actor.player.name,
        )

    # ------------------------- limited VAR review queue -------------------------

    def _emit_review_resolution(self) -> Event:
        row = self._review_queue.pop(0)
        kind = str(row["kind"])
        if kind == "overturn_simulation_penalty":
            attacking_team = int(row["team"])
            defending_team = int(row["defending_team"])
            player_name = str(row["player"])
            player = self.teams[attacking_team].by_name(player_name)
            card = self._apply_unsporting_caution(attacking_team, player, "simulation")
            self.state.restart = "free_kick"
            self.state.restart_team = defending_team
            self.state.restart_zone = Zone(Band.DEF, Lane.CENTER)
            self.state.phase = "restart"
            event = Event(
                round(self.minute, 2),
                defending_team,
                EventType.INFO,
                5,
                "var_overturns_penalty_simulation",
                {"player": player_name, "card": card},
            )
            self.state.event_log.append(event)
            if card is not None:
                self._queue_event(
                    EventType.CARD,
                    attacking_team,
                    4 if card != "yellow" else 2,
                    "card_for_simulation",
                    player=player_name,
                    card=card,
                    reason="simulation",
                )
            return event

        if kind == "award_handball_penalty":
            attacking_team = int(row["team"])
            defending_team = int(row["defending_team"])
            defender_name = str(row["defender"])
            defender = self.teams[defending_team].by_name(defender_name)
            incident = dict(row["incident"])
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

        raise RuntimeError(f"unknown review kind: {kind}")

    # ------------------------- gameplay hook -------------------------

    def _resolve_pending(self) -> Event:
        pending = self.state.pending
        if pending is not None:
            actor = self._named_or_fallback(
                pending.team, pending.actor, role="actor", zone=pending.zone
            )

            # Rare unsporting choice by an attacker in a dribble duel.
            sim_p = self._simulation_probability(actor, pending)
            if sim_p > 0.0 and self.rng.random() < sim_p:
                return self._commit_simulation(pending, actor)

            # Handball is assessed only against a concrete shot/cross-derived
            # dangerous action and a concrete defender.
            if pending.kind == "shoot":
                defender = self._named_or_fallback(
                    1 - pending.team,
                    pending.defender,
                    role="defender",
                    zone=pending.zone,
                )
                contact_p = self._handball_contact_probability(pending, defender)
                if self.rng.random() < contact_p:
                    incident = self._build_handball_incident(pending, defender)
                    event = self._commit_handball(pending, defender, incident)
                    if event is not None:
                        return event
                    # No offence/no call: restore the pending action because the
                    # ordinary resolver still needs to determine the football play.
                    self.state.pending = pending
                    self.state.phase = "normal"

        return super()._resolve_pending()

    def step(self) -> Event:
        if self._review_queue:
            event = self._emit_review_resolution()
        else:
            event = super().step()
        self._update_match_heat(event)
        return event


MatchEngine = MatchEngineV13RefereeExtended

__all__ = [
    "RefereeProfile",
    "MatchEngineV13RefereeExtended",
    "MatchEngine",
    "VERSION",
]
