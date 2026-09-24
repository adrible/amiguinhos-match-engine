from __future__ import annotations

"""v1.3 stage 2: passes into space and coordinated runs."""

from engine import Lane, PlayerState, Zone, clamp
from engine_experiment_v13_combinations import MatchEngineV13Combinations

VERSION = "1.3-candidate-coordinated-runs"


class MatchEngineV13Runs(MatchEngineV13Combinations):
    def _ensure_run_state(self):
        if not hasattr(self, "_v13_forced_space_target"):
            self._v13_forced_space_target = None
        if not hasattr(self, "_v13_active_run_plan"):
            self._v13_active_run_plan = None

    @staticmethod
    def _run_type_for(ps: PlayerState, zone: Zone) -> tuple[str, float]:
        pos = ps.player.position.upper()
        if zone.lane != Lane.CENTER:
            if pos in {"LB", "RB"}:
                return "overlap", 1.14
            if pos in {"CM", "DM", "AM"}:
                return "underlap", 1.06
            if pos in {"LW", "RW"}:
                return "diagonal", 1.08
            if pos == "ST":
                return "depth", 1.12
        else:
            if pos == "ST":
                return "depth", 1.18
            if pos in {"LW", "RW"}:
                return "diagonal", 1.12
            if pos == "AM":
                return "third_line", 1.08
        return "support", 0.86

    def run_diagnostic(self, team: int, actor: PlayerState, zone: Zone, ctx: dict | None = None) -> dict:
        context = dict(ctx or {"pressure": 0.5, "space": 0.5, "space_behind": 0.4, "support": 0.5})
        pressure = clamp(float(context.get("pressure", 0.5)))
        behind = clamp(float(context.get("space_behind", 0.4)))
        rows = []
        for ps in self.teams[team].on_field:
            if ps.player.name == actor.player.name or ps.player.position.upper() == "GK" or ps.red:
                continue
            run_type, affinity = self._run_type_for(ps, zone)
            quality = clamp(
                affinity * (
                    0.30 * ps.effective("off_ball") / 100.0
                    + 0.22 * ps.effective("anticipation") / 100.0
                    + 0.22 * ps.effective("pace") / 100.0
                    + 0.10 * ps.effective("stamina") / 100.0
                    + 0.08 * ps.effective("composure") / 100.0
                    + 0.08 * ps.energy
                )
                + 0.10 * behind - 0.08 * pressure
            )
            rows.append((quality, ps.player.name, run_type))
        if not rows:
            return {"available": False, "runner": None, "run_type": None, "quality": 0.0, "pass_into_space_probability": 0.0}
        quality, name, run_type = max(rows)
        vision = clamp(actor.effective("vision") / 100.0)
        passing = clamp(actor.effective("passing") / 100.0)
        probability = clamp(0.03 + 0.22 * quality + 0.12 * vision + 0.08 * passing + 0.08 * behind - 0.10 * pressure, 0.04, 0.46)
        return {
            "available": quality >= 0.42,
            "runner": name,
            "run_type": run_type,
            "quality": quality,
            "pass_into_space_probability": probability,
        }

    def _prepare_space_run(self, team, actor, zone, ctx, kind):
        self._ensure_run_state()
        plan = self.run_diagnostic(team, actor, zone, ctx)
        if (
            plan["available"]
            and kind in {"progressive_pass", "switch", "long_ball", "through_ball", "cross", "cutback"}
            and self.rng.random() < plan["pass_into_space_probability"]
        ):
            self._v13_forced_space_target = {"team": team, "actor": actor.player.name, "target": plan["runner"], "kind": kind}
            self._v13_active_run_plan = plan
            return plan
        self._v13_forced_space_target = None
        self._v13_active_run_plan = None
        return None

    def _choose_target(self, team, zone, attacking=True, exclude=None):
        self._ensure_run_state()
        marker = self._v13_forced_space_target
        if attacking and marker and marker.get("team") == team and marker.get("actor") == exclude:
            try:
                return self.teams[team].by_name(marker["target"])
            except KeyError:
                pass
        return super()._choose_target(team, zone, attacking=attacking, exclude=exclude)

    @staticmethod
    def _apply_run_context(ctx: dict, plan: dict | None) -> dict:
        if not plan:
            return dict(ctx)
        adjusted = dict(ctx)
        q = float(plan["quality"])
        adjusted["support"] = clamp(float(adjusted.get("support", 0.5)) + 0.035 * q)
        adjusted["space_behind"] = clamp(float(adjusted.get("space_behind", 0.4)) + 0.055 * q)
        return adjusted

    @staticmethod
    def _annotate_run(event, plan):
        if plan:
            event.data["pass_into_space"] = True
            event.data["run_target"] = plan["runner"]
            event.data["run_type"] = plan["run_type"]
            event.data["run_quality"] = round(float(plan["quality"]), 3)

    def _progressive_action(self, team, actor, zone, kind, ctx):
        plan = self._prepare_space_run(team, actor, zone, ctx, kind)
        try:
            event = super()._progressive_action(team, actor, zone, kind, self._apply_run_context(ctx, plan))
            self._annotate_run(event, plan)
            return event
        finally:
            self._v13_forced_space_target = None
            self._v13_active_run_plan = None

    def _create_or_resolve_danger(self, team, actor, zone, kind, ctx):
        plan = self._prepare_space_run(team, actor, zone, ctx, kind)
        try:
            event = super()._create_or_resolve_danger(team, actor, zone, kind, self._apply_run_context(ctx, plan))
            self._annotate_run(event, plan)
            return event
        finally:
            self._v13_forced_space_target = None
            self._v13_active_run_plan = None


MatchEngine = MatchEngineV13Runs
