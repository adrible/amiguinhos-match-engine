from __future__ import annotations

"""v1.3 advanced collective stage 3: disguise, feints and deliberate pauses."""

from engine import PlayerState, Zone, clamp
from engine_experiment_v13_passing_texture import (
    MatchEngineV13PassingTexture,
    _stable_fraction,
)

VERSION = "1.3-candidate-deception-pauses"


class MatchEngineV13Deception(MatchEngineV13PassingTexture):
    def _ensure_deception_state(self) -> None:
        if not hasattr(self, "_v13_pause_context"):
            self._v13_pause_context = None

    def deception_diagnostic(
        self,
        actor: PlayerState,
        zone: Zone,
        decision: str,
        ctx: dict,
    ) -> dict:
        eligible = decision in {
            "safe_pass",
            "progressive_pass",
            "through_ball",
            "switch",
            "long_ball",
            "carry",
            "dribble",
            "shoot",
            "cross",
            "cutback",
        }
        if not eligible:
            return {
                "attempt": False,
                "success": False,
                "type": None,
                "quality": 0.0,
                "attempt_probability": 0.0,
            }

        technique = clamp(actor.effective("technique") / 100.0)
        vision = clamp(actor.effective("vision") / 100.0)
        dribbling = clamp(actor.effective("dribbling") / 100.0)
        composure = clamp(actor.effective("composure") / 100.0)
        boldness = clamp(self._boldness(actor))
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        defensive_quality = clamp(float(ctx.get("defensive_quality", 0.55)))

        attempt_p = clamp(
            0.015
            + 0.085 * technique
            + 0.075 * vision
            + 0.060 * dribbling
            + 0.045 * boldness
            + 0.020 * pressure,
            0.02,
            0.28,
        )
        fraction = _stable_fraction(
            "deception",
            self.seed,
            round(self.state.second, 3),
            actor.player.name,
            decision,
            zone.band.value,
            zone.lane.value,
        )
        attempt = fraction < attempt_p
        if not attempt:
            return {
                "attempt": False,
                "success": False,
                "type": None,
                "quality": 0.0,
                "attempt_probability": attempt_p,
            }

        if decision in {"safe_pass", "progressive_pass", "through_ball", "switch", "long_ball"}:
            deception_type = "no_look_pass" if vision >= 0.78 and fraction < attempt_p * 0.45 else "disguised_pass"
        elif decision in {"cross", "cutback"}:
            deception_type = "cross_feint"
        elif decision == "shoot":
            deception_type = "disguised_shot"
        elif decision == "dribble":
            deception_type = "body_feint"
        else:
            deception_type = "stop_go"

        success_p = clamp(
            0.24
            + 0.24 * technique
            + 0.18 * vision
            + 0.15 * dribbling
            + 0.11 * composure
            - 0.22 * defensive_quality
            - 0.09 * pressure,
            0.16,
            0.78,
        )
        success_fraction = _stable_fraction(
            "deception-success",
            self.seed,
            round(self.state.second, 3),
            actor.player.name,
            decision,
            deception_type,
        )
        success = success_fraction < success_p
        quality = clamp(
            0.28 * technique
            + 0.25 * vision
            + 0.18 * dribbling
            + 0.15 * composure
            + 0.14 * boldness
        )
        return {
            "attempt": True,
            "success": success,
            "type": deception_type,
            "quality": quality,
            "attempt_probability": attempt_p,
            "success_probability": success_p,
        }

    def _spatial_context(self, attacking_team: int, zone: Zone) -> dict:
        ctx = super()._spatial_context(attacking_team, zone)
        self._ensure_deception_state()
        actor_name = getattr(self, "_v13_current_open_actor", None)
        if not actor_name:
            return ctx
        try:
            actor = self.teams[attacking_team].by_name(actor_name)
        except KeyError:
            return ctx

        scan = clamp(float(ctx.get("scan_quality", 0.5)))
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        support = clamp(float(ctx.get("support", 0.5)))
        composure = clamp(actor.effective("composure") / 100.0)
        technique = clamp(actor.effective("technique") / 100.0)
        pause_p = clamp(
            0.015
            + 0.085 * scan
            + 0.055 * composure
            + 0.040 * technique
            + 0.040 * support
            - 0.070 * max(0.0, pressure - 0.62),
            0.01,
            0.20,
        )
        fraction = _stable_fraction(
            "pause",
            self.seed,
            round(self.state.second, 3),
            actor_name,
            zone.band.value,
            zone.lane.value,
        )
        active = fraction < pause_p and 0.24 <= pressure <= 0.78
        self._v13_pause_context = {
            "team": attacking_team,
            "actor": actor_name,
            "zone": zone,
            "active": active,
            "probability": pause_p,
            "clock_scale": 1.14 if active else 1.0,
        }
        if active:
            ctx["pressure"] = clamp(pressure + 0.012)
            ctx["support"] = clamp(support + 0.020)
        return ctx

    def combination_clock_scale(self, possession_team: int | None = None) -> float:
        scale = super().combination_clock_scale(possession_team)
        self._ensure_deception_state()
        marker = self._v13_pause_context
        actor_name = getattr(self, "_v13_current_open_actor", None)
        team = self.state.possession if possession_team is None else possession_team
        if (
            marker
            and marker.get("active")
            and marker.get("team") == team
            and marker.get("actor") == actor_name
            and marker.get("zone") == self.state.zone
        ):
            scale *= float(marker.get("clock_scale", 1.0))
        return clamp(scale, 0.20, 1.20)

    def _execute_decision(self, team, actor, zone, decision, ctx):
        diag = self.deception_diagnostic(actor, zone, decision, ctx)
        adjusted = dict(ctx)
        if diag["attempt"]:
            quality = float(diag["quality"])
            if diag["success"]:
                adjusted["pressure"] = clamp(
                    float(adjusted.get("pressure", 0.5)) - 0.032 * quality
                )
                adjusted["space"] = clamp(
                    float(adjusted.get("space", 0.5)) + 0.024 * quality
                )
                adjusted["defensive_quality"] = clamp(
                    float(adjusted.get("defensive_quality", 0.55)) - 0.020 * quality
                )
            else:
                adjusted["pressure"] = clamp(
                    float(adjusted.get("pressure", 0.5)) + 0.032
                )
                adjusted["space"] = clamp(
                    float(adjusted.get("space", 0.5)) - 0.018
                )

        event = super()._execute_decision(team, actor, zone, decision, adjusted)
        if diag["attempt"]:
            event.data.setdefault("deception", diag["type"])
            event.data.setdefault("deception_success", bool(diag["success"]))
            event.data.setdefault("deception_quality", round(float(diag["quality"]), 3))
            event.data.setdefault(
                "deception_attempt_probability",
                round(float(diag["attempt_probability"]), 3),
            )

        pause = getattr(self, "_v13_pause_context", None)
        if (
            pause
            and pause.get("active")
            and pause.get("team") == team
            and pause.get("actor") == actor.player.name
            and pause.get("zone") == zone
        ):
            event.data.setdefault("deliberate_pause", True)
            event.data.setdefault(
                "pause_probability",
                round(float(pause["probability"]), 3),
            )
        return event


MatchEngine = MatchEngineV13Deception
