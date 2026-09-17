from __future__ import annotations

"""v1.3 final-third stage 1: contextual shot selection and target choice."""

from engine import Band, Lane, PendingAction, PlayerState, clamp
from engine_experiment_v13_crossing_aerial import MatchEngineV13CrossingAerial
from engine_experiment_v13_passing_texture import _stable_fraction

VERSION = "1.3-candidate-advanced-finishing"


class MatchEngineV13AdvancedFinishing(MatchEngineV13CrossingAerial):
    def shot_selection_diagnostic(
        self,
        shooter: PlayerState,
        p: PendingAction,
        keeper: PlayerState | None = None,
    ) -> dict:
        keeper = keeper or self._goalkeeper(1 - p.team)
        finishing = clamp(shooter.effective("finishing") / 100.0)
        technique = clamp(shooter.effective("technique") / 100.0)
        composure = clamp(shooter.effective("composure") / 100.0)
        long_shots = clamp(shooter.effective("long_shots") / 100.0)
        heading = clamp(shooter.effective("heading") / 100.0)
        pressure = clamp(float(p.pressure))
        danger = clamp(float(p.danger))
        keeper_pos = clamp(keeper.effective("gk_positioning") / 100.0)
        keeper_1v1 = clamp(keeper.effective("one_on_one") / 100.0)
        fraction = _stable_fraction(
            "shot-selection",
            self.seed,
            round(self.state.second, 3),
            shooter.player.name,
            keeper.player.name,
            p.origin,
            p.zone.band.value,
            p.zone.lane.value,
            p.body_part,
        )

        if p.body_part == "head":
            shot_type = "directed_header" if technique + composure >= 1.42 else "power_header"
        elif p.origin == "cross" and fraction < 0.22 and technique >= 0.66:
            shot_type = "volley"
        elif p.origin in {"cutback", "through_ball", "rebound"} and fraction < 0.26:
            shot_type = "first_time"
        elif p.zone.band != Band.BOX and long_shots >= 0.72 and fraction < 0.48:
            shot_type = "power"
        elif danger >= 0.67 and keeper_1v1 >= 0.68 and composure >= 0.70 and fraction < 0.25:
            shot_type = "chip"
        elif pressure >= 0.66:
            shot_type = "low_driven" if finishing >= 0.66 else "power"
        elif technique + composure >= 1.48 and fraction < 0.58:
            shot_type = "placed"
        elif p.zone.lane != Lane.CENTER:
            shot_type = "across_goal"
        else:
            shot_type = "low_driven" if fraction < 0.54 else "power"

        preferred = str(getattr(shooter.player, "preferred_foot", "R")).upper()
        if shot_type == "chip":
            target = "central_chip"
        elif p.zone.lane == Lane.LEFT:
            target = "far_post" if preferred in {"R", "B", "BOTH"} else "near_post"
        elif p.zone.lane == Lane.RIGHT:
            target = "far_post" if preferred in {"L", "B", "BOTH"} else "near_post"
        elif shot_type in {"placed", "across_goal"}:
            target = "low_far_corner" if fraction < 0.60 else "high_far_corner"
        elif shot_type == "low_driven":
            target = "low_corner"
        else:
            target = "far_corner" if fraction < 0.54 else "near_corner"

        execution = clamp(
            0.35 * finishing
            + 0.23 * technique
            + 0.20 * composure
            + 0.10 * danger
            + 0.07 * (heading if p.body_part == "head" else long_shots)
            + 0.05 * shooter.energy
            - 0.18 * pressure
        )
        type_delta = {
            "placed": 0.030,
            "low_driven": 0.018,
            "power": -0.005,
            "across_goal": 0.018,
            "chip": 0.012,
            "first_time": -0.012,
            "volley": -0.030,
            "directed_header": 0.008,
            "power_header": -0.010,
        }.get(shot_type, 0.0)
        keeper_difficulty = clamp(
            0.46
            + 0.30 * execution
            + type_delta
            - 0.12 * keeper_pos
            - 0.07 * keeper_1v1
        )
        # Kept as a diagnostic finishing signal for backwards compatibility.
        # It must NOT be folded into PendingAction.danger because xG describes
        # the chance situation; finisher/keeper quality belongs to conversion.
        danger_delta = clamp(
            (execution - 0.55) * 0.055 + type_delta,
            -0.045,
            0.055,
        )
        return {
            "shot_type": shot_type,
            "target_zone": target,
            "execution_quality": execution,
            "keeper_difficulty": keeper_difficulty,
            "danger_delta": danger_delta,
        }

    def _resolve_shot(self, p):
        try:
            shooter = self.teams[p.team].by_name(p.actor)
        except KeyError:
            shooter = self._named_or_fallback(p.team, p.actor, role="actor", zone=p.zone)
        keeper = self._goalkeeper(1 - p.team)
        diag = self.shot_selection_diagnostic(shooter, p, keeper)

        # Deliberately do not mutate p.danger here. The base conversion stage
        # already applies shooter-vs-keeper quality after xG is calculated.
        # Feeding execution back into danger double-counted finishing inside xG.
        event = super()._resolve_shot(p)
        event.data.setdefault("shot_type", diag["shot_type"])
        event.data.setdefault("shot_target", diag["target_zone"])
        event.data.setdefault(
            "shot_execution_quality",
            round(float(diag["execution_quality"]), 3),
        )
        event.data.setdefault(
            "shot_keeper_difficulty",
            round(float(diag["keeper_difficulty"]), 3),
        )
        return event


MatchEngine = MatchEngineV13AdvancedFinishing
