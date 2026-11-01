from __future__ import annotations

"""Temporary tactical micro-adjustments without formation changes.

The team may make a small contextual tweak in response to a learned pattern,
a repeated individual mismatch, or a late score requirement.  Adjustments are
short-lived, have cooldowns and explicit spatial trade-offs.  They do not
change player attributes or the declared formation.
"""

from copy import deepcopy

from engine import Band, EventType, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_mismatches import MatchEngineV13Mismatches


class MatchEngineV13MicroAdjustments(MatchEngineV13Mismatches):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._v13_micro_adjustments = {
            "0": self._empty_micro_row(),
            "1": self._empty_micro_row(),
        }

    @staticmethod
    def _empty_micro_row() -> dict:
        return {
            "mode": None,
            "player": None,
            "started_second": -1.0,
            "expires_second": -1.0,
            "last_change_second": -9999.0,
            "evidence": None,
        }

    def _ensure_micro_state(self) -> dict:
        if not isinstance(getattr(self, "_v13_micro_adjustments", None), dict):
            self._v13_micro_adjustments = {}
        for key in ("0", "1"):
            row = self._v13_micro_adjustments.setdefault(key, self._empty_micro_row())
            for name, default in self._empty_micro_row().items():
                row.setdefault(name, deepcopy(default))
        return self._v13_micro_adjustments

    def micro_adjustment_diagnostic(self, team: int | None = None) -> dict:
        state = deepcopy(self._ensure_micro_state())
        if team is None:
            return state
        row = state[str(int(team))]
        active = bool(row.get("mode") and self.state.second < float(row.get("expires_second", -1.0)))
        return {"team": int(team), "active": active, **row}

    def _active_micro(self, team: int) -> dict | None:
        row = self._ensure_micro_state()[str(int(team))]
        if not row.get("mode"):
            return None
        if self.state.second >= float(row.get("expires_second", -1.0)):
            row["mode"] = None
            row["player"] = None
            row["evidence"] = None
            return None
        return row

    def _best_hot_player(self, team: int) -> tuple[PlayerState | None, dict | None]:
        best_player = None
        best_diag = None
        for ps in self.teams[int(team)].on_field:
            if ps.red or ps.player.position.upper() == "GK":
                continue
            diag = self._best_player_mismatch(team, ps.player.name)
            if not diag.get("active") or float(diag.get("strength", 0.0)) <= 0.0:
                continue
            if best_diag is None or (
                float(diag["strength"]), int(diag["sample_count"]), ps.player.name
            ) > (
                float(best_diag["strength"]), int(best_diag["sample_count"]), best_player.player.name
            ):
                best_player, best_diag = ps, diag
        return best_player, best_diag

    def _role_player(self, team: int, positions: set[str], attrs: tuple[str, ...]) -> PlayerState | None:
        rows = [
            ps for ps in self.teams[int(team)].on_field
            if not ps.red and ps.player.position.upper() in positions
        ]
        if not rows:
            return None
        return max(rows, key=lambda ps: (sum(ps.effective(attr) for attr in attrs), ps.player.name))

    def _select_micro_adjustment(self, team: int) -> dict | None:
        team = int(team)
        if self.minute < 15.0:
            return None

        hot_player, hot = self._best_hot_player(team)
        if hot_player is not None and hot is not None and float(hot["strength"]) >= 0.16:
            return {
                "mode": "feed_hot_player",
                "player": hot_player.player.name,
                "evidence": {
                    "pattern": hot["pattern"],
                    "strength": round(float(hot["strength"]), 3),
                    "samples": int(hot["sample_count"]),
                },
            }

        game = self.game_management_diagnostic(team)
        diff = int(game.get("score_diff", 0))
        late = clamp(float(game.get("late_factor", 0.0)))
        if diff > 0 and late >= 0.42:
            fullback = self._role_player(team, {"LB", "RB"}, ("positioning", "composure", "stamina"))
            if fullback is not None:
                return {
                    "mode": "hold_fullback",
                    "player": fullback.player.name,
                    "evidence": {"score_diff": diff, "late": round(late, 3)},
                }
        if diff < 0 and late >= 0.35:
            runner = self._role_player(team, {"CM", "AM", "LW", "RW"}, ("off_ball", "stamina", "pace"))
            if runner is not None:
                return {
                    "mode": "extra_runner",
                    "player": runner.player.name,
                    "evidence": {"score_diff": diff, "late": round(late, 3)},
                }

        memory = self.tactical_memory_diagnostic(team, 1 - team)
        if memory.get("learned") and float(memory.get("confidence", 0.0)) >= 0.44:
            pattern = str(memory.get("pattern"))
            if pattern == "wide_service":
                player = self._role_player(team, {"LB", "RB", "DM"}, ("positioning", "anticipation", "stamina"))
                return None if player is None else {
                    "mode": "protect_wide",
                    "player": player.player.name,
                    "evidence": {"pattern": pattern, "confidence": round(float(memory["confidence"]), 3)},
                }
            if pattern in {"vertical_progression", "carry_dribble", "shooting"}:
                player = self._role_player(team, {"DM", "CM"}, ("positioning", "anticipation", "tackling"))
                return None if player is None else {
                    "mode": "screen_center",
                    "player": player.player.name,
                    "evidence": {"pattern": pattern, "confidence": round(float(memory["confidence"]), 3)},
                }
        return None

    def _maybe_refresh_micro_adjustment(self):
        if self.state.pending is not None or self.state.restart is not None:
            return None
        state = self._ensure_micro_state()
        for team in (0, 1):
            current = self._active_micro(team)
            if current is not None:
                continue
            row = state[str(team)]
            if self.state.second - float(row.get("last_change_second", -9999.0)) < 7.5 * 60.0:
                continue
            choice = self._select_micro_adjustment(team)
            if choice is None:
                continue
            row.update(choice)
            row["started_second"] = float(self.state.second)
            row["expires_second"] = float(self.state.second) + 11.0 * 60.0
            row["last_change_second"] = float(self.state.second)
            return self._emit(
                EventType.INFO,
                team,
                2,
                "tactical_micro_adjustment",
                mode=row["mode"],
                player=row["player"],
                evidence=deepcopy(row["evidence"]),
            )
        return None

    def _decision_weights(self, actor: PlayerState, zone: Zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        team = self._team_for_player_state(actor)
        if team is None:
            return items
        row = self._active_micro(team)
        if row is None or row.get("player") != actor.player.name:
            return items
        mode = str(row["mode"])
        factors: dict[str, float] = {}

        def mul(action: str, factor: float) -> None:
            factors[action] = factors.get(action, 1.0) * factor

        if mode == "feed_hot_player":
            for action in ("progressive_pass", "through_ball", "carry", "dribble", "cross", "shoot"):
                mul(action, 1.045)
            mul("safe_pass", 0.97)
        elif mode == "hold_fullback":
            mul("safe_pass", 1.08)
            mul("progressive_pass", 0.96)
            mul("carry", 0.88)
            mul("dribble", 0.84)
            mul("cross", 0.91)
        elif mode == "extra_runner":
            mul("progressive_pass", 1.05)
            mul("carry", 1.07)
            mul("dribble", 1.04)
            mul("shoot", 1.06)
            mul("safe_pass", 0.96)
        elif mode in {"protect_wide", "screen_center"}:
            mul("safe_pass", 1.035)
            mul("carry", 0.96)
        return [
            (action, max(0.001, float(weight) * clamp(factors.get(action, 1.0), 0.82, 1.12)))
            for action, weight in items
        ]

    def _base_target_weights(self, team: int, zone: Zone, actor: PlayerState | None, ctx: dict | None = None):
        weights = super()._base_target_weights(team, zone, actor, ctx)
        row = self._active_micro(team)
        if row is None or row.get("mode") != "feed_hot_player":
            return weights
        target_name = row.get("player")
        return [
            (ps, float(weight) * (1.08 if ps.player.name == target_name else 1.0))
            for ps, weight in weights
        ]

    def _spatial_context(self, attacking_team: int, zone: Zone) -> dict:
        ctx = dict(super()._spatial_context(attacking_team, zone))
        defending_team = 1 - int(attacking_team)
        row = self._active_micro(defending_team)
        if row is None:
            return ctx
        mode = str(row["mode"])
        if mode == "protect_wide" and zone.lane != Lane.CENTER:
            ctx["pressure"] = clamp(float(ctx["pressure"]) + 0.024)
            ctx["space"] = clamp(float(ctx["space"]) - 0.016)
            # Shifting bodies wide opens a little central/far-side room.
            ctx["space_behind"] = clamp(float(ctx["space_behind"]) + 0.012)
        elif mode == "screen_center" and zone.lane == Lane.CENTER:
            ctx["pressure"] = clamp(float(ctx["pressure"]) + 0.021)
            ctx["space"] = clamp(float(ctx["space"]) - 0.014)
            ctx["wide_space"] = clamp(float(ctx.get("wide_space", 0.0)) + 0.018)
        return ctx

    def step(self):
        event = self._maybe_refresh_micro_adjustment()
        if event is not None:
            return event
        return super().step()

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["micro_adjustments"] = self.micro_adjustment_diagnostic()
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        data["v13_micro_adjustments"] = deepcopy(self._ensure_micro_state())
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_micro_adjustments")
        obj._v13_micro_adjustments = deepcopy(raw) if isinstance(raw, dict) else {
            "0": cls._empty_micro_row(),
            "1": cls._empty_micro_row(),
        }
        obj._ensure_micro_state()
        return obj


MatchEngine = MatchEngineV13MicroAdjustments

__all__ = ["MatchEngineV13MicroAdjustments", "MatchEngine"]
