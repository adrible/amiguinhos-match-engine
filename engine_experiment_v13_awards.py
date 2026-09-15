from __future__ import annotations

"""v1.3 match awards derived exclusively from event-derived ratings."""

from engine_experiment_v13_leadership import MatchEngineV13Leadership


class MatchEngineV13Awards(MatchEngineV13Leadership):
    def match_awards_diagnostic(self, top_n: int = 3) -> dict:
        top_n = max(1, int(top_n))
        rows = []
        ratings = self.match_ratings()
        for team in (0, 1):
            for row in ratings[str(team)]:
                enriched = dict(row)
                enriched["team_name"] = self.teams[team].team.name
                rows.append(enriched)
        if not self.state.event_log:
            return {
                "provisional": not self.state.ended,
                "man_of_the_match": None,
                "top_performers": [],
                "basis": "event_derived_match_rating",
            }
        rows.sort(
            key=lambda row: (
                -float(row["rating"]),
                -float(row["raw_impact"]),
                -int(row["rated_events"]),
                str(row["player"]),
            )
        )
        return {
            "provisional": not self.state.ended,
            "man_of_the_match": dict(rows[0]) if rows else None,
            "top_performers": [dict(row) for row in rows[:top_n]],
            "basis": "event_derived_match_rating",
        }

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["awards"] = self.match_awards_diagnostic()
        return data


MatchEngine = MatchEngineV13Awards

__all__ = ["MatchEngineV13Awards", "MatchEngine"]
