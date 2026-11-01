from __future__ import annotations

"""Experimental v1.3 layer: marking structure and marking hand-offs.

Extends contextual defensive intelligence with a second, orthogonal question:
*how is the threat being marked?*

The defence still chooses exactly one primary response (press, delay, track,
cover, etc.). This layer then chooses exactly one marking organisation for the
beat (zonal, individual/man, or hybrid), assigns one marker to a concrete
runner, and may hand that runner to a better-positioned defender when the run
crosses a defensive zone.

No defender may cover two disconnected threats in the same diagnostic
assignment, and marking never changes attacker or defender attributes.
"""

from typing import Optional

from engine import Band, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_defense import MatchEngineV13Defense


VERSION = "1.3-candidate-spatial-creativity-boldness-offball-body-defense-marking"


class MatchEngineV13Marking(MatchEngineV13Defense):
    """Adds zonal/man/hybrid marking and contextual hand-offs."""

    # ---------------------------- marking style ----------------------------

    def _marking_style_scores(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        *,
        kind: Optional[str] = None,
        target: Optional[str] = None,
    ) -> dict[str, float]:
        defending_team = 1 - attacking_team
        t = self.teams[defending_team].team.tactics
        depth = clamp(float(ctx.get("space_behind", 0.4)))
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        transition = clamp(float(getattr(self.state, "transition_boost", 0.0)))
        kind = (kind or "open_play").lower()

        # These are organisation preferences, not success probabilities.
        zonal = (
            0.36 + 0.38 * t.compactness + 0.11 * (1.0 - t.pressing)
            + 0.08 * (1.0 if zone.band == Band.BOX else 0.0)
            + 0.06 * (1.0 if zone.lane == Lane.CENTER else 0.0)
        )
        man = (
            0.24 + 0.27 * t.pressing + 0.16 * t.defensive_line
            + 0.14 * depth + 0.08 * pressure + 0.10 * transition
        )
        if target:
            man += 0.16
        if kind in {"through_ball", "progressive_pass", "long_ball"}:
            man += 0.14
        if kind in {"cross", "cutback", "shoot"} or zone.band == Band.BOX:
            zonal += 0.12

        # Hybrid is not a fallback bonus stack: it is one coherent scheme where
        # the line protects zones but a concrete runner can be handed between
        # defenders as he moves through them.
        hybrid = 0.30 + 0.20 * t.compactness + 0.16 * t.pressing + 0.10 * depth
        if target:
            hybrid += 0.12
        if abs(zonal - man) < 0.16:
            hybrid += 0.12

        return {"zonal": max(0.0, zonal), "man": max(0.0, man), "hybrid": max(0.0, hybrid)}

    def _marking_mode(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        *,
        kind: Optional[str] = None,
        target: Optional[str] = None,
    ) -> tuple[str, dict[str, float]]:
        scores = self._marking_style_scores(attacking_team, zone, ctx, kind=kind, target=target)
        mode = max(scores.items(), key=lambda kv: kv[1])[0]
        return mode, scores

    @staticmethod
    def _marking_skill(ps: PlayerState, mode: str) -> float:
        if mode == "man":
            raw = (
                0.30 * ps.effective("anticipation") + 0.24 * ps.effective("pace")
                + 0.22 * ps.effective("positioning") + 0.12 * ps.effective("tackling")
                + 0.07 * ps.effective("stamina") + 0.05 * ps.effective("composure")
            )
        elif mode == "zonal":
            raw = (
                0.38 * ps.effective("positioning") + 0.29 * ps.effective("anticipation")
                + 0.12 * ps.effective("composure") + 0.09 * ps.effective("tackling")
                + 0.07 * ps.effective("discipline") + 0.05 * ps.effective("pace")
            )
        else:  # hybrid
            raw = (
                0.33 * ps.effective("anticipation") + 0.31 * ps.effective("positioning")
                + 0.14 * ps.effective("pace") + 0.10 * ps.effective("tackling")
                + 0.07 * ps.effective("composure") + 0.05 * ps.effective("discipline")
            )
        return clamp(raw / 100.0)

    @staticmethod
    def _zone_role_affinity(ps: PlayerState, zone: Zone) -> float:
        pos = ps.player.position.upper()
        if pos == "GK":
            return 0.01

        # Zone is expressed from the attacking team's perspective, therefore an
        # attack down LEFT is normally defended by the defending team's RIGHT.
        if zone.lane == Lane.LEFT:
            lane = {"RB": 1.28, "CB": 1.08, "DM": 0.82, "CM": 0.58, "LB": 0.42}
        elif zone.lane == Lane.RIGHT:
            lane = {"LB": 1.28, "CB": 1.08, "DM": 0.82, "CM": 0.58, "RB": 0.42}
        else:
            lane = {"CB": 1.24, "DM": 1.12, "CM": 0.82, "LB": 0.74, "RB": 0.74}

        base = lane.get(pos, 0.30)
        if zone.band == Band.BOX:
            if pos == "CB":
                base *= 1.16
            elif pos in {"LB", "RB", "DM"}:
                base *= 1.06
        elif zone.band == Band.MID and pos in {"DM", "CM"}:
            base *= 1.10
        return base

    def _marker_score(
        self,
        ps: PlayerState,
        zone: Zone,
        mode: str,
        target: Optional[PlayerState] = None,
    ) -> float:
        skill = self._marking_skill(ps, mode)
        affinity = self._zone_role_affinity(ps, zone)
        pace_match = 0.0
        strength_match = 0.0
        if target is not None:
            pace_gap = (ps.effective("pace") - target.effective("pace")) / 100.0
            strength_gap = (ps.effective("strength") - target.effective("strength")) / 100.0
            pace_match = clamp(0.50 + 0.45 * pace_gap, 0.20, 0.85)
            strength_match = clamp(0.50 + 0.35 * strength_gap, 0.25, 0.80)
        else:
            pace_match = strength_match = 0.50
        energy = 0.82 + 0.18 * ps.energy
        caution = 0.95 if ps.yellow and mode == "man" else 1.0
        return max(
            0.001,
            affinity * (0.50 + 0.40 * skill + 0.06 * pace_match + 0.04 * strength_match)
            * energy * caution,
        )

    def _best_marker(
        self,
        defending_team: int,
        zone: Zone,
        mode: str,
        target: Optional[PlayerState] = None,
        *,
        exclude_names: Optional[set[str]] = None,
    ) -> tuple[PlayerState, float]:
        exclude_names = exclude_names or set()
        rows = []
        for ps in self.teams[defending_team].on_field:
            if ps.player.position.upper() == "GK" or ps.player.name in exclude_names:
                continue
            rows.append((ps, self._marker_score(ps, zone, mode, target)))
        if not rows:
            gk = self._goalkeeper(defending_team)
            return gk, 0.001
        return max(rows, key=lambda row: row[1])

    # ---------------------------- runner projection / handoff ----------------------------

    @staticmethod
    def _current_runner_lane(target: PlayerState, fallback: Lane) -> Lane:
        pos = target.player.position.upper()
        if pos in {"LW", "LB"}:
            return Lane.LEFT
        if pos in {"RW", "RB"}:
            return Lane.RIGHT
        if pos in {"ST", "AM", "CM", "DM", "CB"}:
            return Lane.CENTER
        return fallback

    def _runner_projection(
        self,
        attacking_team: int,
        actor_name: Optional[str],
        target: PlayerState,
        zone: Zone,
        ctx: dict,
    ) -> dict:
        current = Zone(zone.band, self._current_runner_lane(target, zone.lane))
        movement = None
        if actor_name and actor_name != target.player.name:
            try:
                actor = self.teams[attacking_team].by_name(actor_name)
                movement = self._best_movement(attacking_team, actor, target, zone, ctx)
            except (KeyError, AttributeError):
                movement = None

        if movement:
            projected = Zone(movement["projected_band"], movement["projected_lane"])
            hiddenness = clamp(float(movement.get("hiddenness", 0.0)))
            timing = clamp(float(movement.get("timing", 0.5)))
        else:
            projected = current
            hiddenness = 0.0
            timing = clamp(target.effective("anticipation") / 100.0)

        return {
            "current_zone": current,
            "projected_zone": projected,
            "movement": movement,
            "hiddenness": hiddenness,
            "timing": timing,
        }

    @staticmethod
    def _handoff_quality(a: PlayerState, b: PlayerState, hiddenness: float) -> float:
        raw = (
            0.23 * a.effective("anticipation") + 0.19 * a.effective("positioning")
            + 0.10 * a.effective("composure") + 0.08 * a.effective("discipline")
            + 0.18 * b.effective("anticipation") + 0.14 * b.effective("positioning")
            + 0.05 * b.effective("composure") + 0.03 * b.effective("discipline")
        ) / 100.0
        return clamp(raw * (1.02 - 0.24 * hiddenness))

    def _marking_plan(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        *,
        kind: Optional[str] = None,
        actor_name: Optional[str] = None,
        target_name: Optional[str] = None,
    ) -> dict:
        defending_team = 1 - attacking_team
        mode, style_scores = self._marking_mode(
            attacking_team, zone, ctx, kind=kind, target=target_name
        )

        target = None
        if target_name:
            try:
                target = self.teams[attacking_team].by_name(target_name)
            except KeyError:
                target = None

        # With no concrete runner, zonal/hybrid organisation protects the local
        # lane. This still remains one marking organisation, not several marks.
        if target is None:
            marker, score = self._best_marker(defending_team, zone, mode)
            q = self._marking_skill(marker, mode)
            return {
                "mode": mode,
                "style_scores": style_scores,
                "target": None,
                "marker": marker,
                "marker_name": marker.player.name,
                "initial_marker": marker.player.name,
                "switched": False,
                "handoff_quality": 1.0,
                "quality": q,
                "current_zone": zone,
                "projected_zone": zone,
                "movement": None,
                "effects": self._marking_effects(mode, q, False, 1.0, 0.0, 0.0),
            }

        projection = self._runner_projection(attacking_team, actor_name, target, zone, ctx)
        current_zone: Zone = projection["current_zone"]
        projected_zone: Zone = projection["projected_zone"]
        hiddenness = float(projection["hiddenness"])

        initial, initial_score = self._best_marker(defending_team, current_zone, mode, target)
        projected, projected_score = self._best_marker(defending_team, projected_zone, mode, target)

        # Individual marking is sticky; zonal marking hands runners over more
        # readily; hybrid sits between. The gain is measured in the *new zone*.
        initial_in_new_zone = self._marker_score(initial, projected_zone, mode, target)
        stickiness = {"zonal": 0.00, "hybrid": 0.045, "man": 0.095}[mode]
        threshold = {"zonal": 0.025, "hybrid": 0.055, "man": 0.095}[mode]
        handoff = self._handoff_quality(initial, projected, hiddenness)
        gain = projected_score - (initial_in_new_zone + stickiness)

        crossed_zone = (
            current_zone.lane != projected_zone.lane
            or current_zone.band != projected_zone.band
        )
        switched = bool(
            crossed_zone
            and projected.player.name != initial.player.name
            and gain > threshold
            and handoff >= 0.46
        )
        marker = projected if switched else initial
        q = self._marking_skill(marker, mode)

        # A highly obvious central decoy can drag a strict man-marker and make
        # the rest of the structure a touch less compact. This is a trade-off,
        # not an attacker bonus and not a guaranteed opening.
        decoy = 0.0
        if actor_name:
            try:
                actor = self.teams[attacking_team].by_name(actor_name)
                decoy = self._decoy_pull(attacking_team, actor, zone)
            except (KeyError, AttributeError):
                decoy = 0.0

        effects = self._marking_effects(mode, q, switched, handoff, hiddenness, decoy)
        return {
            "mode": mode,
            "style_scores": style_scores,
            "target": target.player.name,
            "marker": marker,
            "marker_name": marker.player.name,
            "initial_marker": initial.player.name,
            "projected_marker": projected.player.name,
            "switched": switched,
            "handoff_quality": handoff,
            "quality": q,
            "gain": gain,
            "current_zone": current_zone,
            "projected_zone": projected_zone,
            "movement": projection["movement"],
            "hiddenness": hiddenness,
            "decoy_pull": decoy,
            "effects": effects,
        }

    @staticmethod
    def _marking_effects(
        mode: str,
        quality: float,
        switched: bool,
        handoff: float,
        hiddenness: float,
        decoy: float,
    ) -> dict:
        q = clamp((quality - 0.48) / 0.48)
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
        if mode == "man":
            effects["runner_control"] = 0.060 * q
            effects["depth_delta"] = -0.030 * q
            effects["space_delta"] = 0.010 + 0.014 * decoy
        elif mode == "zonal":
            effects["runner_control"] = 0.025 * q
            effects["pass_lane_control"] = 0.045 * q
            effects["box_protection"] = 0.030 * q
            effects["space_delta"] = -0.012 * q
        else:
            effects["runner_control"] = 0.043 * q
            effects["pass_lane_control"] = 0.028 * q
            effects["box_protection"] = 0.016 * q
            effects["depth_delta"] = -0.016 * q

        # Clean hand-offs preserve a runner across zones. Hidden runs are harder
        # to exchange, so they reduce this extra control rather than magically
        # making the attack succeed.
        if switched:
            effects["runner_control"] += 0.024 * handoff * (1.0 - 0.35 * hiddenness)
            effects["pressure_delta"] -= 0.004  # momentary attention cost
        return effects

    # ---------------------------- public diagnostics ----------------------------

    def marking_diagnostic(
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
        })
        p = self._marking_plan(
            attacking_team, zone, context,
            kind=kind, actor_name=actor, target_name=target,
        )
        return {
            "mode": p["mode"],
            "target": p.get("target"),
            "marker": p["marker_name"],
            "initial_marker": p.get("initial_marker"),
            "projected_marker": p.get("projected_marker", p["marker_name"]),
            "switched": p["switched"],
            "handoff_quality": p["handoff_quality"],
            "quality": p["quality"],
            "style_scores": dict(p["style_scores"]),
            "current_zone": {
                "band": p["current_zone"].band.value,
                "lane": p["current_zone"].lane.value,
            },
            "projected_zone": {
                "band": p["projected_zone"].band.value,
                "lane": p["projected_zone"].lane.value,
            },
            "movement": dict(p["movement"]) if isinstance(p.get("movement"), dict) else None,
            "effects": dict(p["effects"]),
        }

    def marking_assignments_diagnostic(
        self,
        attacking_team: int,
        actor_name: str,
        zone: Zone,
        ctx: Optional[dict] = None,
        *,
        max_threats: int = 4,
    ) -> list[dict]:
        """Assign distinct defenders to the most dangerous projected runs.

        This is a diagnostic of the structure, not several simultaneously stacked
        defensive bonuses. Each defender can appear at most once.
        """
        context = dict(ctx or {
            "pressure": 0.48,
            "space": 0.52,
            "space_behind": 0.55,
            "support": 0.50,
            "wide_space": 0.10,
        })
        actor = self.teams[attacking_team].by_name(actor_name)
        threats = []
        for ps in self.teams[attacking_team].on_field:
            if ps.player.name == actor_name or ps.player.position.upper() == "GK":
                continue
            mv = self._best_movement(attacking_team, actor, ps, zone, context)
            q = self._movement_quality(ps, mv, zone, context)
            threats.append((ps, mv, q))
        threats.sort(key=lambda row: row[2], reverse=True)

        used: set[str] = set()
        rows = []
        defending_team = 1 - attacking_team
        for target, mv, threat_q in threats[:max_threats]:
            projected = Zone(mv["projected_band"], mv["projected_lane"])
            mode, _ = self._marking_mode(
                attacking_team, projected, context, kind=mv.get("action"), target=target.player.name
            )
            marker, marker_score = self._best_marker(
                defending_team, projected, mode, target, exclude_names=used
            )
            used.add(marker.player.name)
            rows.append({
                "target": target.player.name,
                "movement": mv["intent"],
                "projected_band": projected.band.value,
                "projected_lane": projected.lane.value,
                "threat_quality": threat_q,
                "mode": mode,
                "marker": marker.player.name,
                "marker_score": marker_score,
            })
        return rows

    # ---------------------------- integration with defensive plan ----------------------------

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
        hint = self._current_defensive_hint()
        actor_name = hint.get("actor")
        marking = self._marking_plan(
            attacking_team, zone, ctx,
            kind=kind, actor_name=actor_name, target_name=target,
        )

        merged = dict(plan["effects"])
        for key, value in marking["effects"].items():
            merged[key] = merged.get(key, 0.0) + value
        plan["effects"] = merged
        plan["marking"] = marking

        # If the primary response itself is about a concrete runner/lane, the
        # active defender should be the marker selected by the marking scheme.
        if target and plan["intent"] in {"track_runner", "cover_depth", "block_lane"}:
            marker = marking["marker"]
            plan["defender"] = marker
            plan["defender_name"] = marker.player.name
            plan["quality"] = max(plan["quality"], self._marking_skill(marker, marking["mode"]))
        return plan

    @staticmethod
    def _apply_plan_effects(ctx: dict, plan: dict) -> dict:
        adjusted = MatchEngineV13Defense._apply_plan_effects(ctx, plan)
        marking = plan.get("marking")
        if isinstance(marking, dict):
            adjusted["marking_mode"] = marking.get("mode")
            adjusted["marking_target"] = marking.get("target")
            adjusted["marking_actor"] = marking.get("marker_name")
            adjusted["marking_switched"] = bool(marking.get("switched"))
            adjusted["marking_handoff_quality"] = round(float(marking.get("handoff_quality", 1.0)), 6)
        return adjusted

    # Carry actor identity into the parent defensive-context machinery so a
    # target's movement can be evaluated without rewriting the base engine.
    def _with_actor_hint(self, kind: str, actor_name: str, target: Optional[str], fn, *args, **kwargs):
        old = getattr(self, "_v13_defense_hint", None)
        self._v13_defense_hint = {"kind": kind, "target": target, "actor": actor_name}
        try:
            return fn(*args, **kwargs)
        finally:
            self._v13_defense_hint = old

    def _progressive_action(self, team, actor, zone, kind, ctx):
        return self._with_actor_hint(
            kind, actor.player.name, None,
            super()._progressive_action, team, actor, zone, kind, ctx,
        )

    def _carry(self, team, actor, zone, ctx):
        return self._with_actor_hint(
            "carry", actor.player.name, None,
            super()._carry, team, actor, zone, ctx,
        )

    def _create_or_resolve_danger(self, team, actor, zone, kind, ctx):
        forced = getattr(self, "_v13_forced_target", None)
        target = None
        if isinstance(forced, dict) and forced.get("team") == team and forced.get("actor") == actor.player.name:
            target = forced.get("target")
        return self._with_actor_hint(
            kind, actor.player.name, target,
            super()._create_or_resolve_danger, team, actor, zone, kind, ctx,
        )

    def _resolve_pending(self):
        p = self.state.pending
        if p is None:
            return super()._resolve_pending()
        return self._with_actor_hint(
            p.kind, p.actor, p.target or p.actor,
            super()._resolve_pending,
        )

    def _resolve_shot(self, p):
        return self._with_actor_hint(
            "shoot", p.actor, p.actor,
            super()._resolve_shot, p,
        )


MatchEngine = MatchEngineV13Marking
