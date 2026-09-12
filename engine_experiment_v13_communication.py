from __future__ import annotations

"""Experimental v1.3 layer: contextual defensive communication.

Communication coordinates relationships that already exist in the defensive
plan (a marking hand-off or a covering defender). It is deliberately *not* a
second defensive intention and never adds a generic team-wide bonus.

The layer answers a narrow question: when one defender must transfer a runner
or another defender must protect the space behind an action, who makes the
call, who receives it, and how cleanly is that instruction understood in the
current context?

Good communication can preserve a little more of the already-selected handoff
or cover effect. Poor communication can erode a little of that effect. It does
not create a new mark, a new cover, or alter player attributes.
"""

from typing import Optional

from engine import Band, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_cover import MatchEngineV13Cover


VERSION = (
    "1.3-candidate-spatial-creativity-boldness-offball-body-defense-"
    "marking-cover-communication"
)


class MatchEngineV13Communication(MatchEngineV13Cover):
    """Adds one contextual communication link to an existing defensive relation."""

    @staticmethod
    def _communication_need(plan: dict) -> dict:
        marking = plan.get("marking") if isinstance(plan.get("marking"), dict) else {}
        coverage = plan.get("coverage") if isinstance(plan.get("coverage"), dict) else {}

        # A live marking exchange is the most timing-sensitive relationship, so
        # it takes precedence over a simultaneous cover call in the diagnostic.
        if marking.get("switched"):
            return {
                "active": True,
                "type": "handoff_call",
                "initiator_name": marking.get("initial_marker"),
                "receiver_name": marking.get("marker_name"),
            }

        if coverage.get("active"):
            return {
                "active": True,
                "type": "cover_call",
                "initiator_name": plan.get("defender_name") or marking.get("marker_name"),
                "receiver_name": coverage.get("defender_name"),
            }

        return {
            "active": False,
            "type": None,
            "initiator_name": None,
            "receiver_name": None,
        }

    @staticmethod
    def _communication_skill(ps: PlayerState, call_type: str) -> float:
        # No hidden communication attribute: behaviour emerges from existing
        # defensive reading, calmness and discipline.
        if ps.player.position.upper() == "GK":
            raw = (
                0.28 * ps.effective("anticipation")
                + 0.27 * ps.effective("gk_positioning")
                + 0.25 * ps.effective("composure")
                + 0.20 * ps.effective("discipline")
            )
        elif call_type == "handoff_call":
            raw = (
                0.31 * ps.effective("anticipation")
                + 0.29 * ps.effective("positioning")
                + 0.22 * ps.effective("composure")
                + 0.18 * ps.effective("discipline")
            )
        else:
            raw = (
                0.29 * ps.effective("positioning")
                + 0.28 * ps.effective("anticipation")
                + 0.24 * ps.effective("composure")
                + 0.19 * ps.effective("discipline")
            )
        return clamp(raw / 100.0)

    @staticmethod
    def _communication_role_affinity(ps: PlayerState, zone: Zone, call_type: str) -> float:
        pos = ps.player.position.upper()
        if call_type == "handoff_call":
            base = {
                "CB": 1.22, "DM": 1.10, "LB": 0.98, "RB": 0.98,
                "GK": 0.88, "CM": 0.74,
            }.get(pos, 0.34)
        else:
            base = {
                "CB": 1.24, "DM": 1.12, "GK": 1.00, "LB": 0.92,
                "RB": 0.92, "CM": 0.72,
            }.get(pos, 0.32)

        if zone.band == Band.BOX and pos == "GK":
            base *= 1.16
        elif zone.band in {Band.ATT, Band.BOX} and pos == "CB":
            base *= 1.08
        elif zone.band == Band.MID and pos == "DM":
            base *= 1.07
        if zone.lane != Lane.CENTER and pos in {"CB", "DM"}:
            base *= 1.05
        return base

    def _best_communicator(
        self,
        defending_team: int,
        zone: Zone,
        call_type: str,
        *,
        initiator_name: Optional[str],
        receiver_name: Optional[str],
    ) -> tuple[Optional[PlayerState], float]:
        rows: list[tuple[PlayerState, float]] = []
        for ps in self.teams[defending_team].on_field:
            if ps.player.name == receiver_name:
                continue
            skill = self._communication_skill(ps, call_type)
            affinity = self._communication_role_affinity(ps, zone, call_type)
            energy = 0.86 + 0.14 * ps.energy
            initiator_bonus = 1.13 if initiator_name and ps.player.name == initiator_name else 1.0
            score = affinity * (0.58 + 0.42 * skill) * energy * initiator_bonus
            rows.append((ps, score))
        if not rows:
            return None, 0.0
        return max(rows, key=lambda row: row[1])

    @staticmethod
    def _receiver_readiness(ps: Optional[PlayerState], call_type: str) -> float:
        if ps is None:
            return 0.0
        if call_type == "handoff_call":
            raw = (
                0.33 * ps.effective("anticipation")
                + 0.30 * ps.effective("positioning")
                + 0.22 * ps.effective("composure")
                + 0.15 * ps.effective("discipline")
            )
        else:
            raw = (
                0.31 * ps.effective("positioning")
                + 0.29 * ps.effective("anticipation")
                + 0.22 * ps.effective("composure")
                + 0.18 * ps.effective("discipline")
            )
        return clamp((raw / 100.0) * (0.90 + 0.10 * ps.energy))

    def _communication_quality(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        plan: dict,
        call_type: str,
        communicator: Optional[PlayerState],
        receiver: Optional[PlayerState],
    ) -> float:
        if communicator is None or receiver is None:
            return 0.0

        defending_team = 1 - attacking_team
        tactics = self.teams[defending_team].team.tactics
        sender = self._communication_skill(communicator, call_type)
        listener = self._receiver_readiness(receiver, call_type)
        structure = (
            0.55 * tactics.compactness
            + 0.45 * clamp(float(ctx.get("defending_availability", 1.0)))
        )
        transition = clamp(float(getattr(self.state, "transition_boost", 0.0)))
        marking = plan.get("marking") if isinstance(plan.get("marking"), dict) else {}
        hiddenness = clamp(float(marking.get("hiddenness", 0.0)))

        quality = 0.48 * sender + 0.34 * listener + 0.18 * structure
        quality -= 0.12 * transition
        if call_type == "handoff_call":
            quality -= 0.11 * hiddenness
        if communicator.player.yellow:
            quality -= 0.015
        return clamp(quality)

    @staticmethod
    def _zero_effects() -> dict:
        return {
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

    @classmethod
    def _communication_effects(cls, plan: dict, call_type: str, quality: float) -> dict:
        """Return only the correction to an already-existing relation."""
        effects = cls._zero_effects()
        quality = clamp(quality)

        if call_type == "handoff_call":
            marking = plan.get("marking") if isinstance(plan.get("marking"), dict) else {}
            handoff = clamp(float(marking.get("handoff_quality", 0.0)))
            hiddenness = clamp(float(marking.get("hiddenness", 0.0)))
            existing_exchange = 0.024 * handoff * (1.0 - 0.35 * hiddenness)
            factor = 0.84 + 0.30 * quality
            effects["runner_control"] = existing_exchange * (factor - 1.0)
            if quality < 0.48:
                effects["pressure_delta"] = -0.004 * (0.48 - quality) / 0.48
            elif quality > 0.72:
                effects["pressure_delta"] = 0.0015 * (quality - 0.72) / 0.28
            return effects

        coverage = plan.get("coverage") if isinstance(plan.get("coverage"), dict) else {}
        base = coverage.get("effects") if isinstance(coverage.get("effects"), dict) else {}
        factor = 0.88 + 0.20 * quality

        # Scale only the useful part of the already-selected cover relation. The
        # spatial trade-off remains, so communication cannot become a free extra
        # defender.
        for key in ("runner_control", "pass_lane_control", "box_protection"):
            value = max(0.0, float(base.get(key, 0.0)))
            effects[key] = value * (factor - 1.0)
        if quality < 0.45:
            effects["space_delta"] = 0.004 * (0.45 - quality) / 0.45
        return effects

    def _communication_plan(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        plan: dict,
    ) -> dict:
        need = self._communication_need(plan)
        if not need["active"]:
            return {
                **need,
                "communicator": None,
                "communicator_name": None,
                "receiver": None,
                "quality": 0.0,
                "heard": False,
                "effects": self._zero_effects(),
            }

        defending_team = 1 - attacking_team
        receiver = None
        if need["receiver_name"]:
            try:
                receiver = self.teams[defending_team].by_name(str(need["receiver_name"]))
            except KeyError:
                receiver = None

        communicator, score = self._best_communicator(
            defending_team,
            zone,
            str(need["type"]),
            initiator_name=need["initiator_name"],
            receiver_name=need["receiver_name"],
        )
        quality = self._communication_quality(
            attacking_team, zone, ctx, plan, str(need["type"]), communicator, receiver
        )
        effects = self._communication_effects(plan, str(need["type"]), quality)
        return {
            **need,
            "communicator": communicator,
            "communicator_name": None if communicator is None else communicator.player.name,
            "receiver": receiver,
            "quality": quality,
            "score": score,
            "heard": bool(communicator is not None and receiver is not None and quality >= 0.44),
            "effects": effects,
        }

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
        communication = self._communication_plan(attacking_team, zone, ctx, plan)
        merged = dict(plan["effects"])
        for key, value in communication["effects"].items():
            merged[key] = float(merged.get(key, 0.0)) + float(value)
        plan["effects"] = merged
        plan["communication"] = communication
        return plan

    @staticmethod
    def _apply_plan_effects(ctx: dict, plan: dict) -> dict:
        adjusted = MatchEngineV13Cover._apply_plan_effects(ctx, plan)
        communication = plan.get("communication")
        if isinstance(communication, dict):
            adjusted["communication_active"] = bool(communication.get("active"))
            adjusted["communication_type"] = communication.get("type")
            adjusted["communication_actor"] = communication.get("communicator_name")
            adjusted["communication_receiver"] = communication.get("receiver_name")
            adjusted["communication_quality"] = round(float(communication.get("quality", 0.0)), 6)
            adjusted["communication_heard"] = bool(communication.get("heard"))
        return adjusted

    def communication_diagnostic(
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

        communication = plan["communication"]
        adjusted = self._apply_plan_effects(context, plan)
        return {
            "intent": plan["intent"],
            "marking_mode": plan.get("marking", {}).get("mode"),
            "marking_switched": bool(plan.get("marking", {}).get("switched")),
            "coverage_active": bool(plan.get("coverage", {}).get("active")),
            "active": communication["active"],
            "communication_type": communication["type"],
            "communicator": communication["communicator_name"],
            "initiator": communication["initiator_name"],
            "receiver": communication["receiver_name"],
            "quality": communication["quality"],
            "heard": communication["heard"],
            "effects": dict(communication["effects"]),
            "base": context,
            "adjusted": adjusted,
        }


MatchEngine = MatchEngineV13Communication
