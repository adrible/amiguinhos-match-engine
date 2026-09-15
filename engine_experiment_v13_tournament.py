from __future__ import annotations

"""v1.3 tournament-aware decision layer.

Competition context changes intentions, not player ability. The engine consumes
only a JSON-safe snapshot supplied by ``TournamentStateV13`` or another trusted
competition controller. No future results are inferred here.
"""

from copy import deepcopy

from engine import PlayerState, Zone, clamp
from engine_experiment_v13_awards import MatchEngineV13Awards
from engine_experiment_v13_knockout import MatchEngineV13Knockout


class MatchEngineV13TournamentContext(MatchEngineV13Awards):
    def __init__(self, *args, tournament_context: dict | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._v13_tournament_context = self._normalise_tournament_context(tournament_context)

    @staticmethod
    def _normalise_tournament_context(raw: dict | None) -> dict | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise TypeError("tournament_context must be a mapping or None")
        context = deepcopy(raw)
        team_context = context.get("team_context", {})
        if not isinstance(team_context, dict):
            raise TypeError("team_context must be a mapping")
        for side in ("0", "1"):
            row = team_context.get(side, {})
            if row is not None and not isinstance(row, dict):
                raise TypeError(f"team_context[{side}] must be a mapping")
        policy = context.get("knowledge_policy")
        if policy is not None and "future" in str(policy).lower() and "only" not in str(policy).lower():
            raise ValueError("tournament context may not advertise future knowledge")
        return context

    def set_tournament_context(self, raw: dict | None) -> None:
        self._v13_tournament_context = self._normalise_tournament_context(raw)

    def tournament_context_diagnostic(self, team: int | None = None):
        if getattr(self, "_v13_tournament_context", None) is None:
            return None
        if team is None:
            return deepcopy(self._v13_tournament_context)
        return deepcopy(self._team_tournament_context(int(team)))

    def _team_tournament_context(self, team: int) -> dict:
        raw = getattr(self, "_v13_tournament_context", None)
        if raw is None:
            return {}
        team_context = raw.get("team_context", {})
        row = team_context.get(str(int(team)), {})
        return row if isinstance(row, dict) else {}

    def _competition_intent(self, team: int) -> tuple[float, float]:
        comp = self._team_tournament_context(team)
        return (
            clamp(float(comp.get("need_goal", 0.0))),
            clamp(float(comp.get("protect_result", 0.0))),
        )

    def _score_diff_for(self, team: int) -> int:
        """Competition-aware result state used by coaching systems."""
        match_diff = int(self.score[int(team)] - self.score[1 - int(team)])
        comp = self._team_tournament_context(team)
        if not comp:
            return match_diff
        need_goal, protect = self._competition_intent(team)
        aggregate_diff = comp.get("aggregate_diff")
        if aggregate_diff is not None:
            aggregate_diff = int(aggregate_diff)
            if aggregate_diff < 0:
                return -max(1, abs(aggregate_diff))
            if aggregate_diff > 0:
                return max(1, aggregate_diff)
            if need_goal >= 0.55:
                return -1
            if protect >= 0.55:
                return 1
            return 0
        if need_goal >= max(0.55, protect + 0.12):
            return -1
        if protect >= max(0.55, need_goal + 0.12):
            return 1
        return match_diff

    def game_management_diagnostic(self, team: int) -> dict:
        data = super().game_management_diagnostic(team)
        comp = self._team_tournament_context(team)
        if not comp:
            return data
        need_goal, protect = self._competition_intent(team)
        effective_diff = self._score_diff_for(team)
        late = float(data.get("late_factor", 0.0))
        short = float(data.get("short_handed", 0.0))
        extra = float(data.get("numerical_advantage", 0.0))
        data["match_score_diff"] = int(data.get("score_diff", 0))
        data["score_diff"] = int(effective_diff)
        data["competition_need_goal"] = need_goal
        data["competition_protect_result"] = protect
        data["competition_override"] = bool(
            effective_diff != data["match_score_diff"] or need_goal > 0.0 or protect > 0.0
        )
        data["clock_factor"] = clamp(
            1.0 + 0.085 * protect - 0.065 * need_goal - 0.018 * late * short,
            0.93,
            1.12,
        )
        data["risk_shift"] = clamp(
            0.32 * need_goal - 0.27 * protect - 0.06 * short + 0.04 * extra,
            -0.45,
            0.45,
        )
        return data

    def _decision_weights(self, actor: PlayerState, zone: Zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        team = self._team_for_player_state(actor)
        if team is None:
            return items
        comp = self._team_tournament_context(team)
        if not comp:
            return items
        need_goal, protect = self._competition_intent(team)
        time_pressure = 0.30 + 0.70 * clamp((self.minute - 45.0) / 45.0)
        chase = need_goal * time_pressure
        control = protect * (0.35 + 0.65 * clamp((self.minute - 55.0) / 35.0))
        factors: dict[str, float] = {}

        def mul(action: str, factor: float) -> None:
            factors[action] = factors.get(action, 1.0) * float(factor)

        if chase > 0.0:
            for action, factor in {
                "safe_pass": 1.0 - 0.06 * chase,
                "progressive_pass": 1.0 + 0.05 * chase,
                "through_ball": 1.0 + 0.08 * chase,
                "long_ball": 1.0 + 0.05 * chase,
                "dribble": 1.0 + 0.03 * chase,
                "cross": 1.0 + 0.04 * chase,
                "shoot": 1.0 + 0.06 * chase,
            }.items():
                mul(action, factor)
        if control > 0.0:
            for action, factor in {
                "safe_pass": 1.0 + 0.06 * control,
                "switch": 1.0 + 0.03 * control,
                "through_ball": 1.0 - 0.05 * control,
                "dribble": 1.0 - 0.04 * control,
                "shoot": 1.0 - 0.025 * control,
            }.items():
                mul(action, factor)

        return [
            (action, max(0.001, float(weight) * clamp(factors.get(action, 1.0), 0.78, 1.22)))
            for action, weight in items
        ]

    def _adaptation_profile(self, team: int) -> dict:
        profile = super()._adaptation_profile(team)
        comp = self._team_tournament_context(team)
        if not comp:
            return profile
        need_goal, protect = self._competition_intent(team)
        if max(need_goal, protect) < 0.55:
            return {**profile, "competition_context_applied": False}

        scores = dict(profile.get("scores") or {})
        minute = float(self.minute)
        effective_diff = self._score_diff_for(team)
        target = None
        if need_goal >= max(0.55, protect + 0.10):
            target = "chase_game"
            scores["protect_lead"] = -1.0
            if minute >= 58.0:
                urgency = clamp((minute - 58.0) / 32.0)
                scores[target] = max(
                    float(scores.get(target, -1.0)),
                    0.57 + 0.14 * need_goal + 0.14 * urgency,
                )
        elif protect >= max(0.55, need_goal + 0.10):
            target = "protect_lead"
            scores["chase_game"] = -1.0
            if minute >= 68.0:
                urgency = clamp((minute - 68.0) / 22.0)
                scores[target] = max(
                    float(scores.get(target, -1.0)),
                    0.56 + 0.13 * protect + 0.14 * urgency,
                )

        if target is None:
            return {
                **profile,
                "score_diff": effective_diff,
                "scores": scores,
                "competition_context_applied": True,
            }

        cooldown = dict(profile.get("cooldown") or {})
        count = int(cooldown.get("count", 0) or 0)
        threshold_fn = getattr(self, "_stable_threshold", None)
        if callable(threshold_fn):
            threshold = float(threshold_fn(target, count))
        else:
            threshold = 0.58 if target in {"chase_game", "protect_lead"} else 0.55
        target_score = float(scores.get(target, -1.0))
        response_used = getattr(self, "_response_used", None)
        already_used = bool(callable(response_used) and response_used(team, target))

        generic_blockers = {
            "too_early",
            "team_adaptation_limit",
            "cooldown",
            "progressive_adaptation_inertia",
        }
        reasons = [
            reason for reason in list(profile.get("blocked_reasons") or [])
            if reason in generic_blockers
        ]
        eligible = target_score >= threshold and not reasons and not already_used
        if already_used:
            reasons.append("competition_response_already_applied")
        if target_score < threshold:
            reasons.append("competition_evidence_below_threshold")

        return {
            **profile,
            "score_diff": effective_diff,
            "response": target if target_score >= 0.0 else None,
            "response_score": target_score,
            "threshold": threshold,
            "eligible": eligible,
            "blocked_reasons": reasons,
            "scores": scores,
            "competition_context_applied": True,
            "competition_target_response": target,
        }

    def _competition_boundary_context(self) -> dict | None:
        raw = getattr(self, "_v13_tournament_context", None)
        if not isinstance(raw, dict):
            return None
        if str(raw.get("stage_kind")) not in {"playoff", "knockout", "third_place", "final"}:
            return None
        home = self._team_tournament_context(0)
        if not home or not bool(home.get("decisive_leg", True)):
            return None
        aggregate_diff = home.get("aggregate_diff")
        if aggregate_diff is None:
            return None
        return {
            "stage_kind": raw.get("stage_kind"),
            "two_legged": bool(home.get("two_legged", False)),
            "decisive_leg": bool(home.get("decisive_leg", True)),
            "aggregate_diff": int(aggregate_diff),
        }

    def _check_period_boundary(self):
        context = self._competition_boundary_context()
        if context is None:
            return super()._check_period_boundary()
        if self.state.period_index >= len(self.state.period_markers):
            return None
        marker = self.state.period_markers[self.state.period_index]
        if self.minute < marker:
            return None

        # In a decisive knockout leg, continuation is determined by the tie,
        # not by the score of this leg in isolation.
        if marker == 90 and self.state.period_markers == [45, 90] and self.config.allow_extra_time:
            if int(context["aggregate_diff"]) == 0:
                return self._start_extra_time()
            return super(MatchEngineV13Knockout, self)._check_period_boundary()

        if marker == 120 and self.state.period_markers == [105, 120]:
            if int(context["aggregate_diff"]) == 0:
                return self._start_shootout()
            return super(MatchEngineV13Knockout, self)._check_period_boundary()

        return super()._check_period_boundary()

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["tournament_context"] = self.tournament_context_diagnostic()
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        data["v13_tournament_context"] = deepcopy(
            getattr(self, "_v13_tournament_context", None)
        )
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        obj._v13_tournament_context = cls._normalise_tournament_context(
            data.get("v13_tournament_context")
        )
        return obj


MatchEngine = MatchEngineV13TournamentContext

__all__ = ["MatchEngineV13TournamentContext", "MatchEngine"]
