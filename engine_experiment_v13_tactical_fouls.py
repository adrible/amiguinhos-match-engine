from __future__ import annotations

"""Conscious tactical fouls and booked-player management for v1.3.

A tactical foul can stop an actually generated dangerous or clearly promising
transition. The choice considers transition danger, coverage, score/minute
context, discipline and existing cautions. It never creates an attacking
chance and never boosts technical attributes.
"""

from copy import deepcopy
import ast
import hashlib
import random

from engine import Band, Event, EventType, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_mental_state import MatchEngineV13MentalState


class MatchEngineV13TacticalFouls(MatchEngineV13MentalState):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._v13_tactical_foul_rng = random.Random(self._tactical_foul_seed())
        self._v13_tactical_fouls = {
            "attempts": [0, 0],
            "committed": [0, 0],
            "cards": [0, 0],
        }

    def _tactical_foul_seed(self) -> int:
        payload = f"{getattr(self, 'seed', None)}|v13-tactical-fouls".encode("utf-8")
        return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")

    def _ensure_tactical_fouls(self) -> dict:
        if not isinstance(getattr(self, "_v13_tactical_fouls", None), dict):
            self._v13_tactical_fouls = {
                "attempts": [0, 0],
                "committed": [0, 0],
                "cards": [0, 0],
            }
        state = self._v13_tactical_fouls
        for key in ("attempts", "committed", "cards"):
            state.setdefault(key, [0, 0])
        if not hasattr(self, "_v13_tactical_foul_rng"):
            self._v13_tactical_foul_rng = random.Random(self._tactical_foul_seed())
        return state

    def tactical_foul_diagnostic(self, team: int | None = None) -> dict:
        state = deepcopy(self._ensure_tactical_fouls())
        if team is None:
            return state
        team = int(team)
        return {key: int(value[team]) for key, value in state.items()}

    def _foul_probability(self, defender, attacker, ctx) -> float:
        base = float(super()._foul_probability(defender, attacker, ctx))
        if not defender.yellow:
            return base
        discipline = clamp(defender.effective("discipline") / 100.0)
        team = self._team_for_player_state(defender)
        if team is None:
            return base * 0.72
        game = self.game_management_diagnostic(team)
        chasing = 1.0 if int(game.get("score_diff", 0)) < 0 else 0.0
        late = clamp(float(game.get("late_factor", 0.0)))
        caution = 0.62 + 0.12 * (1.0 - discipline) + 0.12 * late * chasing
        return clamp(base * caution, 0.006, 0.16)

    def _tactical_foul_candidate(self, defending_team: int, zone: Zone) -> PlayerState:
        candidates = [
            ps for ps in self.teams[int(defending_team)].on_field
            if not ps.red and ps.player.position.upper() != "GK"
        ]
        if not candidates:
            return self._goalkeeper(defending_team)

        def score(ps: PlayerState) -> float:
            pos = ps.player.position.upper()
            positional = {
                "DM": 9.0,
                "CM": 7.0,
                "CB": 6.0,
                "LB": 5.0,
                "RB": 5.0,
                "AM": 2.0,
            }.get(pos, 0.0)
            if zone.lane == Lane.LEFT and pos in {"LB", "CB", "DM"}:
                positional += 2.0
            if zone.lane == Lane.RIGHT and pos in {"RB", "CB", "DM"}:
                positional += 2.0
            yellow_cost = 17.0 if ps.yellow else 0.0
            return (
                0.32 * ps.effective("pace")
                + 0.30 * ps.effective("positioning")
                + 0.22 * ps.effective("tackling")
                + 0.16 * ps.effective("composure")
                + positional
                - yellow_cost
            )

        return max(candidates, key=score)

    def _transition_carrier(self, attacking_team: int, zone: Zone) -> PlayerState:
        """Choose a deterministic likely carrier for a promising transition.

        A non-dangerous turnover does not create a PendingAction, so there is no
        named receiver yet. Selecting the most transition-suited active player
        avoids consuming the main match RNG solely for diagnostic attribution.
        """
        candidates = [
            ps for ps in self.teams[int(attacking_team)].on_field
            if not ps.red and ps.player.position.upper() != "GK"
        ]
        if not candidates:
            return self._goalkeeper(attacking_team)

        def score(ps: PlayerState) -> float:
            pos = ps.player.position.upper()
            role = {
                "ST": 7.0,
                "LW": 6.0,
                "RW": 6.0,
                "AM": 5.0,
                "CM": 2.0,
            }.get(pos, 0.0)
            if zone.lane == Lane.LEFT and pos in {"LW", "LB", "AM"}:
                role += 2.0
            elif zone.lane == Lane.RIGHT and pos in {"RW", "RB", "AM"}:
                role += 2.0
            return (
                0.31 * ps.effective("pace")
                + 0.27 * ps.effective("off_ball")
                + 0.24 * ps.effective("dribbling")
                + 0.18 * ps.effective("anticipation")
                + role
            )

        return max(candidates, key=lambda ps: (score(ps), ps.player.name))

    def _coverage_context(self, defending_team: int, zone: Zone) -> float:
        profile = self._formation_profile(defending_team)
        outfield = int(profile.get("outfield", 10))
        if zone.band in {Band.ATT, Band.BOX}:
            line = float(profile.get("actual_def", 4))
            expected = max(1.0, float(profile.get("def", 4)))
        else:
            line = float(profile.get("actual_mid", 4))
            expected = max(1.0, float(profile.get("mid", 4)))
        numerical = clamp(outfield / 10.0)
        return clamp(0.60 * (line / expected) + 0.40 * numerical, 0.0, 1.2)

    def _tactical_foul_probability(
        self,
        defending_team: int,
        fouler: PlayerState,
        *,
        transition: float,
        zone: Zone,
    ) -> float:
        transition = clamp(float(transition))
        # A cynical foul can target a promising break before it becomes a full
        # engine DANGER event. Weak/ordinary turnovers remain ineligible.
        if transition < 0.52:
            return 0.0
        coverage = self._coverage_context(defending_team, zone)
        game = self.game_management_diagnostic(defending_team)
        diff = int(game.get("score_diff", 0))
        late = clamp(float(game.get("late_factor", 0.0)))
        discipline = clamp(fouler.effective("discipline") / 100.0)
        composure = clamp(fouler.effective("composure") / 100.0)

        context = 0.035
        if diff > 0:
            context += 0.055 + 0.055 * late
        elif diff < 0:
            context -= 0.025 * late
        context += 0.10 * max(0.0, 0.85 - coverage)
        context += 0.09 * max(0.0, transition - 0.52) / 0.48
        context += 0.025 * composure
        context -= 0.055 * discipline
        if fouler.yellow:
            context -= 0.16
        if zone.band == Band.ATT:
            context += 0.035
        elif zone.band == Band.BOX:
            context -= 0.06  # penalty/DOGSO risk makes cynical contact less attractive
        return clamp(context, 0.0, 0.34)

    def _tactical_foul_card(
        self,
        team: int,
        fouler: PlayerState,
        transition: float,
        zone: Zone,
    ) -> str | None:
        discipline = clamp(fouler.effective("discipline") / 100.0)
        severity = clamp((float(transition) - 0.50) / 0.50)
        central_dogso = (
            zone.band in {Band.ATT, Band.BOX}
            and zone.lane == Lane.CENTER
            and float(transition) >= 0.90
        )
        if central_dogso:
            p_red = clamp(0.015 + 0.12 * severity - 0.035 * discipline, 0.005, 0.11)
            if self._v13_tactical_foul_rng.random() < p_red:
                fouler.red = True
                self.stats[team].red += 1
                if fouler in self.teams[team].on_field:
                    self.teams[team].on_field.remove(fouler)
                return "direct_red"

        p_yellow = clamp(0.38 + 0.34 * severity - 0.10 * discipline, 0.28, 0.72)
        if fouler.yellow:
            # Referee management makes the same tactical infringement less
            # likely to become a second caution, while keeping dismissal real.
            p_yellow *= 0.38
        if self._v13_tactical_foul_rng.random() >= p_yellow:
            return None
        if fouler.yellow:
            fouler.red = True
            self.stats[team].yellow += 1
            self.stats[team].red += 1
            if fouler in self.teams[team].on_field:
                self.teams[team].on_field.remove(fouler)
            return "second_yellow_red"
        fouler.yellow = 1
        self.stats[team].yellow += 1
        return "yellow"

    def _transition_event_context(self, event: Event) -> tuple[float, int, PlayerState] | None:
        attacking_team = int(event.team)
        zone = self.state.zone
        if event.type == EventType.DANGER and event.text_key == "dangerous_turnover":
            if self.state.pending is None:
                return None
            transition = clamp(float(event.data.get("transition", self.state.transition_boost)))
            victim = self.teams[attacking_team].by_name(self.state.pending.actor)
            return transition, attacking_team, victim
        if event.type == EventType.TURNOVER and event.text_key == "turnover":
            transition = clamp(float(self.state.transition_boost))
            if transition < 0.52:
                return None
            victim = self._transition_carrier(attacking_team, zone)
            return transition, attacking_team, victim
        return None

    def _convert_transition_to_tactical_foul(
        self,
        event: Event,
        defending_team: int,
    ) -> Event:
        context = self._transition_event_context(event)
        if context is None:
            return event
        transition, attacking_team, victim = context
        zone = self.state.zone
        fouler = self._tactical_foul_candidate(defending_team, zone)
        p_foul = self._tactical_foul_probability(
            defending_team,
            fouler,
            transition=transition,
            zone=zone,
        )
        state = self._ensure_tactical_fouls()
        state["attempts"][defending_team] += 1
        if p_foul <= 0.0 or self._v13_tactical_foul_rng.random() >= p_foul:
            return event

        self.state.pending = None
        self.state.restart = "free_kick"
        self.state.restart_team = attacking_team
        self.state.restart_zone = zone
        self.state.transition_boost = 0.0
        self.state.phase = "restart"
        self.stats[defending_team].fouls += 1
        card = self._tactical_foul_card(defending_team, fouler, transition, zone)
        state["committed"][defending_team] += 1
        if card:
            state["cards"][defending_team] += 1

        event.type = EventType.FOUL
        event.team = attacking_team
        event.relevance = 3 if card else 2
        event.text_key = "tactical_foul_stops_transition"
        event.data = {
            "fouler": fouler.player.name,
            "fouled": victim.player.name,
            "transition": round(transition, 3),
            "zone": self._zone_data(zone),
            "card": card,
            "decision_probability": round(p_foul, 3),
        }
        if card:
            self._record_card_event(defending_team, fouler, card)
        return event

    def _turnover(self, losing_team, actor, zone, reason, ctx, severity=0.5) -> Event:
        event = super()._turnover(losing_team, actor, zone, reason, ctx, severity=severity)
        return self._convert_transition_to_tactical_foul(event, int(losing_team))

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["tactical_fouls"] = self.tactical_foul_diagnostic()
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        data["v13_tactical_fouls"] = deepcopy(self._ensure_tactical_fouls())
        data["v13_tactical_foul_rng_state"] = repr(self._v13_tactical_foul_rng.getstate())
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_tactical_fouls")
        obj._v13_tactical_fouls = deepcopy(raw) if isinstance(raw, dict) else {
            "attempts": [0, 0],
            "committed": [0, 0],
            "cards": [0, 0],
        }
        obj._v13_tactical_foul_rng = random.Random(obj._tactical_foul_seed())
        if data.get("v13_tactical_foul_rng_state"):
            obj._v13_tactical_foul_rng.setstate(ast.literal_eval(data["v13_tactical_foul_rng_state"]))
        obj._ensure_tactical_fouls()
        return obj


MatchEngine = MatchEngineV13TacticalFouls

__all__ = ["MatchEngineV13TacticalFouls", "MatchEngine"]