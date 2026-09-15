from __future__ import annotations

"""v1.3 final-third stage 4: progressive value from actually breaking lines."""

from engine import Band, PlayerState, Zone, clamp
from engine_experiment_v13_passing_lanes import MatchEngineV13PassingLanes

VERSION = "1.3-candidate-line-breaking"


class MatchEngineV13LineBreaking(MatchEngineV13PassingLanes):
    def line_break_diagnostic(
        self,
        team: int,
        actor: PlayerState,
        target: PlayerState,
        zone: Zone,
        kind: str,
        ctx: dict,
    ) -> dict:
        passing = clamp(actor.effective("passing") / 100.0)
        vision = clamp(actor.effective("vision") / 100.0)
        technique = clamp(actor.effective("technique") / 100.0)
        movement = clamp(
            0.50 * target.effective("off_ball") / 100.0
            + 0.28 * target.effective("anticipation") / 100.0
            + 0.22 * target.effective("pace") / 100.0
        )
        openness = clamp(float(ctx.get("passing_lane_openness", ctx.get("space", 0.5))))
        def_tactics = self.teams[1 - team].team.tactics
        line_height = clamp(def_tactics.defensive_line)
        compactness = clamp(def_tactics.compactness)
        base = {
            "progressive_pass": 0.38,
            "through_ball": 0.52,
            "switch": 0.20,
            "long_ball": 0.34,
        }.get(kind, 0.18)
        if zone.band == Band.DEF:
            base -= 0.08
        elif zone.band == Band.ATT:
            base += 0.09
        score = clamp(
            base
            + 0.18 * passing
            + 0.20 * vision
            + 0.08 * technique
            + 0.16 * movement
            + 0.12 * openness
            + 0.08 * line_height
            - 0.14 * compactness
            - 0.10 * float(ctx.get("pressure", 0.5))
        )
        if score >= 0.72:
            lines = 2
        elif score >= 0.50:
            lines = 1
        else:
            lines = 0
        advantage = clamp(
            0.20
            + 0.26 * score
            + 0.18 * movement
            + 0.14 * float(ctx.get("space_behind", 0.5))
            - 0.12 * compactness
        )
        return {
            "score": score,
            "lines_broken": lines,
            "advantage_created": advantage,
        }

    def _decision_weights(self, actor, zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        vision = clamp(actor.effective("vision") / 100.0)
        passing = clamp(actor.effective("passing") / 100.0)
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        line_appetite = clamp(
            0.24 + 0.32 * vision + 0.24 * passing + 0.12 * tactics.risk - 0.18 * pressure
        )
        out = []
        for action, weight in items:
            mod = 1.0
            if action == "progressive_pass":
                mod += 0.12 * line_appetite
            elif action == "through_ball":
                mod += 0.16 * line_appetite * float(ctx.get("space_behind", 0.5))
            elif action == "safe_pass" and line_appetite >= 0.68:
                mod -= 0.04
            out.append((action, max(0.0, weight * mod)))
        return out

    @staticmethod
    def _annotate_break(event, diag: dict) -> None:
        event.data.setdefault("line_break_score", round(float(diag["score"]), 3))
        event.data.setdefault("lines_broken", int(diag["lines_broken"]))
        event.data.setdefault(
            "positional_advantage",
            round(float(diag["advantage_created"]), 3),
        )

    def _progressive_action(self, team, actor, zone, kind, ctx):
        event = super()._progressive_action(team, actor, zone, kind, ctx)
        target_name = event.data.get("target") or event.data.get("receiver")
        if not target_name:
            return event
        try:
            target = self.teams[team].by_name(str(target_name))
        except KeyError:
            return event
        enriched = dict(ctx)
        enriched["passing_lane_openness"] = float(event.data.get("passing_lane_openness", ctx.get("space", 0.5)))
        diag = self.line_break_diagnostic(team, actor, target, zone, kind, enriched)
        self._annotate_break(event, diag)
        if (
            int(diag["lines_broken"]) > 0
            and self.state.pending is not None
            and self.state.pending.team == team
        ):
            self.state.pending.danger = clamp(
                float(self.state.pending.danger)
                + 0.035 * int(diag["lines_broken"]) * float(diag["advantage_created"])
            )
            event.data["danger"] = round(float(self.state.pending.danger), 3)
        return event

    def _create_or_resolve_danger(self, team, actor, zone, kind, ctx):
        event = super()._create_or_resolve_danger(team, actor, zone, kind, ctx)
        if kind != "through_ball":
            return event
        target_name = event.data.get("runner") or event.data.get("receiver") or event.data.get("target")
        if not target_name and self.state.pending is not None and self.state.pending.team == team:
            target_name = self.state.pending.actor
        if not target_name:
            return event
        try:
            target = self.teams[team].by_name(str(target_name))
        except KeyError:
            return event
        enriched = dict(ctx)
        enriched["passing_lane_openness"] = float(event.data.get("passing_lane_openness", ctx.get("space", 0.5)))
        diag = self.line_break_diagnostic(team, actor, target, zone, kind, enriched)
        self._annotate_break(event, diag)
        if (
            int(diag["lines_broken"]) > 0
            and self.state.pending is not None
            and self.state.pending.team == team
        ):
            self.state.pending.danger = clamp(
                float(self.state.pending.danger)
                + 0.040 * int(diag["lines_broken"]) * float(diag["advantage_created"])
            )
            event.data["danger"] = round(float(self.state.pending.danger), 3)
        return event


MatchEngine = MatchEngineV13LineBreaking
