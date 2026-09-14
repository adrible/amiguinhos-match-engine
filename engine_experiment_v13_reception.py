from __future__ import annotations

"""v1.3 layer: contextual first touch, oriented reception and first-time play.

This layer sits above legal-body contacts and below defensive intelligence.
It does not add player attributes: technique, composure, anticipation, vision,
dribbling, body orientation, pressure, trajectory and legal contact surfaces
explain reception quality and whether a player can act first-time.
"""

from dataclasses import replace
from typing import Optional

from engine import Band, EventType, Lane, PendingAction, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_legal_body import MatchEngineV13LegalBody


VERSION = "1.3-candidate-contextual-reception"

FIRST_TIME_ACTIONS = {
    "safe_pass", "progressive_pass", "switch", "long_ball",
    "through_ball", "cross", "cutback", "shoot",
}


class MatchEngineV13Reception(MatchEngineV13LegalBody):
    """Adds reception mechanics without inventing a first-touch attribute."""

    def _ensure_reception_state(self) -> None:
        if not hasattr(self, "_v13_reception_plan"):
            self._v13_reception_plan = None
        if not hasattr(self, "_v13_pending_first_time"):
            self._v13_pending_first_time = None

    @staticmethod
    def _marker_to_json(marker):
        if not marker:
            return None
        zone = marker.get("zone")
        return {
            "target": marker.get("target"),
            "source": marker.get("source") or "open_play",
            "zone": None if zone is None else {
                "band": zone.band.value,
                "lane": zone.lane.value,
            },
        }

    @staticmethod
    def _marker_from_json(marker):
        if not marker:
            return None
        raw_zone = marker.get("zone")
        zone = None
        if raw_zone:
            zone = Zone(Band(raw_zone["band"]), Lane(raw_zone["lane"]))
        return {
            "target": marker.get("target"),
            "source": marker.get("source") or "open_play",
            "zone": zone,
        }

    def export_state(self) -> dict:
        data = super().export_state()
        self._ensure_reception_state()
        data["v13_reception_marker"] = self._marker_to_json(
            getattr(self, "_v13_reception_marker", None)
        )
        data["v13_pending_first_time"] = (
            None if self._v13_pending_first_time is None
            else dict(self._v13_pending_first_time)
        )
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        obj._v13_reception_plan = None
        obj._v13_reception_marker = cls._marker_from_json(
            data.get("v13_reception_marker")
        )
        obj._v13_pending_first_time = (
            None if not data.get("v13_pending_first_time")
            else dict(data["v13_pending_first_time"])
        )
        return obj

    @staticmethod
    def _source_trajectory(source: str) -> tuple[float, float]:
        """Return (speed/difficulty, height) on a 0..1 scale."""
        source = (source or "open_play").lower()
        difficulty = {
            "safe_pass": 0.12,
            "progression": 0.28,
            "progressive_pass": 0.32,
            "switch": 0.44,
            "through_ball": 0.48,
            "cutback": 0.38,
            "cross": 0.70,
            "long_ball": 0.67,
            "corner": 0.76,
            "free_kick": 0.61,
            "rebound": 0.82,
            "transition": 0.43,
            "carry": 0.06,
            "dribble": 0.08,
            "dummy": 0.20,
            "open_play": 0.22,
        }.get(source, 0.28)
        return difficulty, MatchEngineV13LegalBody._incoming_height(source)

    def reception_diagnostic(
        self,
        actor: PlayerState,
        zone: Zone,
        ctx: Optional[dict] = None,
        *,
        source: str = "open_play",
    ) -> dict:
        context = dict(ctx or {
            "pressure": 0.50,
            "space": 0.50,
            "space_behind": 0.40,
            "support": 0.50,
        })
        pressure = clamp(float(context.get("pressure", 0.5)))
        space = clamp(float(context.get("space", 0.5)))
        space_behind = clamp(float(context.get("space_behind", 0.4)))
        difficulty, height = self._source_trajectory(source)
        body = self.body_orientation_diagnostic(actor, zone, context, source=source)

        technique = clamp(actor.effective("technique") / 100.0)
        composure = clamp(actor.effective("composure") / 100.0)
        anticipation = clamp(actor.effective("anticipation") / 100.0)
        dribbling = clamp(actor.effective("dribbling") / 100.0)
        vision = clamp(actor.effective("vision") / 100.0)

        part_probs = self.body_part_probabilities(
            actor, "carry", zone, context, source=source
        )
        likely_part = max(part_probs, key=part_probs.get)
        contact_mod = self._part_execution_modifier(
            actor, "carry", likely_part
        )

        control = clamp(
            0.29 * technique
            + 0.18 * composure
            + 0.16 * anticipation
            + 0.13 * dribbling
            + 0.08 * vision
            + 0.10 * space
            + 0.09 * float(body["open_body"])
            + 0.07 * contact_mod
            - 0.17 * pressure
            - 0.14 * difficulty
            - 0.06 * height
        )

        scan = clamp(
            0.40 * vision
            + 0.27 * anticipation
            + 0.16 * composure
            + 0.10 * float(body["open_body"])
            + 0.07 * space
            - 0.12 * pressure
        )

        return {
            "source": source,
            "trajectory_difficulty": difficulty,
            "height": height,
            "control_score": control,
            "scan_score": scan,
            "likely_body_part": likely_part,
            "likely_contact_modifier": contact_mod,
            "stance": body["stance"],
            "open_body": float(body["open_body"]),
            "forward_view": float(body["forward_view"]),
            "turn_cost": float(body["turn_cost"]),
            "space": space,
            "space_behind": space_behind,
            "pressure": pressure,
        }

    @staticmethod
    def _touch_outcome_weights(diag: dict) -> list[tuple[str, float]]:
        score = clamp(float(diag["control_score"]))
        pressure = clamp(float(diag["pressure"]))
        difficulty = clamp(float(diag["trajectory_difficulty"]))
        perfect = 0.05 + 0.58 * score * score + 0.08 * (1.0 - pressure)
        clean = 0.40 + 0.38 * score + 0.08 * (1.0 - difficulty)
        loose = 0.12 + 0.28 * (1.0 - score) + 0.10 * pressure
        heavy = 0.05 + 0.24 * (1.0 - score) + 0.13 * difficulty
        miscontrol = 0.008 + 0.12 * ((1.0 - score) ** 2) + 0.055 * pressure * difficulty
        return [
            ("perfect", perfect),
            ("clean", clean),
            ("loose", loose),
            ("heavy", heavy),
            ("miscontrol", miscontrol),
        ]

    def _oriented_touch_weights(
        self,
        actor: PlayerState,
        zone: Zone,
        diag: dict,
    ) -> list[tuple[str, float]]:
        pressure = float(diag["pressure"])
        space = float(diag["space"])
        behind = float(diag["space_behind"])
        open_body = float(diag["open_body"])
        scan = float(diag["scan_score"])
        inverted = bool(
            self._wide_foot_profile(actor, zone.lane).get("inverted", False)
        )
        weights = [
            ("secure", 0.20 + 0.38 * pressure + 0.15 * (1.0 - scan)),
            ("half_turn", 0.20 + 0.34 * open_body + 0.22 * scan),
            ("forward_space", 0.10 + 0.30 * behind + 0.20 * space + 0.12 * scan),
        ]
        if zone.lane != Lane.CENTER:
            weights.extend([
                ("inside", 0.12 + (0.30 if inverted else 0.10) + 0.16 * scan),
                ("line", 0.12 + (0.28 if not inverted else 0.08) + 0.12 * space),
            ])
        if zone.band in {Band.ATT, Band.BOX}:
            finishing = clamp(actor.effective("finishing") / 100.0)
            weights.append(
                ("set_action", 0.06 + 0.20 * finishing + 0.15 * open_body)
            )
        return weights

    def _first_time_probability(
        self,
        actor: PlayerState,
        action: str,
        diag: dict,
    ) -> float:
        if (diag.get("source") or "open_play") == "open_play":
            return 0.0
        if action not in FIRST_TIME_ACTIONS:
            return 0.0

        base = {
            "safe_pass": 0.13,
            "progressive_pass": 0.10,
            "switch": 0.06,
            "long_ball": 0.04,
            "through_ball": 0.11,
            "cross": 0.12,
            "cutback": 0.14,
            "shoot": 0.15,
        }.get(action, 0.08)

        technique = clamp(actor.effective("technique") / 100.0)
        vision = clamp(actor.effective("vision") / 100.0)
        anticipation = clamp(actor.effective("anticipation") / 100.0)
        composure = clamp(actor.effective("composure") / 100.0)
        pressure = float(diag["pressure"])
        difficulty = float(diag["trajectory_difficulty"])
        open_body = float(diag["open_body"])
        scan = float(diag["scan_score"])

        return clamp(
            base
            + 0.20 * technique
            + 0.10 * vision
            + 0.10 * anticipation
            + 0.08 * composure
            + 0.08 * open_body
            + 0.06 * scan
            - 0.18 * pressure
            - 0.14 * difficulty,
            0.015,
            0.66,
        )

    @staticmethod
    def _intent_action_modifier(intent: str, action: str) -> float:
        table = {
            "secure": {
                "safe_pass": 1.18, "progressive_pass": 0.94,
                "through_ball": 0.90, "carry": 0.92, "dribble": 0.84,
                "shoot": 0.84,
            },
            "half_turn": {
                "progressive_pass": 1.10, "through_ball": 1.10,
                "carry": 1.08, "dribble": 1.05, "shoot": 1.04,
            },
            "forward_space": {
                "carry": 1.15, "dribble": 1.12, "through_ball": 1.08,
                "shoot": 1.06, "safe_pass": 0.94,
            },
            "inside": {
                "shoot": 1.10, "through_ball": 1.08,
                "dribble": 1.08, "cross": 0.91,
            },
            "line": {
                "cross": 1.14, "cutback": 1.11,
                "carry": 1.06, "shoot": 0.92,
            },
            "set_action": {
                "shoot": 1.14, "through_ball": 1.07,
                "progressive_pass": 1.05,
            },
        }
        return table.get(intent, {}).get(action, 1.0)

    def _decision_weights(self, actor, zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        self._ensure_reception_state()
        plan = self._v13_reception_plan
        if not plan or plan.get("actor") != actor.player.name or plan.get("zone") != zone:
            return items

        diag = plan["diagnostic"]
        intent = plan["intent"]
        out = []
        for action, weight in items:
            mod = self._intent_action_modifier(intent, action)
            ft = self._first_time_probability(actor, action, diag)
            mod *= 1.0 + 0.10 * ft
            out.append((action, max(0.0, weight * mod)))
        return out

    def _peek_reception_source(self, actor: PlayerState, zone: Zone) -> str:
        marker = getattr(self, "_v13_reception_marker", None)
        if not marker:
            return "open_play"
        if marker.get("target") != actor.player.name or marker.get("zone") != zone:
            return "open_play"
        return str(marker.get("source") or "open_play")

    def _choose_decision(self, actor, zone, tactics, ctx):
        self._ensure_reception_state()
        source = self._peek_reception_source(actor, zone)
        if source == "open_play":
            self._v13_reception_plan = None
            return super()._choose_decision(actor, zone, tactics, ctx)

        diag = self.reception_diagnostic(actor, zone, ctx, source=source)
        intent = weighted_choice(
            self.rng, self._oriented_touch_weights(actor, zone, diag)
        )
        self._v13_reception_plan = {
            "actor": actor.player.name,
            "zone": zone,
            "source": source,
            "diagnostic": diag,
            "intent": intent,
            "mode": None,
            "touch_outcome": None,
            "reception_body_part": None,
        }

        decision = super()._choose_decision(actor, zone, tactics, ctx)

        if decision == "dummy":
            self._v13_reception_plan["mode"] = "dummy"
            return decision

        first_time_p = self._first_time_probability(actor, decision, diag)
        if first_time_p > 0.0 and self.rng.random() < first_time_p:
            self._v13_reception_plan["mode"] = "first_time"
            self._v13_reception_plan["first_time_probability"] = first_time_p
            return decision

        part = self._select_action_body_part(
            actor, "carry", zone, ctx, source=source
        )
        outcome = weighted_choice(self.rng, self._touch_outcome_weights(diag))
        self._v13_reception_plan["mode"] = "controlled"
        self._v13_reception_plan["touch_outcome"] = outcome
        self._v13_reception_plan["reception_body_part"] = part
        return decision

    @staticmethod
    def _apply_reception_to_context(ctx: dict, plan: dict) -> dict:
        adjusted = dict(ctx)
        mode = plan.get("mode")
        if mode == "first_time":
            diag = plan["diagnostic"]
            difficulty = float(diag["trajectory_difficulty"])
            technique_margin = float(diag["control_score"]) - difficulty * 0.35
            adjusted["pressure"] = clamp(
                float(adjusted.get("pressure", 0.5))
                + 0.045 * max(0.0, difficulty - technique_margin)
                - 0.025 * max(0.0, technique_margin)
            )
            adjusted["space"] = clamp(
                float(adjusted.get("space", 0.5))
                + 0.025 * max(0.0, technique_margin)
            )
            return adjusted

        outcome = plan.get("touch_outcome")
        outcome_delta = {
            "perfect": (-0.055, +0.070),
            "clean": (-0.020, +0.025),
            "loose": (+0.045, -0.045),
            "heavy": (+0.080, -0.085),
        }.get(outcome, (0.0, 0.0))
        adjusted["pressure"] = clamp(
            float(adjusted.get("pressure", 0.5)) + outcome_delta[0]
        )
        adjusted["space"] = clamp(
            float(adjusted.get("space", 0.5)) + outcome_delta[1]
        )

        intent = plan.get("intent")
        if intent == "secure":
            adjusted["pressure"] = clamp(adjusted["pressure"] - 0.035)
            adjusted["space_behind"] = clamp(
                float(adjusted.get("space_behind", 0.4)) - 0.035
            )
        elif intent == "half_turn":
            adjusted["space"] = clamp(adjusted["space"] + 0.025)
        elif intent == "forward_space":
            adjusted["space"] = clamp(adjusted["space"] + 0.045)
            adjusted["pressure"] = clamp(adjusted["pressure"] + 0.015)
        elif intent in {"inside", "line"}:
            adjusted["space"] = clamp(adjusted["space"] + 0.018)
        elif intent == "set_action":
            adjusted["pressure"] = clamp(adjusted["pressure"] - 0.018)
        return adjusted

    @staticmethod
    def _annotate_reception_event(event, plan: dict) -> None:
        event.data.setdefault("reception_source", plan.get("source"))
        event.data.setdefault("reception_mode", plan.get("mode"))
        event.data.setdefault("oriented_touch", plan.get("intent"))
        event.data.setdefault(
            "reception_control_score",
            round(float(plan["diagnostic"]["control_score"]), 3),
        )
        if plan.get("mode") == "first_time":
            event.data["first_time"] = True
            event.data.setdefault(
                "first_time_probability",
                round(float(plan.get("first_time_probability", 0.0)), 3),
            )
        elif plan.get("mode") == "dummy":
            event.data["first_time"] = True
            event.data["reception_body_part"] = "no_touch"
        else:
            event.data.setdefault("first_touch", plan.get("touch_outcome"))
            event.data.setdefault(
                "reception_body_part", plan.get("reception_body_part")
            )

    def _execute_decision(self, team, actor, zone, decision, ctx):
        self._ensure_reception_state()
        plan = self._v13_reception_plan
        valid = (
            plan
            and plan.get("actor") == actor.player.name
            and plan.get("zone") == zone
        )
        if not valid:
            return super()._execute_decision(team, actor, zone, decision, ctx)

        try:
            if plan.get("touch_outcome") == "miscontrol":
                event = self._turnover(
                    team, actor, zone, "poor_first_touch", ctx, severity=0.40
                )
                self._annotate_reception_event(event, plan)
                event.data["first_touch"] = "miscontrol"
                return event

            adjusted = self._apply_reception_to_context(ctx, plan)
            event = super()._execute_decision(
                team, actor, zone, decision, adjusted
            )
            self._annotate_reception_event(event, plan)

            if (
                plan.get("mode") == "first_time"
                and self.state.pending is not None
                and self.state.pending.team == team
                and self.state.pending.actor == actor.player.name
            ):
                self._v13_pending_first_time = {
                    "team": team,
                    "actor": actor.player.name,
                    "kind": self.state.pending.kind,
                    "source": plan.get("source"),
                }
            return event
        finally:
            self._v13_reception_plan = None

    def _resolve_shot(self, p: PendingAction):
        self._ensure_reception_state()
        marker = self._v13_pending_first_time
        matching = bool(
            marker
            and marker.get("team") == p.team
            and marker.get("actor") == p.actor
            and marker.get("kind") == p.kind
        )
        event = super()._resolve_shot(p)
        if matching:
            event.data["first_time"] = True
            event.data.setdefault("reception_mode", "first_time")
            event.data.setdefault("reception_source", marker.get("source"))
            self._v13_pending_first_time = None
        return event


MatchEngine = MatchEngineV13Reception

__all__ = ["MatchEngineV13Reception", "MatchEngine", "VERSION", "FIRST_TIME_ACTIONS"]
