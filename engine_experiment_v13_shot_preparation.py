from __future__ import annotations

"""v1.3 final-third stage 2: preparation before the shot and real block windows."""

from engine import PendingAction, PlayerState, clamp
from engine_experiment_v13_finishing import MatchEngineV13AdvancedFinishing
from engine_experiment_v13_passing_texture import _stable_fraction

VERSION = "1.3-candidate-shot-preparation"


class MatchEngineV13ShotPreparation(MatchEngineV13AdvancedFinishing):
    def shot_preparation_diagnostic(
        self,
        shooter: PlayerState,
        p: PendingAction,
    ) -> dict:
        pressure = clamp(float(p.pressure))
        danger = clamp(float(p.danger))
        technique = clamp(shooter.effective("technique") / 100.0)
        composure = clamp(shooter.effective("composure") / 100.0)
        finishing = clamp(shooter.effective("finishing") / 100.0)
        pace = clamp(shooter.effective("pace") / 100.0)
        first_time_source = p.origin in {"cross", "cutback", "through_ball", "rebound", "second_ball"}
        fraction = _stable_fraction(
            "shot-preparation",
            self.seed,
            round(self.state.second, 3),
            shooter.player.name,
            p.origin,
            p.zone.band.value,
            p.zone.lane.value,
            p.body_part,
        )
        first_time_score = clamp(
            0.18
            + 0.24 * technique
            + 0.20 * finishing
            + 0.18 * composure
            + 0.11 * danger
            - 0.18 * pressure
            + (0.16 if first_time_source else -0.10)
        )

        if p.body_part == "head":
            preparation = "attack_ball"
            seconds = 0.10
            pressure_delta = 0.005
            danger_delta = 0.0
        elif first_time_source and fraction < first_time_score:
            preparation = "first_time"
            seconds = 0.08
            pressure_delta = -0.018
            danger_delta = 0.008 if technique >= 0.68 else -0.008
        elif pressure >= 0.68 and pace + technique >= 1.35:
            preparation = "create_separation"
            seconds = 0.38
            pressure_delta = -0.032
            danger_delta = 0.012
        elif str(getattr(shooter.player, "preferred_foot", "R")).upper() not in {"B", "BOTH"} and fraction < 0.48:
            preparation = "shift_to_strong_foot"
            seconds = 0.55
            pressure_delta = 0.040
            danger_delta = 0.018 * technique
        elif p.origin == "cross" and fraction > 0.76:
            preparation = "let_ball_drop"
            seconds = 0.46
            pressure_delta = 0.032
            danger_delta = 0.010 * composure
        else:
            preparation = "set_touch"
            seconds = 0.30
            pressure_delta = 0.024
            danger_delta = 0.012 * composure

        block_window = clamp(
            0.28
            + 0.45 * pressure
            + 0.34 * seconds
            - 0.18 * technique
            - 0.10 * composure
        )
        return {
            "preparation": preparation,
            "seconds": seconds,
            "pressure_delta": pressure_delta,
            "danger_delta": danger_delta,
            "block_window": block_window,
            "first_time_score": first_time_score,
        }

    def _resolve_shot(self, p):
        try:
            shooter = self.teams[p.team].by_name(p.actor)
        except KeyError:
            shooter = self._named_or_fallback(p.team, p.actor, role="actor", zone=p.zone)
        diag = self.shot_preparation_diagnostic(shooter, p)
        seconds = float(diag["seconds"])
        if seconds > 0.0:
            self._advance_clock(seconds, p.team)
        p.pressure = clamp(float(p.pressure) + float(diag["pressure_delta"]))
        p.danger = clamp(float(p.danger) + float(diag["danger_delta"]))
        event = super()._resolve_shot(p)
        event.data.setdefault("shot_preparation", diag["preparation"])
        event.data.setdefault("shot_preparation_seconds", round(seconds, 3))
        event.data.setdefault("shot_block_window", round(float(diag["block_window"]), 3))
        event.data.setdefault("first_time_readiness", round(float(diag["first_time_score"]), 3))
        return event


MatchEngine = MatchEngineV13ShotPreparation
