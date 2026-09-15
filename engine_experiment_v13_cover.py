from __future__ import annotations

"""Experimental v1.3 layer: contextual defensive cover relationships.

This layer sits on top of marking/handoffs. The primary defensive intention is
still unique. Coverage is not a second independent defensive intention and is
not a free generic bonus: it describes which *other* defender protects the
space created when the primary defender/marker commits to the ball, runner or
wide lane.

Coverage can therefore mitigate a specific trade-off (depth behind a press,
inside lane behind a contain, cutback/box space behind a cross block, or the
zone vacated by a runner-track), but every cover shifts a defender away from
some other space.
"""

from typing import Optional

from engine import Band, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_marking import MatchEngineV13Marking


VERSION = "1.3-candidate-spatial-creativity-boldness-offball-body-defense-marking-cover"


class MatchEngineV13Cover(MatchEngineV13Marking):
    """Adds one contextual cover relationship behind the primary defender."""

    # ---------------------------- cover selection ----------------------------

    @staticmethod
    def _coverage_type(plan: dict, zone: Zone, kind: Optional[str]) -> Optional[str]:
        intent = str(plan.get("intent") or "")
        kind = (kind or plan.get("kind") or "open_play").lower()

        # When the primary intention is already the safety action, do not create
        # a second safety shield on top of it.
        if intent in {"cover_depth", "protect_box", "block_shot", "close_cutback", "delay"}:
            return None

        if intent == "press_ball":
            return "cover_inside" if zone.lane != Lane.CENTER else "cover_depth"
        if intent == "contain":
            return "cover_inside"
        if intent == "block_cross" or kind == "cross":
            return "protect_cutback"
        if intent == "track_runner":
            return "protect_vacated_zone"
        if intent == "block_lane" and kind in {"through_ball", "progressive_pass", "long_ball"}:
            return "cover_depth"
        return None

    @staticmethod
    def _coverage_skill(ps: PlayerState, cover_type: str) -> float:
        if cover_type == "cover_depth":
            raw = (
                0.31 * ps.effective("anticipation") + 0.29 * ps.effective("positioning")
                + 0.20 * ps.effective("pace") + 0.09 * ps.effective("composure")
                + 0.06 * ps.effective("stamina") + 0.05 * ps.effective("discipline")
            )
        elif cover_type == "cover_inside":
            raw = (
                0.34 * ps.effective("positioning") + 0.27 * ps.effective("anticipation")
                + 0.15 * ps.effective("tackling") + 0.10 * ps.effective("composure")
                + 0.08 * ps.effective("discipline") + 0.06 * ps.effective("pace")
            )
        elif cover_type == "protect_cutback":
            raw = (
                0.35 * ps.effective("positioning") + 0.28 * ps.effective("anticipation")
                + 0.14 * ps.effective("tackling") + 0.09 * ps.effective("composure")
                + 0.08 * ps.effective("discipline") + 0.06 * ps.effective("strength")
            )
        else:  # protect_vacated_zone
            raw = (
                0.36 * ps.effective("positioning") + 0.30 * ps.effective("anticipation")
                + 0.12 * ps.effective("pace") + 0.10 * ps.effective("composure")
                + 0.07 * ps.effective("discipline") + 0.05 * ps.effective("stamina")
            )
        return clamp(raw / 100.0)

    @staticmethod
    def _coverage_role_affinity(ps: PlayerState, zone: Zone, cover_type: str) -> float:
        pos = ps.player.position.upper()
        if pos == "GK":
            return 0.01

        if cover_type == "cover_depth":
            base = {"CB": 1.30, "DM": 1.04, "LB": 0.94, "RB": 0.94, "CM": 0.62}.get(pos, 0.20)
        elif cover_type == "cover_inside":
            base = {"DM": 1.22, "CB": 1.12, "CM": 0.90, "LB": 0.74, "RB": 0.74}.get(pos, 0.24)
        elif cover_type == "protect_cutback":
            base = {"CB": 1.24, "DM": 1.10, "LB": 0.92, "RB": 0.92, "CM": 0.72}.get(pos, 0.20)
        else:  # protect_vacated_zone
            base = {"CB": 1.15, "DM": 1.12, "LB": 0.96, "RB": 0.96, "CM": 0.78}.get(pos, 0.22)

        # The covering player should normally be adjacent to the threatened
        # lane, not the same wide defender who already jumped to the ball.
        if zone.lane == Lane.LEFT:
            if pos in {"CB", "DM"}:
                base *= 1.10
            elif pos == "RB":
                base *= 0.90
        elif zone.lane == Lane.RIGHT:
            if pos in {"CB", "DM"}:
                base *= 1.10
            elif pos == "LB":
                base *= 0.90
        elif pos in {"CB", "DM"}:
            base *= 1.08
        return base

    def _best_cover_defender(
        self,
        defending_team: int,
        zone: Zone,
        cover_type: str,
        *,
        exclude_names: set[str],
    ) -> tuple[Optional[PlayerState], float]:
        rows: list[tuple[PlayerState, float]] = []
        for ps in self.teams[defending_team].on_field:
            if ps.player.position.upper() == "GK" or ps.player.name in exclude_names:
                continue
            skill = self._coverage_skill(ps, cover_type)
            affinity = self._coverage_role_affinity(ps, zone, cover_type)
            energy = 0.82 + 0.18 * ps.energy
            score = affinity * (0.56 + 0.44 * skill) * energy
            rows.append((ps, score))
        if not rows:
            return None, 0.0
        return max(rows, key=lambda row: row[1])

    def _coverage_activation(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        plan: dict,
        cover_type: str,
    ) -> float:
        defending_team = 1 - attacking_team
        tactics = self.teams[defending_team].team.tactics
        transition = clamp(float(getattr(self.state, "transition_boost", 0.0)))
        availability = clamp(float(ctx.get("defending_availability", 1.0)))
        marking = plan.get("marking") if isinstance(plan.get("marking"), dict) else {}
        mode = marking.get("mode")

        score = 0.22 + 0.30 * tactics.compactness + 0.12 * availability + 0.10 * (1.0 - transition)
        score += {"zonal": 0.12, "hybrid": 0.09, "man": 0.035}.get(mode, 0.06)

        if cover_type == "cover_depth":
            score += 0.13 * tactics.defensive_line + 0.10 * clamp(float(ctx.get("space_behind", 0.4)))
        elif cover_type == "cover_inside":
            score += 0.09 * tactics.compactness + 0.05 * (1.0 if zone.lane != Lane.CENTER else 0.0)
        elif cover_type == "protect_cutback":
            score += 0.11 * (1.0 if zone.band in {Band.ATT, Band.BOX} else 0.0) + 0.06 * tactics.compactness
        else:
            score += 0.09 * tactics.compactness

        # A live hand-off costs attention for a moment. Strict man marking also
        # leaves fewer free defenders for clean cover relationships.
        if marking.get("switched"):
            score -= 0.035
        if mode == "man" and marking.get("target"):
            score -= 0.045
        return clamp(score)

    @staticmethod
    def _coverage_effects(cover_type: str, quality: float, activation: float) -> dict:
        q = clamp((quality - 0.48) / 0.48) * clamp(activation)
        effects = {
            "pressure_delta": 0.0,
            "space_delta": 0.0,
            "depth_delta": 0.0,
            "wide_space_delta": 0.0,
            "pass_lane_control": 0.0,
            "runner_control": 0.0,
            "dribble_control": 0.0,
            "cross_control": 0.0,
            "box_protection": 0.0,
        }
        if cover_type == "cover_depth":
            effects["depth_delta"] = -0.026 * q
            effects["runner_control"] = 0.016 * q
            effects["pressure_delta"] = -0.004 * q
        elif cover_type == "cover_inside":
            effects["space_delta"] = -0.015 * q
            effects["pass_lane_control"] = 0.017 * q
            effects["wide_space_delta"] = 0.011 * q
        elif cover_type == "protect_cutback":
            effects["pass_lane_control"] = 0.018 * q
            effects["box_protection"] = 0.020 * q
            effects["pressure_delta"] = -0.004 * q
            effects["wide_space_delta"] = 0.006 * q
        else:  # protect_vacated_zone
            effects["space_delta"] = -0.010 * q
            effects["runner_control"] = 0.015 * q
            effects["pressure_delta"] = -0.005 * q
        return effects

    def _coverage_plan(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        plan: dict,
        *,
        kind: Optional[str] = None,
    ) -> dict:
        cover_type = self._coverage_type(plan, zone, kind)
        if cover_type is None:
            return {
                "active": False,
                "type": None,
                "defender": None,
                "defender_name": None,
                "quality": 0.0,
                "activation": 0.0,
                "effects": self._coverage_effects("cover_depth", 0.0, 0.0),
            }

        defending_team = 1 - attacking_team
        marking = plan.get("marking") if isinstance(plan.get("marking"), dict) else {}
        exclude = {str(plan.get("defender_name"))}
        marker_name = marking.get("marker_name")
        if marker_name:
            exclude.add(str(marker_name))

        defender, score = self._best_cover_defender(
            defending_team, zone, cover_type, exclude_names=exclude
        )
        activation = self._coverage_activation(attacking_team, zone, ctx, plan, cover_type)
        active = bool(defender is not None and activation >= 0.56)
        quality = self._coverage_skill(defender, cover_type) if defender is not None else 0.0
        effects = self._coverage_effects(cover_type, quality, activation) if active else self._coverage_effects(cover_type, 0.0, 0.0)
        return {
            "active": active,
            "type": cover_type,
            "defender": defender,
            "defender_name": None if defender is None else defender.player.name,
            "quality": quality,
            "score": score,
            "activation": activation,
            "effects": effects,
        }

    @staticmethod
    def _merge_coverage_effects(base_effects: dict, coverage: dict) -> dict:
        merged = dict(base_effects)
        if not coverage.get("active"):
            return merged

        eff = coverage["effects"]
        ctype = coverage["type"]

        # Coverage primarily repairs the trade-off created by the first
        # defender's action. It does not simply stack a second full-strength
        # defensive intention.
        if ctype == "cover_depth":
            recovery = abs(float(eff["depth_delta"]))
            if merged.get("depth_delta", 0.0) > 0.0:
                merged["depth_delta"] = max(0.0, float(merged["depth_delta"]) - recovery)
            else:
                merged["depth_delta"] = float(merged.get("depth_delta", 0.0)) - min(recovery, 0.010)
            merged["runner_control"] = float(merged.get("runner_control", 0.0)) + eff["runner_control"]
            merged["pressure_delta"] = float(merged.get("pressure_delta", 0.0)) + eff["pressure_delta"]
        else:
            for key, value in eff.items():
                merged[key] = float(merged.get(key, 0.0)) + float(value)

        return merged

    # ---------------------------- integration / diagnostics ----------------------------

    def _build_defensive_plan(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        *,
        kind: Optional[str] = None,
        target: Optional[str] = None,
    ) -> dict:
        plan = super()._build_defensive_plan(
            attacking_team, zone, ctx, kind=kind, target=target
        )
        coverage = self._coverage_plan(
            attacking_team, zone, ctx, plan, kind=kind
        )
        plan["effects"] = self._merge_coverage_effects(plan["effects"], coverage)
        plan["coverage"] = coverage
        return plan

    @staticmethod
    def _apply_plan_effects(ctx: dict, plan: dict) -> dict:
        adjusted = MatchEngineV13Marking._apply_plan_effects(ctx, plan)
        coverage = plan.get("coverage")
        if isinstance(coverage, dict):
            adjusted["coverage_active"] = bool(coverage.get("active"))
            adjusted["coverage_type"] = coverage.get("type")
            adjusted["coverage_actor"] = coverage.get("defender_name")
            adjusted["coverage_quality"] = round(float(coverage.get("quality", 0.0)), 6)
            adjusted["coverage_activation"] = round(float(coverage.get("activation", 0.0)), 6)
        return adjusted

    def coverage_diagnostic(
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
        coverage = plan["coverage"]
        adjusted = self._apply_plan_effects(context, plan)
        return {
            "intent": plan["intent"],
            "primary_defender": plan["defender_name"],
            "marking_mode": plan.get("marking", {}).get("mode"),
            "marker": plan.get("marking", {}).get("marker_name"),
            "active": coverage["active"],
            "coverage_type": coverage["type"],
            "cover_defender": coverage["defender_name"],
            "coverage_quality": coverage["quality"],
            "activation": coverage["activation"],
            "effects": dict(coverage["effects"]),
            "base": context,
            "adjusted": adjusted,
        }


MatchEngine = MatchEngineV13Cover
