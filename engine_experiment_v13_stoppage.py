from __future__ import annotations

"""Causal stoppage time and physical clock for the v1.3 candidate.

The ordinary engine clock historically advanced almost entirely during open
play.  This layer separates three concepts without changing player ability:

* active/live seconds (which still count towards possession);
* dead-ball elapsed seconds (which do not count as possession);
* recoverable lost seconds used to calculate announced added time.

Added time is therefore a consequence of events that actually happened.  No
late goal, scoreline or statistical quota is targeted by this module.
"""

from copy import deepcopy
import math

from engine import Event, EventType, clamp
from engine_experiment_v13_tournament import MatchEngineV13TournamentContext


class MatchEngineV13Stoppage(MatchEngineV13TournamentContext):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._v13_stoppage = self._new_stoppage_state()

    @staticmethod
    def _new_stoppage_state() -> dict:
        return {
            "recoverable_by_marker": {},
            "dead_elapsed_by_marker": {},
            "announced_seconds_by_marker": {},
            "extension_seconds_by_marker": {},
            "dead_by_reason": {},
            "active_detail_seconds": 0.0,
        }

    def _ensure_stoppage_state(self) -> dict:
        if not isinstance(getattr(self, "_v13_stoppage", None), dict):
            self._v13_stoppage = self._new_stoppage_state()
        for key, default in self._new_stoppage_state().items():
            self._v13_stoppage.setdefault(key, deepcopy(default))
        return self._v13_stoppage

    def _current_base_marker(self) -> int | None:
        if self.state.period_index >= len(self.state.period_markers):
            return None
        return int(self.state.period_markers[self.state.period_index])

    @staticmethod
    def _marker_key(marker: int) -> str:
        return str(int(marker))

    def _phase_clock_factor(self) -> float:
        zone = getattr(self.state, "zone", None)
        transition = clamp(float(getattr(self.state, "transition_boost", 0.0)))
        if transition > 0.20:
            return clamp(0.88 - 0.25 * transition, 0.62, 0.86)
        band = getattr(getattr(zone, "band", None), "value", "middle_third")
        if band == "defensive_third":
            team = int(self.state.possession)
            tempo = float(self.teams[team].team.tactics.tempo)
            return clamp(1.18 - 0.18 * tempo, 1.00, 1.16)
        if band == "middle_third":
            return 1.0
        if band == "final_third":
            return 0.90
        if band == "box":
            return 0.78
        return 1.0

    def _advance_clock(self, seconds: float, possession_team: int):
        adjusted = float(seconds) * self._phase_clock_factor()
        return super()._advance_clock(adjusted, possession_team)

    def _advance_dead_clock(self, elapsed_seconds: float, recoverable_seconds: float, *, reason: str) -> None:
        elapsed = max(0.0, float(elapsed_seconds))
        recoverable = clamp(float(recoverable_seconds), 0.0, elapsed)
        if elapsed <= 0.0:
            return
        marker = self._current_base_marker()
        self.state.second += elapsed
        for rt in self.teams:
            for ps in rt.on_field:
                ps.minutes += elapsed / 60.0
        state = self._ensure_stoppage_state()
        if marker is None:
            return
        key = self._marker_key(marker)
        state["dead_elapsed_by_marker"][key] = float(state["dead_elapsed_by_marker"].get(key, 0.0)) + elapsed
        state["recoverable_by_marker"][key] = float(state["recoverable_by_marker"].get(key, 0.0)) + recoverable
        state["dead_by_reason"][reason] = float(state["dead_by_reason"].get(reason, 0.0)) + elapsed
        if key in state["announced_seconds_by_marker"] and recoverable > 0.0:
            state["extension_seconds_by_marker"][key] = float(state["extension_seconds_by_marker"].get(key, 0.0)) + recoverable

    def _advance_live_detail_clock(self, seconds: float, possession_team: int) -> None:
        seconds = max(0.0, float(seconds))
        if seconds <= 0.0:
            return
        super()._advance_clock(seconds, int(possession_team))
        state = self._ensure_stoppage_state()
        state["active_detail_seconds"] = float(state.get("active_detail_seconds", 0.0)) + seconds

    def _dead_time_profile(self, event: Event) -> tuple[float, float, str]:
        if not isinstance(event, Event):
            return 0.0, 0.0, "none"
        if event.data.get("shootout"):
            return 0.0, 0.0, "shootout"

        key = str(event.text_key or "")
        typ = event.type

        # The referee acknowledging a foul but playing advantage does not stop
        # the ball.  The foul still counts for discipline/statistics, but there
        # is no dead-ball interval to recover later.
        if typ == EventType.FOUL and bool(event.data.get("advantage")):
            return 0.0, 0.0, "advantage_played"
        if typ == EventType.GOAL and key == "goal":
            return 42.0, 28.0, "goal_celebration"
        if typ == EventType.SUBSTITUTION:
            return 30.0, 22.0, "substitution"
        if typ == EventType.INJURY:
            grade = str(event.data.get("grade") or event.data.get("injury_grade") or "minor")
            profile = {
                "knock": (24.0, 12.0),
                "minor": (36.0, 24.0),
                "head_check": (58.0, 48.0),
                "moderate": (82.0, 68.0),
                "severe": (125.0, 108.0),
                "concussion": (118.0, 104.0),
            }.get(grade, (42.0, 28.0))
            return profile[0], profile[1], f"injury:{grade}"
        if "var" in key:
            return 68.0, 58.0, "var_review"
        if "mass_confront" in key or "confrontation" in key:
            return 36.0, 27.0, "confrontation"
        if typ == EventType.CARD:
            return 20.0, 12.0, "card"
        if typ == EventType.PENALTY:
            return 34.0, 19.0, "penalty_setup"
        if typ == EventType.FREE_KICK:
            return 18.0, 5.0, "free_kick_setup"
        if typ == EventType.FOUL:
            card = event.data.get("card")
            return (24.0, 10.0, "foul_with_card") if card else (14.0, 4.0, "foul")
        if typ == EventType.CORNER:
            return 15.0, 2.0, "corner_setup"
        if typ == EventType.OFFSIDE:
            return 8.0, 1.0, "offside_restart"
        if typ in {EventType.SAVE, EventType.MISS, EventType.BLOCK, EventType.POST}:
            return 4.0, 0.0, "natural_reset"
        return 0.0, 0.0, "none"

    @staticmethod
    def _pending_detail_seconds(event: Event) -> float:
        if event.type in {EventType.SHOT, EventType.GOAL, EventType.SAVE, EventType.MISS, EventType.POST, EventType.BLOCK}:
            return 2.1
        if event.type == EventType.REBOUND:
            return 1.4
        if event.type == EventType.DANGER:
            return 3.2
        if event.type in {EventType.TURNOVER, EventType.CORNER}:
            return 2.6
        return 2.0

    def _apply_clock_for_event(self, event: Event, *, had_pending: bool = False) -> None:
        if not isinstance(event, Event):
            return
        if event.data.get("clock_accounted"):
            return
        if event.type in {EventType.PERIOD_END, EventType.MATCH_END}:
            event.data["clock_accounted"] = True
            return
        if had_pending and not event.data.get("shootout"):
            detail = self._pending_detail_seconds(event)
            self._advance_live_detail_clock(detail, event.team)
            event.data["live_action_seconds"] = round(detail, 2)
        elapsed, recoverable, reason = self._dead_time_profile(event)
        if elapsed > 0.0:
            self._advance_dead_clock(elapsed, recoverable, reason=reason)
            event.data["dead_elapsed_seconds"] = round(elapsed, 2)
            event.data["recoverable_seconds"] = round(recoverable, 2)
            event.data["clock_reason"] = reason
        event.data["clock_accounted"] = True

    def step(self) -> Event:
        had_pending = self.state.pending is not None
        event = super().step()
        self._apply_clock_for_event(event, had_pending=had_pending)
        return event

    def substitute(self, team: int, out_name: str, in_name: str) -> Event:
        event = super().substitute(team, out_name, in_name)
        self._apply_clock_for_event(event, had_pending=False)
        return event

    def _announced_seconds(self, marker: int) -> float:
        state = self._ensure_stoppage_state()
        key = self._marker_key(marker)
        if key in state["announced_seconds_by_marker"]:
            return float(state["announced_seconds_by_marker"][key])
        recoverable = float(state["recoverable_by_marker"].get(key, 0.0))
        announced = 0.0 if recoverable < 15.0 else math.ceil(recoverable / 60.0) * 60.0
        cap = 12.0 * 60.0 if marker in (45, 90) else 6.0 * 60.0
        announced = min(announced, cap)
        state["announced_seconds_by_marker"][key] = announced
        state["extension_seconds_by_marker"].setdefault(key, 0.0)
        return announced

    def _period_target_second(self, marker: int) -> float:
        state = self._ensure_stoppage_state()
        key = self._marker_key(marker)
        return marker * 60.0 + self._announced_seconds(marker) + float(state["extension_seconds_by_marker"].get(key, 0.0))

    def _check_period_boundary(self):
        marker = self._current_base_marker()
        if marker is None:
            return None
        base_second = float(marker) * 60.0
        if self.state.second < base_second:
            return None
        state = self._ensure_stoppage_state()
        key = self._marker_key(marker)
        was_announced = key in state["announced_seconds_by_marker"]
        announced = self._announced_seconds(marker)
        if not was_announced and announced > 0.0:
            return self._emit(
                EventType.INFO,
                self.state.possession,
                2,
                "stoppage_time_announced",
                marker=marker,
                added_minutes=int(announced // 60),
                recoverable_seconds=round(float(state["recoverable_by_marker"].get(key, 0.0)), 2),
            )
        if self.state.second + 1e-9 < self._period_target_second(marker):
            return None
        return super()._check_period_boundary()

    def stoppage_time_diagnostic(self) -> dict:
        state = deepcopy(self._ensure_stoppage_state())
        marker = self._current_base_marker()
        current = None
        if marker is not None:
            key = self._marker_key(marker)
            current = {
                "marker": marker,
                "recoverable_seconds": round(float(state["recoverable_by_marker"].get(key, 0.0)), 2),
                "dead_elapsed_seconds": round(float(state["dead_elapsed_by_marker"].get(key, 0.0)), 2),
                "announced_seconds": round(float(state["announced_seconds_by_marker"].get(key, 0.0)), 2),
                "extension_seconds": round(float(state["extension_seconds_by_marker"].get(key, 0.0)), 2),
            }
        return {"current_period": current, **state}

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["stoppage_time"] = self.stoppage_time_diagnostic()
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        data["v13_stoppage"] = deepcopy(self._ensure_stoppage_state())
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_stoppage")
        obj._v13_stoppage = deepcopy(raw) if isinstance(raw, dict) else cls._new_stoppage_state()
        obj._ensure_stoppage_state()
        return obj


MatchEngine = MatchEngineV13Stoppage

__all__ = ["MatchEngineV13Stoppage", "MatchEngine"]
