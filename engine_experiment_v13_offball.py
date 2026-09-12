from __future__ import annotations

"""Experimental v1.3 layer: off-ball movement + short-horizon anticipation.

This module extends the existing v1.3 spatial/creativity/boldness candidate.
It does not alter the frozen v1.2 engine.

Core idea:
    player role/attributes + ball zone + tactical context
    -> one active off-ball movement intention per player
    -> projected location/value 0.7-2.3 s ahead
    -> normal receiver selection / hidden-option discovery

Creativity still governs whether a non-obvious movement is *noticed*.
Boldness still governs whether a harder high-upside idea is *accepted*.
Off-ball movement and anticipation govern whether the run exists and is timed well.
"""

from typing import Optional

from engine import Band, Lane, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_spatial import MatchEngineV13Spatial


VERSION = "1.3-candidate-spatial-creativity-boldness-offball"


class MatchEngineV13OffBall(MatchEngineV13Spatial):
    """v1.3 candidate with a single active off-ball intention per receiver.

    The layer is deliberately generic: no player-name rules. A winger with high
    off-ball movement, anticipation and pace can make a blind-side run; a striker
    can attack depth or the box; a midfielder can arrive late or occupy a pocket;
    a fullback can overlap/underlap according to side-specific tactics.
    """

    # ---------- movement primitives ----------

    @staticmethod
    def _natural_lane(ps: PlayerState) -> Lane:
        pos = ps.player.position.upper()
        if pos in {"LW", "LB"}:
            return Lane.LEFT
        if pos in {"RW", "RB"}:
            return Lane.RIGHT
        return Lane.CENTER

    @staticmethod
    def _opposite_lane(lane: Lane) -> Lane:
        if lane == Lane.LEFT:
            return Lane.RIGHT
        if lane == Lane.RIGHT:
            return Lane.LEFT
        return Lane.CENTER

    @staticmethod
    def _next_band(band: Band) -> Band:
        if band == Band.DEF:
            return Band.MID
        if band == Band.MID:
            return Band.ATT
        return Band.BOX

    @staticmethod
    def _movement_action(intent: str, zone: Zone) -> str:
        if intent == "far_post_run":
            return "cross"
        if intent in {"late_arrival", "cutback_support"} and zone.band == Band.BOX:
            return "cutback"
        if intent in {
            "run_in_behind", "blind_side_run", "diagonal_run", "third_man_run",
            "box_attack", "wide_overlap", "underlap",
        }:
            return "through_ball"
        return "progressive_pass"

    def _movement_projection_seconds(self, ps: PlayerState, ctx: dict, intent: str) -> float:
        """Short horizon for where the runner is expected to be.

        Better anticipation/off-ball timing reduces how long the useful window
        takes to form; heavy pressure makes synchronization harder.
        """
        anticipation = ps.effective("anticipation") / 100.0
        off_ball = ps.effective("off_ball") / 100.0
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        intent_extra = {
            "support": -0.20,
            "check_short": -0.12,
            "between_lines": -0.05,
            "late_arrival": 0.16,
            "far_post_run": 0.18,
            "blind_side_run": 0.10,
        }.get(intent, 0.0)
        seconds = 2.20 - 0.62 * anticipation - 0.38 * off_ball + 0.22 * pressure + intent_extra
        return clamp(seconds, 0.70, 2.30)

    def _decoy_pull(self, team: int, actor: PlayerState, zone: Zone) -> float:
        """How strongly obvious threats can pull defenders away from another run.

        This is not a team-wide attack bonus. It only helps explain why a
        separate under-attended movement may become valuable in that moment.
        """
        threats = []
        for ps in self.teams[team].on_field:
            if ps.player.name == actor.player.name or ps.player.position.upper() == "GK":
                continue
            obvious = self._target_obviousness(ps, zone)
            if obvious < 0.72:
                continue
            threat = (
                0.34 * ps.effective("off_ball") / 100.0
                + 0.22 * ps.effective("anticipation") / 100.0
                + 0.18 * ps.effective("finishing") / 100.0
                + 0.14 * ps.effective("composure") / 100.0
                + 0.12 * ps.effective("pace") / 100.0
            )
            threats.append(obvious * threat)
        threats.sort(reverse=True)
        return clamp(sum(threats[:2]) / 1.75 if threats else 0.0)

    def _movement_intents(
        self,
        team: int,
        actor: PlayerState,
        ps: PlayerState,
        zone: Zone,
        ctx: dict,
    ) -> list[dict]:
        """Generate plausible movements for one player; no RNG is consumed."""
        pos = ps.player.position.upper()
        tactics = self.teams[team].team.tactics
        natural = self._natural_lane(ps)

        off = ps.effective("off_ball") / 100.0
        ant = ps.effective("anticipation") / 100.0
        pace = ps.effective("pace") / 100.0
        tech = ps.effective("technique") / 100.0
        vision = ps.effective("vision") / 100.0
        comp = ps.effective("composure") / 100.0
        finish = ps.effective("finishing") / 100.0
        heading = ps.effective("heading") / 100.0
        strength = ps.effective("strength") / 100.0
        stamina = ps.effective("stamina") / 100.0
        crossing = ps.effective("crossing") / 100.0
        long_shots = ps.effective("long_shots") / 100.0

        pressure = clamp(float(ctx.get("pressure", 0.5)))
        space = clamp(float(ctx.get("space", 0.5)))
        depth = clamp(float(ctx.get("space_behind", 0.4)))
        support = clamp(float(ctx.get("support", 0.5)))
        decoy = self._decoy_pull(team, actor, zone)

        timing = clamp(0.45 * off + 0.34 * ant + 0.13 * pace + 0.08 * comp)
        scan_space = clamp(0.58 + 0.28 * space + 0.20 * depth - 0.16 * pressure)

        intents: list[dict] = []

        def add(
            name: str,
            score: float,
            *,
            projected_band: Band,
            projected_lane: Lane,
            hiddenness: float,
            depth_gain: float,
        ) -> None:
            # Keep scores continuous rather than binary. A player always has an
            # active movement, but weak/ill-timed movements simply have low value.
            score = clamp(score)
            hiddenness = clamp(hiddenness)
            intents.append({
                "intent": name,
                "score": score,
                "timing": timing,
                "hiddenness": hiddenness,
                "depth_gain": clamp(depth_gain),
                "projected_band": projected_band,
                "projected_lane": projected_lane,
                "projection_seconds": self._movement_projection_seconds(ps, ctx, name),
                "action": self._movement_action(name, zone),
            })

        # Safe support exists almost everywhere and prevents the model from
        # forcing a forward run when the context does not justify one.
        support_score = (
            0.22 * off + 0.22 * ant + 0.17 * tech + 0.14 * vision
            + 0.15 * comp + 0.10 * stamina
        ) * (0.88 + 0.18 * (1.0 - support) + 0.08 * pressure)
        add(
            "support", support_score,
            projected_band=zone.band,
            projected_lane=natural if natural != Lane.CENTER else zone.lane,
            hiddenness=0.10,
            depth_gain=0.05,
        )

        check_score = (
            0.30 * off + 0.22 * ant + 0.17 * tech + 0.14 * strength + 0.17 * comp
        ) * (0.78 + 0.20 * pressure + 0.10 * (1.0 - depth))
        add(
            "check_short", check_score,
            projected_band=zone.band,
            projected_lane=zone.lane,
            hiddenness=0.14,
            depth_gain=0.02,
        )

        # Deep possession: do not let a forward teleport from the own third to
        # the opponent box. The active movement is support/checking/progression.
        if zone.band == Band.DEF:
            if pos in {"LW", "RW", "ST", "AM"}:
                progressive = (
                    0.33 * off + 0.28 * ant + 0.24 * pace + 0.08 * tech + 0.07 * stamina
                ) * (0.68 + 0.22 * depth)
                add(
                    "release_forward", progressive,
                    projected_band=Band.MID,
                    projected_lane=natural,
                    hiddenness=0.18,
                    depth_gain=0.24,
                )
            return intents

        # Between-lines availability: usually visible rather than "creative".
        if pos in {"AM", "CM", "DM", "ST", "LW", "RW"}:
            between = (
                0.27 * off + 0.27 * ant + 0.17 * tech + 0.14 * vision + 0.15 * comp
            ) * (0.78 + 0.22 * space - 0.10 * pressure)
            add(
                "between_lines", between,
                projected_band=zone.band,
                projected_lane=Lane.CENTER if pos in {"AM", "CM", "DM", "ST"} else natural,
                hiddenness=0.28,
                depth_gain=0.18,
            )

        if pos in {"ST", "LW", "RW", "AM"} and zone.band in {Band.MID, Band.ATT}:
            run = (
                0.31 * off + 0.28 * ant + 0.25 * pace + 0.09 * comp + 0.07 * stamina
            ) * (0.70 + 0.46 * depth + 0.08 * self.state.transition_boost)
            add(
                "run_in_behind", run,
                projected_band=self._next_band(zone.band),
                projected_lane=natural if pos in {"LW", "RW"} else Lane.CENTER,
                hiddenness=0.34,
                depth_gain=0.70 * depth + 0.16,
            )

        if pos in {"LW", "RW", "AM", "CM"} and zone.band in {Band.MID, Band.ATT}:
            diagonal = (
                0.30 * off + 0.29 * ant + 0.20 * pace + 0.11 * tech + 0.10 * comp
            ) * (0.72 + 0.34 * depth + 0.08 * space)
            add(
                "diagonal_run", diagonal,
                projected_band=self._next_band(zone.band),
                projected_lane=Lane.CENTER,
                hiddenness=0.47,
                depth_gain=0.60 * depth + 0.18,
            )

        # Blind-side movement gets stronger when central/obvious threats are
        # occupying the defence. Creativity is NOT part of this score: the run
        # can exist even if the ball carrier never notices it.
        if pos in {"LW", "RW", "AM", "CM"} and zone.band in {Band.MID, Band.ATT}:
            blind_lane = (
                natural if zone.lane == Lane.CENTER and natural != Lane.CENTER
                else self._opposite_lane(zone.lane) if zone.lane != Lane.CENTER
                else Lane.CENTER
            )
            blind = (
                0.34 * off + 0.33 * ant + 0.17 * pace + 0.08 * tech + 0.08 * comp
            ) * (0.66 + 0.36 * depth + 0.14 * decoy + 0.06 * space)
            add(
                "blind_side_run", blind,
                projected_band=self._next_band(zone.band),
                projected_lane=blind_lane,
                hiddenness=clamp(0.70 + 0.18 * decoy),
                depth_gain=0.66 * depth + 0.22,
            )

        if pos in {"CM", "AM", "DM"} and zone.band in {Band.MID, Band.ATT}:
            third_man = (
                0.29 * off + 0.31 * ant + 0.15 * pace + 0.12 * tech
                + 0.07 * vision + 0.06 * comp
            ) * (0.76 + 0.20 * support + 0.12 * depth)
            add(
                "third_man_run", third_man,
                projected_band=self._next_band(zone.band),
                projected_lane=Lane.CENTER,
                hiddenness=0.57,
                depth_gain=0.44 * depth + 0.22,
            )

        if pos in {"LB", "RB"} and zone.band in {Band.MID, Band.ATT}:
            overlap_setting = tactics.overlap_left if pos == "LB" else tactics.overlap_right
            overlap = (
                0.27 * off + 0.23 * ant + 0.22 * pace + 0.13 * stamina + 0.15 * crossing
            ) * (0.66 + 0.42 * overlap_setting + 0.10 * space)
            add(
                "wide_overlap", overlap,
                projected_band=self._next_band(zone.band),
                projected_lane=natural,
                hiddenness=0.38,
                depth_gain=0.48 * depth + 0.20,
            )
            underlap = (
                0.29 * off + 0.27 * ant + 0.17 * pace + 0.12 * tech
                + 0.08 * vision + 0.07 * stamina
            ) * (0.64 + 0.30 * overlap_setting + 0.10 * support)
            add(
                "underlap", underlap,
                projected_band=self._next_band(zone.band),
                projected_lane=Lane.CENTER,
                hiddenness=0.50,
                depth_gain=0.42 * depth + 0.18,
            )

        if zone.band == Band.ATT and pos in {"ST", "AM", "LW", "RW", "CM"}:
            box_attack = (
                0.30 * off + 0.27 * ant + 0.12 * pace + 0.14 * finish
                + 0.10 * heading + 0.07 * comp
            ) * (0.74 + 0.30 * scan_space)
            add(
                "box_attack", box_attack,
                projected_band=Band.BOX,
                projected_lane=Lane.CENTER,
                hiddenness=0.33 if pos == "ST" else 0.48,
                depth_gain=0.74,
            )

        if zone.band in {Band.ATT, Band.BOX} and zone.lane != Lane.CENTER and pos in {"ST", "AM", "LW", "RW"}:
            far_lane = self._opposite_lane(zone.lane)
            far_post = (
                0.29 * off + 0.28 * ant + 0.13 * pace + 0.13 * heading
                + 0.11 * finish + 0.06 * comp
            ) * (0.76 + 0.18 * decoy + 0.10 * support)
            add(
                "far_post_run", far_post,
                projected_band=Band.BOX,
                projected_lane=far_lane,
                hiddenness=0.58,
                depth_gain=0.62,
            )

        if zone.band in {Band.ATT, Band.BOX} and pos in {"CM", "AM", "DM"}:
            late = (
                0.27 * off + 0.33 * ant + 0.10 * pace + 0.12 * finish
                + 0.09 * long_shots + 0.09 * comp
            ) * (0.76 + 0.16 * support + 0.10 * (1.0 - pressure))
            add(
                "late_arrival", late,
                projected_band=Band.BOX,
                projected_lane=Lane.CENTER,
                hiddenness=0.55,
                depth_gain=0.46,
            )

        if zone.band == Band.BOX and pos in {"AM", "CM", "LW", "RW", "LB", "RB"}:
            cutback_support = (
                0.28 * off + 0.29 * ant + 0.14 * tech + 0.12 * vision
                + 0.10 * comp + 0.07 * stamina
            ) * (0.78 + 0.18 * support)
            add(
                "cutback_support", cutback_support,
                projected_band=Band.BOX,
                projected_lane=Lane.CENTER,
                hiddenness=0.46,
                depth_gain=0.18,
            )

        return intents

    def _best_movement(
        self,
        team: int,
        actor: PlayerState,
        ps: PlayerState,
        zone: Zone,
        ctx: dict,
    ) -> dict:
        intents = self._movement_intents(team, actor, ps, zone, ctx)
        # One player cannot simultaneously occupy disconnected spaces. Selecting
        # exactly one intent enforces that invariant for this beat.
        return max(intents, key=lambda x: x["score"])

    def _movement_quality(self, ps: PlayerState, movement: dict, zone: Zone, ctx: dict) -> float:
        """Projected receiver value 0.7-2.3s ahead, independent of creativity."""
        base = super()._receiver_option_quality(ps, zone, ctx)
        timing = float(movement["timing"])
        score = float(movement["score"])
        depth_gain = float(movement["depth_gain"])
        projection = float(movement["projection_seconds"])

        # Fast-developing, well-timed movement has more immediate value. This is
        # movement quality, not pass execution quality.
        horizon = clamp(1.12 - 0.12 * max(0.0, projection - 1.0))
        multiplier = 0.78 + 0.20 * score + 0.12 * timing + 0.10 * depth_gain
        if movement["projected_band"] == Band.BOX and zone.band != Band.BOX:
            multiplier += 0.04
        return clamp(base * multiplier * horizon)

    def movement_diagnostic(
        self,
        team: int,
        actor: PlayerState,
        zone: Zone,
        ctx: Optional[dict] = None,
    ) -> list[dict]:
        """Deterministic snapshot of teammates' active off-ball intentions."""
        context = dict(ctx or {
            "pressure": 0.50, "space": 0.50, "space_behind": 0.40, "support": 0.50,
        })
        rows = []
        for ps in self.teams[team].on_field:
            if ps.player.name == actor.player.name or ps.player.position.upper() == "GK":
                continue
            mv = self._best_movement(team, actor, ps, zone, context)
            projected_quality = self._movement_quality(ps, mv, zone, context)
            rows.append({
                "player": ps.player.name,
                "position": ps.player.position,
                **mv,
                "projected_band": mv["projected_band"].value,
                "projected_lane": mv["projected_lane"].value,
                "projected_quality": projected_quality,
                "obviousness": self._target_obviousness(ps, zone),
            })
        rows.sort(key=lambda x: x["projected_quality"], reverse=True)
        return rows

    # ---------- integration with receiver selection / creativity ----------

    def _receiver_option_quality(self, ps: PlayerState, zone: Zone, ctx: dict) -> float:
        # Preserve the parent behavior for callers that do not provide a movement
        # candidate explicitly. Movement-aware paths call _movement_quality.
        return super()._receiver_option_quality(ps, zone, ctx)

    def _hidden_opportunity(
        self,
        team: int,
        actor: PlayerState,
        zone: Zone,
        ctx: dict,
    ) -> Optional[dict]:
        """Find a high-value under-attended *movement*, not just a player."""
        if zone.band == Band.DEF:
            return None

        hidden_candidates = []
        obvious_candidates = []
        for ps in self.teams[team].on_field:
            if ps.player.name == actor.player.name or ps.player.position.upper() == "GK":
                continue
            mv = self._best_movement(team, actor, ps, zone, ctx)
            quality = self._movement_quality(ps, mv, zone, ctx)
            base_obvious = self._target_obviousness(ps, zone)
            effective_obvious = clamp(base_obvious * (1.0 - 0.36 * mv["hiddenness"]))

            # The obvious comparison is the receiver the defence/ball carrier
            # already sees *now*, not that same player's most exotic projected
            # movement. This preserves the intended Félix/Valverde vs. Remo
            # structure: central threats can occupy attention while a winger or
            # midfielder creates a separate blind-side option.
            if base_obvious >= 0.72:
                current_quality = super()._receiver_option_quality(ps, zone, ctx)
                obvious_candidates.append((ps, current_quality, base_obvious, mv))

            if (
                base_obvious <= 0.82
                and effective_obvious < 0.69
                and mv["hiddenness"] >= 0.42
            ):
                hidden_candidates.append((ps, quality, effective_obvious, mv))

        if not hidden_candidates or not obvious_candidates:
            return None

        hidden_ps, hidden_quality, hidden_obviousness, hidden_mv = max(
            hidden_candidates, key=lambda x: x[1]
        )
        obvious_ps, obvious_quality, _, obvious_mv = max(obvious_candidates, key=lambda x: x[1])
        margin = hidden_quality - obvious_quality

        qualifies = hidden_quality >= 0.54 and margin >= 0.014
        return {
            "target": hidden_ps,
            "target_name": hidden_ps.player.name,
            "quality": hidden_quality,
            "obviousness": hidden_obviousness,
            "best_obvious": obvious_ps.player.name,
            "best_obvious_quality": obvious_quality,
            "margin": margin,
            "qualifies": qualifies,
            "action": hidden_mv["action"],
            "movement": dict(hidden_mv),
            "obvious_movement": dict(obvious_mv),
        }

    def hidden_option_diagnostic(
        self,
        team: int,
        actor: PlayerState,
        zone: Zone,
        ctx: Optional[dict] = None,
    ) -> Optional[dict]:
        out = super().hidden_option_diagnostic(team, actor, zone, ctx)
        if out is None:
            return None
        context = dict(ctx or {
            "pressure": 0.50, "space": 0.50, "space_behind": 0.40, "support": 0.50,
        })
        info = self._hidden_opportunity(team, actor, zone, context)
        if info is not None:
            mv = info["movement"]
            out["movement"] = {
                **mv,
                "projected_band": mv["projected_band"].value,
                "projected_lane": mv["projected_lane"].value,
            }
        return out

    def _base_target_weights(
        self,
        team: int,
        zone: Zone,
        actor: PlayerState,
        ctx: Optional[dict] = None,
    ) -> list[tuple[PlayerState, float]]:
        """Normal receiver preference plus *visible* off-ball movement.

        Highly hidden runs are intentionally damped here; creativity is the
        mechanism that can explicitly surface them as a hidden option.
        """
        context = dict(ctx or {
            "pressure": 0.50, "space": 0.50, "space_behind": 0.40, "support": 0.50,
        })
        base = super()._base_target_weights(team, zone, actor)
        out = []
        for ps, w in base:
            mv = self._best_movement(team, actor, ps, zone, context)
            visible = 1.0 - 0.58 * float(mv["hiddenness"])
            movement_factor = 0.90 + 0.30 * float(mv["score"]) * visible
            out.append((ps, max(0.001, w * movement_factor)))
        return out

    def target_probabilities(
        self,
        team: int,
        actor: PlayerState,
        zone: Zone,
        ctx: Optional[dict] = None,
    ) -> dict[str, float]:
        context = dict(ctx or {
            "pressure": 0.50, "space": 0.50, "space_behind": 0.40, "support": 0.50,
        })
        weights = self._base_target_weights(team, zone, actor, context)
        total = sum(w for _, w in weights)
        base = {ps.player.name: w / total for ps, w in weights}

        info = self._hidden_opportunity(team, actor, zone, context)
        if not info or not info["qualifies"]:
            return base

        tactics = self.teams[team].team.tactics
        confidence = clamp(0.44 + 2.9 * max(0.0, info["margin"]), 0.44, 0.92)
        perceive = clamp(self._creative_scope(actor, zone, tactics, context) * confidence)
        risk = self._risk_reward_profile(team, actor, zone, context, info)
        choose_hidden = clamp(perceive * risk["acceptance_probability"])
        if choose_hidden <= 0:
            return base

        target_name = info["target_name"]
        return {
            name: ((1.0 - choose_hidden) * prob + (choose_hidden if name == target_name else 0.0))
            for name, prob in base.items()
        }

    def _choose_decision(self, actor, zone, tactics, ctx) -> str:
        team = self._team_index_for_actor(actor)
        self._v13_receiver_context = (
            {"team": team, "actor": actor.player.name, "zone": zone, "ctx": dict(ctx)}
            if team is not None else None
        )
        decision = super()._choose_decision(actor, zone, tactics, ctx)
        if decision not in {"progressive_pass", "switch", "long_ball", "through_ball", "cross", "cutback"}:
            self._v13_receiver_context = None
        return decision

    def _choose_target(self, team, zone, attacking=True, exclude=None) -> PlayerState:
        if not attacking:
            self._v13_receiver_context = None
            return super()._choose_target(team, zone, attacking=False, exclude=exclude)

        ctx_marker = getattr(self, "_v13_receiver_context", None)
        context = None
        actor = None
        if (
            ctx_marker is not None
            and ctx_marker.get("team") == team
            and ctx_marker.get("actor") == exclude
            and ctx_marker.get("zone") == zone
        ):
            context = dict(ctx_marker["ctx"])
        try:
            actor = self.teams[team].by_name(exclude) if exclude else None
        except KeyError:
            actor = None

        marker = getattr(self, "_v13_forced_target", None)
        if marker is not None:
            if marker.get("team") == team and marker.get("actor") == exclude:
                try:
                    target = self.teams[team].by_name(marker["target"])
                except KeyError:
                    target = None
                self._v13_forced_target = None
                self._v13_receiver_context = None
                if target is not None and actor is not None:
                    info = self._hidden_opportunity(
                        team, actor, zone,
                        context or {"pressure": 0.50, "space": 0.50, "space_behind": 0.40, "support": 0.50},
                    )
                    movement = info["movement"] if info and info["target_name"] == target.player.name else self._best_movement(
                        team, actor, target, zone,
                        context or {"pressure": 0.50, "space": 0.50, "space_behind": 0.40, "support": 0.50},
                    )
                    self._v13_active_movement = {
                        "team": team, "actor": actor.player.name, "target": target.player.name,
                        "movement": dict(movement), "creative": True,
                    }
                    return target
            else:
                self._v13_forced_target = None

        if actor is None:
            self._v13_receiver_context = None
            return super()._choose_target(team, zone, attacking=True, exclude=exclude)

        use_ctx = context or {"pressure": 0.50, "space": 0.50, "space_behind": 0.40, "support": 0.50}
        target = weighted_choice(self.rng, self._base_target_weights(team, zone, actor, use_ctx))
        movement = self._best_movement(team, actor, target, zone, use_ctx)
        self._v13_active_movement = {
            "team": team, "actor": actor.player.name, "target": target.player.name,
            "movement": dict(movement), "creative": False,
        }
        self._v13_receiver_context = None
        return target

    def _danger_score(self, team, actor, target, zone, kind, ctx) -> float:
        base = super()._danger_score(team, actor, target, zone, kind, ctx)
        active = getattr(self, "_v13_active_movement", None)
        if not active:
            return base
        if (
            active.get("team") != team
            or active.get("actor") != actor.player.name
            or active.get("target") != target.player.name
        ):
            self._v13_active_movement = None
            return base

        mv = active["movement"]
        self._v13_active_movement = None
        score = float(mv["score"])
        timing = float(mv["timing"])
        depth_gain = float(mv["depth_gain"])

        # Smart movement can improve the *situation* created, but does not boost
        # the passer's technical execution. Hiddenness itself gives no bonus.
        movement_boost = max(0.0, score - 0.55) * 0.075
        movement_boost += max(0.0, timing - 0.58) * 0.045
        if kind == "through_ball":
            movement_boost += max(0.0, depth_gain - 0.30) * 0.035
        return clamp(base + min(0.085, movement_boost))


MatchEngine = MatchEngineV13OffBall
