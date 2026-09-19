from __future__ import annotations

"""v1.3 advanced collective stage 2: pass weight, shape and arrival quality.

A completed pass is no longer semantically identical to every other completed
pass. The ball can arrive in stride, to feet, slightly behind, underhit or
overhit, and can be ground, driven, lofted, chipped or curled. These are
contextual execution properties derived from existing attributes.
"""

import hashlib

from engine import Band, PlayerState, Zone, clamp
from engine_experiment_v13_scanning import MatchEngineV13Scanning

VERSION = "1.3-candidate-pass-texture"

_PASS_EVENT_KEYS = {"safe_pass", "progression", "progression_creates_danger", "danger_created"}


def _stable_fraction(*parts) -> float:
    raw = "|".join(str(x) for x in parts).encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


class MatchEngineV13PassingTexture(MatchEngineV13Scanning):
    @staticmethod
    def _pass_shape(kind: str, zone: Zone, fraction: float) -> str:
        kind = (kind or "safe_pass").lower()
        if kind == "safe_pass":
            return "ground"
        if kind == "progressive_pass":
            return "driven" if fraction > 0.58 else "ground"
        if kind == "through_ball":
            return "chipped" if fraction > 0.76 else "ground"
        if kind == "switch":
            return "curled" if fraction > 0.55 else "lofted"
        if kind == "long_ball":
            return "driven" if fraction > 0.72 else "lofted"
        if kind == "cross":
            if fraction > 0.72:
                return "curled"
            if fraction > 0.38:
                return "driven"
            return "lofted"
        if kind == "cutback":
            return "driven" if fraction > 0.62 else "ground"
        if zone.band == Band.BOX:
            return "driven"
        return "ground"

    def pass_delivery_diagnostic(
        self,
        actor: PlayerState,
        zone: Zone,
        kind: str,
        ctx: dict,
        *,
        target: str | None = None,
        event=None,
    ) -> dict:
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        space = clamp(float(ctx.get("space", 0.5)))
        support = clamp(float(ctx.get("support", 0.5)))
        scan = clamp(
            float(
                (event.data.get("scan_quality") if event is not None else None)
                or ctx.get("scan_quality", 0.5)
            )
        )
        passing = clamp(actor.effective("passing") / 100.0)
        technique = clamp(actor.effective("technique") / 100.0)
        vision = clamp(actor.effective("vision") / 100.0)
        composure = clamp(actor.effective("composure") / 100.0)
        difficulty = {
            "safe_pass": 0.08,
            "progressive_pass": 0.18,
            "switch": 0.30,
            "long_ball": 0.34,
            "through_ball": 0.29,
            "cross": 0.31,
            "cutback": 0.23,
        }.get(kind, 0.16)

        fraction = _stable_fraction(
            self.seed,
            round(self.state.second, 3),
            actor.player.name,
            target or "",
            kind,
            zone.band.value,
            zone.lane.value,
        )
        noise = (fraction - 0.5) * 0.22
        score = clamp(
            0.34 * passing
            + 0.22 * technique
            + 0.18 * vision
            + 0.10 * composure
            + 0.07 * scan
            + 0.05 * space
            + 0.04 * support
            - 0.17 * pressure
            - difficulty
            + noise
        )

        forward_kind = kind in {
            "progressive_pass",
            "through_ball",
            "switch",
            "long_ball",
            "cross",
            "cutback",
        }
        if score >= 0.76:
            placement = "ahead" if forward_kind else "feet"
        elif score >= 0.60:
            placement = "feet"
        elif score >= 0.45:
            placement = "slightly_behind"
        else:
            placement = "underhit" if fraction < 0.5 else "overhit"

        control_delta = {
            "ahead": 0.040,
            "feet": 0.020,
            "slightly_behind": -0.035,
            "underhit": -0.055,
            "overhit": -0.075,
        }[placement]
        trajectory_delta = {
            "ahead": -0.025,
            "feet": -0.015,
            "slightly_behind": 0.025,
            "underhit": 0.035,
            "overhit": 0.060,
        }[placement]
        shape = self._pass_shape(kind, zone, fraction)
        return {
            "score": score,
            "placement": placement,
            "shape": shape,
            "control_delta": control_delta,
            "trajectory_delta": trajectory_delta,
            "fraction": fraction,
        }

    def export_state(self) -> dict:
        data = super().export_state()
        marker = getattr(self, "_v13_reception_marker", None)
        extras = None
        if marker and marker.get("pass_delivery"):
            extras = {
                "pass_delivery": marker.get("pass_delivery"),
                "pass_shape": marker.get("pass_shape"),
                "pass_delivery_score": marker.get("pass_delivery_score"),
                "delivery_control_delta": marker.get("delivery_control_delta"),
                "delivery_trajectory_delta": marker.get("delivery_trajectory_delta"),
            }
        data["v13_pass_delivery_marker"] = extras
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        extras = data.get("v13_pass_delivery_marker")
        marker = getattr(obj, "_v13_reception_marker", None)
        if extras and marker:
            marker.update({k: v for k, v in extras.items() if v is not None})
        return obj

    def reception_diagnostic(
        self,
        actor: PlayerState,
        zone: Zone,
        ctx: dict | None = None,
        *,
        source: str = "open_play",
    ) -> dict:
        diag = dict(super().reception_diagnostic(actor, zone, ctx, source=source))
        marker = getattr(self, "_v13_reception_marker", None)
        if (
            marker
            and marker.get("target") == actor.player.name
            and marker.get("zone") == zone
            and marker.get("pass_delivery")
        ):
            diag["control_score"] = clamp(
                float(diag["control_score"])
                + float(marker.get("delivery_control_delta", 0.0))
            )
            diag["trajectory_difficulty"] = clamp(
                float(diag["trajectory_difficulty"])
                + float(marker.get("delivery_trajectory_delta", 0.0))
            )
            diag["pass_delivery"] = marker.get("pass_delivery")
            diag["pass_shape"] = marker.get("pass_shape")
            diag["pass_delivery_score"] = float(marker.get("pass_delivery_score", 0.5))
        return diag

    def _execute_decision(self, team, actor, zone, decision, ctx):
        event = super()._execute_decision(team, actor, zone, decision, ctx)
        target = event.data.get("target") or event.data.get("receiver")
        if not target or event.text_key not in _PASS_EVENT_KEYS:
            return event

        kind = str(event.data.get("kind") or decision)
        delivery = self.pass_delivery_diagnostic(
            actor,
            zone,
            kind,
            ctx,
            target=str(target),
            event=event,
        )
        event.data.setdefault("pass_delivery", delivery["placement"])
        event.data.setdefault("pass_shape", delivery["shape"])
        event.data.setdefault("pass_delivery_score", round(float(delivery["score"]), 3))

        marker = getattr(self, "_v13_reception_marker", None)
        if marker and marker.get("target") == target:
            marker.update(
                {
                    "pass_delivery": delivery["placement"],
                    "pass_shape": delivery["shape"],
                    "pass_delivery_score": float(delivery["score"]),
                    "delivery_control_delta": float(delivery["control_delta"]),
                    "delivery_trajectory_delta": float(delivery["trajectory_delta"]),
                }
            )
        return event


MatchEngine = MatchEngineV13PassingTexture
