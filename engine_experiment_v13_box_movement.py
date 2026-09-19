from __future__ import annotations

"""v1.3 duel/box stage 3: contextual movement inside the penalty area."""

from engine import Band, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_one_v_one import MatchEngineV13OneVOne
from engine_experiment_v13_passing_texture import _stable_fraction

VERSION = "1.3-candidate-box-movement"


class MatchEngineV13BoxMovement(MatchEngineV13OneVOne):
    def _ensure_box_movement_state(self) -> None:
        if not hasattr(self, "_v13_box_target_override"):
            self._v13_box_target_override = None

    def box_movement_diagnostic(
        self,
        team: int,
        crosser: PlayerState,
        zone: Zone,
        kind: str,
        ctx: dict,
    ) -> dict:
        rows = []
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position.upper() == "GK" or ps.player.name == crosser.player.name:
                continue
            off_ball = clamp(ps.effective("off_ball") / 100.0)
            anticipation = clamp(ps.effective("anticipation") / 100.0)
            pace = clamp(ps.effective("pace") / 100.0)
            heading = clamp(ps.effective("heading") / 100.0)
            finishing = clamp(ps.effective("finishing") / 100.0)
            strength = clamp(ps.effective("strength") / 100.0)
            fraction = _stable_fraction(
                "box-run",
                self.seed,
                round(self.state.second, 3),
                ps.player.name,
                crosser.player.name,
                kind,
                zone.lane.value,
            )
            if kind == "cutback":
                run_type = "cutback_lane" if fraction < 0.62 else "penalty_spot"
                finish_component = finishing
                aerial_component = 0.20 * heading
            elif fraction < 0.28:
                run_type = "near_post"
                finish_component = 0.62 * finishing + 0.38 * pace
                aerial_component = 0.44 * heading
            elif fraction < 0.56:
                run_type = "far_post"
                finish_component = 0.54 * finishing + 0.46 * heading
                aerial_component = 0.58 * heading
            elif fraction < 0.80:
                run_type = "blindside"
                finish_component = 0.60 * finishing + 0.40 * anticipation
                aerial_component = 0.42 * heading
            else:
                run_type = "penalty_spot"
                finish_component = finishing
                aerial_component = 0.34 * heading

            score = clamp(
                0.28 * off_ball
                + 0.22 * anticipation
                + 0.12 * pace
                + 0.12 * strength
                + 0.20 * finish_component
                + 0.06 * aerial_component
                + (fraction - 0.5) * 0.035
            )
            rows.append((score, ps.player.name, run_type, heading, finishing))

        score, target, run_type, heading, finishing = max(
            rows,
            default=(0.0, None, None, 0.0, 0.0),
            key=lambda row: row[0],
        )
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        run_quality = clamp(score + 0.08 * float(ctx.get("space", 0.5)) - 0.06 * pressure)
        return {
            "target": target,
            "run_type": run_type,
            "run_quality": run_quality,
            "heading": heading,
            "finishing": finishing,
            "candidate_count": len(rows),
        }

    def _choose_target(self, team, zone, attacking=True, exclude=None):
        self._ensure_box_movement_state()
        marker = self._v13_box_target_override
        if attacking and marker and marker.get("team") == team:
            target = marker.get("target")
            if target and target != exclude:
                try:
                    return self.teams[team].by_name(target)
                except KeyError:
                    pass
        return super()._choose_target(team, zone, attacking=attacking, exclude=exclude)

    def _create_or_resolve_danger(self, team, actor, zone, kind, ctx):
        self._ensure_box_movement_state()
        diag = None
        if kind in {"cross", "cutback"} and zone.band in {Band.ATT, Band.BOX}:
            diag = self.box_movement_diagnostic(team, actor, zone, kind, ctx)
            if diag["target"]:
                self._v13_box_target_override = {"team": team, **diag}
        try:
            event = super()._create_or_resolve_danger(team, actor, zone, kind, ctx)
            if diag and diag["target"]:
                event.data.setdefault("box_run", diag["run_type"])
                event.data.setdefault("box_run_target", diag["target"])
                event.data.setdefault("box_run_quality", round(float(diag["run_quality"]), 3))
                pending = self.state.pending
                if pending is not None and pending.team == team and pending.actor == diag["target"]:
                    pending.danger = clamp(float(pending.danger) + 0.060 * (float(diag["run_quality"]) - 0.50))
                    event.data["danger"] = round(float(pending.danger), 3)
            return event
        finally:
            self._v13_box_target_override = None

    def _resolve_pending(self):
        p = self.state.pending
        diag = None
        if p is not None and p.kind in {"cross", "cutback"}:
            try:
                actor = self.teams[p.team].by_name(p.actor)
            except KeyError:
                actor = None
            if actor is not None:
                ctx = {
                    "pressure": clamp(float(p.pressure)),
                    "space": clamp(0.62 - 0.40 * float(p.pressure) + 0.12 * float(p.danger)),
                    "support": 0.55,
                    "space_behind": 0.40,
                }
                diag = self.box_movement_diagnostic(p.team, actor, p.zone, p.kind, ctx)
                if p.target is None and diag["target"]:
                    p.target = diag["target"]
                p.danger = clamp(float(p.danger) + 0.045 * (float(diag["run_quality"]) - 0.50))
        event = super()._resolve_pending()
        if diag and diag["target"]:
            event.data.setdefault("box_run", diag["run_type"])
            event.data.setdefault("box_run_target", diag["target"])
            event.data.setdefault("box_run_quality", round(float(diag["run_quality"]), 3))
        return event


MatchEngine = MatchEngineV13BoxMovement
