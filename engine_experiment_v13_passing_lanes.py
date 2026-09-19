from __future__ import annotations

"""v1.3 final-third stage 3: pass lanes, partial closures and interception risk."""

from engine import Band, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_shot_preparation import MatchEngineV13ShotPreparation

VERSION = "1.3-candidate-passing-lanes"


class MatchEngineV13PassingLanes(MatchEngineV13ShotPreparation):
    def _ensure_passing_lane_state(self) -> None:
        if not hasattr(self, "_v13_lane_target_override"):
            self._v13_lane_target_override = None

    def passing_lane_diagnostic(
        self,
        team: int,
        actor: PlayerState,
        target: PlayerState,
        zone: Zone,
        kind: str,
        ctx: dict,
    ) -> dict:
        defenders = []
        for ps in self.teams[1 - team].on_field:
            if ps.red or ps.player.position.upper() == "GK":
                continue
            positioning = clamp(ps.effective("positioning") / 100.0)
            anticipation = clamp(ps.effective("anticipation") / 100.0)
            pace = clamp(ps.effective("pace") / 100.0)
            tackling = clamp(ps.effective("tackling") / 100.0)
            pos = ps.player.position.upper()
            role_factor = 1.0
            if zone.band in {Band.ATT, Band.BOX} and pos in {"CB", "DM", "LB", "RB"}:
                role_factor += 0.12
            elif zone.band == Band.MID and pos in {"DM", "CM"}:
                role_factor += 0.10
            lane_factor = 1.0
            if zone.lane == Lane.CENTER and pos in {"CB", "DM", "CM"}:
                lane_factor += 0.10
            elif zone.lane != Lane.CENTER and pos in {"LB", "RB", "CB"}:
                lane_factor += 0.06
            score = clamp(
                (
                    0.34 * positioning
                    + 0.30 * anticipation
                    + 0.18 * pace
                    + 0.18 * tackling
                )
                * role_factor
                * lane_factor
            )
            defenders.append((score, ps.player.name))
        closure, interceptor = max(defenders, default=(0.0, None), key=lambda row: row[0])

        passing = clamp(actor.effective("passing") / 100.0)
        vision = clamp(actor.effective("vision") / 100.0)
        technique = clamp(actor.effective("technique") / 100.0)
        target_movement = clamp(
            0.48 * target.effective("off_ball") / 100.0
            + 0.30 * target.effective("anticipation") / 100.0
            + 0.22 * target.effective("pace") / 100.0
        )
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        compactness = clamp(self.teams[1 - team].team.tactics.compactness)
        difficulty = {
            "safe_pass": 0.05,
            "progressive_pass": 0.16,
            "switch": 0.12,
            "long_ball": 0.18,
            "through_ball": 0.24,
        }.get(kind, 0.12)
        openness = clamp(
            0.52
            + 0.16 * passing
            + 0.12 * vision
            + 0.08 * technique
            + 0.15 * target_movement
            + 0.08 * float(ctx.get("space", 0.5))
            - 0.28 * closure
            - 0.12 * compactness
            - 0.14 * pressure
            - difficulty
        )
        interception_risk = clamp(
            0.10
            + 0.48 * closure
            + 0.16 * compactness
            + 0.10 * pressure
            + difficulty
            - 0.25 * passing
            - 0.18 * vision
            - 0.12 * target_movement
        )
        status = "open" if openness >= 0.62 else "partial" if openness >= 0.40 else "closed"
        return {
            "status": status,
            "openness": openness,
            "interception_risk": interception_risk,
            "interceptor": interceptor,
            "target_movement": target_movement,
        }

    def _choose_target(self, team, zone, attacking=True, exclude=None):
        self._ensure_passing_lane_state()
        marker = self._v13_lane_target_override
        if (
            marker
            and marker.get("team") == team
            and marker.get("attacking") == bool(attacking)
            and marker.get("exclude") == exclude
        ):
            try:
                return self.teams[team].by_name(marker["target"])
            except KeyError:
                pass
        return super()._choose_target(team, zone, attacking=attacking, exclude=exclude)

    def _lane_adjusted_context(self, ctx: dict, diag: dict) -> dict:
        adjusted = dict(ctx)
        risk = float(diag["interception_risk"])
        openness = float(diag["openness"])
        adjusted["pressure"] = clamp(float(adjusted.get("pressure", 0.5)) + 0.055 * risk)
        adjusted["support"] = clamp(float(adjusted.get("support", 0.5)) + 0.035 * (openness - 0.5))
        adjusted["space"] = clamp(float(adjusted.get("space", 0.5)) + 0.028 * (openness - 0.5))
        adjusted["passing_lane_openness"] = openness
        adjusted["interception_risk"] = risk
        return adjusted

    @staticmethod
    def _annotate_lane(event, diag: dict) -> None:
        event.data.setdefault("passing_lane", diag["status"])
        event.data.setdefault("passing_lane_openness", round(float(diag["openness"]), 3))
        event.data.setdefault("interception_risk", round(float(diag["interception_risk"]), 3))
        if diag.get("interceptor"):
            event.data.setdefault("lane_interceptor", diag["interceptor"])

    def _safe_pass(self, team, actor, zone, ctx):
        target = super()._choose_target(team, zone, attacking=False, exclude=actor.player.name)
        diag = self.passing_lane_diagnostic(team, actor, target, zone, "safe_pass", ctx)
        self._v13_lane_target_override = {
            "team": team,
            "target": target.player.name,
            "attacking": False,
            "exclude": actor.player.name,
        }
        try:
            event = super()._safe_pass(team, actor, zone, self._lane_adjusted_context(ctx, diag))
        finally:
            self._v13_lane_target_override = None
        self._annotate_lane(event, diag)
        return event

    def _progressive_action(self, team, actor, zone, kind, ctx):
        target = super()._choose_target(team, zone, attacking=True, exclude=actor.player.name)
        diag = self.passing_lane_diagnostic(team, actor, target, zone, kind, ctx)
        self._v13_lane_target_override = {
            "team": team,
            "target": target.player.name,
            "attacking": True,
            "exclude": actor.player.name,
        }
        try:
            event = super()._progressive_action(
                team,
                actor,
                zone,
                kind,
                self._lane_adjusted_context(ctx, diag),
            )
        finally:
            self._v13_lane_target_override = None
        self._annotate_lane(event, diag)
        return event

    def _create_or_resolve_danger(self, team, actor, zone, kind, ctx):
        if kind != "through_ball":
            return super()._create_or_resolve_danger(team, actor, zone, kind, ctx)
        target = super()._choose_target(team, zone, attacking=True, exclude=actor.player.name)
        diag = self.passing_lane_diagnostic(team, actor, target, zone, kind, ctx)
        self._v13_lane_target_override = {
            "team": team,
            "target": target.player.name,
            "attacking": True,
            "exclude": actor.player.name,
        }
        try:
            event = super()._create_or_resolve_danger(
                team,
                actor,
                zone,
                kind,
                self._lane_adjusted_context(ctx, diag),
            )
        finally:
            self._v13_lane_target_override = None
        self._annotate_lane(event, diag)
        return event


MatchEngine = MatchEngineV13PassingLanes
