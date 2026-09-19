from __future__ import annotations

"""v1.3 stage 4: pressing triggers and defensive steering.

A pressing jump carries an explicit depth trade-off, so it is not an additional
free defensive bonus. Steering can bias a one-footed attacker toward the less
natural foot, but never forces a body-part choice or outcome.
"""

from engine import Band, PlayerState, Zone, clamp
from engine_experiment_v13_thirdman import MatchEngineV13ThirdMan

VERSION = "1.3-candidate-pressing-triggers"


class MatchEngineV13PressingTriggers(MatchEngineV13ThirdMan):
    def _ensure_press_state(self):
        if not hasattr(self, "_v13_steering_context"):
            self._v13_steering_context = None

    def pressing_trigger_diagnostic(self, attacking_team: int, zone: Zone) -> dict:
        defending_team = 1 - attacking_team
        pressing = clamp(self.teams[defending_team].team.tactics.pressing)
        last = self.state.event_log[-1] if self.state.event_log else None
        trigger = None
        severity = 0.0
        if last is not None:
            touch = last.data.get("first_touch")
            if touch == "miscontrol":
                trigger, severity = "miscontrol", 1.0
            elif touch == "heavy":
                trigger, severity = "heavy_touch", 0.88
            elif touch == "loose":
                trigger, severity = "loose_touch", 0.72
            elif last.type.value == "rebound":
                trigger, severity = "second_ball", 0.82
            elif last.text_key == "safe_pass" and zone.band in {Band.DEF, Band.MID}:
                trigger, severity = "safe_recycle", 0.46
            elif last.data.get("reception_mode") == "controlled" and last.data.get("oriented_touch") == "secure":
                trigger, severity = "receiver_closed", 0.40
        active = bool(trigger and pressing >= 0.30)
        pressure_delta = clamp((0.012 + 0.055 * severity) * pressing, 0.0, 0.060) if active else 0.0
        return {
            "active": active,
            "trigger": trigger,
            "severity": severity,
            "pressing": pressing,
            "pressure_delta": pressure_delta,
            "depth_tradeoff": pressure_delta * 0.90,
        }

    def steering_diagnostic(self, actor: PlayerState, zone: Zone, ctx: dict) -> dict:
        footedness = self._footedness(actor)
        defensive_quality = clamp(float(ctx.get("defensive_quality", 0.55)))
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        attacker_escape = clamp((actor.effective("dribbling") + actor.effective("technique")) / 200.0)
        quality = clamp(0.38 + 0.34 * defensive_quality + 0.16 * pressure - 0.22 * attacker_escape, 0.18, 0.78)
        intent = "weak_foot" if footedness != "B" else ("force_line" if zone.lane.value != "center" else "contain")
        return {"intent": intent, "quality": quality, "footedness": footedness}

    def _spatial_context(self, attacking_team: int, zone: Zone) -> dict:
        ctx = super()._spatial_context(attacking_team, zone)
        diag = self.pressing_trigger_diagnostic(attacking_team, zone)
        if diag["active"]:
            delta = diag["pressure_delta"]
            ctx["pressure"] = clamp(float(ctx.get("pressure", 0.5)) + delta)
            ctx["space"] = clamp(float(ctx.get("space", 0.5)) - 0.42 * delta)
            ctx["space_behind"] = clamp(float(ctx.get("space_behind", 0.4)) + diag["depth_tradeoff"])
            ctx["pressing_trigger"] = diag["trigger"]
            ctx["pressing_trigger_delta"] = delta
        return ctx

    def body_part_probabilities(self, actor, action, zone, ctx=None, *, source="open_play"):
        probs = super().body_part_probabilities(actor, action, zone, ctx, source=source)
        marker = getattr(self, "_v13_steering_context", None)
        if not marker or marker.get("actor") != actor.player.name or marker.get("intent") != "weak_foot":
            return probs
        if self._footedness(actor) == "B":
            return probs
        preferred, weak = self._preferred_and_weak_foot(actor)
        q = float(marker.get("quality", 0.0))
        tuned = dict(probs)
        tuned[preferred] *= max(0.64, 1.0 - 0.28 * q)
        tuned[weak] *= 1.0 + 0.48 * q
        total = sum(tuned.values()) or 1.0
        return {k: v / total for k, v in tuned.items()}

    def _execute_decision(self, team, actor, zone, decision, ctx):
        press = self.pressing_trigger_diagnostic(team, zone)
        steering = self.steering_diagnostic(actor, zone, ctx)
        adjusted = dict(ctx)
        if decision in {"carry", "dribble", "shoot", "cross", "cutback"}:
            q = steering["quality"]
            adjusted["pressure"] = clamp(float(adjusted.get("pressure", 0.5)) + 0.018 * q)
            adjusted["space_behind"] = clamp(float(adjusted.get("space_behind", 0.4)) + 0.016 * q)
        self._v13_steering_context = {"actor": actor.player.name, "intent": steering["intent"], "quality": steering["quality"]}
        try:
            event = super()._execute_decision(team, actor, zone, decision, adjusted)
        finally:
            self._v13_steering_context = None
        if press["active"]:
            event.data.setdefault("pressing_trigger", press["trigger"])
            event.data.setdefault("pressing_trigger_strength", round(float(press["pressure_delta"]), 3))
            event.data.setdefault("pressing_depth_tradeoff", round(float(press["depth_tradeoff"]), 3))
        if decision in {"carry", "dribble", "shoot", "cross", "cutback"}:
            event.data.setdefault("defensive_steering", steering["intent"])
            event.data.setdefault("steering_quality", round(float(steering["quality"]), 3))
        return event


MatchEngine = MatchEngineV13PressingTriggers
