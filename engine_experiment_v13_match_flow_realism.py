from __future__ import annotations

"""Causal event-frequency realism for the v1.3 candidate.

The real-match benchmark showed that score and shot distributions were already
close to real football while corners and ordinary fouls were under-produced.
This layer adds missing causal exits from existing actions; it never reads a
benchmark target, desired result, team identity or goal quota.
"""

from engine import Band, Event, EventType, Lane, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_penalties import MatchEngineV13Penalties

VERSION = "1.3-candidate-match-flow-realism"


class MatchEngineV13MatchFlowRealism(MatchEngineV13Penalties):
    _CORNER_TURNOVER_BASE = {
        "cross_stopped": 0.34,
        "cross_cleared": 0.28,
        "cutback_stopped": 0.30,
        "cutback_cleared": 0.25,
        "dribble_stopped": 0.10,
        "dispossessed": 0.07,
        "progressive_pass_failed": 0.055,
    }
    _CONTACT_ACTION_BASE = {
        "safe_pass": 0.012,
        "progressive_pass": 0.026,
        "switch": 0.014,
        "long_ball": 0.016,
        "carry": 0.050,
        "through_ball": 0.032,
        "cross": 0.030,
        "cutback": 0.040,
        "shoot": 0.018,
        "dribble": 0.064,
    }

    # ----------------------------- corners -----------------------------

    def corner_turnover_probability(self, zone: Zone, reason: str, ctx: dict) -> float:
        base = float(self._CORNER_TURNOVER_BASE.get(str(reason), 0.0))
        if base <= 0.0 or zone.band not in {Band.ATT, Band.BOX}:
            return 0.0
        wide = zone.lane != Lane.CENTER
        if str(reason) in {"dribble_stopped", "dispossessed", "progressive_pass_failed"} and not wide:
            return 0.0
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        space = clamp(float(ctx.get("space", 0.5)))
        probability = (
            base
            + 0.11 * pressure
            + (0.055 if wide else 0.0)
            + (0.055 if zone.band == Band.BOX else 0.0)
            - 0.035 * space
        )
        return clamp(probability, 0.0, 0.56)

    def _turnover(self, losing_team, actor, zone, reason, ctx, severity=0.5):
        corner_p = self.corner_turnover_probability(zone, str(reason), ctx)
        if corner_p > 0.0 and self.rng.random() < corner_p:
            self.state.pending = None
            self.state.transition_boost = 0.0
            event = self._award_corner(int(losing_team), actor.player.name)
            event.data.update(
                corner_cause="deflection_or_clearance",
                failed_action=str(reason),
                corner_probability=round(corner_p, 4),
            )
            return event
        return super()._turnover(losing_team, actor, zone, reason, ctx, severity=severity)

    def shot_corner_probability(self, p, event: Event) -> float:
        if event.type not in {EventType.SAVE, EventType.BLOCK}:
            return 0.0
        if event.data.get("shootout") or self.state.restart is not None:
            return 0.0
        xg = clamp(float(event.data.get("xg", 0.0)))
        danger = clamp(float(getattr(p, "danger", event.data.get("danger", 0.4))))
        pressure = clamp(float(getattr(p, "pressure", event.data.get("pressure", 0.4))))
        if event.type == EventType.BLOCK:
            return clamp(0.13 + 0.13 * pressure + 0.07 * danger + 0.05 * xg, 0.10, 0.34)
        keeper = self._goalkeeper(1 - int(p.team))
        handling = clamp(keeper.effective("handling") / 100.0)
        return clamp(0.045 + 0.12 * xg + 0.07 * pressure + 0.09 * (1.0 - handling), 0.035, 0.22)

    def _arm_corner_after_shot(self, team: int, p, event: Event, probability: float) -> Event:
        self.stats[team].corners += 1
        self.state.pending = None
        self.state.restart = "corner"
        self.state.restart_team = int(team)
        lane = p.zone.lane if p.zone.lane != Lane.CENTER else self.rng.choice([Lane.LEFT, Lane.RIGHT])
        self.state.restart_zone = Zone(Band.ATT, lane)
        self.state.phase = "restart"
        self.state.transition_boost = 0.0
        event.data.update(
            corner_awarded=True,
            corner_probability=round(float(probability), 4),
            corner_cause="save_parry" if event.type == EventType.SAVE else "blocked_deflection",
        )
        return event

    def _resolve_shot(self, p):
        event = super()._resolve_shot(p)
        corner_p = self.shot_corner_probability(p, event)
        if corner_p > 0.0 and self.rng.random() < corner_p:
            return self._arm_corner_after_shot(int(p.team), p, event, corner_p)
        return event

    # ----------------------------- ordinary contact fouls -----------------------------

    def contact_foul_probability(
        self,
        team: int,
        actor: PlayerState,
        defender: PlayerState,
        zone: Zone,
        decision: str,
        ctx: dict,
    ) -> float:
        base = float(self._CONTACT_ACTION_BASE.get(str(decision), 0.0))
        if base <= 0.0:
            return 0.0
        in_box = zone.band == Band.BOX
        if in_box and str(decision) not in {"carry", "dribble", "cutback"}:
            return 0.0

        pressure = clamp(float(ctx.get("pressure", 0.5)))
        aggression = clamp(defender.effective("aggression") / 100.0)
        discipline = clamp(defender.effective("discipline") / 100.0)
        composure = clamp(defender.effective("composure") / 100.0)
        dribble = clamp(actor.effective("dribbling") / 100.0)
        transition = clamp(float(self.state.transition_boost))
        strictness = clamp(float(getattr(self.referee, "strictness", 0.55)))
        tolerance = clamp(float(getattr(self.referee, "contact_tolerance", 0.50)))
        whistle_factor = clamp(0.92 + 0.28 * strictness - 0.22 * tolerance, 0.78, 1.16)

        probability = (
            base
            + 0.030 * pressure
            + 0.020 * aggression
            + 0.016 * (1.0 - discipline)
            + 0.012 * dribble
            + 0.014 * transition
        ) * whistle_factor

        # A booked player should manage borderline physical interventions more
        # carefully.  This acts on whether the contact is attempted, not on the
        # referee's later card decision, and therefore reduces repeat-foul risk
        # without making a second yellow impossible when a foul still occurs.
        if defender.yellow:
            management = clamp(
                0.70 - 0.18 * discipline - 0.08 * composure + 0.08 * aggression,
                0.46,
                0.62,
            )
            probability *= management

        # The whole extension, not only its base term, is suppressed in the box.
        # Existing dribble/handball/referee systems remain the main penalty route.
        if in_box:
            probability *= 0.18
            return clamp(probability, 0.001, 0.032)
        return clamp(probability, 0.002, 0.115)

    def _ordinary_contact_incident(
        self,
        defender: PlayerState,
        actor: PlayerState,
        zone: Zone,
        decision: str,
        ctx: dict,
    ) -> dict:
        decision = str(decision)
        if decision in {"carry", "dribble"}:
            foul_type = weighted_choice(self.rng, [("trip", 0.46), ("holding", 0.30), ("late_tackle", 0.24)])
        elif decision in {"through_ball", "progressive_pass", "cutback", "cross"}:
            foul_type = weighted_choice(self.rng, [("holding", 0.42), ("trip", 0.34), ("push_charge", 0.24)])
        else:
            foul_type = weighted_choice(self.rng, [("trip", 0.45), ("push_charge", 0.32), ("holding", 0.23)])

        aggression = clamp(defender.effective("aggression") / 100.0)
        discipline = clamp(defender.effective("discipline") / 100.0)
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        action_bonus = 0.045 if decision in {"dribble", "carry"} else 0.025 if decision in {"through_ball", "cutback"} else 0.0
        severity = clamp(
            0.20 + 0.12 * aggression - 0.07 * discipline + 0.06 * pressure + action_bonus + self.rng.uniform(-0.045, 0.055),
            0.16,
            0.54,
        )
        transition = clamp(float(self.state.transition_boost))
        spa = bool(
            zone.band in {Band.MID, Band.ATT}
            and transition >= 0.58
            and decision in {"carry", "dribble", "through_ball", "progressive_pass"}
        )
        return {
            "type": str(foul_type),
            "severity": severity,
            "attempt_to_play_ball": foul_type in {"trip", "late_tackle"},
            "spa": spa,
            "dogso": False,
            "violent": False,
            "ordinary_contact": True,
        }

    def _execute_decision(self, team, actor, zone, decision, ctx):
        defender = self._choose_defender(1 - int(team), zone)
        foul_p = self.contact_foul_probability(int(team), actor, defender, zone, str(decision), ctx)
        if foul_p > 0.0 and self.rng.random() < foul_p:
            incident = self._ordinary_contact_incident(defender, actor, zone, str(decision), ctx)
            event = self._commit_foul(1 - int(team), defender, actor, zone, forced_incident=incident)
            event.data.update(
                ordinary_contact=True,
                contact_action=str(decision),
                contact_foul_probability=round(foul_p, 4),
            )
            return event
        return super()._execute_decision(team, actor, zone, decision, ctx)


MatchEngine = MatchEngineV13MatchFlowRealism

__all__ = ["MatchEngineV13MatchFlowRealism", "MatchEngine", "VERSION"]
