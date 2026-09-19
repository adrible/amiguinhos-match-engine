from __future__ import annotations

"""v1.3 stage 6: collective integration and rapid combination tempo."""

from engine_experiment_v13_duels import MatchEngineV13Duels

VERSION = "1.3-candidate-collective-play"


class MatchEngineV13Collective(MatchEngineV13Duels):
    def combination_clock_scale(self, possession_team: int | None = None) -> float:
        self._ensure_combination_state()
        team = self.state.possession if possession_team is None else possession_team
        actor = getattr(self, "_v13_current_open_actor", None)
        if not actor:
            return 1.0
        link = self._recent_link(team=team, actor_name=actor, max_age=12.0)
        if not link:
            return 1.0
        chain = self.active_pass_chain(team, max_age=16.0)
        if len(chain) >= 3:
            return 0.28
        if len(chain) == 2:
            return 0.38
        return 0.55

    def _advance_clock(self, seconds: float, possession_team: int):
        scale = self.combination_clock_scale(possession_team)
        try:
            return super()._advance_clock(seconds * scale, possession_team)
        finally:
            self._v13_current_open_actor = None

    def collective_diagnostic(self, team: int | None = None) -> dict:
        self._ensure_combination_state()
        selected = self.state.possession if team is None else team
        chain = self.active_pass_chain(selected, max_age=18.0)
        players = []
        if chain:
            players = [chain[0]["actor"]] + [row["target"] for row in chain]
        return {
            "team": selected,
            "chain_length": len(chain),
            "players": players[-6:],
            "rapid": len(chain) >= 2,
            "next_clock_scale": self.combination_clock_scale(selected),
        }

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["v13_collective"] = self.collective_diagnostic(self.state.possession)
        return data


MatchEngine = MatchEngineV13Collective
