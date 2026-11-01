from __future__ import annotations

"""Intelligent exploitation of numerical advantage for v1.3.

Playing 11v10 creates an extra option rather than an attribute bonus.  This
layer diagnoses which defensive line is numerically thinnest, shifts attacking
choice toward switches/progression and exposes the compactness trade-off: a
short-handed side may protect the centre, but then gives away wider space.
"""

from engine import Band, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_offensive_communication import MatchEngineV13OffensiveCommunication


class MatchEngineV13NumericalAdvantage(MatchEngineV13OffensiveCommunication):
    def numerical_exploitation_diagnostic(self, attacking_team: int) -> dict:
        attacking_team = int(attacking_team)
        defending_team = 1 - attacking_team
        atk_count = len(self.teams[attacking_team].on_field)
        def_count = len(self.teams[defending_team].on_field)
        advantage = max(0, atk_count - def_count)
        profile = self._formation_profile(defending_team)
        line_ratios = {}
        for line in ("def", "mid", "att"):
            intended = max(1.0, float(profile.get(line, 1)))
            actual = float(profile.get(f"actual_{line}", intended))
            line_ratios[line] = actual / intended
        weak_line = min(line_ratios, key=lambda line: (line_ratios[line], line))
        tactics = self.teams[defending_team].team.tactics
        compact = clamp(float(tactics.compactness))
        return {
            "attacking_team": attacking_team,
            "defending_team": defending_team,
            "attacking_players": atk_count,
            "defending_players": def_count,
            "advantage": advantage,
            "weak_line": weak_line,
            "line_ratios": line_ratios,
            "defensive_compactness": compact,
            "central_protection": clamp(compact * (0.55 + 0.15 * advantage)) if advantage else 0.0,
            "wide_exposure": clamp((0.24 + 0.34 * compact) * advantage) if advantage else 0.0,
        }

    def _spatial_context(self, attacking_team: int, zone: Zone) -> dict:
        ctx = dict(super()._spatial_context(attacking_team, zone))
        diag = self.numerical_exploitation_diagnostic(attacking_team)
        advantage = int(diag["advantage"])
        if advantage <= 0:
            return ctx
        degree = clamp(advantage / 2.0, 0.0, 1.0)
        compact = float(diag["defensive_compactness"])
        weak_line = str(diag["weak_line"])

        if zone.lane != Lane.CENTER:
            # Compact 10-man blocks protect central zones at the expense of the
            # weak-side/full-width occupation.
            ctx["space"] = clamp(float(ctx["space"]) + (0.020 + 0.032 * compact) * degree)
            ctx["wide_space"] = clamp(float(ctx.get("wide_space", 0.0)) + (0.035 + 0.040 * compact) * degree)
            ctx["pressure"] = clamp(float(ctx["pressure"]) - 0.018 * degree)
        else:
            # Centre is not simply opened by the red card; a compact block can
            # protect it and concede the flanks instead.
            central_opening = 0.030 * degree * (1.0 - compact)
            central_closure = 0.014 * degree * compact
            ctx["space"] = clamp(float(ctx["space"]) + central_opening - central_closure)
            ctx["pressure"] = clamp(float(ctx["pressure"]) + 0.012 * degree * compact)

        if (zone.band in {Band.ATT, Band.BOX} and weak_line == "def") or (zone.band == Band.MID and weak_line == "mid"):
            ctx["support"] = clamp(float(ctx["support"]) + 0.025 * degree)
            ctx["space_behind"] = clamp(float(ctx["space_behind"]) + 0.020 * degree)
        return ctx

    def _decision_weights(self, actor: PlayerState, zone: Zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        team = self._team_for_player_state(actor)
        if team is None:
            return items
        diag = self.numerical_exploitation_diagnostic(team)
        advantage = int(diag["advantage"])
        if advantage <= 0:
            return items
        degree = clamp(advantage / 2.0, 0.0, 1.0)
        wide_space = clamp(float(ctx.get("wide_space", 0.0)))
        factors = {
            "switch": 1.0 + 0.12 * degree + 0.06 * wide_space,
            "progressive_pass": 1.0 + 0.07 * degree,
            "safe_pass": 1.0 + 0.025 * degree,
            "through_ball": 1.0 + 0.045 * degree,
            "cross": 1.0 + 0.055 * degree * wide_space,
            "dribble": 1.0 - 0.035 * degree,
        }
        return [
            (action, max(0.001, float(weight) * clamp(factors.get(action, 1.0), 0.92, 1.16)))
            for action, weight in items
        ]

    def _base_target_weights(self, team: int, zone: Zone, actor: PlayerState | None, ctx: dict | None = None):
        rows = super()._base_target_weights(team, zone, actor, ctx)
        diag = self.numerical_exploitation_diagnostic(team)
        if int(diag["advantage"]) <= 0:
            return rows
        weak_line = str(diag["weak_line"])
        preferred = {
            "def": {"ST", "AM", "LW", "RW", "LB", "RB"},
            "mid": {"CM", "AM", "DM", "LW", "RW"},
            "att": {"CB", "DM", "CM"},
        }[weak_line]
        out = []
        for ps, weight in rows:
            factor = 1.055 if ps.player.position.upper() in preferred else 0.985
            if zone.lane != Lane.CENTER and ps.player.position.upper() in {"LW", "RW", "LB", "RB"}:
                factor *= 1.025
            out.append((ps, float(weight) * clamp(factor, 0.96, 1.09)))
        return out

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["numerical_exploitation"] = [
            self.numerical_exploitation_diagnostic(0),
            self.numerical_exploitation_diagnostic(1),
        ]
        return data


MatchEngine = MatchEngineV13NumericalAdvantage

__all__ = ["MatchEngineV13NumericalAdvantage", "MatchEngine"]
