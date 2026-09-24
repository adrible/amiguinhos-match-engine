from __future__ import annotations

"""v1.3 contextual game management and numerical-state layer.

This layer models score/minute clock management and the practical consequences
of playing with fewer outfielders. It does not award a compensating defensive
buff to a dismissed team and does not alter player ratings.
"""

from engine import Band, PlayerState, Zone, clamp
from engine_experiment_v13_environment import MatchEngineV13Environment


class MatchEngineV13GameManagement(MatchEngineV13Environment):
    def numerical_context_diagnostic(self, team: int) -> dict:
        own = len(self.teams[int(team)].on_field)
        opp = len(self.teams[1 - int(team)].on_field)
        diff = own - opp
        return {
            "team": int(team),
            "own_players": own,
            "opponent_players": opp,
            "player_difference": diff,
            "short_handed": max(0, -diff),
            "numerical_advantage": max(0, diff),
        }

    def _management_composure(self, team: int) -> float:
        rows = [
            clamp((0.62 * ps.effective("composure") + 0.38 * ps.effective("discipline")) / 100.0)
            for ps in self.teams[int(team)].on_field
            if not ps.red
        ]
        return sum(rows) / len(rows) if rows else 0.50

    def game_management_diagnostic(self, team: int) -> dict:
        team = int(team)
        diff = self.score[team] - self.score[1 - team]
        late = clamp((self.minute - 68.0) / 25.0)
        leading = 1.0 if diff > 0 else 0.0
        chasing = 1.0 if diff < 0 else 0.0
        composure = self._management_composure(team)
        numerical = self.numerical_context_diagnostic(team)
        clock_factor = (
            1.0
            + 0.075 * late * leading
            + 0.035 * late * leading * composure
            - 0.055 * late * chasing
            - 0.018 * late * float(numerical["short_handed"])
        )
        clock_factor = clamp(clock_factor, 0.93, 1.12)
        risk_shift = clamp(
            0.34 * late * chasing
            - 0.28 * late * leading
            - 0.06 * float(numerical["short_handed"])
            + 0.04 * float(numerical["numerical_advantage"]),
            -0.45,
            0.45,
        )
        return {
            "team": team,
            "score_diff": diff,
            "late_factor": late,
            "management_composure": composure,
            "clock_factor": clock_factor,
            "risk_shift": risk_shift,
            **numerical,
        }

    def _advance_clock(self, seconds: float, possession_team: int):
        diag = self.game_management_diagnostic(int(possession_team))
        adjusted = float(seconds) * float(diag["clock_factor"])
        super()._advance_clock(adjusted, possession_team)

        # Covering extra space with ten (or fewer) players has a small but real
        # physical cost. This is intentionally not mirrored by an artificial
        # execution bonus for the team with eleven.
        for team in (0, 1):
            num = self.numerical_context_diagnostic(team)
            missing = int(num["short_handed"])
            if missing <= 0:
                continue
            extra = adjusted / 60.0 * 0.00012 * missing
            for ps in self.teams[team].on_field:
                stamina_factor = 0.88 + 0.12 * (100.0 - ps.player.stamina) / 80.0
                ps.energy = clamp(ps.energy - extra * stamina_factor, 0.18, 1.0)

    def _decision_weights(self, actor: PlayerState, zone: Zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        team = self._team_for_player_state(actor)
        if team is None:
            return items
        diag = self.game_management_diagnostic(team)
        late = float(diag["late_factor"])
        diff = int(diag["score_diff"])
        short = int(diag["short_handed"])
        extra = int(diag["numerical_advantage"])

        factors: dict[str, float] = {}

        def mul(action: str, factor: float) -> None:
            factors[action] = factors.get(action, 1.0) * float(factor)

        if diff > 0 and late > 0.0:
            for action, factor in {
                "safe_pass": 1.0 + 0.18 * late,
                "switch": 1.0 + 0.10 * late,
                "progressive_pass": 1.0 - 0.07 * late,
                "through_ball": 1.0 - 0.13 * late,
                "dribble": 1.0 - 0.14 * late,
                "shoot": 1.0 - 0.10 * late,
            }.items():
                mul(action, factor)
        elif diff < 0 and late > 0.0:
            for action, factor in {
                "safe_pass": 1.0 - 0.14 * late,
                "progressive_pass": 1.0 + 0.10 * late,
                "through_ball": 1.0 + 0.16 * late,
                "long_ball": 1.0 + 0.10 * late,
                "shoot": 1.0 + 0.13 * late,
            }.items():
                mul(action, factor)

        if short:
            for action, factor in {
                "safe_pass": 1.0 + 0.07 * short,
                "long_ball": 1.0 + 0.05 * short,
                "carry": 1.0 - 0.06 * short,
                "dribble": 1.0 - 0.08 * short,
                "through_ball": 1.0 - 0.04 * short,
            }.items():
                mul(action, factor)
        if extra:
            for action, factor in {
                "progressive_pass": 1.0 + 0.04 * extra,
                "through_ball": 1.0 + 0.05 * extra,
                "safe_pass": 1.0 + 0.02 * extra,
            }.items():
                mul(action, factor)

        return [
            (action, max(0.001, float(weight) * clamp(factors.get(action, 1.0), 0.55, 1.35)))
            for action, weight in items
        ]

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["game_management"] = [
            self.game_management_diagnostic(0),
            self.game_management_diagnostic(1),
        ]
        return data


MatchEngine = MatchEngineV13GameManagement

__all__ = ["MatchEngineV13GameManagement", "MatchEngine"]
