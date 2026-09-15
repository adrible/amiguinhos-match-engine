from __future__ import annotations

"""v1.3 match-intelligence stage 5: choose what to do after winning the ball."""

from copy import deepcopy

from engine import Band, Zone, clamp
from engine_experiment_v13_tempo_control import MatchEngineV13TempoControl

VERSION = "1.3-candidate-transition-choice"


class MatchEngineV13TransitionChoice(MatchEngineV13TempoControl):
    def _ensure_transition_choice_state(self) -> None:
        if not hasattr(self, "_v13_transition_plan"):
            self._v13_transition_plan = None

    def export_state(self) -> dict:
        data = super().export_state()
        self._ensure_transition_choice_state()
        data["v13_transition_plan"] = deepcopy(self._v13_transition_plan)
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_transition_plan")
        obj._v13_transition_plan = deepcopy(raw) if isinstance(raw, dict) else None
        return obj

    def transition_choice_diagnostic(self, team: int, zone: Zone, transition: float) -> dict:
        outfield = [
            ps for ps in self.teams[team].on_field
            if not ps.red and ps.player.position.upper() != "GK"
        ]
        if outfield:
            runner_values = sorted(
                (
                    0.36 * ps.effective("pace") / 100.0
                    + 0.35 * ps.effective("off_ball") / 100.0
                    + 0.29 * ps.effective("anticipation") / 100.0
                    for ps in outfield
                ),
                reverse=True,
            )
            control_values = sorted(
                (
                    0.34 * ps.effective("passing") / 100.0
                    + 0.34 * ps.effective("vision") / 100.0
                    + 0.32 * ps.effective("composure") / 100.0
                    for ps in outfield
                ),
                reverse=True,
            )
            runner_quality = sum(runner_values[:4]) / min(4, len(runner_values))
            control_quality = sum(control_values[:4]) / min(4, len(control_values))
        else:
            runner_quality = control_quality = 0.35

        losing_team = 1 - team
        try:
            rest = self.rest_defense_diagnostic(losing_team, zone.mirror())
            rest_quality = float(rest["quality"])
        except Exception:
            rest_quality = 0.52
        tactics = self.teams[team].team.tactics
        transition = clamp(float(transition))
        h, a = self.score
        diff = (h - a) if team == 0 else (a - h)
        late = clamp((self.minute - 60.0) / 30.0)
        urgency = clamp(max(0, -diff) * late)
        advantage = clamp(
            0.32 * transition
            + 0.24 * runner_quality
            + 0.17 * (1.0 - rest_quality)
            + 0.13 * tactics.counter
            + 0.08 * max(0.0, tactics.mentality)
            + 0.06 * urgency
        )

        if diff > 0 and self.minute >= 70.0:
            mode = "consolidate"
        elif transition >= 0.30 and advantage >= 0.52:
            mode = "counterattack"
        elif control_quality >= 0.68 and (rest_quality >= 0.56 or transition < 0.34):
            mode = "consolidate"
        else:
            mode = "reset"
        strength = clamp(0.42 + 0.38 * max(advantage, control_quality) + 0.20 * transition)
        return {
            "mode": mode,
            "advantage": advantage,
            "strength": strength,
            "runner_quality": runner_quality,
            "control_quality": control_quality,
            "opponent_rest_defense": rest_quality,
            "transition": transition,
        }

    def _active_transition_plan(self, team: int) -> dict | None:
        self._ensure_transition_choice_state()
        marker = self._v13_transition_plan
        if not marker:
            return None
        if self.state.second > float(marker.get("until", 0.0)):
            self._v13_transition_plan = None
            return None
        if int(marker.get("team", -1)) != int(team):
            return None
        return marker

    def _switch_possession(self, new_team, zone, transition=0.0):
        super()._switch_possession(new_team, zone, transition=transition)
        self._ensure_transition_choice_state()
        if float(transition) <= 0.14:
            self._v13_transition_plan = None
            return
        diag = self.transition_choice_diagnostic(new_team, zone, transition)
        self._v13_transition_plan = {
            "team": int(new_team),
            "until": float(self.state.second) + 8.0 + 10.0 * clamp(float(transition)),
            **diag,
        }

    def _spatial_context(self, attacking_team: int, zone: Zone) -> dict:
        ctx = super()._spatial_context(attacking_team, zone)
        marker = self._active_transition_plan(attacking_team)
        if not marker:
            return ctx
        mode = str(marker["mode"])
        strength = clamp(float(marker["strength"]))
        if mode == "counterattack":
            ctx["support"] = clamp(float(ctx.get("support", 0.5)) + 0.024 * strength)
        elif mode in {"consolidate", "reset"}:
            ctx["support"] = clamp(float(ctx.get("support", 0.5)) + 0.018 * strength)
        ctx["transition_choice"] = mode
        ctx["transition_choice_strength"] = strength
        ctx["transition_advantage"] = float(marker["advantage"])
        return ctx

    def _decision_weights(self, actor, zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        mode = str(ctx.get("transition_choice", ""))
        strength = clamp(float(ctx.get("transition_choice_strength", 0.0)))
        out = []
        for action, weight in items:
            modifier = 1.0
            if mode == "counterattack":
                if action in {"progressive_pass", "through_ball", "carry", "dribble"}:
                    modifier += 0.27 * strength
                elif action == "safe_pass":
                    modifier -= 0.18 * strength
            elif mode == "consolidate":
                if action in {"safe_pass", "switch", "progressive_pass"}:
                    modifier += 0.20 * strength
                elif action in {"shoot", "dribble", "long_ball"}:
                    modifier -= 0.13 * strength
            elif mode == "reset":
                if action == "safe_pass":
                    modifier += 0.28 * strength
                elif action == "switch":
                    modifier += 0.12 * strength
                elif action in {"through_ball", "shoot", "dribble", "long_ball"}:
                    modifier -= 0.16 * strength
            out.append((action, max(0.0, float(weight) * clamp(modifier, 0.76, 1.28))))
        return out

    def _execute_decision(self, team, actor, zone, decision, ctx):
        marker = self._active_transition_plan(team)
        event = super()._execute_decision(team, actor, zone, decision, ctx)
        if marker:
            mode = str(marker["mode"])
            if self.state.possession == team:
                if mode == "consolidate" and decision in {"safe_pass", "switch", "progressive_pass"}:
                    self.state.transition_boost *= 0.72
                elif mode == "reset" and decision in {"safe_pass", "switch"}:
                    self.state.transition_boost *= 0.50
            event.data.setdefault("transition_choice", mode)
            event.data.setdefault("transition_choice_strength", round(float(marker["strength"]), 3))
            event.data.setdefault("transition_advantage", round(float(marker["advantage"]), 3))
            event.data.setdefault("opponent_rest_defense", round(float(marker["opponent_rest_defense"]), 3))
        return event


MatchEngine = MatchEngineV13TransitionChoice
