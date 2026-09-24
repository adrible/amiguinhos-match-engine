from __future__ import annotations

"""v1.3 match-intelligence stage 3: inferred individual football habits.

Habits alter preference, never execution quality. They are derived from existing
attributes/role and do not add hidden numeric player attributes.
"""

from engine import Band, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_individual_adaptation import MatchEngineV13IndividualAdaptation

VERSION = "1.3-candidate-player-habits"


class MatchEngineV13PlayerHabits(MatchEngineV13IndividualAdaptation):
    def player_habit_profile(self, actor: PlayerState) -> dict:
        pos = actor.player.position.upper()
        crossing = clamp(actor.effective("crossing") / 100.0)
        vision = clamp(actor.effective("vision") / 100.0)
        passing = clamp(actor.effective("passing") / 100.0)
        technique = clamp(actor.effective("technique") / 100.0)
        composure = clamp(actor.effective("composure") / 100.0)
        dribbling = clamp(actor.effective("dribbling") / 100.0)
        pace = clamp(actor.effective("pace") / 100.0)
        off_ball = clamp(actor.effective("off_ball") / 100.0)
        anticipation = clamp(actor.effective("anticipation") / 100.0)
        heading = clamp(actor.effective("heading") / 100.0)
        finishing = clamp(actor.effective("finishing") / 100.0)
        long_shots = clamp(actor.effective("long_shots") / 100.0)
        explicit_boldness = getattr(actor.player, "boldness", getattr(actor.player, "ousadia", 50))
        boldness = clamp(float(explicit_boldness) / 100.0)
        wide_role = 1.0 if pos in {"LW", "RW", "LB", "RB"} else 0.0
        attacking_role = 1.0 if pos in {"ST", "AM", "LW", "RW"} else 0.0

        scores = {
            "early_cross": clamp(0.46 * crossing + 0.20 * vision + 0.14 * technique + 0.12 * wide_role + 0.08 * composure),
            "carry_first": clamp(0.40 * dribbling + 0.25 * pace + 0.20 * technique + 0.10 * boldness + 0.05 * attacking_role),
            "quick_combination": clamp(0.31 * passing + 0.25 * vision + 0.23 * technique + 0.21 * composure),
            "vertical_risk": clamp(0.32 * vision + 0.28 * passing + 0.18 * boldness + 0.12 * technique + 0.10 * anticipation),
            "shoot_on_sight": clamp(0.37 * long_shots + 0.25 * finishing + 0.20 * composure + 0.13 * technique + 0.05 * attacking_role),
            "far_post_attack": clamp(0.34 * off_ball + 0.25 * anticipation + 0.22 * heading + 0.14 * pace + 0.05 * attacking_role),
        }
        dominant = max(scores, key=lambda name: (scores[name], name))
        return {**scores, "dominant": dominant, "dominant_score": scores[dominant]}

    def _decision_weights(self, actor, zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        habits = self.player_habit_profile(actor)
        out = []
        for action, weight in items:
            modifier = 1.0
            if action == "cross" and zone.lane != Lane.CENTER and zone.band in {Band.ATT, Band.BOX}:
                modifier += 0.22 * (float(habits["early_cross"]) - 0.50)
            if action in {"carry", "dribble"}:
                modifier += 0.18 * (float(habits["carry_first"]) - 0.50)
            if action in {"safe_pass", "progressive_pass"}:
                modifier += 0.13 * (float(habits["quick_combination"]) - 0.50)
            if action in {"progressive_pass", "through_ball", "long_ball"}:
                modifier += 0.16 * (float(habits["vertical_risk"]) - 0.50)
            if action == "shoot" and zone.band in {Band.ATT, Band.BOX}:
                modifier += 0.20 * (float(habits["shoot_on_sight"]) - 0.50)
            out.append((action, max(0.0, float(weight) * clamp(modifier, 0.80, 1.22))))
        return out

    def _base_target_weights(
        self,
        team: int,
        zone: Zone,
        actor: PlayerState | None,
        ctx: dict | None = None,
    ):
        weights = super()._base_target_weights(team, zone, actor, ctx)
        if zone.band not in {Band.ATT, Band.BOX} or zone.lane == Lane.CENTER:
            return weights
        out = []
        for ps, weight in weights:
            profile = self.player_habit_profile(ps)
            pos = ps.player.position.upper()
            far_side = (
                zone.lane == Lane.LEFT and pos in {"RW", "RB", "ST", "AM"}
            ) or (
                zone.lane == Lane.RIGHT and pos in {"LW", "LB", "ST", "AM"}
            )
            bonus = 1.0
            if far_side:
                bonus += 0.16 * max(0.0, float(profile["far_post_attack"]) - 0.52)
            out.append((ps, float(weight) * bonus))
        return out

    def _execute_decision(self, team, actor, zone, decision, ctx):
        habits = self.player_habit_profile(actor)
        event = super()._execute_decision(team, actor, zone, decision, ctx)
        mapping = {
            "cross": "early_cross",
            "carry": "carry_first",
            "dribble": "carry_first",
            "safe_pass": "quick_combination",
            "progressive_pass": "vertical_risk",
            "through_ball": "vertical_risk",
            "long_ball": "vertical_risk",
            "shoot": "shoot_on_sight",
        }
        used = mapping.get(decision)
        if used and float(habits.get(used, 0.0)) >= 0.64:
            event.data.setdefault("player_habit", used)
            event.data.setdefault("player_habit_strength", round(float(habits[used]), 3))
        return event


MatchEngine = MatchEngineV13PlayerHabits
