from __future__ import annotations

"""v1.3 referee / foul-incident layer.

This layer replaces the candidate's generic ``severity -> card`` interpretation
with a contextual incident model while leaving frozen v1.2 untouched.

Principles
----------
* the referee has a deterministic match-specific profile, never a team bias;
* foul type and gravity are separate concepts;
* promising-attack / DOGSO context matters;
* persistent infringement and prior warnings matter;
* advantage can be played and a yellow shown at the next stoppage;
* player reactions are attribute-driven and may themselves be sanctioned;
* injuries have match-level grades instead of one undifferentiated boolean;
* public follow-up events are emitted one-by-one so the live ``p`` runner does
  not silently swallow cards, confrontations or medical assessments.
"""

from dataclasses import asdict, dataclass
import hashlib
import random
from typing import Optional

from engine import Band, Event, EventType, Lane, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_substitutions import MatchEngineV13Substitutions


VERSION = (
    "1.3-candidate-spatial-creativity-boldness-determination-offball-body-"
    "defense-marking-cover-communication-offside-overload-errors-chemistry-"
    "adaptation-stability-persistence-knockout-auto-subs-referee"
)


@dataclass
class RefereeProfile:
    style: str
    strictness: float
    contact_tolerance: float
    advantage_tendency: float
    dissent_tolerance: float
    game_management: float
    consistency: float


class MatchEngineV13Referee(MatchEngineV13Substitutions):
    """Contextual referee, discipline, reaction and injury model."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.referee = self._generate_referee_profile()
        self._ref_player_fouls: dict[str, int] = {}
        self._ref_team_fouls: list[int] = [0, 0]
        self._ref_warned_players: set[str] = set()
        self._referee_event_queue: list[Event] = []
        self._deferred_discipline: list[dict] = []
        self._injury_details: dict[str, dict] = {}
        self._last_foul_incident: Optional[dict] = None

    # ------------------------- persistence -------------------------

    @classmethod
    def from_state_dict(cls, data: dict) -> "MatchEngineV13Referee":
        obj = super().from_state_dict(data)
        raw = data.get("referee_profile")
        if isinstance(raw, dict):
            obj.referee = RefereeProfile(**raw)
        else:
            obj.referee = obj._generate_referee_profile()
        obj._ref_player_fouls = {
            str(k): int(v) for k, v in data.get("ref_player_fouls", {}).items()
        }
        team_fouls = list(data.get("ref_team_fouls", [0, 0]))
        obj._ref_team_fouls = [int(team_fouls[0]), int(team_fouls[1])]
        obj._ref_warned_players = set(data.get("ref_warned_players", []))
        obj._referee_event_queue = [
            obj._event_from_dict(ev) for ev in data.get("referee_event_queue", [])
        ]
        obj._deferred_discipline = [dict(row) for row in data.get("deferred_discipline", [])]
        obj._injury_details = {
            str(k): dict(v) for k, v in data.get("injury_details", {}).items()
        }
        obj._last_foul_incident = data.get("last_foul_incident")
        return obj

    def export_state(self) -> dict:
        data = super().export_state()
        data["engine_version"] = VERSION
        data["referee_profile"] = asdict(self.referee)
        data["ref_player_fouls"] = dict(self._ref_player_fouls)
        data["ref_team_fouls"] = list(self._ref_team_fouls)
        data["ref_warned_players"] = sorted(self._ref_warned_players)
        data["referee_event_queue"] = [
            self._event_to_dict(ev) for ev in self._referee_event_queue
        ]
        data["deferred_discipline"] = [dict(row) for row in self._deferred_discipline]
        data["injury_details"] = {k: dict(v) for k, v in self._injury_details.items()}
        data["last_foul_incident"] = self._last_foul_incident
        return data

    # ------------------------- referee identity -------------------------

    def _generate_referee_profile(self) -> RefereeProfile:
        identity = (
            f"v13-referee|{self.seed}|{self.teams[0].team.name}|{self.teams[1].team.name}"
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        rr = random.Random(int(digest[:16], 16))
        strictness = clamp(rr.uniform(0.42, 0.72))
        contact_tolerance = clamp(0.78 - 0.48 * strictness + rr.uniform(-0.08, 0.08), 0.32, 0.68)
        advantage = clamp(rr.uniform(0.42, 0.72))
        dissent_tolerance = clamp(rr.uniform(0.36, 0.72))
        management = clamp(rr.uniform(0.48, 0.84))
        consistency = clamp(rr.uniform(0.62, 0.90))
        if strictness >= 0.62 and contact_tolerance <= 0.50:
            style = "strict"
        elif strictness <= 0.50 and contact_tolerance >= 0.54:
            style = "permissive"
        else:
            style = "balanced"
        return RefereeProfile(
            style=style,
            strictness=strictness,
            contact_tolerance=contact_tolerance,
            advantage_tendency=advantage,
            dissent_tolerance=dissent_tolerance,
            game_management=management,
            consistency=consistency,
        )

    def referee_diagnostic(self) -> dict:
        """RNG-pure public diagnostic for tests/debugging."""
        return {
            **asdict(self.referee),
            "team_fouls": list(self._ref_team_fouls),
            "warned_players": sorted(self._ref_warned_players),
            "deferred_discipline": [dict(row) for row in self._deferred_discipline],
            "injuries": {k: dict(v) for k, v in self._injury_details.items()},
        }

    # ------------------------- foul construction -------------------------

    @staticmethod
    def _foul_key(team: int, player: PlayerState) -> str:
        return f"{int(team)}:{player.player.name}"

    def _select_foul_type(
        self,
        defender: PlayerState,
        attacker: PlayerState,
        zone: Zone,
    ) -> str:
        aggression = defender.effective("aggression") / 100.0
        discipline = defender.effective("discipline") / 100.0
        tackling = defender.effective("tackling") / 100.0
        pace_gap = clamp((attacker.effective("pace") - defender.effective("pace") + 25.0) / 50.0)
        transition = clamp(self.state.transition_boost)
        attacking_zone = 1.0 if zone.band in (Band.ATT, Band.BOX) else 0.0
        items = [
            ("trip", 0.30 + 0.06 * tackling),
            ("holding", 0.13 + 0.16 * pace_gap + 0.12 * transition),
            ("push_charge", 0.13 + 0.07 * defender.effective("strength") / 100.0),
            ("late_tackle", 0.15 + 0.12 * aggression + 0.06 * attacking_zone),
            ("sliding_tackle", 0.10 + 0.10 * tackling + 0.06 * transition),
            (
                "reckless_tackle",
                0.025 + 0.11 * aggression * (1.0 - discipline) + 0.035 * attacking_zone,
            ),
            (
                "elbow_or_forearm",
                0.004
                + 0.022 * aggression * (1.0 - discipline)
                + 0.008 * defender.effective("strength") / 100.0,
            ),
        ]
        return str(weighted_choice(self.rng, items))

    def _build_foul_incident(
        self,
        defending_team: int,
        defender: PlayerState,
        attacker: PlayerState,
        zone: Zone,
        *,
        forced: Optional[dict] = None,
    ) -> dict:
        if forced is not None:
            incident = dict(forced)
            incident.setdefault("type", "trip")
            incident.setdefault("severity", 0.45)
            incident.setdefault("attempt_to_play_ball", incident["type"] not in {"holding", "push_charge", "elbow_or_forearm"})
            incident.setdefault("spa", False)
            incident.setdefault("dogso", False)
            incident.setdefault("violent", incident["type"] == "elbow_or_forearm")
            incident["severity"] = clamp(float(incident["severity"]))
            return incident

        foul_type = self._select_foul_type(defender, attacker, zone)
        aggression = defender.effective("aggression") / 100.0
        discipline = defender.effective("discipline") / 100.0
        strength_delta = clamp(
            (defender.effective("strength") - attacker.effective("strength") + 45.0) / 90.0
        )
        bases = {
            "trip": 0.30,
            "holding": 0.24,
            "push_charge": 0.32,
            "late_tackle": 0.43,
            "sliding_tackle": 0.46,
            "reckless_tackle": 0.65,
            "elbow_or_forearm": 0.72,
        }
        severity = clamp(
            bases[foul_type]
            + 0.19 * aggression
            - 0.10 * discipline
            + 0.07 * strength_delta
            + (0.035 if zone.band in (Band.ATT, Band.BOX) else 0.0)
            + self.rng.uniform(-0.10, 0.10)
        )
        attempt = foul_type in {"trip", "late_tackle", "sliding_tackle", "reckless_tackle"}
        transition = clamp(self.state.transition_boost)
        pace_edge = clamp((attacker.effective("pace") - defender.effective("pace") + 20.0) / 45.0)
        attack_quality = clamp(
            0.42 * attacker.effective("off_ball") / 100.0
            + 0.32 * attacker.effective("pace") / 100.0
            + 0.26 * attacker.effective("composure") / 100.0
        )
        spa_score = (
            0.28
            + 0.30 * transition
            + 0.17 * pace_edge
            + 0.14 * attack_quality
            + (0.12 if zone.band == Band.ATT else 0.04 if zone.band == Band.MID else -0.18)
        )
        spa = bool(spa_score >= 0.63 or (foul_type == "holding" and zone.band == Band.ATT))
        central = zone.lane == Lane.CENTER
        dogso_score = (
            0.30 * attack_quality
            + 0.22 * pace_edge
            + 0.21 * transition
            + (0.28 if zone.band == Band.BOX else 0.18 if zone.band == Band.ATT else -0.15)
            + (0.08 if central else -0.04)
            - 0.16 * defender.effective("positioning") / 100.0
        )
        dogso = bool(dogso_score >= 0.63)
        return {
            "type": foul_type,
            "severity": severity,
            "attempt_to_play_ball": attempt,
            "spa": spa,
            "dogso": dogso,
            "violent": foul_type == "elbow_or_forearm" and severity >= 0.73,
        }

    # ------------------------- discipline -------------------------

    def _card_probabilities(
        self,
        defending_team: int,
        defender: PlayerState,
        incident: dict,
        zone: Zone,
        foul_count_after: int,
    ) -> dict:
        severity = float(incident["severity"])
        aggression = defender.effective("aggression") / 100.0
        discipline = defender.effective("discipline") / 100.0
        persistent = clamp((foul_count_after - 1) / 3.0)
        warned = self._foul_key(defending_team, defender) in self._ref_warned_players
        strict = self.referee.strictness
        tolerance = self.referee.contact_tolerance

        # More consistent referees have less incident-to-incident threshold noise.
        noise_width = 0.10 * (1.0 - self.referee.consistency)
        judgment_noise = self.rng.uniform(-noise_width, noise_width)

        yellow_signal = (
            0.02
            + 0.50 * severity
            + 0.16 * float(bool(incident.get("spa")))
            + 0.17 * persistent
            + 0.09 * float(warned)
            + 0.11 * aggression
            - 0.09 * discipline
            + 0.18 * (strict - 0.50)
            + 0.12 * (0.52 - tolerance)
            + judgment_noise
        )
        if incident.get("type") == "holding" and incident.get("spa"):
            yellow_signal += 0.10
        yellow_p = clamp(yellow_signal - 0.20, 0.015, 0.88)

        red_signal = (
            0.002
            + 0.80 * max(0.0, severity - 0.68)
            + 0.28 * float(bool(incident.get("violent")))
            + 0.23 * float(bool(incident.get("dogso")))
            + 0.05 * aggression
            - 0.04 * discipline
            + 0.06 * (strict - 0.50)
        )
        # Penalty-area DOGSO with a genuine attempt to play the ball is normally
        # downgraded relative to non-ball challenges (double-jeopardy principle).
        if zone.band == Band.BOX and incident.get("dogso") and incident.get("attempt_to_play_ball"):
            red_signal -= 0.22
            yellow_p = max(yellow_p, 0.64)
        if incident.get("dogso") and not incident.get("attempt_to_play_ball"):
            red_signal += 0.22
        red_p = clamp(red_signal, 0.001, 0.86)
        return {"yellow": yellow_p, "direct_red": red_p}

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
        if self.rng.random() >= probs["yellow"]:
            return None, probs
        return ("second_yellow_red" if defender.yellow else "yellow"), probs

    def _apply_card_state(self, team: int, player: PlayerState, card: Optional[str]) -> None:
        if card is None:
            return
        if card == "yellow":
            if not player.yellow:
                player.yellow = 1
                self.stats[team].yellow += 1
            return
        if card == "second_yellow_red":
            if not player.yellow:
                player.yellow = 1
            self.stats[team].yellow += 1
            self.stats[team].red += 1
            player.red = True
        elif card == "direct_red":
            self.stats[team].red += 1
            player.red = True
        else:
            raise ValueError(card)
        if player in self.teams[team].on_field:
            self.teams[team].on_field.remove(player)

    def _warning_probability(self, defender: PlayerState, incident: dict, foul_count: int) -> float:
        if foul_count <= 0:
            return 0.0
        severity = float(incident["severity"])
        return clamp(
            0.06
            + 0.30 * self.referee.game_management
            + 0.22 * severity
            + 0.10 * min(1.0, (foul_count - 1) / 2.0)
            + 0.08 * self.referee.strictness
            - 0.18 * self.referee.contact_tolerance,
            0.04,
            0.62,
        )

    # ------------------------- injury -------------------------

    @staticmethod
    def _body_area_for_foul(foul_type: str) -> str:
        if foul_type == "elbow_or_forearm":
            return "head_or_face"
        if foul_type == "push_charge":
            return "upper_body"
        if foul_type == "holding":
            return "soft_tissue"
        if foul_type in {"sliding_tackle", "reckless_tackle", "late_tackle"}:
            return "ankle_knee_or_lower_leg"
        return "lower_leg"

    def _injury_outcome(
        self,
        defender: PlayerState,
        attacker: PlayerState,
        incident: dict,
    ) -> Optional[dict]:
        if not self.config.injuries_enabled:
            return None
        severity = float(incident["severity"])
        foul_type = str(incident["type"])
        strength_mismatch = clamp(
            (defender.effective("strength") - attacker.effective("strength") + 40.0) / 80.0
        )
        type_risk = {
            "holding": -0.004,
            "trip": 0.000,
            "push_charge": 0.003,
            "late_tackle": 0.006,
            "sliding_tackle": 0.008,
            "reckless_tackle": 0.018,
            "elbow_or_forearm": 0.015,
        }[foul_type]
        injury_p = clamp(
            0.0015
            + 0.038 * max(0.0, severity - 0.40)
            + type_risk
            + 0.006 * max(0.0, strength_mismatch - 0.55),
            0.0008,
            0.060,
        )
        if self.rng.random() >= injury_p:
            return None

        impact = clamp(
            0.58 * severity
            + 0.20 * strength_mismatch
            + (0.14 if foul_type in {"reckless_tackle", "elbow_or_forearm"} else 0.0)
            + self.rng.uniform(-0.10, 0.10)
        )
        if impact < 0.47:
            grade = "knock"
            attacker.energy = max(0.18, attacker.energy - 0.035)
            forced_off = False
        elif impact < 0.63:
            grade = "minor"
            attacker.energy = max(0.18, attacker.energy - 0.075)
            forced_off = False
        elif impact < 0.80:
            grade = "moderate"
            attacker.energy = max(0.18, attacker.energy - 0.10)
            attacker.injured = True
            forced_off = True
        else:
            grade = "severe"
            attacker.energy = max(0.18, attacker.energy - 0.14)
            attacker.injured = True
            forced_off = True
        return {
            "grade": grade,
            "body_area": self._body_area_for_foul(foul_type),
            "impact": round(impact, 4),
            "probability": round(injury_p, 4),
            "forced_off": forced_off,
        }

    # ------------------------- advantage -------------------------

    def _advantage_probability(
        self,
        attacking_team: int,
        attacker: PlayerState,
        zone: Zone,
        incident: dict,
        card: Optional[str],
        injury: Optional[dict],
    ) -> float:
        if zone.band in {Band.DEF, Band.BOX}:
            return 0.0
        if card in {"direct_red", "second_yellow_red"}:
            return 0.0
        if injury and injury.get("grade") in {"moderate", "severe"}:
            return 0.0
        severity = float(incident["severity"])
        if severity >= 0.82:
            return 0.0
        transition = clamp(self.state.transition_boost)
        zone_bonus = 0.20 if zone.band == Band.ATT else 0.06
        composure = attacker.effective("composure") / 100.0
        return clamp(
            0.05
            + 0.48 * self.referee.advantage_tendency
            + 0.22 * transition
            + zone_bonus
            + 0.08 * composure
            - 0.34 * severity,
            0.0,
            0.82,
        )

    # ------------------------- reactions -------------------------

    def _reaction_outcome(
        self,
        attacking_team: int,
        attacker: PlayerState,
        defending_team: int,
        defender: PlayerState,
        incident: dict,
    ) -> Optional[dict]:
        severity = float(incident["severity"])
        victim_aggression = attacker.effective("aggression") / 100.0
        victim_composure = attacker.effective("composure") / 100.0
        victim_determination = getattr(attacker.player, "determination", 50.0) / 100.0
        react_p = clamp(
            -0.05
            + 0.46 * severity
            + 0.22 * victim_aggression
            + 0.10 * victim_determination
            - 0.20 * victim_composure,
            0.02,
            0.62,
        )
        if self.rng.random() >= react_p:
            return None

        confrontation_drive = clamp(
            0.48 * victim_aggression
            + 0.30 * severity
            + 0.12 * victim_determination
            - 0.26 * victim_composure
        )
        if confrontation_drive >= 0.62 and self.rng.random() < confrontation_drive:
            reaction = "shove" if severity >= 0.72 and self.rng.random() < 0.24 else "confront"
        elif victim_composure >= 0.72:
            reaction = "appeal_to_referee"
        else:
            reaction = "verbal_protest"

        defender_discipline = defender.effective("discipline") / 100.0
        defender_aggression = defender.effective("aggression") / 100.0
        if defender_discipline >= 0.78 and self.rng.random() < 0.58:
            aggressor_response = "apology_or_deescalation"
        elif defender_aggression >= 0.78 and self.rng.random() < 0.40:
            aggressor_response = "confronts_back"
        else:
            aggressor_response = "walks_away"

        mass_p = 0.0
        if reaction in {"confront", "shove"} or aggressor_response == "confronts_back":
            mass_p = clamp(0.05 + 0.26 * severity + 0.12 * victim_aggression + 0.10 * defender_aggression)
        mass_confrontation = self.rng.random() < mass_p

        sanctions: list[dict] = []
        dissent_pressure = 1.0 - self.referee.dissent_tolerance
        if reaction in {"verbal_protest", "appeal_to_referee"}:
            dissent_yellow_p = clamp(
                0.015 + 0.16 * dissent_pressure + 0.08 * victim_aggression - 0.08 * victim_composure,
                0.005,
                0.24,
            )
            if self.rng.random() < dissent_yellow_p:
                sanctions.append({"team": attacking_team, "player": attacker, "reason": "dissent", "card": "yellow"})
        elif reaction == "confront":
            if self.rng.random() < clamp(0.14 + 0.20 * dissent_pressure + 0.10 * severity, 0.08, 0.42):
                sanctions.append({"team": attacking_team, "player": attacker, "reason": "confrontation", "card": "yellow"})
        elif reaction == "shove":
            retaliation_red_p = clamp(0.02 + 0.16 * victim_aggression + 0.12 * severity - 0.10 * victim_composure, 0.01, 0.25)
            sanctions.append(
                {
                    "team": attacking_team,
                    "player": attacker,
                    "reason": "retaliation",
                    "card": "direct_red" if self.rng.random() < retaliation_red_p else "yellow",
                }
            )

        if aggressor_response == "confronts_back" and not defender.red:
            if self.rng.random() < clamp(0.12 + 0.20 * dissent_pressure + 0.10 * defender_aggression, 0.06, 0.40):
                sanctions.append({"team": defending_team, "player": defender, "reason": "confrontation", "card": "yellow"})

        return {
            "reaction": reaction,
            "aggressor_response": aggressor_response,
            "mass_confrontation": mass_confrontation,
            "sanctions": sanctions,
        }

    def _apply_reaction_sanctions(self, sanctions: list[dict]) -> list[dict]:
        applied: list[dict] = []
        for row in sanctions:
            team = int(row["team"])
            player: PlayerState = row["player"]
            proposed = str(row["card"])
            if player.red:
                continue
            if proposed == "yellow" and player.yellow:
                actual = "second_yellow_red"
            else:
                actual = proposed
            self._apply_card_state(team, player, actual)
            applied.append(
                {
                    "team": team,
                    "player": player.player.name,
                    "card": actual,
                    "reason": str(row["reason"]),
                }
            )
        return applied

    # ------------------------- event orchestration -------------------------

    def _queue_event(
        self,
        event_type: EventType,
        team: int,
        relevance: int,
        text_key: str,
        **data,
    ) -> None:
        self._referee_event_queue.append(
            Event(self.minute, int(team), event_type, int(relevance), text_key, data)
        )

    def _commit_foul(
        self,
        defending_team,
        defender,
        attacker,
        zone,
        *,
        forced_incident: Optional[dict] = None,
    ) -> Event:
        defending_team = int(defending_team)
        attacking_team = 1 - defending_team
        self.stats[defending_team].fouls += 1
        self._ref_team_fouls[defending_team] += 1
        key = self._foul_key(defending_team, defender)
        foul_count = self._ref_player_fouls.get(key, 0) + 1
        self._ref_player_fouls[key] = foul_count

        incident = self._build_foul_incident(
            defending_team, defender, attacker, zone, forced=forced_incident
        )
        card, probabilities = self._decide_card(
            defending_team, defender, incident, zone, foul_count
        )
        injury = self._injury_outcome(defender, attacker, incident)

        advantage_p = self._advantage_probability(
            attacking_team, attacker, zone, incident, card, injury
        )
        advantage = self.rng.random() < advantage_p

        # A red-card offence is never hidden behind advantage in this model.
        self._apply_card_state(defending_team, defender, card)

        warning = False
        if card is None and not advantage and key not in self._ref_warned_players:
            if self.rng.random() < self._warning_probability(defender, incident, foul_count):
                self._ref_warned_players.add(key)
                warning = True

        reaction = None
        reaction_cards: list[dict] = []
        if not advantage:
            reaction = self._reaction_outcome(
                attacking_team, attacker, defending_team, defender, incident
            )
            if reaction is not None:
                reaction_cards = self._apply_reaction_sanctions(reaction["sanctions"])

        incident_public = {
            "type": str(incident["type"]),
            "severity": round(float(incident["severity"]), 4),
            "spa": bool(incident.get("spa")),
            "dogso": bool(incident.get("dogso")),
            "attempt_to_play_ball": bool(incident.get("attempt_to_play_ball")),
            "violent": bool(incident.get("violent")),
        }
        self._last_foul_incident = {
            **incident_public,
            "minute": round(self.minute, 4),
            "defending_team": defending_team,
            "defender": defender.player.name,
            "attacker": attacker.player.name,
            "zone": self._zone_data(zone),
            "card": card,
            "advantage": advantage,
            "warning": warning,
            "foul_count": foul_count,
        }

        if injury is not None:
            injury_key = f"{attacking_team}:{attacker.player.name}"
            self._injury_details[injury_key] = {
                **injury,
                "minute": round(self.minute, 4),
                "caused_by": defender.player.name,
                "foul_type": incident_public["type"],
            }

        common = {
            "fouled": attacker.player.name,
            "defender": defender.player.name,
            "zone": self._zone_data(zone),
            "foul_type": incident_public["type"],
            "severity": incident_public["severity"],
            "spa": incident_public["spa"],
            "dogso": incident_public["dogso"],
            "card": card,
            "warning": warning,
            "injury": None if injury is None else injury["grade"],
            "foul_count": foul_count,
            "referee_style": self.referee.style,
            "yellow_probability": round(probabilities["yellow"], 4),
            "red_probability": round(probabilities["direct_red"], 4),
        }

        if advantage:
            # Yellow state is applied immediately for integrity, but the public
            # card is shown at the next stoppage.
            if card == "yellow":
                self._deferred_discipline.append(
                    {
                        "team": defending_team,
                        "player": defender.player.name,
                        "card": "yellow",
                        "reason": "original_foul",
                        "incident_type": incident_public["type"],
                        "minute_of_foul": round(self.minute, 4),
                    }
                )
            self.state.transition_boost = clamp(self.state.transition_boost + 0.08)
            return self._emit(
                EventType.FOUL,
                attacking_team,
                2 if card or incident_public["spa"] else 1,
                "advantage_played",
                advantage=True,
                advantage_probability=round(advantage_p, 4),
                **common,
            )

        # Stop play and establish the correct restart.
        if zone.band == Band.BOX:
            self.state.restart = "penalty"
            self.state.restart_team = attacking_team
            self.state.restart_zone = Zone(Band.BOX, Lane.CENTER)
            self.state.phase = "restart"
            primary = self._emit(
                EventType.PENALTY,
                attacking_team,
                5,
                "penalty_awarded_contextual",
                advantage=False,
                **common,
            )
        else:
            self.state.restart = "free_kick"
            self.state.restart_team = attacking_team
            self.state.restart_zone = zone
            self.state.transition_boost = 0.0
            self.state.phase = "restart"
            relevance = 4 if card in {"direct_red", "second_yellow_red"} else 3 if card or incident_public["severity"] >= 0.72 else 2 if warning or injury else 1
            primary = self._emit(
                EventType.FOUL,
                attacking_team,
                relevance,
                "foul_incident",
                advantage=False,
                **common,
            )

        # Follow-up public events are deliberately queued rather than silently
        # appended, so each can be surfaced by the live p runner.
        if reaction is not None:
            self._queue_event(
                EventType.INFO,
                attacking_team,
                3 if reaction["mass_confrontation"] else 2,
                "mass_confrontation" if reaction["mass_confrontation"] else "player_reaction_to_foul",
                fouled=attacker.player.name,
                defender=defender.player.name,
                reaction=reaction["reaction"],
                aggressor_response=reaction["aggressor_response"],
                mass_confrontation=bool(reaction["mass_confrontation"]),
            )
        if card is not None:
            self._queue_event(
                EventType.CARD,
                defending_team,
                4 if card != "yellow" else 2,
                "card_shown_contextual",
                player=defender.player.name,
                card=card,
                reason="original_foul",
                foul_type=incident_public["type"],
                persistent_infringement=foul_count >= 3,
                dogso=incident_public["dogso"],
                spa=incident_public["spa"],
            )
        elif warning:
            self._queue_event(
                EventType.INFO,
                defending_team,
                1,
                "referee_warning",
                player=defender.player.name,
                foul_count=foul_count,
                foul_type=incident_public["type"],
            )

        for row in reaction_cards:
            self._queue_event(
                EventType.CARD,
                int(row["team"]),
                4 if row["card"] != "yellow" else 2,
                "card_for_reaction",
                player=row["player"],
                card=row["card"],
                reason=row["reason"],
            )

        if injury is not None:
            self._queue_event(
                EventType.INJURY,
                attacking_team,
                4 if injury["grade"] in {"moderate", "severe"} else 2,
                "medical_assessment",
                player=attacker.player.name,
                caused_by=defender.player.name,
                grade=injury["grade"],
                body_area=injury["body_area"],
                forced_off=bool(injury["forced_off"]),
                impact=injury["impact"],
            )
        return primary

    def _emit_queued_event(self) -> Event:
        event = self._referee_event_queue.pop(0)
        self.state.event_log.append(event)
        return event

    def _emit_deferred_card(self) -> Event:
        row = self._deferred_discipline.pop(0)
        event = Event(
            self.minute,
            int(row["team"]),
            EventType.CARD,
            2,
            "deferred_card_after_advantage",
            dict(row),
        )
        self.state.event_log.append(event)
        return event

    def step(self) -> Event:
        # Immediate foul aftermath always gets surfaced before substitutions or
        # restart resolution.
        if self._referee_event_queue:
            return self._emit_queued_event()

        # A caution deferred by advantage is shown at the next real stoppage.
        if (
            self._deferred_discipline
            and self.state.pending is None
            and not self.state.ended
            and self.state.restart is not None
        ):
            return self._emit_deferred_card()

        return super().step()


MatchEngine = MatchEngineV13Referee

__all__ = ["RefereeProfile", "MatchEngineV13Referee", "MatchEngine", "VERSION"]
