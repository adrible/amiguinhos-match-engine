from __future__ import annotations

"""v1.3 match-intelligence stage 2: individual adaptation to observed patterns."""

from engine import Band, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_tactical_memory import MatchEngineV13TacticalMemory

VERSION = "1.3-candidate-individual-adaptation"

_ACTION_PATTERN = {
    "cross": "wide_service",
    "cutback": "wide_service",
    "progressive_pass": "vertical_progression",
    "through_ball": "vertical_progression",
    "long_ball": "vertical_progression",
    "switch": "switch_play",
    "carry": "carry_dribble",
    "dribble": "carry_dribble",
    "shoot": "shooting",
}


class MatchEngineV13IndividualAdaptation(MatchEngineV13TacticalMemory):
    def _adaptive_defender(self, defending_team: int, zone: Zone) -> PlayerState | None:
        candidates = [
            ps for ps in self.teams[defending_team].on_field
            if not ps.red and ps.player.position.upper() != "GK"
        ]
        if not candidates:
            return None

        def score(ps: PlayerState) -> float:
            pos = ps.player.position.upper()
            role = 0.0
            if zone.lane == Lane.CENTER and pos in {"CB", "DM", "CM"}:
                role = 0.11
            elif zone.lane == Lane.LEFT and pos in {"RB", "CB", "DM"}:
                role = 0.10
            elif zone.lane == Lane.RIGHT and pos in {"LB", "CB", "DM"}:
                role = 0.10
            if zone.band == Band.BOX and pos == "CB":
                role += 0.08
            return (
                0.34 * ps.effective("positioning") / 100.0
                + 0.27 * ps.effective("anticipation") / 100.0
                + 0.21 * ps.effective("tackling") / 100.0
                + 0.10 * ps.effective("pace") / 100.0
                + 0.08 * ps.energy
                + role
            )

        return max(candidates, key=lambda ps: (score(ps), ps.player.name))

    def individual_adaptation_diagnostic(
        self,
        defending_team: int,
        attacker: PlayerState,
        zone: Zone,
        action: str,
        ctx: dict | None = None,
    ) -> dict:
        pattern = _ACTION_PATTERN.get(str(action))
        defender = self._adaptive_defender(defending_team, zone)
        if pattern is None or defender is None:
            return {
                "active": False,
                "pattern": pattern,
                "defender": None if defender is None else defender.player.name,
                "sample_count": 0,
                "confidence": 0.0,
            }

        memory = self.tactical_memory_diagnostic(
            defending_team,
            1 - defending_team,
            player_name=attacker.player.name,
            pattern=pattern,
        )
        reading = clamp(
            0.54 * defender.effective("anticipation") / 100.0
            + 0.46 * defender.effective("positioning") / 100.0
        )
        active = bool(memory["learned"] and reading >= 0.52)
        strength = clamp(float(memory["confidence"]) * (0.72 + 0.28 * reading)) if active else 0.0

        stance = {
            "wide_service": "close_service_angle",
            "vertical_progression": "protect_inside_lane",
            "switch_play": "hold_far_side",
            "carry_dribble": "contain_then_step",
            "shooting": "step_to_shot",
            "fast_transition": "delay_transition",
        }.get(pattern, "balanced")
        base_pressure = {
            "wide_service": 0.030,
            "vertical_progression": 0.020,
            "switch_play": 0.012,
            "carry_dribble": 0.034,
            "shooting": 0.032,
            "fast_transition": 0.018,
        }.get(pattern, 0.016)
        base_space = {
            "wide_service": -0.018,
            "vertical_progression": -0.014,
            "switch_play": -0.010,
            "carry_dribble": -0.022,
            "shooting": -0.018,
            "fast_transition": -0.012,
        }.get(pattern, -0.010)
        base_depth = {
            "wide_service": 0.018,
            "vertical_progression": 0.014,
            "switch_play": 0.020,
            "carry_dribble": 0.024,
            "shooting": 0.022,
            "fast_transition": 0.018,
        }.get(pattern, 0.016)
        return {
            "active": active,
            "pattern": pattern,
            "defender": defender.player.name,
            "stance": stance,
            "sample_count": int(memory["sample_count"]),
            "confidence": float(memory["confidence"]),
            "reading": reading,
            "pressure_delta": base_pressure * strength,
            "space_delta": base_space * strength,
            "depth_tradeoff": base_depth * strength,
        }

    def _execute_decision(self, team, actor, zone, decision, ctx):
        diag = self.individual_adaptation_diagnostic(1 - team, actor, zone, decision, ctx)
        adjusted = dict(ctx)
        if diag.get("active"):
            adjusted["pressure"] = clamp(float(adjusted.get("pressure", 0.5)) + float(diag["pressure_delta"]))
            adjusted["space"] = clamp(float(adjusted.get("space", 0.5)) + float(diag["space_delta"]))
            adjusted["space_behind"] = clamp(
                float(adjusted.get("space_behind", 0.4)) + float(diag["depth_tradeoff"])
            )
        event = super()._execute_decision(team, actor, zone, decision, adjusted)
        if diag.get("active"):
            event.data.setdefault("individual_adaptation", True)
            event.data.setdefault("adapted_to_pattern", diag["pattern"])
            event.data.setdefault("adaptive_defender", diag["defender"])
            event.data.setdefault("adaptive_stance", diag["stance"])
            event.data.setdefault("pattern_samples", int(diag["sample_count"]))
            event.data.setdefault("pattern_confidence", round(float(diag["confidence"]), 3))
            event.data.setdefault("adaptation_depth_tradeoff", round(float(diag["depth_tradeoff"]), 3))
        return event


MatchEngine = MatchEngineV13IndividualAdaptation
