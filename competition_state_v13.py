from __future__ import annotations

"""Complete competition facade for v1.3.

This builds on ``tournament_state_v13`` and adds robust tie resolution for
single- and two-leg playoffs, knockout rounds, third-place ties and finals.
The winner of one leg is never confused with the winner of the tie.
"""

from copy import deepcopy

from tournament_state_v13 import (
    TournamentMatchBridgeV13,
    TournamentStateV13 as _TournamentStateV13Base,
)


class TournamentStateV13(_TournamentStateV13Base):
    def record_tie_winner(
        self,
        tie_id: str,
        winner: str,
        *,
        decided_by: str = "penalties",
    ) -> None:
        """Record an explicit winner when aggregate rules cannot separate a tie.

        Typical uses are penalties or another competition-specific decider.
        The information is stored on the decisive fixture metadata so ordinary
        ``to_dict`` / ``from_dict`` persistence keeps it without hidden state.
        """
        tie_id = str(tie_id)
        fixtures = [
            fixture for fixture in self.fixtures.values()
            if str(fixture.get("tie_id")) == tie_id
        ]
        if not fixtures:
            raise KeyError(tie_id)
        teams = {team for fixture in fixtures for team in (fixture["home"], fixture["away"])}
        if winner not in teams:
            raise ValueError("tie winner must be one of the teams in the tie")
        decisive = max(fixtures, key=lambda fixture: (int(fixture.get("leg", 1)), fixture["id"]))
        decisive.setdefault("metadata", {})["tie_winner"] = str(winner)
        decisive["metadata"]["tie_decided_by"] = str(decided_by)

    def tie_resolution(self, tie_id: str) -> dict:
        tie_id = str(tie_id)
        fixtures = sorted(
            [
                fixture for fixture in self.fixtures.values()
                if str(fixture.get("tie_id")) == tie_id
            ],
            key=lambda fixture: (int(fixture.get("leg", 1)), fixture["id"]),
        )
        if not fixtures:
            raise KeyError(tie_id)
        stage_ids = {fixture["stage_id"] for fixture in fixtures}
        if len(stage_ids) != 1:
            raise ValueError("all legs in a tie must belong to the same stage")
        stage = self.stages[next(iter(stage_ids))]
        teams = []
        for fixture in fixtures:
            for team in (fixture["home"], fixture["away"]):
                if team not in teams:
                    teams.append(team)
        if len(teams) != 2:
            raise ValueError("a knockout tie must contain exactly two teams")

        complete = all(fixture["status"] == "final" for fixture in fixtures)
        aggregate = self.aggregate(tie_id)
        winner = None
        decided_by = None
        if complete:
            a, b = teams
            ga = int(aggregate["goals"].get(a, 0))
            gb = int(aggregate["goals"].get(b, 0))
            if ga != gb:
                winner = a if ga > gb else b
                decided_by = "aggregate"
            elif bool(stage.get("away_goals")):
                aa = int(aggregate["away_goals"].get(a, 0))
                ab = int(aggregate["away_goals"].get(b, 0))
                if aa != ab:
                    winner = a if aa > ab else b
                    decided_by = "away_goals"

            if winner is None:
                for fixture in reversed(fixtures):
                    metadata = fixture.get("metadata") or {}
                    explicit = metadata.get("tie_winner")
                    if explicit in teams:
                        winner = str(explicit)
                        decided_by = str(metadata.get("tie_decided_by", "explicit_decider"))
                        break

            # A single-leg knockout may legitimately expose an explicit winner
            # (for example after penalties) directly on the fixture.
            if winner is None and len(fixtures) == 1:
                explicit = fixtures[0].get("winner")
                if explicit in teams:
                    winner = str(explicit)
                    decided_by = "fixture_winner"
                elif fixtures[0]["score"][0] != fixtures[0]["score"][1]:
                    winner = (
                        fixtures[0]["home"]
                        if fixtures[0]["score"][0] > fixtures[0]["score"][1]
                        else fixtures[0]["away"]
                    )
                    decided_by = "score"

        return {
            "tie_id": tie_id,
            "stage_id": next(iter(stage_ids)),
            "stage_kind": stage["kind"],
            "two_legged": bool(stage.get("two_legged")),
            "complete": complete,
            "teams": list(teams),
            "aggregate": deepcopy(aggregate),
            "winner": winner,
            "decided_by": decided_by,
            "unresolved_after_rules": bool(complete and winner is None),
        }

    def _stage_tie_resolutions(self, stage_id: str) -> list[dict]:
        tie_ids = []
        for fixture in self.fixtures.values():
            if fixture["stage_id"] != stage_id or not fixture.get("tie_id"):
                continue
            tie_id = str(fixture["tie_id"])
            if tie_id not in tie_ids:
                tie_ids.append(tie_id)
        return [self.tie_resolution(tie_id) for tie_id in tie_ids]

    def _knockout_stage_winners(self, stage_id: str) -> list[str]:
        stage = self.stages[stage_id]
        fixtures = [fixture for fixture in self.fixtures.values() if fixture["stage_id"] == stage_id]
        if not fixtures:
            return []
        if stage.get("two_legged"):
            return [
                str(row["winner"])
                for row in self._stage_tie_resolutions(stage_id)
                if row.get("complete") and row.get("winner")
            ]
        winners = []
        for fixture in fixtures:
            if fixture["status"] != "final":
                continue
            winner = fixture.get("winner")
            if winner is None and fixture["score"][0] != fixture["score"][1]:
                winner = fixture["home"] if fixture["score"][0] > fixture["score"][1] else fixture["away"]
            if winner:
                winners.append(str(winner))
        return winners

    def competition_status(self) -> dict:
        champion = None
        third_place = None
        promoted: list[str] = []
        relegated: list[str] = []
        unresolved_ties: list[str] = []

        for stage_id, stage in self.stages.items():
            if stage["kind"] in {"league", "group"} and self._stage_complete(stage_id):
                rows = self.standings(stage_id)
                if stage["award_champion"] and stage.get("champion_position"):
                    position = int(stage["champion_position"])
                    if 1 <= position <= len(rows):
                        champion = rows[position - 1]["team"]
                for position in stage["promotion_positions"]:
                    if 1 <= position <= len(rows):
                        promoted.append(rows[position - 1]["team"])
                for position in stage["relegation_positions"]:
                    if 1 <= position <= len(rows):
                        relegated.append(rows[position - 1]["team"])
                continue

            if stage["kind"] not in {"playoff", "knockout", "third_place", "final"}:
                continue

            resolutions = self._stage_tie_resolutions(stage_id) if stage.get("two_legged") else []
            for row in resolutions:
                if row.get("unresolved_after_rules"):
                    unresolved_ties.append(str(row["tie_id"]))
            winners = self._knockout_stage_winners(stage_id)

            if stage["kind"] == "final" and len(winners) == 1:
                champion = winners[0]
            elif stage["kind"] == "third_place" and len(winners) == 1:
                third_place = winners[0]

            if stage.get("promotion_on_win"):
                promoted.extend(winners)

        return {
            "competition_id": self.competition_id,
            "champion": champion,
            "third_place": third_place,
            "promoted": sorted(set(promoted)),
            "relegated": sorted(set(relegated)),
            "unresolved_ties": sorted(set(unresolved_ties)),
        }


__all__ = ["TournamentStateV13", "TournamentMatchBridgeV13"]
