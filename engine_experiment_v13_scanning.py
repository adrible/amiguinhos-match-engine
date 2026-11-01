from __future__ import annotations

"""v1.3 advanced collective stage 1: scanning and decision tempo.

Scanning is contextual perception, not a new player attribute. Vision,
anticipation, composure, technique, body orientation, pressure and available
space determine how much useful information a player has before acting.
"""

from engine import PlayerState, Zone, clamp
from engine_experiment_v13_collective import MatchEngineV13Collective

VERSION = "1.3-candidate-scanning-decision-tempo"


class MatchEngineV13Scanning(MatchEngineV13Collective):
    def _ensure_scanning_state(self) -> None:
        if not hasattr(self, "_v13_scan_context"):
            self._v13_scan_context = None

    def scanning_diagnostic(self, actor: PlayerState, zone: Zone, ctx: dict) -> dict:
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        space = clamp(float(ctx.get("space", 0.5)))
        support = clamp(float(ctx.get("support", 0.5)))
        body = self.body_orientation_diagnostic(
            actor,
            zone,
            ctx,
            source=getattr(self, "_v13_current_reception_source", "open_play"),
        )
        vision = clamp(actor.effective("vision") / 100.0)
        anticipation = clamp(actor.effective("anticipation") / 100.0)
        composure = clamp(actor.effective("composure") / 100.0)
        technique = clamp(actor.effective("technique") / 100.0)

        scan_quality = clamp(
            0.31 * vision
            + 0.25 * anticipation
            + 0.16 * composure
            + 0.10 * technique
            + 0.08 * float(body["open_body"])
            + 0.07 * space
            + 0.04 * support
            - 0.15 * pressure
        )
        blindside_risk = clamp(
            0.58
            - 0.42 * scan_quality
            + 0.26 * pressure
            - 0.10 * float(body["open_body"])
        )
        decision_seconds = clamp(
            1.34
            - 0.70 * scan_quality
            + 0.38 * pressure
            - 0.22 * space,
            0.34,
            1.55,
        )
        clock_scale = clamp(
            0.82 + 0.28 * (decision_seconds / 1.55),
            0.82,
            1.10,
        )
        return {
            "scan_quality": scan_quality,
            "blindside_risk": blindside_risk,
            "decision_seconds": decision_seconds,
            "decision_clock_scale": clock_scale,
            "open_body": float(body["open_body"]),
            "pressure": pressure,
            "space": space,
        }

    def _spatial_context(self, attacking_team: int, zone: Zone) -> dict:
        ctx = super()._spatial_context(attacking_team, zone)
        self._ensure_scanning_state()
        actor_name = getattr(self, "_v13_current_open_actor", None)
        if not actor_name:
            return ctx
        try:
            actor = self.teams[attacking_team].by_name(actor_name)
        except KeyError:
            return ctx
        diag = self.scanning_diagnostic(actor, zone, ctx)
        self._v13_scan_context = {
            "team": attacking_team,
            "actor": actor_name,
            "zone": zone,
            **diag,
        }
        ctx["scan_quality"] = diag["scan_quality"]
        ctx["decision_seconds"] = diag["decision_seconds"]
        return ctx

    def combination_clock_scale(self, possession_team: int | None = None) -> float:
        scale = super().combination_clock_scale(possession_team)
        self._ensure_scanning_state()
        marker = self._v13_scan_context
        actor_name = getattr(self, "_v13_current_open_actor", None)
        team = self.state.possession if possession_team is None else possession_team
        if (
            marker
            and marker.get("team") == team
            and marker.get("actor") == actor_name
            and marker.get("zone") == self.state.zone
        ):
            scale *= float(marker.get("decision_clock_scale", 1.0))
        return clamp(scale, 0.20, 1.12)

    def _first_time_probability(self, actor: PlayerState, action: str, diag: dict) -> float:
        base = super()._first_time_probability(actor, action, diag)
        if base <= 0.0:
            return base
        scan = clamp(float(diag.get("scan_score", 0.5)))
        return clamp(base + 0.055 * (scan - 0.50), 0.0, 0.74)

    def _decision_weights(self, actor, zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        scan = clamp(float(ctx.get("scan_quality", 0.5)))
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        out = []
        for action, weight in items:
            modifier = 1.0
            if action == "safe_pass":
                modifier += 0.12 * max(0.0, 0.52 - scan) + 0.05 * pressure
            elif action in {"progressive_pass", "through_ball", "switch", "cutback"}:
                modifier += 0.12 * max(0.0, scan - 0.48)
            elif action in {"carry", "dribble"} and pressure > 0.60:
                modifier -= 0.07 * max(0.0, 0.55 - scan)
            out.append((action, max(0.0, weight * modifier)))
        return out

    def _execute_decision(self, team, actor, zone, decision, ctx):
        self._ensure_scanning_state()
        marker = self._v13_scan_context
        if not (
            marker
            and marker.get("team") == team
            and marker.get("actor") == actor.player.name
            and marker.get("zone") == zone
        ):
            marker = {
                "team": team,
                "actor": actor.player.name,
                "zone": zone,
                **self.scanning_diagnostic(actor, zone, ctx),
            }
        event = super()._execute_decision(team, actor, zone, decision, ctx)
        event.data.setdefault("scan_quality", round(float(marker["scan_quality"]), 3))
        event.data.setdefault("blindside_risk", round(float(marker["blindside_risk"]), 3))
        event.data.setdefault("decision_seconds", round(float(marker["decision_seconds"]), 3))
        event.data.setdefault(
            "decision_clock_scale",
            round(float(marker["decision_clock_scale"]), 3),
        )
        return event


MatchEngine = MatchEngineV13Scanning
