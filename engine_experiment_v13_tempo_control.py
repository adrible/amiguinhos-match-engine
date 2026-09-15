from __future__ import annotations

"""v1.3 match-intelligence stage 4: contextual control of match tempo."""

from engine import Band, PlayerState, Zone, clamp
from engine_experiment_v13_player_habits import MatchEngineV13PlayerHabits

VERSION = "1.3-candidate-tempo-control"


class MatchEngineV13TempoControl(MatchEngineV13PlayerHabits):
    def _ensure_tempo_state(self) -> None:
        if not hasattr(self, "_v13_tempo_marker"):
            self._v13_tempo_marker = None

    def export_state(self) -> dict:
        data = super().export_state()
        self._ensure_tempo_state()
        marker = self._v13_tempo_marker
        if isinstance(marker, dict):
            payload = dict(marker)
            zone = payload.get("zone")
            if isinstance(zone, Zone):
                payload["zone"] = {"band": zone.band.value, "lane": zone.lane.value}
            data["v13_tempo_marker"] = payload
        else:
            data["v13_tempo_marker"] = None
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_tempo_marker")
        if isinstance(raw, dict):
            marker = dict(raw)
            zone = marker.get("zone")
            if isinstance(zone, dict):
                marker["zone"] = obj._zone_from_dict(zone)
            obj._v13_tempo_marker = marker
        else:
            obj._v13_tempo_marker = None
        return obj

    def tempo_control_diagnostic(self, team: int, actor: PlayerState, zone: Zone, ctx: dict) -> dict:
        tactics = self.teams[team].team.tactics
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        space = clamp(float(ctx.get("space", 0.5)))
        space_behind = clamp(float(ctx.get("space_behind", 0.4)))
        transition = clamp(float(self.state.transition_boost))
        composure = clamp(actor.effective("composure") / 100.0)
        vision = clamp(actor.effective("vision") / 100.0)
        h, a = self.score
        diff = (h - a) if team == 0 else (a - h)
        minute = self.minute

        if transition >= 0.26 and space + space_behind >= 0.86:
            mode = "accelerate"
            strength = clamp(0.40 + 0.38 * transition + 0.14 * space + 0.08 * vision)
        elif diff < 0 and minute >= 65.0:
            mode = "accelerate"
            strength = clamp(0.50 + 0.18 * min(2, -diff) + 0.18 * tactics.tempo + 0.14 * tactics.risk)
        elif diff > 0 and minute >= 72.0:
            mode = "circulate"
            strength = clamp(0.48 + 0.16 * min(2, diff) + 0.20 * composure + 0.16 * (1.0 - tactics.risk))
        elif zone.band != Band.BOX and pressure >= 0.58 and composure >= 0.68 and vision >= 0.66:
            mode = "pause"
            strength = clamp(0.34 + 0.26 * pressure + 0.22 * composure + 0.18 * vision)
        elif tactics.tempo <= 0.42 and composure >= 0.68:
            mode = "circulate"
            strength = clamp(0.40 + 0.22 * composure + 0.16 * vision + 0.12 * (1.0 - tactics.tempo))
        else:
            mode = "normal"
            strength = 0.0

        clock_scale = 1.0
        if mode == "accelerate":
            clock_scale = clamp(1.0 - 0.18 * strength, 0.80, 0.97)
        elif mode == "pause":
            clock_scale = clamp(1.0 + 0.13 * strength, 1.02, 1.14)
        elif mode == "circulate":
            clock_scale = clamp(1.0 + 0.09 * strength, 1.01, 1.10)
        return {
            "mode": mode,
            "strength": strength,
            "clock_scale": clock_scale,
            "pressure": pressure,
            "transition": transition,
            "score_diff": diff,
        }

    def _spatial_context(self, attacking_team: int, zone: Zone) -> dict:
        ctx = super()._spatial_context(attacking_team, zone)
        self._ensure_tempo_state()
        actor_name = getattr(self, "_v13_current_open_actor", None)
        if not actor_name:
            return ctx
        try:
            actor = self.teams[attacking_team].by_name(actor_name)
        except KeyError:
            return ctx
        diag = self.tempo_control_diagnostic(attacking_team, actor, zone, ctx)
        self._v13_tempo_marker = {
            "team": attacking_team,
            "actor": actor_name,
            "zone": zone,
            **diag,
        }
        ctx["tempo_mode"] = diag["mode"]
        ctx["tempo_control_strength"] = diag["strength"]
        return ctx

    def combination_clock_scale(self, possession_team: int | None = None) -> float:
        scale = super().combination_clock_scale(possession_team)
        self._ensure_tempo_state()
        marker = self._v13_tempo_marker
        team = self.state.possession if possession_team is None else possession_team
        actor_name = getattr(self, "_v13_current_open_actor", None)
        if (
            marker
            and marker.get("team") == team
            and marker.get("actor") == actor_name
            and marker.get("zone") == self.state.zone
        ):
            scale *= float(marker.get("clock_scale", 1.0))
        return clamp(scale, 0.20, 1.20)

    def _decision_weights(self, actor, zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        mode = str(ctx.get("tempo_mode", "normal"))
        strength = clamp(float(ctx.get("tempo_control_strength", 0.0)))
        out = []
        for action, weight in items:
            modifier = 1.0
            if mode == "accelerate":
                if action in {"progressive_pass", "through_ball", "carry", "dribble"}:
                    modifier += 0.23 * strength
                elif action == "safe_pass":
                    modifier -= 0.14 * strength
            elif mode == "circulate":
                if action in {"safe_pass", "switch", "progressive_pass"}:
                    modifier += 0.18 * strength
                elif action in {"shoot", "dribble", "long_ball"}:
                    modifier -= 0.12 * strength
            elif mode == "pause":
                if action in {"safe_pass", "progressive_pass", "cutback"}:
                    modifier += 0.12 * strength
                elif action in {"long_ball", "shoot"}:
                    modifier -= 0.08 * strength
            out.append((action, max(0.0, float(weight) * clamp(modifier, 0.78, 1.24))))
        return out

    def _execute_decision(self, team, actor, zone, decision, ctx):
        marker = self._v13_tempo_marker if isinstance(getattr(self, "_v13_tempo_marker", None), dict) else None
        event = super()._execute_decision(team, actor, zone, decision, ctx)
        if marker and marker.get("team") == team and marker.get("actor") == actor.player.name:
            event.data.setdefault("tempo_mode", marker.get("mode"))
            event.data.setdefault("tempo_control_strength", round(float(marker.get("strength", 0.0)), 3))
            event.data.setdefault("tempo_clock_scale", round(float(marker.get("clock_scale", 1.0)), 3))
        return event


MatchEngine = MatchEngineV13TempoControl
