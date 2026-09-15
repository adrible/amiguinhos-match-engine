from __future__ import annotations

"""v1.3 tournament-aware decision layer.

Competition context changes intentions, not player ability.  The engine consumes
only a JSON-safe snapshot supplied by ``TournamentStateV13`` or another trusted
competition controller.  No future results are inferred here.
"""

from copy import deepcopy

from engine import PlayerState, Zone, clamp
from engine_experiment_v13_awards import MatchEngineV13Awards


class MatchEngineV13TournamentContext(MatchEngineV13Awards):
    def __init__(self, *args, tournament_context: dict | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._v13_tournament_context = self._normalise_tournament_context(tournament_context)

    @staticmethod
    def _normalise_tournament_context(raw: dict | None) -> dict | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise TypeError("tournament_context must be a mapping or None")
        context = deepcopy(raw)
        team_context = context.get("team_context", {})
        if not isinstance(team_context, dict):
            raise TypeError("team_context must be a mapping")
        for side in ("0", "1"):
            row = team_context.get(side, {})
            if row is not None and not isinstance(row, dict):
                raise TypeError(f"team_context[{side}] must be a mapping")
        policy = context.get("knowledge_policy")
        if policy is not None and "future" in str(policy).lower() and "only" not in str(policy).lower():
            raise ValueError("tournament context may not advertise future knowledge")
        return context

    def set_tournament_context(self, raw: dict | None) -> None:
        self._v13_tournament_context = self._normalise_tournament_context(raw)

    def tournament_context_diagnostic(self, team: int | None = None):
        if self._v13_tournament_context is None:
            return None
        if team is None:
            return deepcopy(self._v13_tournament_context)
        return deepcopy(self._team_tournament_context(int(team)))

    def _team_tournament_context(self, team: int) -> dict:
        if self._v13_tournament_context is None:
            return {}
        team_context = self._v13_tournament_context.get("team_context", {})
        row = team_context.get(str(int(team)), {})
        return row if isinstance(row, dict) else {}

    def _decision_weights(self, actor: PlayerState, zone: Zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        team = self._team_for_player_state(actor)
        if team is None:
            return items
        comp = self._team_tournament_context(team)
        if not comp:
            return items

        need_goal = clamp(float(comp.get("need_goal", 0.0)))
        protect = clamp(float(comp.get("protect_result", 0.0)))
        # A competition can demand a result before kickoff, but decision urgency
        # still grows with match time.  This prevents a final at 0:00 from being
        # treated like stoppage time simply because both teams need to win.
        time_pressure = 0.30 + 0.70 * clamp((self.minute - 45.0) / 45.0)
        chase = need_goal * time_pressure
        control = protect * (0.35 + 0.65 * clamp((self.minute - 55.0) / 35.0))

        factors: dict[str, float] = {}

        def mul(action: str, factor: float) -> None:
            factors[action] = factors.get(action, 1.0) * float(factor)

        if chase > 0.0:
            for action, factor in {
                "safe_pass": 1.0 - 0.11 * chase,
                "progressive_pass": 1.0 + 0.08 * chase,
                "through_ball": 1.0 + 0.13 * chase,
                "long_ball": 1.0 + 0.08 * chase,
                "dribble": 1.0 + 0.05 * chase,
                "cross": 1.0 + 0.07 * chase,
                "shoot": 1.0 + 0.10 * chase,
            }.items():
                mul(action, factor)

        if control > 0.0:
            for action, factor in {
                "safe_pass": 1.0 + 0.10 * control,
                "switch": 1.0 + 0.05 * control,
                "through_ball": 1.0 - 0.08 * control,
                "dribble": 1.0 - 0.07 * control,
                "shoot": 1.0 - 0.04 * control,
            }.items():
                mul(action, factor)

        return [
            (action, max(0.001, float(weight) * clamp(factors.get(action, 1.0), 0.72, 1.28)))
            for action, weight in items
        ]

    def _outgoing_reason(self, team: int, player: PlayerState):
        existing = super()._outgoing_reason(team, player)
        if existing is not None:
            return existing
        comp = self._team_tournament_context(team)
        if not comp or player.red or player.injured or player.player.position.upper() == "GK":
            return None
        if self.minute < 60.0:
            return None
        need_goal = clamp(float(comp.get("need_goal", 0.0)))
        protect = clamp(float(comp.get("protect_result", 0.0)))
        if need_goal >= 0.58:
            return {
                "reason": "competition_chase",
                "urgency": 0.68 + 0.72 * need_goal * clamp((self.minute - 58.0) / 32.0),
                "competition_need_goal": need_goal,
            }
        if protect >= 0.62 and self.minute >= 70.0:
            return {
                "reason": "competition_protect",
                "urgency": 0.62 + 0.55 * protect * clamp((self.minute - 68.0) / 22.0),
                "competition_protect_result": protect,
            }
        return None

    def _replacement_profile(self, team, outgoing, incoming, reason):
        mapped = {
            "competition_chase": "tactical_chase",
            "competition_protect": "tactical_protect",
        }.get(str(reason), reason)
        profile = super()._replacement_profile(team, outgoing, incoming, mapped)
        if profile is not None and mapped != reason:
            profile["competition_reason"] = str(reason)
        return profile

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["tournament_context"] = self.tournament_context_diagnostic()
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        data["v13_tournament_context"] = deepcopy(self._v13_tournament_context)
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        obj._v13_tournament_context = cls._normalise_tournament_context(
            data.get("v13_tournament_context")
        )
        return obj


MatchEngine = MatchEngineV13TournamentContext

__all__ = ["MatchEngineV13TournamentContext", "MatchEngine"]
