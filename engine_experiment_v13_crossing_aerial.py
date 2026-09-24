from __future__ import annotations

"""v1.3 duel/box stage 4: crossing texture and aerial contests."""

from copy import deepcopy

from engine import Band, PlayerState, Zone, clamp
from engine_experiment_v13_box_movement import MatchEngineV13BoxMovement
from engine_experiment_v13_passing_texture import _stable_fraction

VERSION = "1.3-candidate-crossing-aerial"


class MatchEngineV13CrossingAerial(MatchEngineV13BoxMovement):
    def _ensure_crossing_state(self) -> None:
        if not hasattr(self, "_v13_cross_context"):
            self._v13_cross_context = None

    def cross_delivery_diagnostic(
        self,
        crosser: PlayerState,
        target: PlayerState,
        zone: Zone,
        kind: str,
        ctx: dict,
    ) -> dict:
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        crossing = clamp(crosser.effective("crossing") / 100.0)
        technique = clamp(crosser.effective("technique") / 100.0)
        vision = clamp(crosser.effective("vision") / 100.0)
        composure = clamp(crosser.effective("composure") / 100.0)
        target_heading = clamp(target.effective("heading") / 100.0)
        target_finishing = clamp(target.effective("finishing") / 100.0)
        fraction = _stable_fraction(
            "cross-delivery",
            self.seed,
            round(self.state.second, 3),
            crosser.player.name,
            target.player.name,
            kind,
            zone.lane.value,
        )
        if kind == "cutback":
            cross_type = "low_cutback"
            aerial = False
            difficulty = 0.10
        elif pressure >= 0.68:
            cross_type = "driven"
            aerial = target_heading >= target_finishing + 0.08
            difficulty = 0.22
        elif target_heading >= 0.74 and fraction < 0.58:
            cross_type = "whipped"
            aerial = True
            difficulty = 0.18
        elif fraction < 0.34:
            cross_type = "low_driven"
            aerial = False
            difficulty = 0.16
        elif fraction < 0.72:
            cross_type = "whipped"
            aerial = True
            difficulty = 0.18
        else:
            cross_type = "floated"
            aerial = True
            difficulty = 0.24

        quality = clamp(
            0.38 * crossing
            + 0.24 * technique
            + 0.18 * vision
            + 0.12 * composure
            + 0.08 * clamp(target.effective("off_ball") / 100.0)
            - 0.18 * pressure
            - difficulty
            + (fraction - 0.5) * 0.10
        )
        return {
            "cross_type": cross_type,
            "aerial": aerial,
            "delivery_quality": quality,
            "pressure": pressure,
            "target": target.player.name,
            "crosser": crosser.player.name,
        }

    def aerial_duel_diagnostic(
        self,
        attacker: PlayerState,
        defender: PlayerState,
        delivery_quality: float = 0.5,
    ) -> dict:
        attack = clamp(
            0.40 * attacker.effective("heading") / 100.0
            + 0.22 * attacker.effective("strength") / 100.0
            + 0.20 * attacker.effective("anticipation") / 100.0
            + 0.12 * attacker.effective("off_ball") / 100.0
            + 0.06 * attacker.energy
        )
        defend = clamp(
            0.36 * defender.effective("heading") / 100.0
            + 0.26 * defender.effective("positioning") / 100.0
            + 0.20 * defender.effective("strength") / 100.0
            + 0.18 * defender.effective("anticipation") / 100.0
        )
        edge = clamp(0.50 + 0.62 * (attack - defend) + 0.12 * (float(delivery_quality) - 0.50), 0.14, 0.86)
        return {"attacker_quality": attack, "defender_quality": defend, "attacker_edge": edge}

    def export_state(self) -> dict:
        data = super().export_state()
        self._ensure_crossing_state()
        data["v13_cross_context"] = deepcopy(self._v13_cross_context)
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        marker = data.get("v13_cross_context")
        obj._v13_cross_context = deepcopy(marker) if isinstance(marker, dict) else None
        return obj

    def _create_or_resolve_danger(self, team, actor, zone, kind, ctx):
        event = super()._create_or_resolve_danger(team, actor, zone, kind, ctx)
        if kind not in {"cross", "cutback"}:
            return event
        target_name = event.data.get("receiver") or event.data.get("box_run_target")
        pending = self.state.pending
        if not target_name or pending is None or pending.team != team:
            return event
        try:
            target = self.teams[team].by_name(str(target_name))
        except KeyError:
            return event
        diag = self.cross_delivery_diagnostic(actor, target, zone, kind, ctx)
        self._v13_cross_context = {
            **diag,
            "team": team,
            "origin": kind,
            "until_resolution": True,
        }
        pending.danger = clamp(float(pending.danger) + 0.075 * (float(diag["delivery_quality"]) - 0.50))
        if kind == "cutback" or not diag["aerial"]:
            pending.body_part = "foot"
        elif target.effective("heading") >= target.effective("finishing") - 3.0:
            pending.body_part = "head"
        event.data.setdefault("cross_type", diag["cross_type"])
        event.data.setdefault("cross_delivery_quality", round(float(diag["delivery_quality"]), 3))
        event.data.setdefault("cross_aerial", bool(diag["aerial"]))
        event.data["danger"] = round(float(pending.danger), 3)
        return event

    def _resolve_pending(self):
        p = self.state.pending
        prepared = False
        if p is not None and p.kind in {"cross", "cutback"}:
            try:
                crosser = self.teams[p.team].by_name(p.actor)
                target = self.teams[p.team].by_name(p.target) if p.target else None
            except KeyError:
                crosser = target = None
            if crosser is not None and target is not None:
                ctx = {
                    "pressure": clamp(float(p.pressure)),
                    "space": clamp(0.62 - 0.40 * float(p.pressure) + 0.10 * float(p.danger)),
                    "support": 0.55,
                }
                diag = self.cross_delivery_diagnostic(crosser, target, p.zone, p.kind, ctx)
                self._v13_cross_context = {**diag, "team": p.team, "origin": p.kind, "until_resolution": True}
                p.danger = clamp(float(p.danger) + 0.060 * (float(diag["delivery_quality"]) - 0.50))
                prepared = True
        event = super()._resolve_pending()
        if prepared and self._v13_cross_context:
            event.data.setdefault("cross_type", self._v13_cross_context.get("cross_type"))
            event.data.setdefault("cross_delivery_quality", round(float(self._v13_cross_context.get("delivery_quality", 0.5)), 3))
            self._v13_cross_context = None
        return event

    def _resolve_shot(self, p):
        self._ensure_crossing_state()
        marker = self._v13_cross_context if isinstance(self._v13_cross_context, dict) else None
        aerial_diag = None
        if p.body_part == "head" and p.defender:
            try:
                attacker = self.teams[p.team].by_name(p.actor)
                defender = self.teams[1 - p.team].by_name(p.defender)
            except KeyError:
                attacker = defender = None
            if attacker is not None and defender is not None:
                delivery = float(marker.get("delivery_quality", 0.5)) if marker else 0.5
                aerial_diag = self.aerial_duel_diagnostic(attacker, defender, delivery)
                edge = float(aerial_diag["attacker_edge"]) - 0.50
                p.danger = clamp(float(p.danger) + 0.10 * edge)
                p.pressure = clamp(float(p.pressure) - 0.055 * edge)
        event = super()._resolve_shot(p)
        if marker and marker.get("target") == p.actor:
            event.data.setdefault("cross_type", marker.get("cross_type"))
            event.data.setdefault("cross_delivery_quality", round(float(marker.get("delivery_quality", 0.5)), 3))
        if aerial_diag is not None:
            event.data.setdefault("aerial_duel", True)
            event.data.setdefault("aerial_attacker_edge", round(float(aerial_diag["attacker_edge"]), 3))
        return event


MatchEngine = MatchEngineV13CrossingAerial
