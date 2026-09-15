from __future__ import annotations

"""v1.3 advanced collective stage 4: rest defence and counter-press after loss."""

from engine import PlayerState, Zone, clamp
from engine_experiment_v13_deception import MatchEngineV13Deception
from engine_experiment_v13_passing_texture import _stable_fraction

VERSION = "1.3-candidate-rest-defense-counterpress"


class MatchEngineV13TransitionStructure(MatchEngineV13Deception):
    def _ensure_transition_structure_state(self) -> None:
        if not hasattr(self, "_v13_counterpress_marker"):
            self._v13_counterpress_marker = None

    def rest_defense_diagnostic(self, attacking_team: int, zone: Zone) -> dict:
        tactics = self.teams[attacking_team].team.tactics
        structural = []
        for ps in self.teams[attacking_team].on_field:
            pos = ps.player.position.upper()
            if ps.red or pos == "GK":
                continue
            if pos in {"CB", "DM", "LB", "RB"}:
                reading = (
                    0.34 * ps.effective("positioning")
                    + 0.27 * ps.effective("anticipation")
                    + 0.22 * ps.effective("tackling")
                    + 0.17 * ps.effective("pace")
                ) / 100.0
                structural.append(clamp(reading) * (0.82 + 0.18 * ps.energy))
        count = len(structural)
        base = sum(structural) / count if count else 0.30
        lane_overlap = (
            tactics.overlap_left
            if zone.lane.value == "left"
            else tactics.overlap_right
            if zone.lane.value == "right"
            else 0.5 * (tactics.overlap_left + tactics.overlap_right)
        )
        commitment = clamp(
            0.24 * max(0.0, tactics.mentality)
            + 0.24 * tactics.pressing
            + 0.20 * tactics.defensive_line
            + 0.18 * lane_overlap
            + 0.14 * tactics.risk
        )
        coverage = clamp(0.50 + 0.11 * (count - 3))
        quality = clamp(
            0.56 * base
            + 0.20 * tactics.compactness
            + 0.14 * coverage
            + 0.10 * (1.0 - commitment)
        )
        return {
            "quality": quality,
            "coverage_count": count,
            "commitment": commitment,
            "compactness": clamp(tactics.compactness),
        }

    def counterpress_diagnostic(
        self,
        losing_team: int,
        zone: Zone,
        ctx: dict,
    ) -> dict:
        rest = self.rest_defense_diagnostic(losing_team, zone)
        tactics = self.teams[losing_team].team.tactics
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        anticipation_values = [
            clamp(ps.effective("anticipation") / 100.0)
            for ps in self.teams[losing_team].on_field
            if not ps.red and ps.player.position.upper() != "GK"
        ]
        anticipation = (
            sum(anticipation_values) / len(anticipation_values)
            if anticipation_values
            else 0.5
        )
        intensity = clamp(
            0.31 * tactics.pressing
            + 0.24 * rest["quality"]
            + 0.18 * tactics.compactness
            + 0.17 * anticipation
            + 0.10 * pressure
        )
        activation_p = clamp(0.08 + 0.58 * intensity, 0.10, 0.66)
        fraction = _stable_fraction(
            "counterpress",
            self.seed,
            round(self.state.second, 3),
            losing_team,
            zone.band.value,
            zone.lane.value,
        )
        active = intensity >= 0.48 and fraction < activation_p
        pressure_delta = clamp(0.010 + 0.060 * intensity, 0.0, 0.065) if active else 0.0
        depth_tradeoff = pressure_delta * (0.72 + 0.36 * rest["commitment"])
        return {
            "active": active,
            "intensity": intensity,
            "activation_probability": activation_p,
            "pressure_delta": pressure_delta,
            "depth_tradeoff": depth_tradeoff,
            "rest_defense_quality": rest["quality"],
            "commitment": rest["commitment"],
            "duration": 3.0 + 5.0 * intensity,
        }

    def export_state(self) -> dict:
        data = super().export_state()
        self._ensure_transition_structure_state()
        marker = self._v13_counterpress_marker
        data["v13_counterpress_marker"] = None if marker is None else dict(marker)
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_counterpress_marker")
        obj._v13_counterpress_marker = None if not raw else dict(raw)
        return obj

    def _active_counterpress(self, attacking_team: int) -> dict | None:
        self._ensure_transition_structure_state()
        marker = self._v13_counterpress_marker
        if not marker:
            return None
        if self.state.second > float(marker.get("until", 0.0)):
            self._v13_counterpress_marker = None
            return None
        if marker.get("target_team") != attacking_team:
            return None
        return marker

    def _spatial_context(self, attacking_team: int, zone: Zone) -> dict:
        ctx = super()._spatial_context(attacking_team, zone)
        marker = self._active_counterpress(attacking_team)
        if not marker:
            return ctx
        delta = float(marker.get("pressure_delta", 0.0))
        tradeoff = float(marker.get("depth_tradeoff", 0.0))
        ctx["pressure"] = clamp(float(ctx.get("pressure", 0.5)) + delta)
        ctx["space"] = clamp(float(ctx.get("space", 0.5)) - 0.44 * delta)
        ctx["space_behind"] = clamp(float(ctx.get("space_behind", 0.4)) + tradeoff)
        ctx["counterpress_active"] = True
        ctx["counterpress_intensity"] = float(marker.get("intensity", 0.0))
        return ctx

    def _turnover(self, losing_team, actor, zone, reason, ctx, severity=0.5):
        self._ensure_transition_structure_state()
        rest = self.rest_defense_diagnostic(losing_team, zone)
        counter = self.counterpress_diagnostic(losing_team, zone, ctx)
        adjusted_severity = clamp(
            float(severity)
            + 0.12 * rest["commitment"]
            - 0.15 * rest["quality"],
            0.08,
            0.92,
        )
        if counter["active"]:
            self._v13_counterpress_marker = {
                "pressing_team": losing_team,
                "target_team": 1 - losing_team,
                "until": self.state.second + float(counter["duration"]),
                "intensity": float(counter["intensity"]),
                "pressure_delta": float(counter["pressure_delta"]),
                "depth_tradeoff": float(counter["depth_tradeoff"]),
                "rest_defense_quality": float(counter["rest_defense_quality"]),
            }
        else:
            self._v13_counterpress_marker = None

        event = super()._turnover(
            losing_team,
            actor,
            zone,
            reason,
            ctx,
            severity=adjusted_severity,
        )
        event.data.setdefault("rest_defense_quality", round(float(rest["quality"]), 3))
        event.data.setdefault("attacking_commitment", round(float(rest["commitment"]), 3))
        if counter["active"]:
            event.data.setdefault("counterpress", True)
            event.data.setdefault("counterpress_intensity", round(float(counter["intensity"]), 3))
            event.data.setdefault(
                "counterpress_depth_tradeoff",
                round(float(counter["depth_tradeoff"]), 3),
            )
        return event

    def _execute_decision(self, team, actor, zone, decision, ctx):
        marker = self._active_counterpress(team)
        event = super()._execute_decision(team, actor, zone, decision, ctx)
        if marker:
            event.data.setdefault("under_counterpress", True)
            event.data.setdefault(
                "counterpress_intensity",
                round(float(marker.get("intensity", 0.0)), 3),
            )
        return event


MatchEngine = MatchEngineV13TransitionStructure
