from __future__ import annotations

"""v1.3 contextual set-piece routines and real late goalkeeper participation.

Routines bias existing corner/free-kick plans; they never create a shot or goal
by themselves. The layer also closes a gap in the pre-existing keeper-up model:
a goalkeeper who is genuinely sent forward for a late corner can now be chosen
as the aerial target, while the open-goal transition risk remains active.
"""

from copy import deepcopy

from engine import Band, Lane, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_game_management import MatchEngineV13GameManagement


class MatchEngineV13SetPieceRoutines(MatchEngineV13GameManagement):
    CORNER_ROUTINES = ("short_triangle", "near_screen", "far_overload", "second_ball_edge")
    FREE_KICK_ROUTINES = ("short_third_man", "far_post_cluster", "second_phase", "direct_screen")

    def _ensure_set_piece_state(self) -> None:
        if not hasattr(self, "_v13_set_piece_usage"):
            self._v13_set_piece_usage: dict[str, int] = {}
        if not hasattr(self, "_v13_active_corner_routine"):
            self._v13_active_corner_routine = None
        if not hasattr(self, "_v13_active_free_kick_routine"):
            self._v13_active_free_kick_routine = None

    @staticmethod
    def _routine_key(team: int, kind: str, routine: str) -> str:
        return f"{int(team)}:{kind}:{routine}"

    def _routine_usage(self, team: int, kind: str, routine: str) -> int:
        self._ensure_set_piece_state()
        return int(self._v13_set_piece_usage.get(self._routine_key(team, kind, routine), 0))

    def _record_routine(self, team: int, kind: str, routine: str) -> None:
        self._ensure_set_piece_state()
        key = self._routine_key(team, kind, routine)
        self._v13_set_piece_usage[key] = self._v13_set_piece_usage.get(key, 0) + 1

    def _edge_second_ball_quality(self, team: int) -> float:
        rows = []
        for ps in self.teams[int(team)].on_field:
            if ps.red or ps.player.position.upper() == "GK":
                continue
            rows.append(
                0.34 * ps.effective("anticipation")
                + 0.28 * ps.effective("positioning")
                + 0.22 * ps.effective("long_shots")
                + 0.16 * ps.effective("composure")
            )
        best = sorted(rows, reverse=True)[:3]
        return clamp(sum(best) / (100.0 * len(best))) if best else 0.50

    def corner_routine_diagnostic(self, team: int, zone: Zone | None = None) -> dict:
        self._ensure_set_piece_state()
        zone = zone or self.state.restart_zone or Zone(Band.ATT, Lane.LEFT)
        base = super().corner_plan_diagnostic(team, zone)
        tactics = self.teams[int(team)].team.tactics
        second_ball = self._edge_second_ball_quality(team)
        raw = {
            "short_triangle": 0.30 + 0.70 * float(base["short_quality"]) + 0.34 * (1.0 - tactics.directness),
            "near_screen": 0.34 + 0.55 * float(base["attack_aerial_quality"]) + 0.30 * float(base["delivery_quality"]),
            "far_overload": 0.30 + 0.48 * float(base["attack_aerial_quality"]) + 0.28 * tactics.width + 0.24 * float(base["delivery_quality"]),
            "second_ball_edge": 0.27 + 0.62 * second_ball + 0.22 * float(base["defense_aerial_quality"]),
        }
        for routine in raw:
            raw[routine] *= 1.0 / (1.0 + 0.16 * self._routine_usage(team, "corner", routine))
        total = sum(raw.values()) or 1.0
        return {
            "team": int(team),
            "zone": self._zone_data(zone),
            "second_ball_quality": second_ball,
            "weights": {key: value / total for key, value in raw.items()},
            "usage": {key: self._routine_usage(team, "corner", key) for key in raw},
        }

    def free_kick_routine_diagnostic(self, team: int, zone: Zone) -> dict:
        self._ensure_set_piece_state()
        base = super().free_kick_plan_diagnostic(team, zone)
        tactics = self.teams[int(team)].team.tactics
        direct_eligible = zone.band == Band.ATT and zone.lane == Lane.CENTER and base["weights"].get("direct_shot", 0.0) > 0.0
        raw = {
            "short_third_man": 0.36 + 0.60 * (1.0 - tactics.directness) + 0.22 * base["weights"].get("short_restart", 0.0),
            "far_post_cluster": 0.38 + 0.52 * float(base["delivery_quality"]) + 0.24 * tactics.width,
            "second_phase": 0.33 + 0.40 * float(base["delivery_quality"]) + 0.28 * (1.0 - float(base["block_density"])),
            "direct_screen": (0.30 + 0.60 * float(base["shot_quality"])) if direct_eligible else 0.02,
        }
        for routine in raw:
            raw[routine] *= 1.0 / (1.0 + 0.16 * self._routine_usage(team, "free_kick", routine))
        total = sum(raw.values()) or 1.0
        return {
            "team": int(team),
            "zone": self._zone_data(zone),
            "direct_eligible": direct_eligible,
            "weights": {key: value / total for key, value in raw.items()},
            "usage": {key: self._routine_usage(team, "free_kick", key) for key in raw},
        }

    @staticmethod
    def _normalise_weights(weights: dict[str, float]) -> dict[str, float]:
        cleaned = {key: max(0.0, float(value)) for key, value in weights.items()}
        total = sum(cleaned.values()) or 1.0
        return {key: value / total for key, value in cleaned.items()}

    def corner_plan_diagnostic(self, team: int, zone: Zone | None = None) -> dict:
        diag = super().corner_plan_diagnostic(team, zone)
        self._ensure_set_piece_state()
        routine = self._v13_active_corner_routine
        if routine is None:
            return diag
        factors = {
            "short_triangle": {"short_corner": 1.82, "near_post": 0.86, "central_delivery": 0.80, "far_post": 0.86},
            "near_screen": {"short_corner": 0.82, "near_post": 1.62, "central_delivery": 1.08, "far_post": 0.92},
            "far_overload": {"short_corner": 0.82, "near_post": 0.88, "central_delivery": 1.05, "far_post": 1.66},
            "second_ball_edge": {"short_corner": 0.86, "near_post": 1.02, "central_delivery": 1.46, "far_post": 1.14},
        }[routine]
        diag = dict(diag)
        diag["weights"] = self._normalise_weights({key: value * factors.get(key, 1.0) for key, value in diag["weights"].items()})
        diag["routine"] = routine
        return diag

    def free_kick_plan_diagnostic(self, team: int, zone: Zone) -> dict:
        diag = super().free_kick_plan_diagnostic(team, zone)
        self._ensure_set_piece_state()
        routine = self._v13_active_free_kick_routine
        if routine is None:
            return diag
        factors = {
            "short_third_man": {"short_restart": 1.72, "delivery": 0.88, "direct_shot": 0.70},
            "far_post_cluster": {"short_restart": 0.82, "delivery": 1.58, "direct_shot": 0.82},
            "second_phase": {"short_restart": 1.12, "delivery": 1.34, "direct_shot": 0.86},
            "direct_screen": {"short_restart": 0.72, "delivery": 0.86, "direct_shot": 1.72},
        }[routine]
        diag = dict(diag)
        diag["weights"] = self._normalise_weights({key: value * factors.get(key, 1.0) for key, value in diag["weights"].items()})
        diag["routine"] = routine
        return diag

    def keeper_set_piece_attack_diagnostic(self, team: int, zone: Zone) -> dict:
        keeper = self._goalkeeper(int(team))
        exposed = self._keeper_is_exposed(int(team))
        diff = self.score[int(team)] - self.score[1 - int(team)]
        eligible = bool(exposed and diff < 0 and self.minute >= 89.0 and zone.band in {Band.ATT, Band.BOX})
        aerial = clamp(
            (0.30 * keeper.effective("heading") + 0.28 * keeper.effective("strength") + 0.24 * keeper.effective("anticipation") + 0.18 * keeper.effective("off_ball")) / 100.0
        )
        probability = clamp(0.055 + 0.13 * aerial, 0.06, 0.19) if eligible else 0.0
        return {
            "team": int(team),
            "keeper": keeper.player.name,
            "eligible": eligible,
            "aerial_quality": aerial,
            "target_probability": probability,
            "goal_exposed": exposed,
        }

    def _corner_target(self, team: int, taker: PlayerState, zone: Zone, pattern: str) -> PlayerState:
        target = super()._corner_target(team, taker, zone, pattern)
        diag = self.keeper_set_piece_attack_diagnostic(team, Zone(Band.ATT, zone.lane))
        if diag["eligible"] and self.rng.random() < float(diag["target_probability"]):
            return self._goalkeeper(team)
        return target

    def _resolve_contextual_corner(self, team: int, zone: Zone):
        self._ensure_set_piece_state()
        # Activate the pre-existing open-goal risk before the corner layer clears
        # restart metadata. This makes keeper-up operational, not cosmetic.
        if self._keeper_attack_mode(team, zone) == "keeper_up":
            self._activate_keeper_up(team, seconds=42.0)
        routine_diag = self.corner_routine_diagnostic(team, zone)
        routine = weighted_choice(self.rng, list(routine_diag["weights"].items()))
        self._v13_active_corner_routine = routine
        try:
            event = super()._resolve_contextual_corner(team, zone)
        finally:
            self._v13_active_corner_routine = None
        self._record_routine(team, "corner", routine)
        event.data["set_piece_routine"] = routine
        if self._keeper_is_exposed(team):
            event.data["keeper_up"] = True
        return event

    def _resolve_deliberate_free_kick(self, team: int, zone: Zone):
        self._ensure_set_piece_state()
        if self._keeper_attack_mode(team, zone) == "keeper_up":
            self._activate_keeper_up(team, seconds=38.0)
        routine_diag = self.free_kick_routine_diagnostic(team, zone)
        routine = weighted_choice(self.rng, list(routine_diag["weights"].items()))
        self._v13_active_free_kick_routine = routine
        try:
            event = super()._resolve_deliberate_free_kick(team, zone)
        finally:
            self._v13_active_free_kick_routine = None
        self._record_routine(team, "free_kick", routine)
        event.data["set_piece_routine"] = routine
        if self._keeper_is_exposed(team):
            event.data["keeper_up"] = True
        return event

    def snapshot(self) -> dict:
        data = super().snapshot()
        self._ensure_set_piece_state()
        data["set_piece_usage"] = dict(self._v13_set_piece_usage)
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        self._ensure_set_piece_state()
        data["v13_set_piece_usage"] = deepcopy(self._v13_set_piece_usage)
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_set_piece_usage", {})
        obj._v13_set_piece_usage = deepcopy(raw) if isinstance(raw, dict) else {}
        obj._v13_active_corner_routine = None
        obj._v13_active_free_kick_routine = None
        return obj


MatchEngine = MatchEngineV13SetPieceRoutines

__all__ = ["MatchEngineV13SetPieceRoutines", "MatchEngine"]
