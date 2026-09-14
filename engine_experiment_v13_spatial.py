from __future__ import annotations

"""Experimental v1.3: geospatial decision adaptation.

This module deliberately leaves the stable engine untouched.  It layers one
structural change on top of the current stable MatchEngine when available:
player decisions are weighted by *where the ball carrier is on the pitch* and
by the local situation (space, pressure, support, lane, preferred foot), rather
than by player attributes alone.

The engine still does not target a score, shot count or per-player quota.
"""

from typing import Optional

from engine import Band, Lane, PlayerState, Tactics, Zone, clamp, weighted_choice

try:  # In the GitHub project, v1.2 is exposed through stable_engine.py.
    from stable_engine import MatchEngine as _StableMatchEngine  # type: ignore
except ImportError:  # Local/fallback compatibility with the audited base engine.
    from engine import MatchEngine as _StableMatchEngine


VERSION = "1.3-candidate-spatial-creativity-boldness"


class MatchEngineV13Spatial(_StableMatchEngine):
    """Stable engine + geospatial/contextual decision weighting.

    Principle:
        location + space + pressure + attributes + role + creativity
        -> perceived options -> decision weights -> execution.

    Creativity is deliberately *not* an execution bonus. It discovers
    plausible non-obvious options, especially latent/blind-side runs. A
    separate boldness/ousadia trait controls willingness to accept a little
    more execution risk for materially more upside. Passing, technique,
    dribbling, finishing, etc. still decide whether the idea succeeds.
    """

    def _creativity(self, actor: PlayerState) -> float:
        """Return 0..1 creative-perception score.

        v1.3 accepts an optional ``player.creativity`` attribute without
        requiring the stable v1.2 Player schema to change.  Until rosters are
        explicitly calibrated, a conservative fallback is inferred from
        vision/technique/composure.
        """
        explicit = getattr(actor.player, "creativity", None)
        if explicit is not None:
            raw = float(explicit) / 100.0
            # Fatigue/injury can narrow the player's attentional bandwidth.
            fatigue = 0.88 + 0.12 * actor.energy
            if actor.injured:
                fatigue *= 0.90
            return clamp(raw * fatigue)
        return clamp(
            0.48 * actor.effective("vision") / 100.0
            + 0.32 * actor.effective("technique") / 100.0
            + 0.20 * actor.effective("composure") / 100.0
        )

    def _team_index_for_actor(self, actor: PlayerState) -> Optional[int]:
        for ti, rt in enumerate(self.teams):
            for ps in rt.on_field:
                if ps is actor or ps.player.name == actor.player.name:
                    return ti
        return None

    @staticmethod
    def _target_obviousness(ps: PlayerState, zone: Zone) -> float:
        """How much a receiver naturally attracts the defence's attention."""
        pos = ps.player.position.upper()
        base = {
            "ST": 0.90, "AM": 0.84, "LW": 0.62, "RW": 0.62,
            "CM": 0.58, "DM": 0.45, "LB": 0.38, "RB": 0.38,
            "CB": 0.25, "GK": 0.08,
        }.get(pos, 0.50)
        if zone.lane == Lane.CENTER and pos in {"ST", "AM", "CM"}:
            base += 0.08
        if zone.lane == Lane.LEFT and pos in {"LW", "LB"}:
            base += 0.07
        if zone.lane == Lane.RIGHT and pos in {"RW", "RB"}:
            base += 0.07
        return clamp(base)

    @staticmethod
    def _lane_novelty(ps: PlayerState, zone: Zone) -> float:
        pos = ps.player.position.upper()
        side = Lane.LEFT if pos in {"LW", "LB"} else Lane.RIGHT if pos in {"RW", "RB"} else Lane.CENTER
        if side == zone.lane:
            return 0.72
        if zone.lane == Lane.CENTER and side != Lane.CENTER:
            return 1.18
        if side == Lane.CENTER and zone.lane != Lane.CENTER:
            return 0.96
        return 1.28  # far-side / blind-side movement

    def _latent_run_value(self, ps: PlayerState, zone: Zone, ctx: dict) -> float:
        """Projected value of a receiver who is not necessarily best *now*."""
        off_ball = ps.effective("off_ball") / 100.0
        anticipation = ps.effective("anticipation") / 100.0
        pace = ps.effective("pace") / 100.0
        technique = ps.effective("technique") / 100.0
        space_behind = clamp(float(ctx.get("space_behind", 0.4)))
        support = clamp(float(ctx.get("support", 0.5)))
        run = 0.36 * off_ball + 0.24 * anticipation + 0.23 * pace + 0.17 * technique
        run *= 0.72 + 0.42 * space_behind + 0.10 * support
        run *= self._lane_novelty(ps, zone)
        return clamp(run)

    def _hidden_option_signal(self, team: int, actor: PlayerState, zone: Zone, ctx: dict) -> float:
        """Strength of the best plausible under-attended future option."""
        values = []
        for ps in self.teams[team].on_field:
            if ps.player.name == actor.player.name or ps.player.position.upper() == "GK":
                continue
            hidden = 1.0 - self._target_obviousness(ps, zone)
            latent = self._latent_run_value(ps, zone, ctx)
            values.append(hidden * latent)
        return max(values, default=0.0)

    def _creative_scope(self, actor: PlayerState, zone: Zone, tactics: Tactics, ctx: dict) -> float:
        """How much freedom there is to search beyond the obvious option."""
        zone_allow = {Band.DEF: 0.10, Band.MID: 0.58, Band.ATT: 1.00, Band.BOX: 0.78}[zone.band]
        creativity = self._creativity(actor)
        # Creativity below roughly average still allows normal vision-based
        # play, but contributes little to *non-obvious* option discovery.
        creative_drive = clamp((creativity - 0.38) / 0.62)
        space = clamp(float(ctx.get("space", 0.5)))
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        # Some pressure can make disguise valuable, but extreme pressure shrinks
        # time to scan. This peaks around moderate pressure.
        pressure_window = clamp(1.08 - 1.25 * max(0.0, pressure - 0.45))
        support = clamp(float(ctx.get("support", 0.5)))
        # Perception is intentionally independent from tactical risk/boldness.
        # A riskier team may *accept* more difficult ideas later, but it does
        # not magically make the player see runs that creativity did not spot.
        scan_environment = 0.94 + 0.08 * support
        return clamp(
            zone_allow * creative_drive * (0.78 + 0.34 * space)
            * pressure_window * scan_environment
        )


    def _boldness(self, actor: PlayerState) -> float:
        """0..1 appetite for high-variance/high-reward decisions.

        This is intentionally separate from creativity. Creativity discovers
        an option; boldness influences whether a perceived option with higher
        upside but more execution risk is worth taking. It never improves
        execution and never makes a clearly bad option acceptable.
        """
        explicit = getattr(actor.player, "boldness", None)
        if explicit is None:
            explicit = getattr(actor.player, "ousadia", None)
        return 0.50 if explicit is None else clamp(float(explicit) / 100.0)

    def _match_risk_context(self, team: int) -> float:
        """-1..1 contextual pressure from score + time."""
        h, a = self.score
        diff = (h - a) if team == 0 else (a - h)
        late = clamp((self.minute - 55.0) / 35.0)
        if diff < 0:
            return clamp((-diff) * late)
        if diff > 0:
            return -clamp(diff * late)
        return 0.0

    @staticmethod
    def _zone_failure_cost(zone: Zone, ctx: dict) -> float:
        base = {
            Band.DEF: 0.92,
            Band.MID: 0.58,
            Band.ATT: 0.31,
            Band.BOX: 0.16,
        }[zone.band]
        transition_threat = clamp(float(ctx.get("transition_threat", 0.50)))
        return clamp(base * (0.86 + 0.28 * transition_threat), 0.08, 1.0)

    def _keeper_attack_mode(self, team: int, zone: Zone) -> str:
        """Contextual goalkeeper positioning: normal, high_support, keeper_up.

        The keeper never leaks forward from a generic tiny probability. Forward
        involvement is enabled only by explicit match context.
        """
        home, away = self.score
        diff = (home - away) if team == 0 else (away - home)
        minute = self.minute
        if diff >= 0 or minute < 86.0:
            return "normal"

        restart_attacking = (
            self.state.restart_team == team
            and self.state.restart in {"corner", "free_kick"}
        )
        if (
            minute >= 89.0
            and restart_attacking
            and zone.band in {Band.ATT, Band.BOX}
        ):
            return "keeper_up"
        if minute >= 92.0 and zone.band in {Band.ATT, Band.BOX}:
            return "keeper_up"
        if minute >= 88.0 and zone.band == Band.MID:
            return "high_support"
        return "normal"

    def _ensure_keeper_exposure_state(self) -> None:
        if not hasattr(self, "_v13_keeper_up_team"):
            self._v13_keeper_up_team = None
        if not hasattr(self, "_v13_keeper_up_until"):
            self._v13_keeper_up_until = 0.0

    def _activate_keeper_up(self, team: int, seconds: float = 32.0) -> None:
        self._ensure_keeper_exposure_state()
        self._v13_keeper_up_team = int(team)
        self._v13_keeper_up_until = max(
            float(self._v13_keeper_up_until), self.state.second + float(seconds)
        )

    def _clear_keeper_up(self, team: Optional[int] = None) -> None:
        self._ensure_keeper_exposure_state()
        if team is None or self._v13_keeper_up_team == team:
            self._v13_keeper_up_team = None
            self._v13_keeper_up_until = 0.0

    def _keeper_is_exposed(self, team: int) -> bool:
        self._ensure_keeper_exposure_state()
        if self.state.second > self._v13_keeper_up_until:
            self._clear_keeper_up()
            return False
        return self._v13_keeper_up_team == team

    def export_state(self) -> dict:
        data = super().export_state()
        self._ensure_keeper_exposure_state()
        data["v13_keeper_up"] = {
            "team": self._v13_keeper_up_team,
            "until": self._v13_keeper_up_until,
        }
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        keeper = data.get("v13_keeper_up", {})
        obj._v13_keeper_up_team = keeper.get("team")
        obj._v13_keeper_up_until = float(keeper.get("until", 0.0))
        return obj

    def _contextual_attacking_receiver_eligible(
        self, team: int, zone: Zone, ps: PlayerState
    ) -> bool:
        if ps.player.position.upper() != "GK":
            return True
        mode = self._keeper_attack_mode(team, zone)
        return (
            (mode == "high_support" and zone.band == Band.MID)
            or (mode == "keeper_up" and zone.band in {Band.MID, Band.ATT, Band.BOX})
        )

    def _resolve_restart(self):
        kind = self.state.restart
        team = self.state.restart_team
        zone = self.state.restart_zone or self.state.zone
        keeper_up = (
            team is not None
            and kind in {"corner", "free_kick"}
            and self._keeper_attack_mode(team, zone) == "keeper_up"
        )
        if keeper_up:
            self._activate_keeper_up(team, seconds=36.0)
        event = super()._resolve_restart()
        if keeper_up:
            event.data["keeper_up"] = True
        return event

    def _calculate_xg(self, p, shooter, defender, keeper) -> float:
        xg = super()._calculate_xg(p, shooter, defender, keeper)
        defending_team = 1 - p.team
        if not self._keeper_is_exposed(defending_team):
            return xg
        # Keeper out of goal: loss of possession has a real downside. The bonus
        # is strongest for transitions and advanced shots, but even a long-range
        # attempt at an empty goal becomes materially more dangerous.
        empty_goal_bonus = {
            Band.DEF: 0.075, Band.MID: 0.145, Band.ATT: 0.235, Band.BOX: 0.285
        }[p.zone.band]
        if p.origin in {"transition", "turnover", "carry", "progression"}:
            empty_goal_bonus += 0.065
        return clamp(xg + empty_goal_bonus, 0.003, 0.88)

    def _switch_possession(self, new_team, zone, transition=0.0):
        super()._switch_possession(new_team, zone, transition=transition)
        # Once the exposed keeper's team safely recovers the ball in a normal
        # build-up zone, he is considered to have retreated.
        if self._keeper_is_exposed(new_team) and zone.band in {Band.DEF, Band.MID}:
            self._clear_keeper_up(new_team)

    def _emit(self, typ, team, relevance, text_key, **data):
        event = super()._emit(typ, team, relevance, text_key, **data)
        if getattr(typ, "value", typ) == "goal":
            self._clear_keeper_up()
        return event

    def _choose_actor(self, team: int, zone: Zone) -> PlayerState:
        """Choose the ball carrier without letting the goalkeeper teleport forward.

        The keeper remains eligible in the defensive third for ordinary build-up.
        Outside that band, open-play possession actors must be outfield players
        unless a future explicit keeper-up mechanic opts in.
        """
        if zone.band == Band.DEF:
            return super()._choose_actor(team, zone)

        rt = self.teams[team]
        tactics = rt.team.tactics
        weights: list[tuple[PlayerState, float]] = []
        for ps in rt.on_field:
            pos = ps.player.position.upper()
            if pos == "GK":
                mode = self._keeper_attack_mode(team, zone)
                if mode == "high_support" and zone.band == Band.MID:
                    w = 0.035
                elif mode == "keeper_up" and zone.band in {Band.MID, Band.ATT, Band.BOX}:
                    w = {Band.MID: 0.045, Band.ATT: 0.070, Band.BOX: 0.105}[zone.band]
                else:
                    continue
                w *= 0.75 + 0.25 * ps.energy
                weights.append((ps, w))
                continue
            if zone.band == Band.MID:
                w = {
                    "DM": 1.2, "CM": 1.5, "AM": 1.15, "LB": 0.65,
                    "RB": 0.65, "LW": 0.85, "RW": 0.85, "ST": 0.45,
                    "CB": 0.35,
                }.get(pos, 0.5)
            elif zone.band == Band.ATT:
                w = {
                    "AM": 1.35, "LW": 1.25, "RW": 1.25, "ST": 1.15,
                    "CM": 0.75, "LB": 0.35, "RB": 0.35, "DM": 0.30,
                    "CB": 0.10,
                }.get(pos, 0.5)
            else:
                w = {
                    "ST": 1.65, "LW": 1.05, "RW": 1.05, "AM": 1.15,
                    "CM": 0.45, "LB": 0.16, "RB": 0.16, "DM": 0.12,
                    "CB": 0.09,
                }.get(pos, 0.4)

            if zone.lane == Lane.LEFT and pos in ("LB", "LW"):
                w *= 1.45
            if zone.lane == Lane.RIGHT and pos in ("RB", "RW"):
                w *= 1.45
            if zone.lane == Lane.CENTER and pos in ("CB", "DM", "CM", "AM", "ST"):
                w *= 1.25

            overlap_helper = getattr(self, "_fullback_overlap_factor", None)
            if callable(overlap_helper):
                w *= overlap_helper(pos, zone, tactics)
            w *= 0.75 + 0.25 * ps.energy
            weights.append((ps, w))

        selected = weighted_choice(self.rng, weights)
        if selected.player.position.upper() == "GK" and zone.band != Band.DEF:
            self._activate_keeper_up(team)
        return selected

    def _receiver_option_quality(self, ps: PlayerState, zone: Zone, ctx: dict) -> float:
        """Projected reward if this receiver gets the ball."""
        off_ball = ps.effective("off_ball") / 100.0
        anticipation = ps.effective("anticipation") / 100.0
        pace = ps.effective("pace") / 100.0
        technique = ps.effective("technique") / 100.0
        finishing = ps.effective("finishing") / 100.0
        composure = ps.effective("composure") / 100.0
        space_behind = clamp(float(ctx.get("space_behind", 0.4)))
        support = clamp(float(ctx.get("support", 0.5)))

        if zone.band == Band.BOX:
            base = (
                0.27 * off_ball + 0.19 * anticipation + 0.13 * pace
                + 0.10 * technique + 0.21 * finishing + 0.10 * composure
            )
        else:
            base = (
                0.31 * off_ball + 0.23 * anticipation + 0.19 * pace
                + 0.11 * technique + 0.08 * finishing + 0.08 * composure
            )
        spatial = 0.84 + 0.16 * space_behind + 0.05 * support
        lane = 0.93 + 0.08 * self._lane_novelty(ps, zone)
        return clamp(base * spatial * lane)

    @staticmethod
    def _attacking_receiver_eligible(ps: PlayerState) -> bool:
        """Whether a player can be selected as an ordinary attacking receiver.

        Goalkeepers remain available for defensive build-up as ball carriers,
        but they are not valid open-play attacking targets. If a future
        keeper-up/set-piece mechanic is added, it should opt in explicitly
        rather than relying on a tiny generic probability.
        """
        return ps.player.position.upper() != "GK"

    def _base_target_weights(
        self,
        team: int,
        zone: Zone,
        actor: Optional[PlayerState],
    ) -> list[tuple[PlayerState, float]]:
        """Normal receiver preference, without creativity or boldness."""
        tactics = self.teams[team].team.tactics
        weights: list[tuple[PlayerState, float]] = []
        for ps in self.teams[team].on_field:
            if actor is not None and ps.player.name == actor.player.name:
                continue
            if not self._contextual_attacking_receiver_eligible(team, zone, ps):
                continue
            pos = ps.player.position.upper()
            if pos == "GK":
                mode = self._keeper_attack_mode(team, zone)
                w = (
                    0.030 if mode == "high_support"
                    else {Band.MID: 0.040, Band.ATT: 0.060, Band.BOX: 0.095}.get(zone.band, 0.0)
                )
            else:
                w = {
                    "ST": 1.55, "AM": 1.35, "LW": 1.25, "RW": 1.25,
                    "CM": 0.75, "LB": 0.42, "RB": 0.42, "DM": 0.35,
                    "CB": 0.12,
                }.get(pos, 0.5)
            w *= 0.70 + 0.30 * ps.effective("off_ball") / 100.0

            overlap_helper = getattr(self, "_fullback_overlap_factor", None)
            if callable(overlap_helper):
                w *= overlap_helper(pos, zone, tactics, target=True)

            if zone.lane == Lane.LEFT and pos in ("LB", "LW"):
                w *= 1.25
            if zone.lane == Lane.RIGHT and pos in ("RB", "RW"):
                w *= 1.25
            weights.append((ps, max(0.001, w)))
        return weights

    def _hidden_opportunity(
        self,
        team: int,
        actor: PlayerState,
        zone: Zone,
        ctx: dict,
    ) -> Optional[dict]:
        """Best under-attended receiver, but only when it offers more upside.

        Creativity is not used in this ranking. A hidden option must first be
        genuinely attractive on footballing grounds.
        """
        if zone.band == Band.DEF:
            return None

        hidden_candidates = []
        obvious_candidates = []
        for ps in self.teams[team].on_field:
            if ps.player.name == actor.player.name or ps.player.position.upper() == "GK":
                continue
            obviousness = self._target_obviousness(ps, zone)
            quality = self._receiver_option_quality(ps, zone, ctx)
            item = (ps, quality, obviousness)
            if obviousness < 0.72:
                hidden_candidates.append(item)
            else:
                obvious_candidates.append(item)

        if not hidden_candidates or not obvious_candidates:
            return None

        hidden_ps, hidden_quality, hidden_obviousness = max(hidden_candidates, key=lambda x: x[1])
        obvious_ps, obvious_quality, _ = max(obvious_candidates, key=lambda x: x[1])
        margin = hidden_quality - obvious_quality

        qualifies = hidden_quality >= 0.56 and margin >= 0.018
        return {
            "target": hidden_ps,
            "target_name": hidden_ps.player.name,
            "quality": hidden_quality,
            "obviousness": hidden_obviousness,
            "best_obvious": obvious_ps.player.name,
            "best_obvious_quality": obvious_quality,
            "margin": margin,
            "qualifies": qualifies,
            "action": "cutback" if zone.band == Band.BOX else "through_ball",
        }

    def _pass_success_probability(
        self,
        actor: PlayerState,
        target: PlayerState,
        zone: Zone,
        ctx: dict,
        *,
        hidden: bool,
    ) -> float:
        """Decision-time estimate; actual execution remains separate."""
        passing = actor.effective("passing") / 100.0
        technique = actor.effective("technique") / 100.0
        vision = actor.effective("vision") / 100.0
        composure = actor.effective("composure") / 100.0
        anticipation = actor.effective("anticipation") / 100.0
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        space = clamp(float(ctx.get("space", 0.5)))
        support = clamp(float(ctx.get("support", 0.5)))
        space_behind = clamp(float(ctx.get("space_behind", 0.4)))

        skill = (
            0.35 * passing + 0.22 * technique + 0.18 * vision
            + 0.15 * composure + 0.10 * anticipation
        )
        target_timing = (
            0.50 * target.effective("off_ball") / 100.0
            + 0.30 * target.effective("anticipation") / 100.0
            + 0.20 * target.effective("pace") / 100.0
        )
        obviousness = self._target_obviousness(target, zone)
        lane_novelty = self._lane_novelty(target, zone)

        prob = (
            0.30 + 0.49 * skill + 0.08 * target_timing
            + 0.06 * space + 0.03 * support
            - 0.22 * pressure - 0.055 * obviousness
        )
        if hidden:
            # Surprise helps, but a blind-side/third-man window is often harder.
            prob += 0.045 * (1.0 - obviousness)
            prob -= 0.105 * max(0.0, lane_novelty - 0.72)
            prob -= 0.075 * space_behind
        else:
            prob -= 0.018 * max(0.0, lane_novelty - 0.72)
        return clamp(prob, 0.12, 0.94)

    def _risk_reward_profile(
        self,
        team: int,
        actor: PlayerState,
        zone: Zone,
        ctx: dict,
        info: dict,
    ) -> dict:
        """Compare hidden upside with obvious safety.

        High boldness may accept a small expected-value deficit for materially
        more upside. A hard floor blocks clearly foolish choices.
        """
        hidden = info["target"]
        try:
            obvious = self.teams[team].by_name(info["best_obvious"])
        except KeyError:
            return {
                "acceptance_probability": 0.0, "sane": False,
                "hidden_expected": -1.0, "obvious_expected": 0.0,
                "hidden_success": 0.0, "obvious_success": 0.0,
                "upside": 0.0, "expected_deficit": 1.0,
                "risk_appetite": 0.0,
            }

        hidden_reward = float(info["quality"])
        obvious_reward = float(info["best_obvious_quality"])
        hidden_success = self._pass_success_probability(actor, hidden, zone, ctx, hidden=True)
        obvious_success = self._pass_success_probability(actor, obvious, zone, ctx, hidden=False)
        failure_cost = self._zone_failure_cost(zone, ctx)

        hidden_expected = hidden_success * hidden_reward - (1.0 - hidden_success) * failure_cost
        obvious_expected = obvious_success * obvious_reward - (1.0 - obvious_success) * failure_cost
        upside = max(0.0, hidden_reward - obvious_reward)
        expected_deficit = max(0.0, obvious_expected - hidden_expected)

        tactics = self.teams[team].team.tactics
        match_context = self._match_risk_context(team)
        zone_allow = {
            Band.DEF: 0.00, Band.MID: 0.42, Band.ATT: 1.00, Band.BOX: 0.82
        }[zone.band]
        risk_appetite = clamp(
            0.66 * self._boldness(actor)
            + 0.20 * tactics.risk
            + 0.08 * max(0.0, tactics.mentality)
            + 0.16 * match_context
        )

        allowed_deficit = (
            0.006 + 0.070 * risk_appetite * zone_allow
            + 0.020 * max(0.0, match_context)
        )
        sane = (
            zone.band != Band.DEF
            and upside >= 0.018
            and hidden_reward >= 0.56
            and expected_deficit <= allowed_deficit
        )

        if not sane:
            acceptance = 0.0
        elif hidden_expected >= obvious_expected:
            acceptance = clamp(
                0.66 + 0.16 * zone_allow + 0.10 * risk_appetite
                + 0.10 * min(1.0, upside / 0.16),
                0.0, 0.98,
            )
        else:
            upside_strength = clamp(upside / 0.18)
            deficit_ratio = clamp(expected_deficit / max(allowed_deficit, 1e-9))
            acceptance = clamp(
                0.05
                + 0.72 * risk_appetite * upside_strength
                * (1.0 - 0.55 * deficit_ratio),
                0.0, 0.90,
            )

        return {
            "acceptance_probability": acceptance,
            "sane": sane,
            "hidden_success": hidden_success,
            "obvious_success": obvious_success,
            "hidden_expected": hidden_expected,
            "obvious_expected": obvious_expected,
            "upside": upside,
            "expected_deficit": expected_deficit,
            "allowed_deficit": allowed_deficit,
            "failure_cost": failure_cost,
            "risk_appetite": risk_appetite,
            "match_risk_context": match_context,
        }

    def hidden_option_diagnostic(
        self,
        team: int,
        actor: PlayerState,
        zone: Zone,
        ctx: Optional[dict] = None,
    ) -> Optional[dict]:
        context = ctx or self._spatial_context(team, zone)
        info = self._hidden_opportunity(team, actor, zone, context)
        if info is None:
            return None
        out = dict(info)
        out.pop("target", None)
        if info["qualifies"]:
            tactics = self.teams[team].team.tactics
            confidence = clamp(0.46 + 3.2 * max(0.0, info["margin"]), 0.46, 0.92)
            perceive = clamp(self._creative_scope(actor, zone, tactics, context) * confidence)
            risk = self._risk_reward_profile(team, actor, zone, context, info)
            out["perception_probability"] = perceive
            out["acceptance_probability_if_perceived"] = risk["acceptance_probability"]
            out["effective_hidden_choice_probability"] = perceive * risk["acceptance_probability"]
        else:
            out["perception_probability"] = 0.0
            out["acceptance_probability_if_perceived"] = 0.0
            out["effective_hidden_choice_probability"] = 0.0
        return out

    def risk_reward_diagnostic(
        self,
        team: int,
        actor: PlayerState,
        zone: Zone,
        ctx: Optional[dict] = None,
    ) -> Optional[dict]:
        context = ctx or self._spatial_context(team, zone)
        info = self._hidden_opportunity(team, actor, zone, context)
        if info is None:
            return None
        return {
            "target_name": info["target_name"],
            "best_obvious": info["best_obvious"],
            "hidden_reward": info["quality"],
            "obvious_reward": info["best_obvious_quality"],
            "qualifies": info["qualifies"],
            **self._risk_reward_profile(team, actor, zone, context, info),
        }

    @staticmethod
    def _player_to_dict(player):
        data = _StableMatchEngine._player_to_dict(player)
        for attr in ("creativity", "boldness", "ousadia"):
            if hasattr(player, attr):
                data[attr] = getattr(player, attr)
        return data

    @staticmethod
    def _player_from_dict(data):
        payload = dict(data)
        extras = {
            k: payload.pop(k)
            for k in ("creativity", "boldness", "ousadia")
            if k in payload
        }
        player = _StableMatchEngine._player_from_dict(payload)
        for key, value in extras.items():
            setattr(player, key, value)
        return player

    @staticmethod
    def _inverted_foot_bonus(actor: PlayerState, lane: Lane) -> float:
        """Return a mild inside-foot shooting bonus for inverted wide players."""
        foot = (actor.player.preferred_foot or "R").upper()
        if lane == Lane.LEFT and foot == "R":
            return 1.12
        if lane == Lane.RIGHT and foot == "L":
            return 1.12
        return 1.0

    def _decision_weights(
        self,
        actor: PlayerState,
        zone: Zone,
        tactics: Tactics,
        ctx: dict,
    ) -> list[tuple[str, float]]:
        """Build context-aware decision weights for the current location.

        The bands are attack-relative:
        DEF = own defensive third, MID = midfield, ATT = final third,
        BOX = opponent penalty area.
        """
        passing = actor.effective("passing") / 100.0
        vision = actor.effective("vision") / 100.0
        technique = actor.effective("technique") / 100.0
        dribbling = actor.effective("dribbling") / 100.0
        crossing = actor.effective("crossing") / 100.0
        finishing = actor.effective("finishing") / 100.0
        long_shots = actor.effective("long_shots") / 100.0
        composure = actor.effective("composure") / 100.0
        pace = actor.effective("pace") / 100.0

        pressure = clamp(float(ctx.get("pressure", 0.5)))
        space = clamp(float(ctx.get("space", 0.5)))
        space_behind = clamp(float(ctx.get("space_behind", 0.4)))
        support = clamp(float(ctx.get("support", 0.5)))

        risk = clamp(0.45 * tactics.risk + 0.30 * max(0.0, tactics.mentality) + 0.25 * vision)
        wide = zone.lane != Lane.CENTER
        center = zone.lane == Lane.CENTER
        inverted = self._inverted_foot_bonus(actor, zone.lane)

        # Own defensive third: survival/progression dominates.  Shooting is not
        # a normal option here. Under heavy pressure, clearing/direct play grows.
        if zone.band == Band.DEF:
            safe_pass = (
                0.30
                + 0.24 * passing
                + 0.20 * composure
                + 0.12 * support
                - 0.12 * pressure
                - 0.08 * tactics.directness
            )
            progressive = (
                0.12
                + 0.20 * passing
                + 0.18 * vision
                + 0.12 * space
                + 0.10 * tactics.directness
                - 0.14 * pressure
            )
            carry = (
                0.03
                + 0.13 * dribbling
                + 0.07 * pace
                + 0.14 * space
                - 0.18 * pressure
            )
            long_ball = (
                0.05
                + 0.18 * tactics.directness
                + 0.11 * passing
                + 0.15 * pressure
                + 0.06 * (1.0 - composure)
            )
            return [
                ("safe_pass", safe_pass),
                ("progressive_pass", progressive),
                ("carry", carry),
                ("long_ball", long_ball),
            ]

        # Midfield: orientation and progression.  A true long-shot specialist
        # may occasionally try from a central, low-pressure pocket, but it is
        # intentionally rare.
        if zone.band == Band.MID:
            items: list[tuple[str, float]] = [
                ("safe_pass", 0.16 + 0.17 * passing + 0.12 * composure + 0.08 * support - 0.06 * risk),
                ("progressive_pass", 0.16 + 0.20 * passing + 0.20 * vision + 0.10 * risk + 0.10 * space),
                ("carry", 0.05 + 0.14 * dribbling + 0.07 * pace + 0.12 * space - 0.10 * pressure),
                ("switch", 0.05 + 0.12 * passing + 0.11 * vision + 0.10 * tactics.width),
                ("through_ball", 0.04 + 0.17 * vision * (0.55 + space_behind) + 0.07 * risk),
                ("long_ball", 0.03 + 0.12 * tactics.directness + 0.07 * passing + 0.05 * pressure),
            ]
            if center and long_shots >= 0.84:
                speculative = (
                    0.005
                    + 0.055 * (long_shots - 0.80)
                    + 0.025 * technique
                    + 0.035 * space
                    - 0.045 * pressure
                )
                if speculative > 0.008:
                    items.append(("shoot", speculative))
            return items

        # Final third: lane and player profile matter strongly.  Central players
        # with space can shoot; wide players naturally see more cross/cutback,
        # while inverted-foot players gain a modest cut-inside shooting option.
        if zone.band == Band.ATT:
            shoot = (
                0.025
                + 0.16 * long_shots
                + 0.08 * finishing
                + 0.07 * technique
                + 0.13 * space
                + 0.05 * composure
                - 0.13 * pressure
            )
            shoot *= 1.35 if center else 0.78 * inverted

            through = (
                0.07
                + 0.22 * vision
                + 0.14 * passing
                + 0.16 * space_behind
                + 0.07 * support
                + 0.06 * risk
            )
            cross = (
                0.015
                + (0.16 * crossing + 0.16 * tactics.cross_frequency + 0.08 * support + 0.07 * space)
                * (1.0 if wide else 0.18)
            )
            cutback = (
                0.018
                + (0.13 * vision + 0.10 * technique + 0.12 * support + 0.08 * pressure)
                * (1.0 if wide else 0.28)
            )
            dribble = (
                0.04
                + 0.17 * dribbling
                + 0.08 * pace
                + 0.11 * space
                + 0.05 * technique
                - 0.12 * pressure
            )
            if wide and inverted > 1.0:
                dribble *= 1.08

            return [
                ("safe_pass", 0.055 + 0.10 * passing + 0.08 * composure + 0.06 * support),
                ("progressive_pass", 0.07 + 0.13 * passing + 0.11 * vision + 0.08 * space),
                ("carry", 0.04 + 0.10 * dribbling + 0.06 * pace + 0.08 * space),
                ("through_ball", through),
                ("cross", cross),
                ("cutback", cutback),
                ("dribble", dribble),
                ("shoot", shoot),
            ]

        # Opponent box: the default offensive thought is to finish, but not
        # blindly. Central angle + space boosts the shot; wide angle, pressure
        # and strong support make cutback/pass more attractive.
        shoot = (
            0.34
            + 0.28 * finishing
            + 0.12 * composure
            + 0.08 * technique
            + 0.24 * space
            - 0.23 * pressure
        )
        if center:
            shoot *= 1.28
        else:
            shoot *= 0.78 * inverted

        cutback = (
            0.045
            + 0.16 * vision
            + 0.10 * technique
            + 0.16 * support
            + 0.10 * pressure
        ) * (1.18 if wide else 0.62)

        dribble = (
            0.035
            + 0.16 * dribbling
            + 0.06 * pace
            + 0.13 * space
            - 0.12 * pressure
        ) * (1.12 if wide else 0.88)

        safe_pass = (
            0.035
            + 0.10 * passing
            + 0.12 * composure
            + 0.12 * support
            + 0.08 * pressure
        ) * (1.15 if wide else 0.75)

        cross = (
            0.01
            + 0.11 * crossing
            + 0.06 * tactics.cross_frequency
        ) * (0.70 if wide else 0.10)

        return [
            ("shoot", shoot),
            ("cutback", cutback),
            ("dribble", dribble),
            ("safe_pass", safe_pass),
            ("cross", cross),
        ]


    def decision_probabilities(
        self,
        actor: PlayerState,
        zone: Zone,
        tactics: Tactics,
        ctx: dict,
    ) -> dict[str, float]:
        """Normalized location/context decision profile.

        Creativity and boldness are deliberately absent from the generic action
        menu: they operate only after a non-obvious receiver has been identified.
        """
        cleaned = [
            (k, max(0.0, float(w)))
            for k, w in self._decision_weights(actor, zone, tactics, ctx)
        ]
        total = sum(w for _, w in cleaned)
        if total <= 0:
            return {cleaned[0][0]: 1.0}
        return {k: w / total for k, w in cleaned}

    def target_probabilities(
        self,
        team: int,
        actor: PlayerState,
        zone: Zone,
        ctx: Optional[dict] = None,
    ) -> dict[str, float]:
        """Expected receiver distribution after perception + risk acceptance."""
        context = ctx or self._spatial_context(team, zone)
        weights = self._base_target_weights(team, zone, actor)
        total = sum(w for _, w in weights)
        base = {ps.player.name: w / total for ps, w in weights}

        info = self._hidden_opportunity(team, actor, zone, context)
        if not info or not info["qualifies"]:
            return base

        tactics = self.teams[team].team.tactics
        confidence = clamp(0.46 + 3.2 * max(0.0, info["margin"]), 0.46, 0.92)
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

    def _choose_target(self, team, zone, attacking=True, exclude=None) -> PlayerState:
        """Choose a receiver, honoring a creative option selected this same beat.

        Creativity must not independently hijack every attacking target choice.
        A hidden receiver is forced only when ``_choose_decision`` has already
        perceived, evaluated and accepted that specific option. The marker is
        transient and consumed immediately by the action execution.
        """
        if not attacking:
            return super()._choose_target(team, zone, attacking=False, exclude=exclude)

        marker = getattr(self, "_v13_forced_target", None)
        if marker is not None:
            if marker.get("team") == team and marker.get("actor") == exclude:
                try:
                    target = self.teams[team].by_name(marker["target"])
                except KeyError:
                    target = None
                self._v13_forced_target = None
                if target is not None and self._contextual_attacking_receiver_eligible(team, zone, target):
                    if target.player.position.upper() == "GK":
                        self._activate_keeper_up(team)
                    return target
            else:
                # Never let a stale idea leak into a later possession/action.
                self._v13_forced_target = None

        try:
            actor = self.teams[team].by_name(exclude) if exclude else None
        except KeyError:
            actor = None
        if actor is None:
            # Do not fall back to the frozen engine here: its historical tiny
            # GK target weight can leak a keeper into an attacking sequence.
            target = weighted_choice(
                self.rng,
                MatchEngineV13Spatial._base_target_weights(self, team, zone, None),
            )
            if target.player.position.upper() == "GK":
                self._activate_keeper_up(team)
            return target
        target = weighted_choice(self.rng, self._base_target_weights(team, zone, actor))
        if target.player.position.upper() == "GK":
            self._activate_keeper_up(team)
        return target

    def _choose_decision(
        self,
        actor: PlayerState,
        zone: Zone,
        tactics: Tactics,
        ctx: dict,
    ) -> str:
        """Choose the action after optionally discovering a superior hidden option.

        The normal menu is evaluated first. Creativity does not make random
        exotic actions more likely. Instead, a qualifying hidden receiver can
        be perceived; risk/reward plus boldness then decide whether to use it.
        If accepted, the associated action and receiver are bound together for
        this beat so the engine cannot choose a through-ball to one player and
        then accidentally target another.
        """
        self._v13_forced_target = None
        team = self._team_index_for_actor(actor)
        if team is not None:
            info = self._hidden_opportunity(team, actor, zone, ctx)
            if info and info["qualifies"]:
                confidence = clamp(0.46 + 3.2 * max(0.0, info["margin"]), 0.46, 0.92)
                perceive = clamp(self._creative_scope(actor, zone, tactics, ctx) * confidence)
                if self.rng.random() < perceive:
                    risk = self._risk_reward_profile(team, actor, zone, ctx, info)
                    if self.rng.random() < risk["acceptance_probability"]:
                        self._v13_forced_target = {
                            "team": team,
                            "actor": actor.player.name,
                            "target": info["target_name"],
                            "action": info["action"],
                        }
                        return info["action"]

        items = self._decision_weights(actor, zone, tactics, ctx)
        composure = actor.effective("composure") / 100.0

        # Ordinary imperfect choices remain possible, independently of the
        # creativity system. High composure reduces but never removes them.
        if self.rng.random() > (0.58 + 0.32 * composure):
            if zone.band in (Band.ATT, Band.BOX):
                items.append(("shoot", 0.08 if zone.band == Band.ATT else 0.11))
            else:
                items.append(("long_ball", 0.08))
        return weighted_choice(self.rng, items)


# Friendly aliases for the eventual stable promotion path.
MatchEngine = MatchEngineV13Spatial
