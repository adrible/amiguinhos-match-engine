from __future__ import annotations

"""v1.3 layer: legal-body contacts, dummies and injury-aware execution.

Every on-ball action may be attempted with any legal outfield contact surface,
but contextual selection keeps normal football dominant: the preferred foot is
by far the default, while head/chest/thigh/knee/shin/shoulder become plausible
mainly when ball height, reception source and pressure justify them.

A dummy (corta-luz) is represented as an intentional no-touch action.
"""

from dataclasses import replace
from typing import Optional

from engine import Band, EventType, Lane, PendingAction, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_body import MatchEngineV13Body

VERSION = "1.3-candidate-legal-body-actions"


class MatchEngineV13LegalBody(MatchEngineV13Body):
    CONTACT_PARTS = (
        "right_foot", "left_foot", "head", "chest", "thigh", "knee", "shin", "shoulder"
    )

    PASS_ACTIONS = {
        "safe_pass", "progressive_pass", "switch", "long_ball",
        "through_ball", "cross", "cutback",
    }
    BALL_ACTIONS = PASS_ACTIONS | {"carry", "dribble", "shoot"}

    def _ensure_contact_state(self) -> None:
        if not hasattr(self, "_v13_injury_locations"):
            self._v13_injury_locations = {}
        if not hasattr(self, "_v13_execution_source"):
            self._v13_execution_source = "open_play"
        if not hasattr(self, "_v13_forced_shot_body_part"):
            self._v13_forced_shot_body_part = None
        if not hasattr(self, "_v13_contact_context"):
            self._v13_contact_context = None

    def export_state(self) -> dict:
        data = super().export_state()
        self._ensure_contact_state()
        data["v13_injury_locations"] = dict(self._v13_injury_locations)
        data["v13_forced_shot_body_part"] = self._v13_forced_shot_body_part
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        obj._v13_injury_locations = dict(data.get("v13_injury_locations") or {})
        obj._v13_execution_source = "open_play"
        obj._v13_contact_context = None
        obj._v13_forced_shot_body_part = data.get("v13_forced_shot_body_part")
        return obj

    def _record_injury_event(
        self,
        team: int,
        player: PlayerState,
        caused_by: Optional[PlayerState] = None,
    ) -> None:
        self._ensure_contact_state()
        region = weighted_choice(
            self.rng,
            [
                ("lower_body", 0.58),
                ("upper_body", 0.14),
                ("torso", 0.16),
                ("head", 0.12),
            ],
        )
        self._v13_injury_locations[player.player.name] = region
        self._emit(
            EventType.INJURY,
            team,
            3,
            "player_injured",
            player=player.player.name,
            caused_by=None if caused_by is None else caused_by.player.name,
            injury_region=region,
        )

    def _injury_part_modifier(self, actor: PlayerState, part: str) -> float:
        self._ensure_contact_state()
        if not actor.injured:
            return 1.0
        region = self._v13_injury_locations.get(actor.player.name)
        if not region:
            return 0.88
        table = {
            "lower_body": {
                "right_foot": 0.55, "left_foot": 0.55, "thigh": 0.48,
                "knee": 0.42, "shin": 0.44, "head": 0.96,
                "chest": 0.94, "shoulder": 0.94,
            },
            "upper_body": {
                "right_foot": 0.96, "left_foot": 0.96, "thigh": 0.94,
                "knee": 0.94, "shin": 0.94, "head": 0.84,
                "chest": 0.62, "shoulder": 0.52,
            },
            "torso": {
                "right_foot": 0.92, "left_foot": 0.92, "thigh": 0.90,
                "knee": 0.90, "shin": 0.90, "head": 0.84,
                "chest": 0.48, "shoulder": 0.70,
            },
            "head": {
                "right_foot": 0.95, "left_foot": 0.95, "thigh": 0.92,
                "knee": 0.92, "shin": 0.92, "head": 0.34,
                "chest": 0.88, "shoulder": 0.82,
            },
        }
        return table.get(region, {}).get(part, 0.88)

    @staticmethod
    def _preferred_and_weak_foot(actor: PlayerState) -> tuple[str, str]:
        preferred = "left_foot" if (actor.player.preferred_foot or "R").upper() == "L" else "right_foot"
        weak = "right_foot" if preferred == "left_foot" else "left_foot"
        return preferred, weak

    @staticmethod
    def _incoming_height(source: str) -> float:
        return {
            "corner": 0.96,
            "cross": 0.88,
            "free_kick": 0.74,
            "long_ball": 0.70,
            "rebound": 0.44,
            "switch": 0.34,
            "progression": 0.24,
            "progressive_pass": 0.22,
            "safe_pass": 0.12,
            "through_ball": 0.08,
            "cutback": 0.04,
            "carry": 0.02,
            "dribble": 0.02,
            "open_play": 0.18,
            "transition": 0.12,
        }.get((source or "open_play").lower(), 0.18)

    def _part_category(self, actor: PlayerState, part: str) -> str:
        preferred, weak = self._preferred_and_weak_foot(actor)
        if part == preferred:
            return "preferred_foot"
        if part == weak:
            return "weak_foot"
        return part

    @staticmethod
    def _action_family(action: str) -> str:
        if action in MatchEngineV13LegalBody.PASS_ACTIONS:
            return "pass"
        if action in {"carry", "dribble"}:
            return "control"
        if action == "shoot":
            return "shoot"
        return "other"

    def _part_execution_modifier(self, actor: PlayerState, action: str, part: str) -> float:
        family = self._action_family(action)
        category = self._part_category(actor, part)
        base = {
            "pass": {
                "preferred_foot": 1.00, "weak_foot": 0.84, "head": 0.76,
                "chest": 0.62, "thigh": 0.64, "knee": 0.54,
                "shin": 0.50, "shoulder": 0.46,
            },
            "control": {
                "preferred_foot": 1.00, "weak_foot": 0.86, "head": 0.48,
                "chest": 0.54, "thigh": 0.58, "knee": 0.47,
                "shin": 0.44, "shoulder": 0.36,
            },
            "shoot": {
                "preferred_foot": 1.00, "weak_foot": 0.82, "head": 0.80,
                "chest": 0.48, "thigh": 0.58, "knee": 0.50,
                "shin": 0.46, "shoulder": 0.42,
            },
        }.get(family, {category: 1.0})
        difficulty = base.get(category, 0.45)
        if category == "head":
            skill = (0.62 * actor.effective("heading") + 0.22 * actor.effective("technique") + 0.16 * actor.effective("composure")) / 75.0
        elif category in {"chest", "thigh", "knee", "shin", "shoulder"}:
            skill = (0.58 * actor.effective("technique") + 0.27 * actor.effective("composure") + 0.15 * actor.effective("strength")) / 75.0
        else:
            relevant = "finishing" if family == "shoot" else ("dribbling" if family == "control" else "passing")
            skill = (0.58 * actor.effective(relevant) + 0.27 * actor.effective("technique") + 0.15 * actor.effective("composure")) / 75.0
        ability_factor = clamp(0.88 + 0.12 * skill, 0.80, 1.08)
        injury = self._injury_part_modifier(actor, part)
        return clamp(difficulty * ability_factor * injury, 0.20, 1.06)

    def body_part_probabilities(
        self,
        actor: PlayerState,
        action: str,
        zone: Zone,
        ctx: Optional[dict] = None,
        *,
        source: str = "open_play",
    ) -> dict[str, float]:
        context = ctx or {"pressure": 0.5, "space": 0.5, "support": 0.5}
        pressure = clamp(float(context.get("pressure", 0.5)))
        space = clamp(float(context.get("space", 0.5)))
        height = self._incoming_height(source)
        preferred, weak = self._preferred_and_weak_foot(actor)
        family = self._action_family(action)

        weights = {
            preferred: 1.00,
            weak: 0.24,
            "head": 0.035,
            "chest": 0.018,
            "thigh": 0.020,
            "knee": 0.008,
            "shin": 0.006,
            "shoulder": 0.004,
        }
        weights[preferred] *= 1.0 - 0.42 * height
        weights[weak] *= 1.0 - 0.28 * height
        weights["head"] *= 1.0 + 12.0 * height
        weights["chest"] *= 1.0 + 8.0 * height
        weights["thigh"] *= 1.0 + 6.5 * height
        weights["knee"] *= 1.0 + 4.0 * height
        weights["shin"] *= 1.0 + 2.8 * height
        weights["shoulder"] *= 1.0 + 4.5 * height

        if family == "shoot":
            weights["head"] *= 1.30
            weights["chest"] *= 0.55
            weights["shoulder"] *= 0.60
        elif family == "control":
            for part in ("head", "chest", "thigh", "knee", "shin", "shoulder"):
                weights[part] *= 0.42
        elif family == "pass":
            weights["head"] *= 1.05

        improvisation = 1.0 + 0.28 * pressure + 0.10 * (1.0 - space)
        for part in ("head", "chest", "thigh", "knee", "shin", "shoulder"):
            weights[part] *= improvisation
        for part in list(weights):
            weights[part] *= max(0.08, self._injury_part_modifier(actor, part))

        total = sum(max(0.0, w) for w in weights.values())
        return {part: max(0.0, w) / total for part, w in weights.items()}

    def _select_action_body_part(
        self,
        actor: PlayerState,
        action: str,
        zone: Zone,
        ctx: dict,
        *,
        source: str,
    ) -> str:
        probs = self.body_part_probabilities(actor, action, zone, ctx, source=source)
        return weighted_choice(self.rng, list(probs.items()))

    @staticmethod
    def _apply_contact_to_context(ctx: dict, modifier: float) -> dict:
        adjusted = dict(ctx)
        penalty = max(0.0, 1.0 - modifier)
        bonus = max(0.0, modifier - 1.0)
        adjusted["pressure"] = clamp(float(adjusted.get("pressure", 0.5)) + 0.20 * penalty - 0.05 * bonus)
        adjusted["space"] = clamp(float(adjusted.get("space", 0.5)) - 0.11 * penalty + 0.03 * bonus)
        adjusted["support"] = clamp(float(adjusted.get("support", 0.5)) - 0.05 * penalty)
        return adjusted

    def _spatial_context(self, attacking_team: int, zone: Zone) -> dict:
        ctx = super()._spatial_context(attacking_team, zone)
        self._ensure_contact_state()
        marker = self._v13_contact_context
        if marker and marker.get("team") == attacking_team and marker.get("zone") == zone:
            return self._apply_contact_to_context(ctx, float(marker.get("modifier", 1.0)))
        return ctx

    def _decision_weights(self, actor, zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        source = getattr(self, "_v13_current_reception_source", "open_play")
        if (
            source != "open_play"
            and zone.band in {Band.MID, Band.ATT, Band.BOX}
            and float(ctx.get("support", 0.5)) >= 0.34
        ):
            vision = actor.effective("vision") / 100.0
            anticipation = actor.effective("anticipation") / 100.0
            composure = actor.effective("composure") / 100.0
            off_ball = actor.effective("off_ball") / 100.0
            pressure = clamp(float(ctx.get("pressure", 0.5)))
            support = clamp(float(ctx.get("support", 0.5)))
            zone_factor = {Band.MID: 0.60, Band.ATT: 1.00, Band.BOX: 0.78}[zone.band]
            dummy = (
                0.010
                + 0.055 * vision
                + 0.045 * anticipation
                + 0.035 * composure
                + 0.035 * off_ball
                + 0.045 * support
                - 0.035 * pressure
            ) * zone_factor
            items.append(("dummy", max(0.002, dummy)))
        return items

    def _resolve_dummy(self, team: int, actor: PlayerState, zone: Zone, ctx: dict):
        target = self._choose_target(team, zone, attacking=True, exclude=actor.player.name)
        defender = self._choose_defender(1 - team, zone)
        atk = (
            0.28 * actor.effective("vision")
            + 0.25 * actor.effective("anticipation")
            + 0.20 * actor.effective("composure")
            + 0.17 * actor.effective("off_ball")
            + 0.10 * target.effective("anticipation")
        )
        deff = 0.54 * defender.effective("anticipation") + 0.46 * defender.effective("positioning")
        success = clamp(
            0.48 + (atk - deff) / 185.0
            + 0.13 * float(ctx.get("support", 0.5))
            + 0.08 * float(ctx.get("space", 0.5))
            - 0.12 * float(ctx.get("pressure", 0.5)),
            0.18, 0.86,
        )
        self._drain(actor, 0.0008)
        if self.rng.random() >= success:
            event = self._turnover(team, actor, zone, "dummy_misread", ctx, severity=0.32)
            event.data["dummy"] = True
            event.data["body_part"] = "no_touch"
            event.data["intended_receiver"] = target.player.name
            return event

        advantage = clamp(
            0.16 + 0.26 * success + 0.15 * float(ctx.get("space_behind", 0.4))
            + 0.08 * float(ctx.get("support", 0.5))
        )
        if zone.band in {Band.ATT, Band.BOX} and self.rng.random() < advantage:
            danger = clamp(0.36 + 0.34 * advantage)
            self.state.pending = PendingAction(
                team=team,
                actor=target.player.name,
                kind=self._natural_next_action(zone, source="dummy"),
                zone=zone,
                danger=danger,
                pressure=clamp(float(ctx.get("pressure", 0.5)) - 0.10),
                defender=defender.player.name,
                origin="dummy",
            )
            return self._emit(
                EventType.DANGER, team, 2 if danger < 0.62 else 3,
                "dummy_creates_danger",
                actor=actor.player.name,
                receiver=target.player.name,
                defender=defender.player.name,
                body_part="no_touch",
                dummy=True,
                danger=round(danger, 3),
            )
        return self._emit(
            EventType.PROGRESSION, team, 1, "dummy_success",
            actor=actor.player.name,
            receiver=target.player.name,
            defender=defender.player.name,
            body_part="no_touch",
            dummy=True,
        )

    def _choose_decision(self, actor, zone, tactics, ctx):
        marker = getattr(self, "_v13_reception_marker", None)
        source = "open_play"
        if marker and marker.get("target") == actor.player.name and marker.get("zone") == zone:
            source = str(marker.get("source") or "open_play")
        decision = super()._choose_decision(actor, zone, tactics, ctx)
        self._v13_execution_source = source
        return decision

    def _execute_decision(self, team, actor, zone, decision, ctx):
        self._ensure_contact_state()
        source = getattr(self, "_v13_execution_source", "open_play") or "open_play"
        if decision == "dummy":
            self._v13_execution_source = "open_play"
            return self._resolve_dummy(team, actor, zone, ctx)

        if decision not in self.BALL_ACTIONS:
            self._v13_execution_source = "open_play"
            return super()._execute_decision(team, actor, zone, decision, ctx)

        part = self._select_action_body_part(actor, decision, zone, ctx, source=source)
        modifier = self._part_execution_modifier(actor, decision, part)
        adjusted = self._apply_contact_to_context(ctx, modifier)
        if decision == "shoot":
            self._v13_forced_shot_body_part = {
                "team": team,
                "actor": actor.player.name,
                "part": part,
                "modifier": modifier,
                "source": source,
            }
        try:
            event = super()._execute_decision(team, actor, zone, decision, adjusted)
        finally:
            self._v13_execution_source = "open_play"

        if decision == "shoot" and self.state.pending is not None and self.state.pending.actor == actor.player.name:
            self.state.pending.body_part = part
        if "body_part" not in event.data:
            event.data["body_part"] = part
        elif event.data.get("body_part") != part and decision != "shoot":
            event.data["delivery_body_part"] = part
        event.data.setdefault("body_difficulty", round(modifier, 3))
        injury_region = self._v13_injury_locations.get(actor.player.name)
        if injury_region:
            event.data.setdefault("injury_region", injury_region)
        return event

    def _resolve_pending(self):
        self._ensure_contact_state()
        p = self.state.pending
        if p is None or p.kind == "shoot":
            return super()._resolve_pending()

        actor = self._named_or_fallback(p.team, p.actor, role="actor", zone=p.zone)
        ctx = super()._spatial_context(p.team, p.zone)
        part = self._select_action_body_part(actor, p.kind, p.zone, ctx, source=p.origin)
        modifier = self._part_execution_modifier(actor, p.kind, part)
        old = self._v13_contact_context
        self._v13_contact_context = {
            "team": p.team,
            "zone": p.zone,
            "modifier": modifier,
        }
        try:
            event = super()._resolve_pending()
        finally:
            self._v13_contact_context = old

        if "body_part" in event.data:
            key = "dribble_body_part" if p.kind == "dribble" else "delivery_body_part"
            event.data.setdefault(key, part)
        else:
            event.data["body_part"] = part
        event.data.setdefault("body_difficulty", round(modifier, 3))
        return event

    def _resolve_shot(self, p: PendingAction):
        self._ensure_contact_state()
        shooter = self._named_or_fallback(p.team, p.actor, role="actor", zone=p.zone)
        ctx = {
            "pressure": clamp(p.pressure),
            "space": clamp(0.30 + 0.58 * p.danger),
            "space_behind": 0.55 if p.origin in {"through_ball", "transition"} else 0.35,
            "support": 0.50,
        }

        forced = self._v13_forced_shot_body_part
        if forced and forced.get("team") == p.team and forced.get("actor") == p.actor:
            part = forced["part"]
            modifier = float(forced.get("modifier", 1.0))
        elif p.body_part not in {None, "", "foot", "head", "auto"}:
            part = p.body_part
            modifier = self._part_execution_modifier(shooter, "shoot", part)
        else:
            source = p.origin or ("cross" if p.body_part == "head" else "open_play")
            part = self._select_action_body_part(shooter, "shoot", p.zone, ctx, source=source)
            modifier = self._part_execution_modifier(shooter, "shoot", part)

        self._v13_forced_shot_body_part = None
        penalty = max(0.0, 1.0 - modifier)
        tuned = replace(
            p,
            body_part=part,
            danger=clamp(p.danger - 0.105 * penalty),
            pressure=clamp(p.pressure + 0.085 * penalty),
        )
        event = super()._resolve_shot(tuned)
        event.data["body_part"] = part
        event.data["body_difficulty"] = round(modifier, 3)
        injury_region = self._v13_injury_locations.get(shooter.player.name)
        if injury_region:
            event.data["injury_region"] = injury_region
        return event


MatchEngine = MatchEngineV13LegalBody

__all__ = ["MatchEngineV13LegalBody", "MatchEngine", "VERSION"]
