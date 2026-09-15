from __future__ import annotations

"""Experimental v1.3 layer: contextual defensive execution errors.

Errors are not injected to manufacture chances or goals.  The engine first
builds the normal defensive plan, including marking, cover, communication,
offside behaviour and local overload response.  It then estimates the burden on
the concrete defender from player quality, fatigue and the actual geometry of
the moment.

Only during a live action can that contextual risk realise. Diagnostics are
pure and do not consume RNG.  A realised error changes the *state of the duel*
(pressure, space, runner/lane control, etc.); it never directly chooses a shot,
goal, turnover or scoreline.
"""

from dataclasses import replace
from typing import Callable, Optional, TypeVar

from engine import Band, Event, PendingAction, PlayerState, Zone, clamp
from engine_experiment_v13_overload import MatchEngineV13Overload


VERSION = (
    "1.3-candidate-spatial-creativity-boldness-offball-body-defense-"
    "marking-cover-communication-offside-overload-errors"
)

T = TypeVar("T")


class MatchEngineV13Errors(MatchEngineV13Overload):
    """Adds occasional, context-driven defensive execution failures."""

    # ---------------------------- deterministic risk model ----------------------------

    @staticmethod
    def _error_kind_multiplier(kind: Optional[str]) -> float:
        return {
            "safe_pass": 0.55,
            "progressive_pass": 0.86,
            "long_ball": 0.84,
            "carry": 0.88,
            "dribble": 1.04,
            "cross": 1.02,
            "cutback": 1.10,
            "through_ball": 1.14,
            "shoot": 1.08,
            "rebound": 1.08,
        }.get(str(kind or "open_play"), 0.82)

    @staticmethod
    def _overload_severity(plan: dict) -> float:
        overload = plan.get("overload") if isinstance(plan.get("overload"), dict) else {}
        if not overload.get("active"):
            return 0.0
        attackers = max(1, int(overload.get("attackers_count", 1)))
        defenders = max(1, int(overload.get("defenders_count", 1)))
        return clamp((attackers - defenders) / float(attackers))

    @staticmethod
    def _coordination_stress(plan: dict) -> tuple[float, float, float]:
        marking = plan.get("marking") if isinstance(plan.get("marking"), dict) else {}
        communication = plan.get("communication") if isinstance(plan.get("communication"), dict) else {}

        switched = bool(marking.get("switched"))
        handoff_quality = clamp(float(marking.get("handoff_quality", 1.0)))
        handoff_stress = (1.0 - handoff_quality) if switched else 0.0

        if communication.get("active"):
            communication_quality = clamp(float(communication.get("quality", 0.0)))
            communication_stress = 1.0 - communication_quality
        else:
            communication_quality = 1.0
            communication_stress = 0.0
        return handoff_stress, communication_stress, communication_quality

    def _defensive_error_profile(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        plan: dict,
        *,
        kind: Optional[str],
        target: Optional[str],
    ) -> dict:
        defender = plan.get("defender")
        if isinstance(defender, PlayerState):
            defender_quality = clamp(
                0.29 * defender.effective("positioning") / 100.0
                + 0.25 * defender.effective("anticipation") / 100.0
                + 0.18 * defender.effective("composure") / 100.0
                + 0.13 * defender.effective("discipline") / 100.0
                + 0.10 * defender.effective("tackling") / 100.0
                + 0.05 * defender.effective("pace") / 100.0
            )
            fatigue = clamp(1.0 - defender.energy)
            yellow = bool(defender.yellow)
            aggression = clamp(defender.effective("aggression") / 100.0)
            discipline = clamp(defender.effective("discipline") / 100.0)
            defender_name = defender.player.name
        else:
            defender_quality = clamp(float(plan.get("quality", 0.65)))
            fatigue = 0.0
            yellow = False
            aggression = 0.55
            discipline = 0.70
            defender_name = plan.get("defender_name")

        transition = clamp(float(getattr(self.state, "transition_boost", 0.0)))
        space = clamp(float(ctx.get("space", 0.50)))
        depth = clamp(float(ctx.get("space_behind", 0.45)))
        support = clamp(float(ctx.get("support", 0.50)))
        availability = clamp(float(ctx.get("defending_availability", 1.0)))
        overload = self._overload_severity(plan)
        handoff_stress, communication_stress, communication_quality = self._coordination_stress(plan)

        zone_stress = {Band.DEF: 0.00, Band.MID: 0.015, Band.ATT: 0.045, Band.BOX: 0.070}[zone.band]
        structural_stress = clamp(
            0.25 * transition
            + 0.20 * space
            + 0.18 * depth
            + 0.12 * support
            + 0.10 * (1.0 - availability)
            + 0.15 * overload
        )

        risk = (
            0.003
            + 0.060 * ((1.0 - defender_quality) ** 1.25)
            + 0.030 * fatigue
            + 0.035 * structural_stress
            + 0.020 * overload
            + 0.018 * handoff_stress
            + 0.012 * communication_stress
            + zone_stress
        )
        if yellow:
            risk += 0.004
        # High aggression with low discipline makes an overcommit/mistiming a
        # little more likely, without treating aggression itself as "bad".
        risk += 0.006 * max(0.0, aggression - discipline)
        # A very clear call can remove a little uncertainty; it never grants a
        # generic defensive bonus beyond lowering the chance of a coordination
        # mistake.
        risk -= 0.006 * max(0.0, communication_quality - 0.78)
        risk *= self._error_kind_multiplier(kind)
        risk = clamp(risk, 0.001, 0.14)

        intent = str(plan.get("intent") or "")
        marking = plan.get("marking") if isinstance(plan.get("marking"), dict) else {}
        scores = {
            "bad_handoff": (
                0.18
                + (0.72 * handoff_stress if marking.get("switched") else -0.25)
                + 0.30 * communication_stress
            ),
            "lost_runner": (
                0.22
                + (0.25 if target else 0.0)
                + 0.30 * depth
                + 0.28 * overload
                + (0.18 if str(kind) in {"through_ball", "cross", "cutback"} else 0.0)
            ),
            "overcommit": (
                0.20
                + (0.28 if intent in {"press_ball", "contain", "block_cross"} else 0.0)
                + 0.26 * transition
                + 0.22 * depth
                + 0.16 * max(0.0, aggression - discipline)
            ),
            "wrong_lane_read": (
                0.18
                + (0.30 if str(kind) in {"progressive_pass", "long_ball", "through_ball", "cutback"} else 0.0)
                + 0.22 * support
                + 0.18 * space
            ),
            "late_block": (
                0.12
                + (0.52 if str(kind) in {"shoot", "rebound"} else 0.0)
                + 0.24 * space
                + 0.16 * fatigue
            ),
            "poor_body_position": (
                0.24
                + (0.24 if str(kind) in {"dribble", "carry", "cross"} else 0.0)
                + 0.22 * space
                + 0.14 * fatigue
            ),
        }
        error_type = max(scores.items(), key=lambda row: row[1])[0]
        severity = clamp(
            0.46
            + 2.2 * risk
            + 0.18 * transition
            + 0.16 * overload
            + 0.10 * fatigue,
            0.46,
            1.0,
        )
        return {
            "risk": risk,
            "error_type": error_type,
            "severity": severity,
            "defender": defender_name,
            "defender_quality": defender_quality,
            "fatigue": fatigue,
            "transition": transition,
            "space": space,
            "depth": depth,
            "support": support,
            "overload_severity": overload,
            "handoff_stress": handoff_stress,
            "communication_stress": communication_stress,
            "communication_quality": communication_quality,
            "kind": kind or "open_play",
            "target": target,
            "scores": scores,
        }

    @staticmethod
    def _apply_defensive_error(ctx: dict, profile: dict) -> dict:
        adjusted = dict(ctx)
        severity = clamp(float(profile.get("severity", 0.6)))
        error_type = str(profile.get("error_type") or "poor_body_position")

        if error_type == "bad_handoff":
            adjusted["runner_control"] = clamp(float(adjusted.get("runner_control", 0.0)) * (1.0 - 0.72 * severity), 0.0, 0.12)
            adjusted["space_behind"] = clamp(float(adjusted.get("space_behind", 0.45)) + 0.040 * severity)
            adjusted["space"] = clamp(float(adjusted.get("space", 0.50)) + 0.024 * severity)
            adjusted["pressure"] = clamp(float(adjusted.get("pressure", 0.50)) - 0.012 * severity)
        elif error_type == "lost_runner":
            adjusted["runner_control"] = clamp(float(adjusted.get("runner_control", 0.0)) * (1.0 - 0.62 * severity), 0.0, 0.12)
            adjusted["space_behind"] = clamp(float(adjusted.get("space_behind", 0.45)) + 0.045 * severity)
            adjusted["space"] = clamp(float(adjusted.get("space", 0.50)) + 0.020 * severity)
        elif error_type == "overcommit":
            adjusted["pressure"] = clamp(float(adjusted.get("pressure", 0.50)) - 0.034 * severity)
            adjusted["space"] = clamp(float(adjusted.get("space", 0.50)) + 0.046 * severity)
            adjusted["space_behind"] = clamp(float(adjusted.get("space_behind", 0.45)) + 0.028 * severity)
            adjusted["dribble_control"] = clamp(float(adjusted.get("dribble_control", 0.0)) * (1.0 - 0.45 * severity), 0.0, 0.12)
        elif error_type == "wrong_lane_read":
            adjusted["pass_lane_control"] = clamp(float(adjusted.get("pass_lane_control", 0.0)) * (1.0 - 0.70 * severity), 0.0, 0.12)
            adjusted["pressure"] = clamp(float(adjusted.get("pressure", 0.50)) - 0.014 * severity)
            adjusted["space"] = clamp(float(adjusted.get("space", 0.50)) + 0.032 * severity)
        elif error_type == "late_block":
            adjusted["box_protection"] = clamp(float(adjusted.get("box_protection", 0.0)) - 0.060 * severity, -0.03, 0.12)
            adjusted["pressure"] = clamp(float(adjusted.get("pressure", 0.50)) - 0.040 * severity)
            adjusted["space"] = clamp(float(adjusted.get("space", 0.50)) + 0.020 * severity)
        else:  # poor_body_position
            adjusted["dribble_control"] = clamp(float(adjusted.get("dribble_control", 0.0)) * (1.0 - 0.55 * severity), 0.0, 0.12)
            adjusted["cross_control"] = clamp(float(adjusted.get("cross_control", 0.0)) * (1.0 - 0.38 * severity), 0.0, 0.12)
            adjusted["pressure"] = clamp(float(adjusted.get("pressure", 0.50)) - 0.022 * severity)
            adjusted["space"] = clamp(float(adjusted.get("space", 0.50)) + 0.034 * severity)

        adjusted["defensive_error_realized"] = True
        adjusted["defensive_error_type"] = error_type
        adjusted["defensive_error_defender"] = profile.get("defender")
        adjusted["defensive_error_risk"] = round(float(profile.get("risk", 0.0)), 6)
        adjusted["defensive_error_severity"] = round(severity, 6)
        return adjusted

    # ---------------------------- one live draw per action window ----------------------------

    def _with_error_window(self, fn: Callable[..., T], *args, **kwargs) -> T:
        depth = int(getattr(self, "_v13_error_window_depth", 0))
        outer = depth == 0
        if outer:
            self._v13_error_window_roll = None
            self._v13_error_window_realized = None
        self._v13_error_window_depth = depth + 1
        try:
            result = fn(*args, **kwargs)
            if outer:
                realized = getattr(self, "_v13_error_window_realized", None)
                if isinstance(realized, dict) and isinstance(result, Event):
                    result.data.setdefault("defensive_error", {
                        "type": realized.get("error_type"),
                        "defender": realized.get("defender"),
                        "risk": round(float(realized.get("risk", 0.0)), 3),
                        "severity": round(float(realized.get("severity", 0.0)), 3),
                    })
            return result
        finally:
            self._v13_error_window_depth = depth
            if outer:
                self._v13_last_defensive_error = getattr(self, "_v13_error_window_realized", None)

    def _realise_defensive_error(self, profile: dict) -> bool:
        if int(getattr(self, "_v13_error_window_depth", 0)) <= 0:
            return False
        if isinstance(getattr(self, "_v13_error_window_realized", None), dict):
            return False
        roll = getattr(self, "_v13_error_window_roll", None)
        if roll is None:
            roll = self.rng.random()
            self._v13_error_window_roll = roll
        if float(roll) < float(profile.get("risk", 0.0)):
            realised = dict(profile)
            realised["roll"] = float(roll)
            self._v13_error_window_realized = realised
            return True
        return False

    # ---------------------------- integration ----------------------------

    def _context_for_action(
        self,
        team: int,
        zone: Zone,
        ctx: dict,
        kind: str,
        target: Optional[str] = None,
    ) -> tuple[dict, dict]:
        adjusted, plan = super()._context_for_action(team, zone, ctx, kind, target=target)
        profile = self._defensive_error_profile(
            team, zone, adjusted, plan, kind=kind, target=target
        )
        adjusted["defensive_error_risk"] = round(profile["risk"], 6)
        adjusted["defensive_error_likely_type"] = profile["error_type"]
        self._v13_last_defensive_error_profile = profile
        if self._realise_defensive_error(profile):
            adjusted = self._apply_defensive_error(adjusted, profile)
        return adjusted, plan

    def _progressive_action(self, team, actor, zone, kind, ctx):
        return self._with_error_window(
            super()._progressive_action, team, actor, zone, kind, ctx
        )

    def _carry(self, team, actor, zone, ctx):
        return self._with_error_window(super()._carry, team, actor, zone, ctx)

    def _create_or_resolve_danger(self, team, actor, zone, kind, ctx):
        return self._with_error_window(
            super()._create_or_resolve_danger, team, actor, zone, kind, ctx
        )

    def _resolve_shot(self, p: PendingAction):
        def resolve():
            neutral = {
                "pressure": clamp(p.pressure),
                "space": clamp(0.30 + 0.58 * p.danger),
                "space_behind": 0.48,
                "support": 0.50,
                "wide_space": 0.08,
                "defending_availability": 1.0,
            }
            old = getattr(self, "_v13_defense_hint", None)
            self._v13_defense_hint = {"kind": "shoot", "target": p.actor, "actor": p.actor}
            try:
                plan = self._build_defensive_plan(
                    p.team, p.zone, neutral, kind="shoot", target=p.actor
                )
            finally:
                self._v13_defense_hint = old
            baseline = self._apply_plan_effects(neutral, plan)
            profile = self._defensive_error_profile(
                p.team, p.zone, baseline, plan, kind="shoot", target=p.actor
            )
            self._v13_last_defensive_error_profile = profile
            tuned = p
            if self._realise_defensive_error(profile):
                errored = self._apply_defensive_error(baseline, profile)
                pressure_delta = float(errored["pressure"]) - float(baseline["pressure"])
                tuned = replace(p, pressure=clamp(float(p.pressure) + pressure_delta))
            return super(MatchEngineV13Errors, self)._resolve_shot(tuned)

        return self._with_error_window(resolve)

    # ---------------------------- diagnostics ----------------------------

    def defensive_error_diagnostic(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: Optional[dict] = None,
        *,
        kind: Optional[str] = None,
        actor: Optional[str] = None,
        target: Optional[str] = None,
    ) -> dict:
        context = dict(ctx or {
            "pressure": 0.48,
            "space": 0.52,
            "space_behind": 0.45,
            "support": 0.50,
            "wide_space": 0.10,
            "defending_availability": 1.0,
        })
        old = getattr(self, "_v13_defense_hint", None)
        self._v13_defense_hint = {"kind": kind, "target": target, "actor": actor}
        try:
            plan = self._build_defensive_plan(
                attacking_team, zone, context, kind=kind, target=target
            )
        finally:
            self._v13_defense_hint = old
        adjusted = self._apply_plan_effects(context, plan)
        profile = self._defensive_error_profile(
            attacking_team, zone, adjusted, plan, kind=kind, target=target
        )
        if_error = self._apply_defensive_error(adjusted, profile)
        return {
            "risk": profile["risk"],
            "likely_type": profile["error_type"],
            "severity": profile["severity"],
            "defender": profile["defender"],
            "defender_quality": profile["defender_quality"],
            "fatigue": profile["fatigue"],
            "transition": profile["transition"],
            "overload_severity": profile["overload_severity"],
            "handoff_stress": profile["handoff_stress"],
            "communication_stress": profile["communication_stress"],
            "scores": dict(profile["scores"]),
            "base": context,
            "defended": adjusted,
            "if_error": if_error,
        }


MatchEngine = MatchEngineV13Errors
