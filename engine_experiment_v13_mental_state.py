from __future__ import annotations

"""Temporary player confidence and pressure state for the v1.3 candidate.

Confidence here is not a hidden technical buff.  It affects willingness to
attempt actions and risk selection; execution still uses the player's ordinary
attributes.  State changes come from events that actually happened and decay
back towards neutral with time.
"""

from copy import deepcopy

from engine import Event, EventType, PlayerState, Zone, clamp
from engine_experiment_v13_clock_behaviour import MatchEngineV13ClockBehaviour


class MatchEngineV13MentalState(MatchEngineV13ClockBehaviour):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._v13_mental_state: dict[str, dict] = {}
        self._ensure_all_mental_rows()

    @staticmethod
    def _mental_key(team: int, name: str) -> str:
        return f"{int(team)}::{name}"

    def _ensure_mental_row(self, team: int, name: str) -> dict:
        if not isinstance(getattr(self, "_v13_mental_state", None), dict):
            self._v13_mental_state = {}
        key = self._mental_key(team, name)
        row = self._v13_mental_state.setdefault(
            key,
            {"confidence": 0.0, "pressure": 0.0, "events": 0},
        )
        row.setdefault("confidence", 0.0)
        row.setdefault("pressure", 0.0)
        row.setdefault("events", 0)
        return row

    def _ensure_all_mental_rows(self) -> None:
        for team, rt in enumerate(self.teams):
            for ps in rt.on_field:
                self._ensure_mental_row(team, ps.player.name)
            for player in rt.bench:
                self._ensure_mental_row(team, player.name)

    def mental_state_diagnostic(self, team: int | None = None) -> dict:
        self._ensure_all_mental_rows()
        if team is None:
            return deepcopy(self._v13_mental_state)
        prefix = f"{int(team)}::"
        return {
            key[len(prefix):]: deepcopy(value)
            for key, value in self._v13_mental_state.items()
            if key.startswith(prefix)
        }

    def _mental_adjust(
        self,
        team: int,
        name: str | None,
        *,
        confidence: float = 0.0,
        pressure: float = 0.0,
    ) -> None:
        if not name:
            return
        row = self._ensure_mental_row(team, str(name))
        row["confidence"] = clamp(
            float(row["confidence"]) + float(confidence),
            -0.45,
            0.45,
        )
        row["pressure"] = clamp(float(row["pressure"]) + float(pressure), 0.0, 1.0)
        row["events"] = int(row.get("events", 0)) + 1

    def _team_for_named_player(self, name: str | None) -> int | None:
        if not name:
            return None
        for team, rt in enumerate(self.teams):
            if any(ps.player.name == name for ps in rt.on_field):
                return team
            if any(player.name == name for player in rt.bench):
                return team
        return None

    def _update_mental_from_event(self, event: Event) -> None:
        if not isinstance(event, Event):
            return
        data = event.data if isinstance(event.data, dict) else {}

        if event.type == EventType.GOAL and not data.get("shootout"):
            scorer = data.get("scorer") or data.get("taker")
            self._mental_adjust(event.team, scorer, confidence=0.16, pressure=-0.05)
            keeper = data.get("keeper")
            keeper_team = self._team_for_named_player(keeper)
            if keeper_team is not None:
                self._mental_adjust(keeper_team, keeper, confidence=-0.035, pressure=0.055)
            return

        if event.type == EventType.SAVE:
            keeper = data.get("keeper")
            keeper_team = self._team_for_named_player(keeper)
            if keeper_team is not None:
                boost = 0.055 if data.get("big_chance") else 0.028
                self._mental_adjust(keeper_team, keeper, confidence=boost, pressure=-0.025)
            shooter = data.get("shooter")
            if shooter:
                drop = -0.055 if data.get("big_chance") else -0.018
                self._mental_adjust(event.team, shooter, confidence=drop, pressure=0.022)
            return

        if event.type in {EventType.MISS, EventType.POST}:
            shooter = data.get("shooter") or data.get("taker")
            drop = -0.075 if data.get("big_chance") else -0.024
            if event.type == EventType.POST:
                drop *= 0.70
            self._mental_adjust(event.team, shooter, confidence=drop, pressure=0.03)
            return

        if event.type == EventType.DANGER:
            creator = data.get("creator")
            receiver = data.get("receiver")
            self._mental_adjust(event.team, creator, confidence=0.022, pressure=-0.008)
            self._mental_adjust(event.team, receiver, confidence=0.010)
            loser = data.get("loser")
            loser_team = self._team_for_named_player(loser)
            if loser_team is not None:
                self._mental_adjust(loser_team, loser, confidence=-0.035, pressure=0.03)
            return

        if event.type == EventType.TURNOVER:
            loser = data.get("loser")
            loser_team = self._team_for_named_player(loser)
            if loser_team is not None:
                self._mental_adjust(loser_team, loser, confidence=-0.018, pressure=0.012)
            return

        if event.type == EventType.CARD:
            player = data.get("player")
            team = self._team_for_named_player(player)
            if team is not None:
                card = str(data.get("card") or "yellow")
                stress = 0.18 if "red" in card else 0.075
                self._mental_adjust(team, player, confidence=-0.025, pressure=stress)
            return

        if event.type == EventType.BLOCK:
            defender = data.get("defender")
            team = self._team_for_named_player(defender)
            if team is not None:
                self._mental_adjust(team, defender, confidence=0.025, pressure=-0.010)

    def _decay_mental_state(self, seconds: float) -> None:
        if seconds <= 0.0:
            return
        self._ensure_all_mental_rows()
        # Confidence has a ~32 minute half-life; acute pressure dissipates
        # faster. Both trends are continuous and deterministic.
        conf_decay = 0.5 ** (float(seconds) / (32.0 * 60.0))
        pressure_decay = 0.5 ** (float(seconds) / (18.0 * 60.0))
        for row in self._v13_mental_state.values():
            row["confidence"] = float(row["confidence"]) * conf_decay
            row["pressure"] = float(row["pressure"]) * pressure_decay

    def _advance_clock(self, seconds: float, possession_team: int):
        result = super()._advance_clock(seconds, possession_team)
        self._decay_mental_state(float(seconds))
        return result

    def _advance_dead_clock(self, elapsed_seconds: float, recoverable_seconds: float, *, reason: str) -> None:
        super()._advance_dead_clock(elapsed_seconds, recoverable_seconds, reason=reason)
        self._decay_mental_state(float(elapsed_seconds))

    def _decision_weights(self, actor: PlayerState, zone: Zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        team = self._team_for_player_state(actor)
        if team is None:
            return items
        row = self._ensure_mental_row(team, actor.player.name)
        confidence = float(row["confidence"])
        pressure = float(row["pressure"])
        assertive = clamp(0.5 + confidence, 0.05, 0.95)

        factors: dict[str, float] = {}

        def mul(action: str, factor: float) -> None:
            factors[action] = factors.get(action, 1.0) * float(factor)

        # Confidence changes willingness, not the chance of executing the same
        # selected action successfully.
        risk_signal = confidence - 0.42 * pressure
        for action, scale in {
            "safe_pass": -0.08,
            "progressive_pass": 0.07,
            "through_ball": 0.08,
            "dribble": 0.085,
            "carry": 0.045,
            "shoot": 0.075,
            "cross": 0.035,
        }.items():
            mul(action, 1.0 + scale * risk_signal)

        if pressure > 0.0:
            mul("safe_pass", 1.0 + 0.045 * pressure)
            mul("dribble", 1.0 - 0.035 * pressure)
            mul("through_ball", 1.0 - 0.025 * pressure)

        return [
            (action, max(0.001, float(weight) * clamp(factors.get(action, 1.0), 0.90, 1.10)))
            for action, weight in items
        ]

    def step(self) -> Event:
        event = super().step()
        self._update_mental_from_event(event)
        return event

    def substitute(self, team: int, out_name: str, in_name: str) -> Event:
        event = super().substitute(team, out_name, in_name)
        self._ensure_mental_row(int(team), in_name)
        self._update_mental_from_event(event)
        return event

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["mental_state"] = self.mental_state_diagnostic()
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        data["v13_mental_state"] = deepcopy(self.mental_state_diagnostic())
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_mental_state")
        obj._v13_mental_state = deepcopy(raw) if isinstance(raw, dict) else {}
        obj._ensure_all_mental_rows()
        return obj


MatchEngine = MatchEngineV13MentalState

__all__ = ["MatchEngineV13MentalState", "MatchEngine"]
