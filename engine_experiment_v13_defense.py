from __future__ import annotations

"""Experimental v1.3 layer: contextual defensive intelligence.

Extends the v1.3 contextual-reception candidate without touching frozen v1.2.

Core idea:
    attacking situation + zone + runner/ball threat + defensive tactics
    -> one primary defensive intention
    -> one defender best suited to that intention
    -> contextual pressure / lane / depth consequences

The layer deliberately avoids a generic defensive bonus stack. A defence cannot
simultaneously press the ball, track every runner, close every passing lane and
protect depth at full strength. It chooses one primary response, with a trade-off.
"""

from dataclasses import replace
from typing import Optional

from engine import Band, Lane, PendingAction, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_reception import MatchEngineV13Reception


VERSION = "1.3-candidate-spatial-creativity-boldness-offball-body-defense"


class MatchEngineV13Defense(MatchEngineV13Reception):
    """Adds contextual defensive decision-making.

    Defensive intelligence here means *choosing what to protect* in the current
    situation. It is not a hidden success bonus. The chosen response alters the
    footballing context (pressure, depth, lanes, box protection), while the
    defender's normal tackling/positioning/anticipation/pace still decide
    execution in the base engine.
    """

    # ---------------------------- player/role model ----------------------------

    @staticmethod
    def _defender_role_affinity(ps: PlayerState, zone: Zone, intent: str) -> float:
        pos = ps.player.position.upper()
        if pos == "GK":
            return 0.02

        table = {
            "press_ball": {
                "DM": 1.20, "CM": 1.08, "LB": 0.95, "RB": 0.95,
                "CB": 0.78, "AM": 0.52, "LW": 0.42, "RW": 0.42, "ST": 0.30,
            },
            "delay": {
                "CB": 1.18, "DM": 1.10, "LB": 1.02, "RB": 1.02,
                "CM": 0.82, "AM": 0.38, "LW": 0.32, "RW": 0.32, "ST": 0.18,
            },
            "block_lane": {
                "DM": 1.22, "CB": 1.08, "CM": 1.02, "LB": 0.92, "RB": 0.92,
                "AM": 0.52, "LW": 0.40, "RW": 0.40, "ST": 0.25,
            },
            "track_runner": {
                "CB": 1.22, "LB": 1.10, "RB": 1.10, "DM": 0.96,
                "CM": 0.60, "AM": 0.25, "LW": 0.25, "RW": 0.25, "ST": 0.12,
            },
            "cover_depth": {
                "CB": 1.28, "LB": 1.04, "RB": 1.04, "DM": 0.92,
                "CM": 0.52, "AM": 0.20, "LW": 0.18, "RW": 0.18, "ST": 0.10,
            },
            "contain": {
                "LB": 1.18, "RB": 1.18, "DM": 1.08, "CB": 1.02,
                "CM": 0.85, "AM": 0.38, "LW": 0.32, "RW": 0.32, "ST": 0.18,
            },
            "block_cross": {
                "LB": 1.24, "RB": 1.24, "CB": 0.98, "DM": 0.82,
                "CM": 0.56, "AM": 0.28, "LW": 0.32, "RW": 0.32, "ST": 0.16,
            },
            "protect_box": {
                "CB": 1.30, "DM": 1.02, "LB": 0.98, "RB": 0.98,
                "CM": 0.58, "AM": 0.22, "LW": 0.16, "RW": 0.16, "ST": 0.10,
            },
            "block_shot": {
                "CB": 1.28, "DM": 1.04, "LB": 0.96, "RB": 0.96,
                "CM": 0.62, "AM": 0.24, "LW": 0.16, "RW": 0.16, "ST": 0.10,
            },
            "close_cutback": {
                "CB": 1.16, "DM": 1.10, "LB": 1.02, "RB": 1.02,
                "CM": 0.72, "AM": 0.28, "LW": 0.20, "RW": 0.20, "ST": 0.10,
            },
        }
        affinity = table.get(intent, table["delay"]).get(pos, 0.35)

        # A defender on the relevant side is more likely to be the actual actor.
        if zone.lane == Lane.LEFT and pos in {"RB", "CB"}:
            affinity *= 1.10
        elif zone.lane == Lane.RIGHT and pos in {"LB", "CB"}:
            affinity *= 1.10
        elif zone.lane == Lane.CENTER and pos in {"CB", "DM", "CM"}:
            affinity *= 1.08
        return affinity

    @staticmethod
    def _defensive_skill(ps: PlayerState, intent: str) -> float:
        """0..1 suitability for executing a particular defensive intention."""
        if intent == "press_ball":
            raw = (
                0.28 * ps.effective("tackling") + 0.22 * ps.effective("pace")
                + 0.18 * ps.effective("positioning") + 0.14 * ps.effective("anticipation")
                + 0.10 * ps.effective("aggression") + 0.08 * ps.effective("stamina")
            )
        elif intent == "delay":
            raw = (
                0.31 * ps.effective("positioning") + 0.27 * ps.effective("anticipation")
                + 0.18 * ps.effective("composure") + 0.14 * ps.effective("pace")
                + 0.10 * ps.effective("discipline")
            )
        elif intent == "block_lane":
            raw = (
                0.37 * ps.effective("positioning") + 0.31 * ps.effective("anticipation")
                + 0.14 * ps.effective("composure") + 0.10 * ps.effective("tackling")
                + 0.08 * ps.effective("discipline")
            )
        elif intent in {"track_runner", "cover_depth"}:
            raw = (
                0.31 * ps.effective("anticipation") + 0.27 * ps.effective("positioning")
                + 0.24 * ps.effective("pace") + 0.10 * ps.effective("stamina")
                + 0.08 * ps.effective("composure")
            )
        elif intent == "contain":
            raw = (
                0.31 * ps.effective("positioning") + 0.26 * ps.effective("tackling")
                + 0.19 * ps.effective("pace") + 0.14 * ps.effective("anticipation")
                + 0.10 * ps.effective("discipline")
            )
        elif intent == "block_cross":
            raw = (
                0.29 * ps.effective("positioning") + 0.24 * ps.effective("pace")
                + 0.22 * ps.effective("tackling") + 0.15 * ps.effective("anticipation")
                + 0.10 * ps.effective("discipline")
            )
        elif intent in {"protect_box", "block_shot", "close_cutback"}:
            raw = (
                0.34 * ps.effective("positioning") + 0.26 * ps.effective("anticipation")
                + 0.18 * ps.effective("tackling") + 0.10 * ps.effective("strength")
                + 0.07 * ps.effective("composure") + 0.05 * ps.effective("discipline")
            )
        else:
            raw = (
                0.34 * ps.effective("positioning") + 0.28 * ps.effective("anticipation")
                + 0.20 * ps.effective("tackling") + 0.10 * ps.effective("pace")
                + 0.08 * ps.effective("composure")
            )
        return clamp(raw / 100.0)

    def _rank_defenders(self, defending_team: int, zone: Zone, intent: str) -> list[tuple[PlayerState, float]]:
        rows: list[tuple[PlayerState, float]] = []
        for ps in self.teams[defending_team].on_field:
            if ps.player.position.upper() == "GK":
                continue
            affinity = self._defender_role_affinity(ps, zone, intent)
            skill = self._defensive_skill(ps, intent)
            energy = 0.82 + 0.18 * ps.energy
            card_caution = 0.94 if ps.yellow and intent in {"press_ball", "contain"} else 1.0
            weight = max(0.001, affinity * (0.55 + 0.45 * skill) * energy * card_caution)
            rows.append((ps, weight))
        return rows

    def _best_defender_for_intent(self, defending_team: int, zone: Zone, intent: str) -> PlayerState:
        rows = self._rank_defenders(defending_team, zone, intent)
        if not rows:
            return self._goalkeeper(defending_team)
        return max(rows, key=lambda x: x[1])[0]

    # ---------------------------- intention choice ----------------------------

    def _defensive_intent_utilities(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        *,
        kind: Optional[str] = None,
        target: Optional[str] = None,
    ) -> dict[str, float]:
        defending_team = 1 - attacking_team
        tactics = self.teams[defending_team].team.tactics
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        space = clamp(float(ctx.get("space", 0.5)))
        depth = clamp(float(ctx.get("space_behind", 0.4)))
        transition = clamp(float(getattr(self.state, "transition_boost", 0.0)))
        kind = (kind or "open_play").lower()
        wide = zone.lane != Lane.CENTER

        # These are *response utilities*, not success chances. Tactical shape and
        # threat decide what the defence should prioritise right now.
        u: dict[str, float] = {
            "press_ball": 0.30 + 0.44 * tactics.pressing + 0.14 * pressure + 0.10 * (1.0 - depth),
            "delay": 0.30 + 0.30 * transition + 0.18 * depth + 0.12 * space + 0.08 * tactics.compactness,
            "block_lane": 0.34 + 0.28 * tactics.compactness + 0.14 * pressure + 0.10 * (1.0 if zone.lane == Lane.CENTER else 0.0),
            "track_runner": 0.24 + 0.34 * depth + 0.20 * tactics.defensive_line + 0.12 * transition,
            "cover_depth": 0.22 + 0.40 * depth + 0.22 * tactics.defensive_line + 0.15 * transition,
            "contain": 0.28 + 0.18 * pressure + 0.20 * (1.0 - tactics.pressing) + 0.10 * space,
            "block_cross": (0.24 + 0.28 * tactics.compactness + 0.18 * pressure + 0.12 * space) if wide else 0.05,
            "protect_box": 0.18 + 0.28 * tactics.compactness + 0.18 * (1.0 - space),
            "block_shot": 0.16 + 0.26 * tactics.compactness + 0.20 * pressure,
            "close_cutback": (0.20 + 0.26 * tactics.compactness + 0.17 * pressure + 0.12 * space) if wide else 0.12,
        }

        # Action-specific threat recognition.
        if kind in {"through_ball", "progressive_pass", "long_ball"}:
            u["track_runner"] += 0.30
            u["cover_depth"] += 0.18
            u["block_lane"] += 0.12
        elif kind == "switch":
            u["block_lane"] += 0.20
            u["delay"] += 0.08
        elif kind in {"carry", "dribble"}:
            u["contain"] += 0.30
            u["delay"] += 0.14
            u["press_ball"] += 0.08
        elif kind == "cross":
            u["block_cross"] += 0.36
            u["protect_box"] += 0.18
        elif kind == "cutback":
            u["close_cutback"] += 0.38
            u["protect_box"] += 0.18
        elif kind == "shoot":
            u["block_shot"] += 0.42
            u["protect_box"] += 0.18

        if zone.band == Band.BOX:
            u["protect_box"] += 0.34
            u["block_shot"] += 0.24
            u["press_ball"] -= 0.16
            u["cover_depth"] -= 0.18
        elif zone.band == Band.ATT:
            u["block_lane"] += 0.10
            u["track_runner"] += 0.08
        elif zone.band == Band.DEF:
            # From the attacking team's point of view, this is high up the pitch
            # for the defending side; pressing can make more sense than protecting
            # its own box.
            u["press_ball"] += 0.16
            u["protect_box"] -= 0.20

        # If a specific runner has been identified, tracking that movement becomes
        # more rational, but only if the defender has enough information/time.
        if target:
            u["track_runner"] += 0.10

        return {k: max(0.0, v) for k, v in u.items()}

    def _build_defensive_plan(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        *,
        kind: Optional[str] = None,
        target: Optional[str] = None,
    ) -> dict:
        defending_team = 1 - attacking_team
        utilities = self._defensive_intent_utilities(
            attacking_team, zone, ctx, kind=kind, target=target
        )

        # Exactly one primary intention. No stacked press+track+cover super-shield.
        intent = max(utilities.items(), key=lambda kv: kv[1])[0]
        defender = self._best_defender_for_intent(defending_team, zone, intent)
        quality = self._defensive_skill(defender, intent)
        q = clamp((quality - 0.52) / 0.43)

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

        if intent == "press_ball":
            effects["pressure_delta"] = 0.060 * q
            effects["space_delta"] = -0.024 * q
            # Pressing commits a player forward and can expose depth.
            effects["depth_delta"] = 0.030 * (0.55 + 0.45 * (1.0 - q))
        elif intent == "delay":
            effects["pressure_delta"] = -0.018
            effects["space_delta"] = 0.016
            effects["depth_delta"] = -0.060 * q
            effects["runner_control"] = 0.030 * q
        elif intent == "block_lane":
            effects["pressure_delta"] = 0.008 * q
            effects["space_delta"] = 0.012
            effects["pass_lane_control"] = 0.078 * q
        elif intent == "track_runner":
            effects["pressure_delta"] = -0.010
            effects["space_delta"] = 0.018
            effects["depth_delta"] = -0.072 * q
            effects["runner_control"] = 0.090 * q
        elif intent == "cover_depth":
            effects["pressure_delta"] = -0.022
            effects["space_delta"] = 0.024
            effects["depth_delta"] = -0.086 * q
            effects["runner_control"] = 0.052 * q
        elif intent == "contain":
            effects["pressure_delta"] = 0.020 * q
            effects["space_delta"] = -0.050 * q
            effects["dribble_control"] = 0.086 * q
        elif intent == "block_cross":
            effects["pressure_delta"] = 0.036 * q
            effects["wide_space_delta"] = -0.060 * q
            effects["cross_control"] = 0.095 * q
            # Closing the crosser can slightly loosen central cover.
            effects["box_protection"] = -0.015
        elif intent == "close_cutback":
            effects["pressure_delta"] = 0.024 * q
            effects["space_delta"] = -0.028 * q
            effects["pass_lane_control"] = 0.060 * q
            effects["box_protection"] = 0.045 * q
        elif intent == "block_shot":
            effects["pressure_delta"] = 0.052 * q
            effects["space_delta"] = -0.036 * q
            effects["box_protection"] = 0.082 * q
        elif intent == "protect_box":
            effects["pressure_delta"] = 0.030 * q
            effects["space_delta"] = -0.048 * q
            effects["box_protection"] = 0.092 * q
            effects["pass_lane_control"] = 0.026 * q

        return {
            "defending_team": defending_team,
            "intent": intent,
            "defender": defender,
            "defender_name": defender.player.name,
            "quality": quality,
            "utility": utilities[intent],
            "effects": effects,
            "kind": kind or "open_play",
            "target": target,
        }

    @staticmethod
    def _apply_plan_effects(ctx: dict, plan: dict) -> dict:
        effects = plan["effects"]
        adjusted = dict(ctx)
        adjusted["pressure"] = clamp(float(ctx.get("pressure", 0.5)) + effects["pressure_delta"])
        adjusted["space"] = clamp(float(ctx.get("space", 0.5)) + effects["space_delta"])
        adjusted["space_behind"] = clamp(float(ctx.get("space_behind", 0.4)) + effects["depth_delta"])
        adjusted["wide_space"] = clamp(float(ctx.get("wide_space", 0.0)) + effects["wide_space_delta"])
        adjusted["pass_lane_control"] = clamp(effects["pass_lane_control"], 0.0, 0.12)
        adjusted["runner_control"] = clamp(effects["runner_control"], 0.0, 0.12)
        adjusted["dribble_control"] = clamp(effects["dribble_control"], 0.0, 0.12)
        adjusted["cross_control"] = clamp(effects["cross_control"], 0.0, 0.12)
        adjusted["box_protection"] = clamp(effects["box_protection"], -0.03, 0.12)
        adjusted["defensive_intent"] = plan["intent"]
        adjusted["defensive_actor"] = plan["defender_name"]
        adjusted["defensive_quality"] = round(plan["quality"], 6)
        return adjusted

    def defensive_diagnostic(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: Optional[dict] = None,
        *,
        kind: Optional[str] = None,
        target: Optional[str] = None,
    ) -> dict:
        """Deterministic defensive-plan diagnostic when explicit context is supplied."""
        context = dict(ctx or {
            "pressure": 0.48,
            "space": 0.52,
            "space_behind": 0.45,
            "support": 0.50,
            "wide_space": 0.10,
        })
        plan = self._build_defensive_plan(
            attacking_team, zone, context, kind=kind, target=target
        )
        adjusted = self._apply_plan_effects(context, plan)
        return {
            "intent": plan["intent"],
            "defender": plan["defender_name"],
            "quality": plan["quality"],
            "kind": plan["kind"],
            "target": target,
            "base": context,
            "adjusted": adjusted,
            "effects": dict(plan["effects"]),
        }

    # ---------------------------- engine integration ----------------------------

    def _current_defensive_hint(self) -> dict:
        hint = getattr(self, "_v13_defense_hint", None)
        return hint if isinstance(hint, dict) else {}

    def _spatial_context(self, attacking_team: int, zone: Zone) -> dict:
        base = super()._spatial_context(attacking_team, zone)
        hint = self._current_defensive_hint()
        kind = hint.get("kind")
        target = hint.get("target")
        plan = self._build_defensive_plan(
            attacking_team, zone, base, kind=kind, target=target
        )
        self._v13_last_defensive_plan = plan
        adjusted = self._apply_plan_effects(base, plan)
        # Keep enough provenance to *replace* this generic response with a
        # concrete action-specific response later in the same beat. This avoids
        # stacking two defensive intentions while preserving other contextual
        # deltas (for example body orientation) that may be applied in between.
        adjusted["_defense_base_context"] = dict(base)
        adjusted["_defense_generic_context"] = {
            k: v for k, v in adjusted.items() if not k.startswith("_defense_")
        }
        return adjusted

    def _choose_defender(self, team, zone) -> PlayerState:
        """Choose a defender suited to the current primary defensive response."""
        hint = self._current_defensive_hint()
        plan = getattr(self, "_v13_last_defensive_plan", None)
        if isinstance(plan, dict) and plan.get("defending_team") == team:
            name = plan.get("defender_name")
            if name:
                try:
                    return self.teams[team].by_name(name)
                except KeyError:
                    pass

        kind = hint.get("kind")
        # Build a neutral plan without recursively calling _spatial_context.
        base = {
            "pressure": 0.48,
            "space": 0.52,
            "space_behind": 0.45,
            "support": 0.50,
            "wide_space": 0.10,
        }
        plan = self._build_defensive_plan(1 - team, zone, base, kind=kind, target=hint.get("target"))
        rows = self._rank_defenders(team, zone, plan["intent"])
        if not rows:
            return super()._choose_defender(team, zone)
        return weighted_choice(self.rng, rows)

    def _context_for_action(self, team: int, zone: Zone, ctx: dict, kind: str, target: Optional[str] = None) -> tuple[dict, dict]:
        # ``ctx`` normally already contains the generic defensive response from
        # _spatial_context. Replace it with the action-specific response instead
        # of stacking both. Any non-defensive deltas added after spatial context
        # (notably body-orientation changes to pressure/space) are preserved.
        base = dict(ctx.get("_defense_base_context", ctx))
        generic = ctx.get("_defense_generic_context")
        external_delta = {}
        if isinstance(generic, dict):
            for key in ("pressure", "space", "space_behind", "wide_space"):
                if key in ctx and key in generic:
                    external_delta[key] = float(ctx[key]) - float(generic[key])

        plan = self._build_defensive_plan(team, zone, base, kind=kind, target=target)
        adjusted = self._apply_plan_effects(base, plan)
        for key, delta in external_delta.items():
            adjusted[key] = clamp(float(adjusted.get(key, 0.0)) + delta)
        self._v13_last_defensive_plan = plan
        return adjusted, plan

    def _progressive_action(self, team, actor, zone, kind, ctx):
        adjusted, plan = self._context_for_action(team, zone, ctx, kind)
        old = getattr(self, "_v13_defense_hint", None)
        self._v13_defense_hint = {"kind": kind, "target": None}
        try:
            # Lane control represents a defender choosing to occupy the passing
            # lane. Translate it into contextual pressure rather than changing
            # player passing attributes.
            adjusted["pressure"] = clamp(adjusted["pressure"] + adjusted.get("pass_lane_control", 0.0) * 0.55)
            return super()._progressive_action(team, actor, zone, kind, adjusted)
        finally:
            self._v13_defense_hint = old

    def _carry(self, team, actor, zone, ctx):
        adjusted, plan = self._context_for_action(team, zone, ctx, "carry")
        old = getattr(self, "_v13_defense_hint", None)
        self._v13_defense_hint = {"kind": "carry", "target": None}
        try:
            adjusted["pressure"] = clamp(adjusted["pressure"] + adjusted.get("dribble_control", 0.0) * 0.50)
            adjusted["space"] = clamp(adjusted["space"] - adjusted.get("dribble_control", 0.0) * 0.35)
            return super()._carry(team, actor, zone, adjusted)
        finally:
            self._v13_defense_hint = old

    def _create_or_resolve_danger(self, team, actor, zone, kind, ctx):
        marker = getattr(self, "_v13_forced_target", None)
        target = None
        if isinstance(marker, dict) and marker.get("team") == team and marker.get("actor") == actor.player.name:
            target = marker.get("target")

        adjusted, plan = self._context_for_action(team, zone, ctx, kind, target=target)
        if kind in {"through_ball"}:
            adjusted["space_behind"] = clamp(adjusted["space_behind"] - adjusted.get("runner_control", 0.0) * 0.60)
            adjusted["pressure"] = clamp(adjusted["pressure"] + adjusted.get("pass_lane_control", 0.0) * 0.35)
        elif kind in {"cross", "cutback"}:
            adjusted["pressure"] = clamp(
                adjusted["pressure"]
                + adjusted.get("cross_control", 0.0) * 0.45
                + adjusted.get("pass_lane_control", 0.0) * 0.30
            )
        elif kind == "dribble":
            adjusted["pressure"] = clamp(adjusted["pressure"] + adjusted.get("dribble_control", 0.0) * 0.50)
            adjusted["space"] = clamp(adjusted["space"] - adjusted.get("dribble_control", 0.0) * 0.35)
        elif kind == "shoot":
            adjusted["pressure"] = clamp(adjusted["pressure"] + adjusted.get("box_protection", 0.0) * 0.45)

        old = getattr(self, "_v13_defense_hint", None)
        self._v13_defense_hint = {"kind": kind, "target": target}
        try:
            return super()._create_or_resolve_danger(team, actor, zone, kind, adjusted)
        finally:
            self._v13_defense_hint = old

    def _resolve_pending(self):
        p = self.state.pending
        if p is None:
            return super()._resolve_pending()

        old = getattr(self, "_v13_defense_hint", None)
        self._v13_defense_hint = {"kind": p.kind, "target": p.target or p.actor}

        # Reassign the active defender to the one whose role/attributes best fit
        # this now-concrete threat. This is a reaction to the play, not a buff.
        neutral = {
            "pressure": clamp(p.pressure),
            "space": clamp(0.32 + 0.48 * p.danger),
            "space_behind": 0.62 if p.kind == "through_ball" else 0.38,
            "support": 0.50,
            "wide_space": 0.10,
        }
        plan = self._build_defensive_plan(
            p.team, p.zone, neutral, kind=p.kind, target=p.target or p.actor
        )
        self.state.pending = replace(p, defender=plan["defender_name"])
        try:
            return super()._resolve_pending()
        finally:
            self._v13_defense_hint = old

    def _resolve_shot(self, p: PendingAction):
        # Choose the relevant shot-blocking/box defender and change only the
        # immediate shot context. Finishing/GK attributes remain untouched.
        neutral = {
            "pressure": clamp(p.pressure),
            "space": clamp(0.30 + 0.58 * p.danger),
            "space_behind": 0.48,
            "support": 0.50,
            "wide_space": 0.08,
        }
        plan = self._build_defensive_plan(p.team, p.zone, neutral, kind="shoot", target=p.actor)
        tuned_pressure = clamp(
            p.pressure
            + plan["effects"]["pressure_delta"]
            + 0.55 * max(0.0, plan["effects"]["box_protection"])
        )
        tuned = replace(
            p,
            pressure=tuned_pressure,
            defender=plan["defender_name"],
        )
        old = getattr(self, "_v13_defense_hint", None)
        self._v13_defense_hint = {"kind": "shoot", "target": p.actor}
        try:
            return super()._resolve_shot(tuned)
        finally:
            self._v13_defense_hint = old


MatchEngine = MatchEngineV13Defense
