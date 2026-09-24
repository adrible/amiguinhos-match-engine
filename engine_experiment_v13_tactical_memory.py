from __future__ import annotations

"""v1.3 match-intelligence stage 1: short tactical memory.

Players only learn patterns that have actually repeated during the current match.
Memory is short, decays with age, is team-symmetric and never reads identity or
future events.
"""

from copy import deepcopy

from engine import EventType, clamp
from engine_experiment_v13_quick_free_kick import MatchEngineV13QuickFreeKick

VERSION = "1.3-candidate-tactical-memory"

_SHOT_TYPES = {EventType.BLOCK, EventType.MISS, EventType.POST, EventType.SAVE, EventType.GOAL}


class MatchEngineV13TacticalMemory(MatchEngineV13QuickFreeKick):
    def _ensure_tactical_memory_state(self) -> None:
        if not hasattr(self, "_v13_tactical_memory"):
            self._v13_tactical_memory = []

    def export_state(self) -> dict:
        data = super().export_state()
        self._ensure_tactical_memory_state()
        data["v13_tactical_memory"] = [deepcopy(row) for row in self._v13_tactical_memory]
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        obj._v13_tactical_memory = [deepcopy(row) for row in data.get("v13_tactical_memory", [])]
        return obj

    @staticmethod
    def _observation_player(event) -> str | None:
        for key in ("actor", "creator", "shooter", "taker", "passer", "receiver"):
            value = event.data.get(key)
            if value:
                return str(value)
        return None

    def _event_tactical_observation(self, event) -> dict | None:
        if event.team not in (0, 1):
            return None
        player = self._observation_player(event)
        if not player:
            return None
        data = event.data
        kind = str(data.get("kind") or "")
        key = str(event.text_key)
        origin = str(data.get("origin") or "")
        zone_data = data.get("zone") if isinstance(data.get("zone"), dict) else {}
        lane = str(zone_data.get("lane") or "unknown")

        if key == "dangerous_turnover" or origin == "transition":
            pattern = "fast_transition"
        elif kind in {"cross", "cutback"} or "cross" in key or "cutback" in key:
            pattern = "wide_service"
        elif kind in {"through_ball", "progressive_pass", "long_ball"}:
            pattern = "vertical_progression"
        elif kind == "switch":
            pattern = "switch_play"
        elif kind in {"carry", "dribble"} or key in {"carry_success", "carry_creates_danger"}:
            pattern = "carry_dribble"
        elif event.type in _SHOT_TYPES and not data.get("shootout"):
            pattern = "shooting"
        else:
            return None

        return {
            "observer": 1 - int(event.team),
            "opponent": int(event.team),
            "player": player,
            "pattern": pattern,
            "lane": lane,
            "second": float(self.state.second),
        }

    def tactical_memory_diagnostic(
        self,
        observer_team: int,
        opponent_team: int,
        *,
        player_name: str | None = None,
        pattern: str | None = None,
        window_minutes: float = 18.0,
    ) -> dict:
        self._ensure_tactical_memory_state()
        cutoff = self.state.second - max(1.0, float(window_minutes)) * 60.0
        rows = [
            row
            for row in self._v13_tactical_memory
            if int(row["observer"]) == int(observer_team)
            and int(row["opponent"]) == int(opponent_team)
            and float(row["second"]) >= cutoff
            and (player_name is None or row["player"] == player_name)
            and (pattern is None or row["pattern"] == pattern)
        ]
        if not rows:
            return {
                "learned": False,
                "pattern": pattern,
                "sample_count": 0,
                "confidence": 0.0,
                "player": player_name,
            }

        if pattern is None:
            counts: dict[str, int] = {}
            for row in rows:
                counts[row["pattern"]] = counts.get(row["pattern"], 0) + 1
            dominant = max(counts, key=lambda name: (counts[name], name))
            rows = [row for row in rows if row["pattern"] == dominant]
        else:
            dominant = pattern

        window_seconds = max(60.0, float(window_minutes) * 60.0)
        recency = sum(
            clamp(1.0 - (self.state.second - float(row["second"])) / window_seconds, 0.20, 1.0)
            for row in rows
        ) / len(rows)
        count = len(rows)
        confidence = clamp(((count - 1) / 3.5) * recency, 0.0, 0.92)
        learned = count >= 3 and confidence >= 0.28
        return {
            "learned": learned,
            "pattern": dominant,
            "sample_count": count,
            "confidence": confidence,
            "player": player_name,
            "last_seen_seconds_ago": max(0.0, self.state.second - float(rows[-1]["second"])),
        }

    def _emit(self, typ, team, relevance, text_key, **data):
        self._ensure_tactical_memory_state()
        event = super()._emit(typ, team, relevance, text_key, **data)
        row = self._event_tactical_observation(event)
        if row is not None:
            self._v13_tactical_memory.append(row)
            cutoff = self.state.second - 25.0 * 60.0
            self._v13_tactical_memory = [
                item for item in self._v13_tactical_memory[-128:] if float(item["second"]) >= cutoff
            ]
        return event


MatchEngine = MatchEngineV13TacticalMemory
