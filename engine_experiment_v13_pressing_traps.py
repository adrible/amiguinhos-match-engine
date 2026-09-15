from __future__ import annotations

"""v1.3 final-third stage 5: pressing traps and intelligent mid-block behaviour."""

from engine import Band, Lane, Zone, clamp
from engine_experiment_v13_line_breaking import MatchEngineV13LineBreaking
from engine_experiment_v13_passing_texture import _stable_fraction

VERSION = "1.3-candidate-pressing-traps-mid-block"


class MatchEngineV13PressingTraps(MatchEngineV13LineBreaking):
    def pressing_trap_diagnostic(self, attacking_team: int, zone: Zone, ctx: dict) -> dict:
        defending_team = 1 - attacking_team
        tactics = self.teams[defending_team].team.tactics
        structural = [
            ps
            for ps in self.teams[defending_team].on_field
            if not ps.red and ps.player.position.upper() in {"CB", "LB", "RB", "DM", "CM"}
        ]
        if structural:
            reading = sum(
                0.54 * ps.effective("positioning") + 0.46 * ps.effective("anticipation")
                for ps in structural
            ) / (100.0 * len(structural))
        else:
            reading = 0.35
        reading = clamp(reading)

        mid_block_score = clamp(
            0.18
            + 0.30 * tactics.compactness
            + 0.18 * reading
            + 0.12 * (1.0 - abs(tactics.pressing - 0.55))
            + 0.10 * (1.0 - abs(tactics.defensive_line - 0.52))
            + (0.12 if zone.band == Band.MID else 0.04 if zone.band == Band.ATT else -0.12)
        )
        trap_score = clamp(
            0.12
            + 0.28 * tactics.pressing
            + 0.24 * tactics.compactness
            + 0.20 * reading
            + 0.08 * tactics.defensive_line
            + (0.08 if zone.band in {Band.MID, Band.ATT} else -0.10)
        )
        fraction = _stable_fraction(
            "pressing-trap",
            self.seed,
            round(self.state.second, 3),
            attacking_team,
            zone.band.value,
            zone.lane.value,
        )
        activation_probability = clamp(0.05 + 0.34 * trap_score, 0.05, 0.38)
        active = (
            zone.band in {Band.MID, Band.ATT}
            and tactics.pressing >= 0.42
            and tactics.compactness >= 0.46
            and fraction < activation_probability
        )
        if zone.lane == Lane.CENTER:
            bait_lane = Lane.LEFT.value if fraction < activation_probability / 2.0 else Lane.RIGHT.value
        else:
            bait_lane = zone.lane.value
        mid_block = bool(
            zone.band == Band.MID
            and mid_block_score >= 0.54
            and not active
        )
        return {
            "active": active,
            "trap_score": trap_score,
            "activation_probability": activation_probability,
            "bait_lane": bait_lane,
            "mid_block": mid_block,
            "mid_block_score": mid_block_score,
            "defensive_reading": reading,
        }

    def _spatial_context(self, attacking_team: int, zone: Zone) -> dict:
        ctx = super()._spatial_context(attacking_team, zone)
        diag = self.pressing_trap_diagnostic(attacking_team, zone, ctx)
        if diag["active"]:
            intensity = float(diag["trap_score"])
            ctx["pressure"] = clamp(float(ctx.get("pressure", 0.5)) + 0.045 * intensity)
            ctx["space_behind"] = clamp(float(ctx.get("space_behind", 0.5)) + 0.040 * intensity)
            ctx["pressing_trap"] = True
            ctx["trap_lane"] = diag["bait_lane"]
        elif diag["mid_block"]:
            q = float(diag["mid_block_score"])
            if zone.lane == Lane.CENTER:
                ctx["space"] = clamp(float(ctx.get("space", 0.5)) - 0.032 * q)
                ctx["pressure"] = clamp(float(ctx.get("pressure", 0.5)) + 0.020 * q)
            else:
                ctx["space"] = clamp(float(ctx.get("space", 0.5)) + 0.018 * q)
            ctx["mid_block"] = True
        ctx["pressing_trap_score"] = float(diag["trap_score"])
        ctx["mid_block_score"] = float(diag["mid_block_score"])
        return ctx

    def _execute_decision(self, team, actor, zone, decision, ctx):
        event = super()._execute_decision(team, actor, zone, decision, ctx)
        if ctx.get("pressing_trap"):
            event.data.setdefault("pressing_trap", True)
            event.data.setdefault("pressing_trap_lane", ctx.get("trap_lane"))
            event.data.setdefault(
                "pressing_trap_score",
                round(float(ctx.get("pressing_trap_score", 0.0)), 3),
            )
            event.data.setdefault(
                "pressing_trap_depth_tradeoff",
                round(0.040 * float(ctx.get("pressing_trap_score", 0.0)), 3),
            )
        elif ctx.get("mid_block"):
            event.data.setdefault("mid_block", True)
            event.data.setdefault(
                "mid_block_score",
                round(float(ctx.get("mid_block_score", 0.0)), 3),
            )
        return event


MatchEngine = MatchEngineV13PressingTraps
