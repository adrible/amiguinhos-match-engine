from __future__ import annotations

"""Contextual urgency, restart speed and time-wasting for v1.3.

This layer acts only on elapsed time and restart behaviour.  Protecting a
result can make a team consume more dead-ball time; chasing a result makes
restarts quicker.  A meaningful share of deliberate delay is recoverable as
added time, and repeated/excessive delay carries a disciplinary risk.

No finishing, passing, defending or goalkeeper ability is changed here.
"""

from copy import deepcopy
import ast
import hashlib
import random

from engine import Event, EventType, PlayerState, clamp
from engine_experiment_v13_stoppage import MatchEngineV13Stoppage


class MatchEngineV13ClockBehaviour(MatchEngineV13Stoppage):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._v13_clock_behaviour = {
            "last_waste_second": [-9999.0, -9999.0],
            "waste_attempts": [0, 0],
            "waste_cards": [0, 0],
            "skip_next_restart_waste": False,
        }
        self._v13_clock_rng = random.Random(self._clock_seed())

    def _clock_seed(self) -> int:
        payload = f"{getattr(self, 'seed', None)}|v13-clock-behaviour".encode("utf-8")
        return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")

    def _ensure_clock_behaviour(self) -> dict:
        if not isinstance(getattr(self, "_v13_clock_behaviour", None), dict):
            self._v13_clock_behaviour = {
                "last_waste_second": [-9999.0, -9999.0],
                "waste_attempts": [0, 0],
                "waste_cards": [0, 0],
                "skip_next_restart_waste": False,
            }
        state = self._v13_clock_behaviour
        state.setdefault("last_waste_second", [-9999.0, -9999.0])
        state.setdefault("waste_attempts", [0, 0])
        state.setdefault("waste_cards", [0, 0])
        state.setdefault("skip_next_restart_waste", False)
        if not hasattr(self, "_v13_clock_rng"):
            self._v13_clock_rng = random.Random(self._clock_seed())
        return state

    def clock_behaviour_diagnostic(self, team: int) -> dict:
        team = int(team)
        game = self.game_management_diagnostic(team)
        late = clamp(float(game.get("late_factor", 0.0)))
        diff = int(game.get("score_diff", 0))
        protect_comp = clamp(float(game.get("competition_protect_result", 0.0)))
        need_goal = clamp(float(game.get("competition_need_goal", 0.0)))
        composure = clamp(float(game.get("management_composure", 0.5)))

        protect = clamp(
            max(protect_comp, (1.0 if diff > 0 else 0.0) * late)
            * (0.72 + 0.28 * composure)
        )
        chase = clamp(
            max(need_goal, (1.0 if diff < 0 else 0.0) * late)
            * (0.78 + 0.22 * composure)
        )
        state = self._ensure_clock_behaviour()
        return {
            "team": team,
            "protect_intent": protect,
            "chase_intent": chase,
            "restart_urgency": clamp(chase - 0.45 * protect, 0.0, 1.0),
            "time_waste_intent": clamp(protect - 0.55 * chase, 0.0, 1.0),
            "waste_attempts": int(state["waste_attempts"][team]),
            "waste_cards": int(state["waste_cards"][team]),
        }

    @staticmethod
    def _restart_waste_base(kind: str) -> float:
        return {
            "goal_kick": 0.42,
            "free_kick": 0.28,
            "throw_in": 0.24,
            "corner": 0.13,
            "kickoff": 0.08,
        }.get(str(kind), 0.08)

    def _restart_waste_probability(self, team: int, kind: str) -> float:
        diag = self.clock_behaviour_diagnostic(team)
        intent = float(diag["time_waste_intent"])
        if self.minute < 72.0 or intent < 0.20:
            return 0.0
        state = self._ensure_clock_behaviour()
        since = self.state.second - float(state["last_waste_second"][int(team)])
        if since < 95.0:
            return 0.0
        late = clamp((self.minute - 72.0) / 22.0)
        attempts = int(state["waste_attempts"][int(team)])
        repeat_penalty = 1.0 / (1.0 + 0.18 * attempts)
        return clamp(
            self._restart_waste_base(kind)
            * intent
            * (0.55 + 0.45 * late)
            * repeat_penalty,
            0.0,
            0.46,
        )

    def _restart_delay_player(self, team: int, kind: str) -> PlayerState:
        if kind == "goal_kick":
            return self._goalkeeper(team)
        candidates = [ps for ps in self.teams[team].on_field if not ps.red]
        if not candidates:
            return self._goalkeeper(team)
        # A composed player is more likely to manage the restart deliberately.
        return max(
            candidates,
            key=lambda ps: 0.58 * ps.effective("composure") + 0.42 * ps.effective("discipline"),
        )

    def _time_wasting_card(self, team: int, player: PlayerState, intent: float) -> str | None:
        discipline = clamp(player.effective("discipline") / 100.0)
        repeated = int(self._ensure_clock_behaviour()["waste_attempts"][team])
        p = clamp(0.035 + 0.11 * intent + 0.018 * max(0, repeated - 1) - 0.035 * discipline, 0.015, 0.18)
        if player.yellow:
            # Referees generally give an already-booked player more warning for
            # the same delay; a second caution remains possible, not forbidden.
            p *= 0.32
        if self._v13_clock_rng.random() >= p:
            return None
        if player.yellow:
            player.red = True
            self.stats[team].yellow += 1
            self.stats[team].red += 1
            if player in self.teams[team].on_field:
                self.teams[team].on_field.remove(player)
            return "second_yellow_red"
        player.yellow = 1
        self.stats[team].yellow += 1
        return "yellow"

    def _maybe_time_waste_restart(self) -> Event | None:
        if not self.state.restart or self.state.restart_team not in (0, 1):
            return None
        state = self._ensure_clock_behaviour()
        if state.get("skip_next_restart_waste"):
            state["skip_next_restart_waste"] = False
            return None

        team = int(self.state.restart_team)
        kind = str(self.state.restart)
        probability = self._restart_waste_probability(team, kind)
        if probability <= 0.0 or self._v13_clock_rng.random() >= probability:
            return None

        diag = self.clock_behaviour_diagnostic(team)
        intent = float(diag["time_waste_intent"])
        player = self._restart_delay_player(team, kind)
        elapsed = 6.0 + 11.0 * intent
        recoverable = elapsed * (0.58 + 0.18 * intent)

        state["waste_attempts"][team] += 1
        state["last_waste_second"][team] = float(self.state.second)
        state["skip_next_restart_waste"] = True
        card = self._time_wasting_card(team, player, intent)
        if card:
            state["waste_cards"][team] += 1

        self._advance_dead_clock(elapsed, recoverable, reason="deliberate_time_wasting")
        event = self._emit(
            EventType.INFO,
            team,
            2,
            "deliberate_time_wasting",
            player=player.player.name,
            restart=kind,
            elapsed_seconds=round(elapsed, 2),
            recoverable_seconds=round(recoverable, 2),
            intent=round(intent, 3),
            card=card,
            clock_accounted=True,
        )
        if card:
            self._record_card_event(team, player, card)
        return event

    def _keeper_hold_profile(self, event: Event) -> tuple[float, float, int] | None:
        if event.type != EventType.SAVE or event.data.get("shootout"):
            return None
        keeper_team = 1 - int(event.team)
        diag = self.clock_behaviour_diagnostic(keeper_team)
        protect = float(diag["time_waste_intent"])
        chase = float(diag["restart_urgency"])
        if self.minute < 55.0:
            return 2.0, 0.0, keeper_team
        elapsed = clamp(3.2 + 5.8 * protect - 1.7 * chase, 1.5, 9.0)
        recoverable = max(0.0, elapsed - 6.0) * 0.65
        return elapsed, recoverable, keeper_team

    def _apply_clock_for_event(self, event: Event, *, had_pending: bool = False) -> None:
        super()._apply_clock_for_event(event, had_pending=had_pending)
        if event.data.get("keeper_clock_accounted"):
            return
        profile = self._keeper_hold_profile(event)
        if profile is not None:
            elapsed, recoverable, keeper_team = profile
            self._advance_dead_clock(elapsed, recoverable, reason="keeper_holding_ball")
            event.data["keeper_hold_seconds"] = round(elapsed, 2)
            event.data["keeper_hold_recoverable_seconds"] = round(recoverable, 2)
            event.data["keeper_team"] = keeper_team
        event.data["keeper_clock_accounted"] = True

    def step(self) -> Event:
        wasting = self._maybe_time_waste_restart()
        if wasting is not None:
            return wasting
        return super().step()

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["clock_behaviour"] = [
            self.clock_behaviour_diagnostic(0),
            self.clock_behaviour_diagnostic(1),
        ]
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        state = self._ensure_clock_behaviour()
        data["v13_clock_behaviour"] = deepcopy(state)
        data["v13_clock_behaviour_rng_state"] = repr(self._v13_clock_rng.getstate())
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_clock_behaviour")
        obj._v13_clock_behaviour = deepcopy(raw) if isinstance(raw, dict) else {
            "last_waste_second": [-9999.0, -9999.0],
            "waste_attempts": [0, 0],
            "waste_cards": [0, 0],
            "skip_next_restart_waste": False,
        }
        obj._v13_clock_rng = random.Random(obj._clock_seed())
        if data.get("v13_clock_behaviour_rng_state"):
            obj._v13_clock_rng.setstate(ast.literal_eval(data["v13_clock_behaviour_rng_state"]))
        obj._ensure_clock_behaviour()
        return obj


MatchEngine = MatchEngineV13ClockBehaviour

__all__ = ["MatchEngineV13ClockBehaviour", "MatchEngine"]
