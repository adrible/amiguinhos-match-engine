from __future__ import annotations

"""v1.3 stage 5: shielding, body feints, physical duels and second-ball reading."""

from engine import PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_pressing_triggers import MatchEngineV13PressingTriggers

VERSION = "1.3-candidate-duels-second-balls"


class MatchEngineV13Duels(MatchEngineV13PressingTriggers):
    def _ensure_duel_state(self):
        if not hasattr(self, "_v13_second_ball_selection"):
            self._v13_second_ball_selection = None

    def protection_diagnostic(self, actor: PlayerState, zone: Zone, ctx: dict) -> dict:
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        body = self.body_orientation_diagnostic(
            actor, zone, ctx,
            source=getattr(self, "_v13_current_reception_source", "open_play"),
        )
        back = 1.0 if body["stance"] == "back_to_goal" else 0.0
        strength = clamp(actor.effective("strength") / 100.0)
        composure = clamp(actor.effective("composure") / 100.0)
        technique = clamp(actor.effective("technique") / 100.0)
        score = clamp(0.18 + 0.30 * strength + 0.20 * composure + 0.15 * technique + 0.17 * pressure + 0.10 * back)
        return {"score": score, "active": pressure >= 0.45 and score >= 0.55, "stance": body["stance"]}

    def _decision_weights(self, actor, zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        shield = self.protection_diagnostic(actor, zone, ctx)
        if not shield["active"]:
            return items
        out = []
        for action, weight in items:
            mod = 1.0
            if action == "safe_pass":
                mod = 1.10
            elif action == "carry":
                mod = 1.07
            elif action in {"shoot", "through_ball"} and shield["stance"] == "back_to_goal":
                mod = 0.93
            out.append((action, weight * mod))
        return out

    def _choose_target(self, team, zone, attacking=True, exclude=None):
        self._ensure_duel_state()
        marker = self._v13_second_ball_selection
        if marker and marker.get("team") == team and attacking:
            rows = []
            for ps in self.teams[team].on_field:
                if ps.player.name == exclude or ps.player.position.upper() == "GK" or ps.red:
                    continue
                score = (
                    0.34 * ps.effective("anticipation")
                    + 0.26 * ps.effective("positioning")
                    + 0.20 * ps.effective("off_ball")
                    + 0.12 * ps.effective("pace")
                    + 8.0 * ps.energy
                )
                rows.append((ps, max(1.0, score)))
            if rows:
                return weighted_choice(self.rng, rows)
        return super()._choose_target(team, zone, attacking=attacking, exclude=exclude)

    def _create_rebound(self, team, p, shooter, xg, blocked=False, post=False):
        self._ensure_duel_state()
        self._v13_second_ball_selection = {"team": team, "source": "rebound"}
        try:
            event = super()._create_rebound(team, p, shooter, xg, blocked=blocked, post=post)
        finally:
            self._v13_second_ball_selection = None
        event.data["second_ball_read"] = True
        next_name = event.data.get("next_player")
        if next_name:
            try:
                ps = self.teams[team].by_name(next_name)
                reaction = clamp((ps.effective("anticipation") + ps.effective("positioning") + ps.effective("off_ball")) / 300.0)
                event.data["second_ball_reaction"] = round(reaction, 3)
            except KeyError:
                pass
        return event

    def _physical_duel(self, team, actor, ctx):
        if float(ctx.get("pressure", 0.5)) < 0.52:
            return None
        defender_name = ctx.get("defensive_actor")
        if not defender_name:
            return None
        try:
            defender = self.teams[1 - team].by_name(defender_name)
        except KeyError:
            return None
        attack = 0.54 * actor.effective("strength") + 0.25 * actor.effective("composure") + 0.21 * actor.effective("technique")
        defend = 0.48 * defender.effective("strength") + 0.32 * defender.effective("tackling") + 0.20 * defender.effective("positioning")
        edge = clamp(0.5 + (attack - defend) / 160.0, 0.20, 0.80)
        return {"defender": defender_name, "attacker_edge": edge}

    def _execute_decision(self, team, actor, zone, decision, ctx):
        adjusted = dict(ctx)
        shield = self.protection_diagnostic(actor, zone, adjusted)
        annotations = {}
        if shield["active"] and decision in {"safe_pass", "carry", "dribble"}:
            score = shield["score"]
            adjusted["pressure"] = clamp(float(adjusted.get("pressure", 0.5)) - 0.025 * score)
            adjusted["space_behind"] = clamp(float(adjusted.get("space_behind", 0.4)) - 0.020 * score)
            annotations["shielding"] = True
            annotations["shielding_quality"] = round(score, 3)

        if decision in {"carry", "dribble"}:
            duel = self._physical_duel(team, actor, adjusted)
            if duel:
                edge = duel["attacker_edge"] - 0.5
                adjusted["pressure"] = clamp(float(adjusted.get("pressure", 0.5)) - 0.055 * edge)
                adjusted["space"] = clamp(float(adjusted.get("space", 0.5)) + 0.045 * edge)
                annotations["physical_duel"] = True
                annotations["duel_defender"] = duel["defender"]
                annotations["duel_attacker_edge"] = round(duel["attacker_edge"], 3)

        eligible_feint = decision in {"carry", "dribble", "shoot", "cross", "cutback", "through_ball", "progressive_pass"}
        pressure = clamp(float(adjusted.get("pressure", 0.5)))
        space = clamp(float(adjusted.get("space", 0.5)))
        if eligible_feint and 0.22 <= pressure <= 0.86:
            technique = clamp(actor.effective("technique") / 100.0)
            dribbling = clamp(actor.effective("dribbling") / 100.0)
            vision = clamp(actor.effective("vision") / 100.0)
            attempt_p = clamp(0.01 + 0.075 * technique + 0.065 * dribbling + 0.035 * vision + 0.025 * pressure - 0.035 * space, 0.01, 0.19)
            if self.rng.random() < attempt_p:
                defensive_quality = clamp(float(adjusted.get("defensive_quality", 0.55)))
                success_p = clamp(0.28 + 0.27 * technique + 0.20 * dribbling + 0.10 * vision - 0.22 * defensive_quality - 0.12 * pressure, 0.18, 0.78)
                success = self.rng.random() < success_p
                if success:
                    adjusted["pressure"] = clamp(pressure - 0.040)
                    adjusted["space"] = clamp(space + 0.030)
                else:
                    adjusted["pressure"] = clamp(pressure + 0.025)
                    adjusted["space"] = clamp(space - 0.015)
                annotations["body_feint"] = True
                annotations["body_feint_success"] = success
                annotations["body_feint_probability"] = round(attempt_p, 3)

        event = super()._execute_decision(team, actor, zone, decision, adjusted)
        for key, value in annotations.items():
            event.data.setdefault(key, value)
        return event


MatchEngine = MatchEngineV13Duels
