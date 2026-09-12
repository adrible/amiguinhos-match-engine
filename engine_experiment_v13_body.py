from __future__ import annotations

"""Experimental v1.3 layer: body orientation + preferred-foot reception.

Extends the v1.3 spatial/creativity/boldness/off-ball candidate without touching
frozen v1.2.

Core principle:
    where the player is + how the ball arrives + body orientation + preferred foot
    -> which actions are natural *now*
    -> modest execution consequences

This layer does not grant hidden bonuses to outcomes. It changes the footballing
situation: receiving on the half-turn, facing goal, or with the body closed alters
which actions make sense and how hard the next action is to execute.
"""

from dataclasses import replace
from typing import Optional

from engine import Band, Lane, PendingAction, PlayerState, Tactics, Zone, clamp
from engine_experiment_v13_offball import MatchEngineV13OffBall


VERSION = "1.3-candidate-spatial-creativity-boldness-offball-body"


class MatchEngineV13Body(MatchEngineV13OffBall):
    """Adds reception/body orientation and preferred-foot consequences.

    The model is deliberately contextual and generic. No player-name rules are
    used. The same player can receive facing goal in one play and back-to-goal in
    another depending on role, zone, pressure, space and pass origin.
    """

    # ---------------------------- body model ----------------------------

    @staticmethod
    def _source_orientation_bonus(source: Optional[str]) -> tuple[float, float, float]:
        """Return (forward_bonus, open_body_bonus, turn_cost_delta)."""
        source = (source or "open_play").lower()
        return {
            "through_ball": (0.22, 0.14, -0.18),
            "cutback": (0.18, 0.10, -0.10),
            "progression": (0.08, 0.07, -0.06),
            "carry": (0.12, 0.08, -0.08),
            "transition": (0.15, 0.10, -0.10),
            "cross": (0.06, -0.02, 0.04),
            "rebound": (-0.04, -0.11, 0.12),
            "corner": (-0.02, -0.08, 0.10),
            "free_kick": (0.02, 0.00, 0.02),
        }.get(source, (0.0, 0.0, 0.0))

    @staticmethod
    def _wide_foot_profile(actor: PlayerState, lane: Lane) -> dict:
        """Describe how preferred foot relates to the current wide lane.

        On the left, a right-footed player is inverted (inside foot toward goal),
        while a left-footer is natural for line/crossing. Vice versa on the right.
        Central reception is neutral.
        """
        foot = (actor.player.preferred_foot or "R").upper()
        if lane == Lane.CENTER:
            return {
                "foot": foot,
                "inverted": False,
                "natural_wide": False,
                "inside_foot": True,
                "shoot": 1.00,
                "cross": 1.00,
                "cutback": 1.00,
                "progressive_pass": 1.00,
                "through_ball": 1.00,
                "carry": 1.00,
                "dribble": 1.00,
                "switch": 1.00,
                "long_ball": 1.00,
                "safe_pass": 1.00,
            }

        natural = (lane == Lane.LEFT and foot == "L") or (lane == Lane.RIGHT and foot == "R")
        inverted = not natural
        return {
            "foot": foot,
            "inverted": inverted,
            "natural_wide": natural,
            "inside_foot": inverted,
            # Small stylistic/execution effects only. The spatial layer already
            # has a mild inverted-wing shooting preference; these values model
            # reception mechanics rather than duplicating a large tactical bonus.
            "shoot": 1.055 if inverted else 0.985,
            "cross": 0.935 if inverted else 1.070,
            "cutback": 1.020 if inverted else 1.035,
            "progressive_pass": 1.020 if inverted else 1.010,
            "through_ball": 1.025 if inverted else 0.995,
            "carry": 1.025 if inverted else 1.020,
            "dribble": 1.040 if inverted else 1.025,
            "switch": 1.000,
            "long_ball": 0.985 if inverted else 1.020,
            "safe_pass": 1.000,
        }

    def _reception_source_for(self, actor: PlayerState, zone: Zone) -> str:
        marker = getattr(self, "_v13_reception_marker", None)
        if not marker:
            return "open_play"
        if marker.get("target") != actor.player.name or marker.get("zone") != zone:
            # The base engine abstracts possession between beats; if the next
            # actor is not the recorded receiver, the marker is no longer valid.
            self._v13_reception_marker = None
            return "open_play"
        self._v13_reception_marker = None
        return str(marker.get("source") or "open_play")

    def body_orientation_diagnostic(
        self,
        actor: PlayerState,
        zone: Zone,
        ctx: Optional[dict] = None,
        *,
        source: Optional[str] = None,
    ) -> dict:
        """Deterministic reception/body profile for diagnostics and decisions."""
        context = dict(ctx or {
            "pressure": 0.50,
            "space": 0.50,
            "space_behind": 0.40,
            "support": 0.50,
        })
        pressure = clamp(float(context.get("pressure", 0.5)))
        space = clamp(float(context.get("space", 0.5)))
        support = clamp(float(context.get("support", 0.5)))

        pos = actor.player.position.upper()
        technique = actor.effective("technique") / 100.0
        anticipation = actor.effective("anticipation") / 100.0
        composure = actor.effective("composure") / 100.0
        off_ball = actor.effective("off_ball") / 100.0
        dribbling = actor.effective("dribbling") / 100.0

        # Role-dependent default: strikers receiving centrally are more likely
        # to have a defender at their back; midfielders tend to receive on a
        # half-turn; wide players have more touchline-defined body shapes.
        forward_base = {
            Band.DEF: {
                "GK": 0.48, "CB": 0.58, "LB": 0.66, "RB": 0.66,
                "DM": 0.64, "CM": 0.66, "AM": 0.60, "LW": 0.62,
                "RW": 0.62, "ST": 0.50,
            },
            Band.MID: {
                "CB": 0.62, "LB": 0.70, "RB": 0.70, "DM": 0.66,
                "CM": 0.70, "AM": 0.73, "LW": 0.76, "RW": 0.76,
                "ST": 0.46,
            },
            Band.ATT: {
                "CB": 0.58, "LB": 0.73, "RB": 0.73, "DM": 0.66,
                "CM": 0.74, "AM": 0.80, "LW": 0.82, "RW": 0.82,
                "ST": 0.50,
            },
            Band.BOX: {
                "CB": 0.62, "LB": 0.70, "RB": 0.70, "DM": 0.68,
                "CM": 0.76, "AM": 0.83, "LW": 0.84, "RW": 0.84,
                "ST": 0.64,
            },
        }[zone.band].get(pos, 0.68)

        src_forward, src_open, src_turn = self._source_orientation_bonus(source)
        forward_view = clamp(
            forward_base
            + 0.12 * space
            - 0.18 * pressure
            + 0.07 * anticipation
            + 0.04 * off_ball
            + src_forward
        )

        wide_bonus = 0.08 if zone.lane != Lane.CENTER and pos in {"LW", "RW", "LB", "RB"} else 0.0
        open_body = clamp(
            0.26
            + 0.23 * technique
            + 0.17 * anticipation
            + 0.15 * composure
            + 0.10 * dribbling
            + 0.12 * space
            - 0.20 * pressure
            + wide_bonus
            + src_open
        )

        striker_back = 0.22 if pos == "ST" and zone.lane == Lane.CENTER and zone.band in {Band.ATT, Band.BOX} else 0.0
        turn_cost = clamp(
            0.62
            - 0.31 * open_body
            - 0.20 * forward_view
            + 0.24 * pressure
            - 0.08 * space
            + striker_back
            + src_turn
        )

        first_touch = clamp(
            0.35 * technique + 0.24 * composure + 0.18 * anticipation
            + 0.11 * dribbling + 0.12 * space - 0.16 * pressure
            + 0.08 * open_body
        )

        if forward_view >= 0.72 and open_body >= 0.63:
            stance = "facing_goal"
        elif turn_cost >= 0.58 and forward_view < 0.58:
            stance = "back_to_goal"
        elif zone.lane != Lane.CENTER and open_body >= 0.60:
            stance = "wide_open"
        else:
            stance = "half_turn"

        foot = self._wide_foot_profile(actor, zone.lane)
        return {
            "stance": stance,
            "source": source or "open_play",
            "forward_view": forward_view,
            "open_body": open_body,
            "turn_cost": turn_cost,
            "first_touch": first_touch,
            "preferred_foot": foot["foot"],
            "inverted": foot["inverted"],
            "natural_wide": foot["natural_wide"],
            "foot_modifiers": {k: v for k, v in foot.items() if isinstance(v, float)},
        }

    def _orientation_action_modifier(self, profile: dict, action: str) -> float:
        forward = float(profile["forward_view"])
        open_body = float(profile["open_body"])
        turn_cost = float(profile["turn_cost"])
        first_touch = float(profile["first_touch"])
        foot = float(profile["foot_modifiers"].get(action, 1.0))

        # A back-to-goal reception does not make the player worse globally; it
        # makes forward actions less natural *at that instant*. Safe recycling
        # can actually become more attractive.
        if action == "safe_pass":
            body = 1.00 + 0.20 * turn_cost + 0.06 * (1.0 - forward)
        elif action in {"progressive_pass", "switch", "long_ball"}:
            body = 0.82 + 0.12 * forward + 0.14 * open_body + 0.07 * first_touch - 0.10 * turn_cost
        elif action == "through_ball":
            body = 0.78 + 0.18 * forward + 0.13 * open_body + 0.07 * first_touch - 0.12 * turn_cost
        elif action in {"carry", "dribble"}:
            body = 0.80 + 0.11 * forward + 0.15 * open_body + 0.12 * first_touch - 0.12 * turn_cost
        elif action == "shoot":
            body = 0.68 + 0.23 * forward + 0.16 * open_body + 0.08 * first_touch - 0.18 * turn_cost
        elif action == "cross":
            body = 0.82 + 0.09 * forward + 0.13 * open_body + 0.08 * first_touch - 0.08 * turn_cost
        elif action == "cutback":
            body = 0.84 + 0.12 * forward + 0.12 * open_body + 0.08 * first_touch - 0.08 * turn_cost
        else:
            body = 1.0
        return clamp(body * foot, 0.68, 1.24)

    # ------------------------- decision integration -------------------------

    def _decision_weights(
        self,
        actor: PlayerState,
        zone: Zone,
        tactics: Tactics,
        ctx: dict,
    ) -> list[tuple[str, float]]:
        base = super()._decision_weights(actor, zone, tactics, ctx)
        source = getattr(self, "_v13_current_reception_source", "open_play")
        profile = self.body_orientation_diagnostic(actor, zone, ctx, source=source)
        return [
            (action, max(0.0, weight * self._orientation_action_modifier(profile, action)))
            for action, weight in base
        ]

    def _choose_decision(self, actor, zone, tactics, ctx) -> str:
        source = self._reception_source_for(actor, zone)
        self._v13_current_reception_source = source
        try:
            return super()._choose_decision(actor, zone, tactics, ctx)
        finally:
            self._v13_current_reception_source = "open_play"

    def decision_probabilities(
        self,
        actor: PlayerState,
        zone: Zone,
        tactics: Tactics,
        ctx: dict,
        *,
        source: str = "open_play",
    ) -> dict[str, float]:
        old = getattr(self, "_v13_current_reception_source", "open_play")
        self._v13_current_reception_source = source
        try:
            return super().decision_probabilities(actor, zone, tactics, ctx)
        finally:
            self._v13_current_reception_source = old

    # ------------------------- execution integration -------------------------

    def _execute_decision(self, team, actor, zone, decision, ctx):
        source = getattr(self, "_v13_execution_source", None) or "open_play"
        profile = self.body_orientation_diagnostic(actor, zone, ctx, source=source)
        modifier = self._orientation_action_modifier(profile, decision)

        # Translate body mechanics into the existing context variables instead
        # of changing player attributes. This preserves the principle that
        # technique/passing/etc. remain the execution skills themselves.
        adjusted = dict(ctx)
        delta = clamp((modifier - 1.0) / 0.24, -1.0, 1.0)
        adjusted["pressure"] = clamp(float(adjusted.get("pressure", 0.5)) - 0.045 * delta)
        adjusted["space"] = clamp(float(adjusted.get("space", 0.5)) + 0.035 * delta)

        event = super()._execute_decision(team, actor, zone, decision, adjusted)

        # Preserve the immediate reception source for a successful receiver.
        target = event.data.get("target") or event.data.get("receiver")
        if target and event.text_key in {
            "safe_pass", "progression", "progression_creates_danger", "danger_created"
        }:
            source_name = event.data.get("kind") or decision
            self._v13_reception_marker = {
                "target": target,
                "zone": self.state.zone,
                "source": source_name,
            }
        return event

    def _resolve_shot(self, p: PendingAction):
        """Apply reception mechanics to foot shots, then use normal resolution.

        Headers are left to heading/pressure mechanics. For foot shots, a player
        arriving onto a through ball/cutback can be better oriented, while a
        rebound or back-to-goal reception can be less clean. The adjustment is
        deliberately modest and changes the *situation*, not the player's stats.
        """
        if p.body_part == "head":
            return super()._resolve_shot(p)

        shooter = self._named_or_fallback(p.team, p.actor, role="actor", zone=p.zone)
        context = {
            "pressure": clamp(p.pressure),
            "space": clamp(0.30 + 0.58 * p.danger),
            "space_behind": 0.55 if p.origin in {"through_ball", "transition"} else 0.35,
            "support": 0.50,
        }
        profile = self.body_orientation_diagnostic(shooter, p.zone, context, source=p.origin)
        modifier = self._orientation_action_modifier(profile, "shoot")
        delta = clamp((modifier - 1.0) / 0.24, -1.0, 1.0)

        tuned = replace(
            p,
            danger=clamp(p.danger + 0.038 * delta),
            pressure=clamp(p.pressure - 0.032 * delta),
        )
        return super()._resolve_shot(tuned)


MatchEngine = MatchEngineV13Body
