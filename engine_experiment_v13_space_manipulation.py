from __future__ import annotations

"""v1.3 advanced collective stage 5: space manipulation and overload-to-isolate."""

from engine import Lane, PlayerState, Zone, clamp
from engine_experiment_v13_transition_structure import MatchEngineV13TransitionStructure
from engine_experiment_v13_passing_texture import _stable_fraction

VERSION = "1.3-candidate-space-manipulation"


class MatchEngineV13SpaceManipulation(MatchEngineV13TransitionStructure):
    def _ensure_space_manipulation_state(self) -> None:
        if not hasattr(self, "_v13_isolation_target"):
            self._v13_isolation_target = None
        if not hasattr(self, "_v13_manipulation_context"):
            self._v13_manipulation_context = None

    @staticmethod
    def _far_side_positions(lane: Lane) -> set[str]:
        if lane == Lane.LEFT:
            return {"RW", "RB"}
        if lane == Lane.RIGHT:
            return {"LW", "LB"}
        return set()

    def space_manipulation_diagnostic(
        self,
        team: int,
        actor: PlayerState,
        zone: Zone,
        ctx: dict,
    ) -> dict:
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        support = clamp(float(ctx.get("support", 0.5)))
        tactics = self.teams[team].team.tactics

        decoys = []
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position.upper() == "GK" or ps.player.name == actor.player.name:
                continue
            quality = clamp(
                0.34 * ps.effective("off_ball") / 100.0
                + 0.26 * ps.effective("anticipation") / 100.0
                + 0.18 * ps.effective("pace") / 100.0
                + 0.12 * ps.effective("technique") / 100.0
                + 0.10 * ps.energy
            )
            decoys.append((quality, ps.player.name))
        decoy_quality, decoy_name = max(decoys, default=(0.0, None))

        far_rows = []
        allowed = self._far_side_positions(zone.lane)
        if allowed:
            for ps in self.teams[team].on_field:
                if ps.red or ps.player.position.upper() not in allowed:
                    continue
                q = clamp(
                    0.32 * ps.effective("off_ball") / 100.0
                    + 0.24 * ps.effective("pace") / 100.0
                    + 0.18 * ps.effective("technique") / 100.0
                    + 0.16 * ps.effective("anticipation") / 100.0
                    + 0.10 * ps.energy
                )
                far_rows.append((q, ps.player.name))
        far_quality, far_target = max(far_rows, default=(0.0, None))

        overload = clamp(
            0.18
            + 0.30 * support
            + 0.16 * decoy_quality
            + 0.12 * tactics.tempo
            + 0.10 * tactics.width
            + 0.08 * tactics.risk
            - 0.12 * pressure
        )
        actor_scan = clamp(
            0.48 * actor.effective("vision") / 100.0
            + 0.30 * actor.effective("anticipation") / 100.0
            + 0.22 * actor.effective("composure") / 100.0
        )
        isolation = clamp(
            overload
            * (0.54 + 0.46 * far_quality)
            * (0.72 + 0.28 * actor_scan)
        ) if far_target else 0.0

        activation_p = clamp(
            0.05 + 0.30 * decoy_quality + 0.16 * support + 0.10 * actor_scan - 0.08 * pressure,
            0.05,
            0.46,
        )
        fraction = _stable_fraction(
            "space-manipulation",
            self.seed,
            round(self.state.second, 3),
            team,
            actor.player.name,
            zone.band.value,
            zone.lane.value,
        )
        active = decoy_name is not None and decoy_quality >= 0.48 and fraction < activation_p
        kind = (
            "overload_to_isolate"
            if active and far_target and isolation >= 0.42
            else "drag_marker"
            if active and zone.lane != Lane.CENTER
            else "pin_line"
            if active
            else None
        )
        return {
            "active": active,
            "kind": kind,
            "decoy": decoy_name,
            "decoy_quality": decoy_quality,
            "far_side_target": far_target,
            "far_side_quality": far_quality,
            "overload_score": overload,
            "isolation_score": isolation,
            "activation_probability": activation_p,
        }

    def _spatial_context(self, attacking_team: int, zone: Zone) -> dict:
        ctx = super()._spatial_context(attacking_team, zone)
        self._ensure_space_manipulation_state()
        actor_name = getattr(self, "_v13_current_open_actor", None)
        if not actor_name:
            return ctx
        try:
            actor = self.teams[attacking_team].by_name(actor_name)
        except KeyError:
            return ctx
        diag = self.space_manipulation_diagnostic(attacking_team, actor, zone, ctx)
        self._v13_manipulation_context = {
            "team": attacking_team,
            "actor": actor_name,
            "zone": zone,
            **diag,
        }
        if diag["active"]:
            q = float(diag["decoy_quality"])
            ctx["support"] = clamp(float(ctx.get("support", 0.5)) + 0.025 * q)
            ctx["space"] = clamp(float(ctx.get("space", 0.5)) + 0.018 * q)
            ctx["transition_threat"] = clamp(
                float(ctx.get("transition_threat", 0.5)) + 0.025 * q
            )
        return ctx

    def _decision_weights(self, actor, zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        diag = self.space_manipulation_diagnostic(
            self.state.possession,
            actor,
            zone,
            ctx,
        )
        if not diag["active"]:
            return items
        out = []
        for action, weight in items:
            modifier = 1.0
            if diag["kind"] == "overload_to_isolate" and action == "switch":
                modifier += 0.30 * float(diag["isolation_score"])
            elif action in {"progressive_pass", "through_ball"}:
                modifier += 0.08 * float(diag["decoy_quality"])
            elif action == "carry" and diag["kind"] == "drag_marker":
                modifier += 0.05 * float(diag["decoy_quality"])
            out.append((action, max(0.0, weight * modifier)))
        return out

    def _prepare_isolation(self, team, actor, zone, ctx, kind):
        self._ensure_space_manipulation_state()
        self._v13_isolation_target = None
        if kind != "switch" or zone.lane == Lane.CENTER:
            return None
        diag = self.space_manipulation_diagnostic(team, actor, zone, ctx)
        target = diag.get("far_side_target")
        if not (diag["active"] and target and diag["kind"] == "overload_to_isolate"):
            return None
        vision = clamp(actor.effective("vision") / 100.0)
        passing = clamp(actor.effective("passing") / 100.0)
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        p = clamp(
            0.04
            + 0.28 * float(diag["isolation_score"])
            + 0.12 * vision
            + 0.08 * passing
            - 0.10 * pressure,
            0.05,
            0.48,
        )
        fraction = _stable_fraction(
            "isolation-switch",
            self.seed,
            round(self.state.second, 3),
            actor.player.name,
            target,
            zone.lane.value,
        )
        if fraction >= p:
            return None
        self._v13_isolation_target = {
            "team": team,
            "actor": actor.player.name,
            "target": target,
            "probability": p,
            "diagnostic": diag,
        }
        return self._v13_isolation_target

    def _choose_target(self, team, zone, attacking=True, exclude=None):
        self._ensure_space_manipulation_state()
        marker = self._v13_isolation_target
        if (
            attacking
            and marker
            and marker.get("team") == team
            and marker.get("actor") == exclude
        ):
            try:
                return self.teams[team].by_name(marker["target"])
            except KeyError:
                pass
        return super()._choose_target(team, zone, attacking=attacking, exclude=exclude)

    def _progressive_action(self, team, actor, zone, kind, ctx):
        marker = self._prepare_isolation(team, actor, zone, ctx, kind)
        try:
            event = super()._progressive_action(team, actor, zone, kind, ctx)
            if marker and (event.data.get("target") or event.data.get("receiver")) == marker["target"]:
                event.data["overload_to_isolate"] = True
                event.data["isolated_target"] = marker["target"]
                event.data["isolation_score"] = round(
                    float(marker["diagnostic"]["isolation_score"]),
                    3,
                )
                event.data["isolation_switch_probability"] = round(
                    float(marker["probability"]),
                    3,
                )
            return event
        finally:
            self._v13_isolation_target = None

    def _execute_decision(self, team, actor, zone, decision, ctx):
        diag = self.space_manipulation_diagnostic(team, actor, zone, ctx)
        adjusted = dict(ctx)
        if diag["active"]:
            q = float(diag["decoy_quality"])
            adjusted["support"] = clamp(float(adjusted.get("support", 0.5)) + 0.018 * q)
            adjusted["transition_threat"] = clamp(
                float(adjusted.get("transition_threat", 0.5)) + 0.020 * q
            )
        event = super()._execute_decision(team, actor, zone, decision, adjusted)
        if diag["active"]:
            event.data.setdefault("space_manipulation", diag["kind"])
            event.data.setdefault("decoy_runner", diag["decoy"])
            event.data.setdefault(
                "space_manipulation_quality",
                round(float(diag["decoy_quality"]), 3),
            )
            if diag.get("far_side_target"):
                event.data.setdefault("far_side_option", diag["far_side_target"])
        return event


MatchEngine = MatchEngineV13SpaceManipulation
