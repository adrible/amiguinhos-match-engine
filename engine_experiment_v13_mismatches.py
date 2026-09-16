from __future__ import annotations

"""Emergent individual mismatch learning for v1.3.

The attack can learn that a player is repeatedly succeeding or failing with a
specific action family.  The signal is based only on events produced in the
current match, decays by recency and modestly changes where the team looks and
which actions that player prefers.  Execution attributes are untouched.
"""

from copy import deepcopy

from engine import Band, EventType, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_tactical_fouls import MatchEngineV13TacticalFouls


_ACTION_PATTERN = {
    "cross": "wide_service",
    "cutback": "wide_service",
    "progressive_pass": "vertical_progression",
    "through_ball": "vertical_progression",
    "long_ball": "vertical_progression",
    "switch": "switch_play",
    "carry": "carry_dribble",
    "dribble": "carry_dribble",
    "shoot": "shooting",
}

_PATTERN_ACTIONS = {
    "wide_service": {"cross", "cutback"},
    "vertical_progression": {"progressive_pass", "through_ball", "long_ball"},
    "switch_play": {"switch"},
    "carry_dribble": {"carry", "dribble"},
    "shooting": {"shoot"},
}


class MatchEngineV13Mismatches(MatchEngineV13TacticalFouls):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._v13_mismatch_observations: list[dict] = []

    def _ensure_mismatch_state(self) -> list[dict]:
        if not isinstance(getattr(self, "_v13_mismatch_observations", None), list):
            self._v13_mismatch_observations = []
        return self._v13_mismatch_observations

    @staticmethod
    def _decision_outcome_score(event) -> float | None:
        key = str(event.text_key or "")
        if event.type in {EventType.TURNOVER, EventType.OFFSIDE}:
            return 0.0
        if "stopped" in key or "cleared" in key or "failed" in key:
            return 0.0
        if event.type == EventType.FOUL:
            # Drawing a foul beats the immediate defender without equating it
            # to creating a clean chance.
            return 0.65
        if event.type in {EventType.DANGER, EventType.PROGRESSION, EventType.CORNER, EventType.FREE_KICK, EventType.PENALTY}:
            return 1.0
        if event.type in {EventType.GOAL, EventType.SAVE, EventType.MISS, EventType.POST, EventType.BLOCK, EventType.SHOT}:
            return 0.85
        if key in {"carry_success", "pass_completed", "switch_completed"}:
            return 0.80
        return None

    def _record_mismatch_observation(
        self,
        team: int,
        actor: PlayerState,
        zone: Zone,
        decision: str,
        event,
    ) -> None:
        pattern = _ACTION_PATTERN.get(str(decision))
        outcome = self._decision_outcome_score(event)
        if pattern is None or outcome is None:
            return
        defender = event.data.get("defender") or event.data.get("adaptive_defender")
        rows = self._ensure_mismatch_state()
        rows.append({
            "team": int(team),
            "player": actor.player.name,
            "pattern": pattern,
            "action": str(decision),
            "lane": zone.lane.value,
            "band": zone.band.value,
            "success": float(outcome),
            "defender": None if defender is None else str(defender),
            "second": float(self.state.second),
        })
        cutoff = self.state.second - 28.0 * 60.0
        self._v13_mismatch_observations = [
            row for row in rows[-180:] if float(row["second"]) >= cutoff
        ]

    def mismatch_diagnostic(
        self,
        team: int,
        player_name: str,
        *,
        pattern: str | None = None,
        lane: Lane | str | None = None,
        window_minutes: float = 18.0,
    ) -> dict:
        rows = self._ensure_mismatch_state()
        cutoff = self.state.second - max(1.0, float(window_minutes)) * 60.0
        lane_value = lane.value if isinstance(lane, Lane) else (str(lane) if lane is not None else None)
        filtered = [
            row for row in rows
            if int(row["team"]) == int(team)
            and row["player"] == str(player_name)
            and float(row["second"]) >= cutoff
            and (pattern is None or row["pattern"] == pattern)
            and (lane_value is None or row["lane"] == lane_value)
        ]
        if not filtered:
            return {
                "active": False,
                "team": int(team),
                "player": str(player_name),
                "pattern": pattern,
                "sample_count": 0,
                "success_rate": 0.5,
                "confidence": 0.0,
                "strength": 0.0,
            }

        if pattern is None:
            groups: dict[str, list[dict]] = {}
            for row in filtered:
                groups.setdefault(str(row["pattern"]), []).append(row)
            dominant = max(groups, key=lambda name: (len(groups[name]), name))
            filtered = groups[dominant]
        else:
            dominant = pattern

        window_seconds = max(60.0, float(window_minutes) * 60.0)
        weighted_success = 0.0
        weight_total = 0.0
        for row in filtered:
            age = self.state.second - float(row["second"])
            weight = clamp(1.0 - age / window_seconds, 0.24, 1.0)
            weighted_success += float(row["success"]) * weight
            weight_total += weight
        success_rate = weighted_success / max(1e-9, weight_total)
        count = len(filtered)
        confidence = clamp(((count - 1) / 4.0) * (weight_total / count), 0.0, 0.90)
        raw = (success_rate - 0.5) * 2.0
        strength = clamp(raw * confidence, -0.80, 0.80)
        active = bool(count >= 3 and confidence >= 0.24 and abs(strength) >= 0.10)
        defenders = [row.get("defender") for row in filtered if row.get("defender")]
        repeated_defender = None
        if defenders:
            repeated_defender = max(set(defenders), key=lambda name: (defenders.count(name), name))
        return {
            "active": active,
            "team": int(team),
            "player": str(player_name),
            "pattern": dominant,
            "sample_count": count,
            "success_rate": success_rate,
            "confidence": confidence,
            "strength": strength if active else 0.0,
            "repeated_defender": repeated_defender,
        }

    def _best_player_mismatch(self, team: int, player_name: str, lane: Lane | None = None) -> dict:
        candidates = [
            self.mismatch_diagnostic(team, player_name, pattern=pattern, lane=lane)
            for pattern in _PATTERN_ACTIONS
        ]
        return max(candidates, key=lambda row: (abs(float(row["strength"])), int(row["sample_count"]), str(row["pattern"])))

    def _decision_weights(self, actor: PlayerState, zone: Zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        team = self._team_for_player_state(actor)
        if team is None:
            return items
        factors: dict[str, float] = {}
        for pattern, actions in _PATTERN_ACTIONS.items():
            diag = self.mismatch_diagnostic(team, actor.player.name, pattern=pattern, lane=zone.lane)
            if not diag["active"]:
                continue
            strength = float(diag["strength"])
            for action in actions:
                factors[action] = factors.get(action, 1.0) * (1.0 + 0.12 * strength)
            factors["safe_pass"] = factors.get("safe_pass", 1.0) * (1.0 - 0.035 * max(0.0, strength))

        return [
            (action, max(0.001, float(weight) * clamp(factors.get(action, 1.0), 0.90, 1.10)))
            for action, weight in items
        ]

    def _base_target_weights(self, team: int, zone: Zone, actor: PlayerState | None, ctx: dict | None = None):
        weights = super()._base_target_weights(team, zone, actor, ctx)
        out = []
        for ps, weight in weights:
            diag = self._best_player_mismatch(team, ps.player.name, lane=zone.lane)
            strength = float(diag["strength"]) if diag.get("active") else 0.0
            factor = 1.0 + 0.09 * max(0.0, strength) + 0.045 * min(0.0, strength)
            out.append((ps, float(weight) * clamp(factor, 0.94, 1.08)))
        return out

    def _execute_decision(self, team, actor, zone, decision, ctx):
        event = super()._execute_decision(team, actor, zone, decision, ctx)
        self._record_mismatch_observation(team, actor, zone, decision, event)
        pattern = _ACTION_PATTERN.get(str(decision))
        if pattern is not None:
            diag = self.mismatch_diagnostic(team, actor.player.name, pattern=pattern, lane=zone.lane)
            if diag.get("active"):
                event.data.setdefault("mismatch_pattern", pattern)
                event.data.setdefault("mismatch_strength", round(float(diag["strength"]), 3))
                event.data.setdefault("mismatch_samples", int(diag["sample_count"]))
                event.data.setdefault("mismatch_success_rate", round(float(diag["success_rate"]), 3))
                if diag.get("repeated_defender"):
                    event.data.setdefault("mismatch_defender", diag["repeated_defender"])
        return event

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["mismatch_observations"] = len(self._ensure_mismatch_state())
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        data["v13_mismatch_observations"] = deepcopy(self._ensure_mismatch_state())
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_mismatch_observations", [])
        obj._v13_mismatch_observations = deepcopy(raw) if isinstance(raw, list) else []
        return obj


MatchEngine = MatchEngineV13Mismatches

__all__ = ["MatchEngineV13Mismatches", "MatchEngine"]
