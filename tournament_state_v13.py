from __future__ import annotations

"""Competition-state model for the v1.3 candidate.

The match engine should know only information that is available at the current
competition instant.  This module owns standings, two-leg aggregates, live
simultaneous fixtures, promotion/relegation/title stakes and pre-match outcome
conditions.  It never simulates a future fixture or supplies future scores.
"""

from copy import deepcopy
from typing import Any, Iterable


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _positions(raw: Any) -> list[int]:
    if raw is None:
        return []
    values = raw if isinstance(raw, (list, tuple, set)) else [raw]
    result = sorted({int(value) for value in values if int(value) > 0})
    return result


class TournamentStateV13:
    VALID_STAGE_KINDS = {
        "league",
        "group",
        "playoff",
        "knockout",
        "third_place",
        "final",
    }
    VALID_FIXTURE_STATUS = {"scheduled", "live", "final"}
    VALID_TIEBREAKERS = {"points", "goal_difference", "goals_for", "wins", "team"}

    def __init__(
        self,
        *,
        competition_id: str,
        teams: Iterable[str],
        stages: dict[str, dict],
        fixtures: Iterable[dict],
    ) -> None:
        self.competition_id = str(competition_id)
        self.teams = tuple(dict.fromkeys(str(team) for team in teams))
        if len(self.teams) < 2:
            raise ValueError("A competition needs at least two teams")
        self.stages = {
            str(stage_id): self._normalise_stage(str(stage_id), raw)
            for stage_id, raw in stages.items()
        }
        self.fixtures: dict[str, dict] = {}
        for raw in fixtures:
            fixture = self._normalise_fixture(raw)
            fixture_id = fixture["id"]
            if fixture_id in self.fixtures:
                raise ValueError(f"Duplicate fixture id: {fixture_id}")
            self.fixtures[fixture_id] = fixture

    def _normalise_stage(self, stage_id: str, raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise TypeError("stage definition must be a mapping")
        kind = str(raw.get("kind", "league")).strip().lower()
        if kind not in self.VALID_STAGE_KINDS:
            raise ValueError(f"Unsupported stage kind: {kind}")
        tiebreakers = [str(item) for item in raw.get(
            "tiebreakers", ["points", "goal_difference", "goals_for", "wins", "team"]
        )]
        if any(item not in self.VALID_TIEBREAKERS for item in tiebreakers):
            raise ValueError(f"Unsupported tiebreaker in {tiebreakers}")
        points = raw.get("points", {})
        return {
            "id": stage_id,
            "kind": kind,
            "name": str(raw.get("name", stage_id)),
            "group": raw.get("group"),
            "groups": deepcopy(raw.get("groups", {})),
            "qualify_positions": _positions(raw.get("qualify_positions")),
            "promotion_positions": _positions(raw.get("promotion_positions")),
            "relegation_positions": _positions(raw.get("relegation_positions")),
            "champion_position": int(raw.get("champion_position", 1)) if raw.get("champion_position", 1) is not None else None,
            "award_champion": bool(raw.get("award_champion", kind == "league")),
            "promotion_on_win": bool(raw.get("promotion_on_win", False)),
            "two_legged": bool(raw.get("two_legged", False)),
            "away_goals": bool(raw.get("away_goals", False)),
            "allow_extra_time": bool(raw.get("allow_extra_time", kind in {"playoff", "knockout", "final", "third_place"})),
            "points": {
                "win": int(points.get("win", 3)),
                "draw": int(points.get("draw", 1)),
                "loss": int(points.get("loss", 0)),
            },
            "tiebreakers": tiebreakers,
            "metadata": deepcopy(raw.get("metadata", {})),
        }

    def _normalise_fixture(self, raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise TypeError("fixture must be a mapping")
        fixture_id = str(raw["id"])
        stage_id = str(raw["stage_id"])
        if stage_id not in self.stages:
            raise KeyError(f"Unknown stage: {stage_id}")
        home = str(raw["home"])
        away = str(raw["away"])
        if home == away:
            raise ValueError("A team cannot play itself")
        if home not in self.teams or away not in self.teams:
            raise KeyError(f"Fixture uses unknown team: {home} v {away}")
        status = str(raw.get("status", "scheduled")).lower().strip()
        if status not in self.VALID_FIXTURE_STATUS:
            raise ValueError(f"Unsupported fixture status: {status}")
        score = raw.get("score", [0, 0])
        if not isinstance(score, (list, tuple)) or len(score) != 2:
            raise ValueError("fixture score must be [home_goals, away_goals]")
        return {
            "id": fixture_id,
            "stage_id": stage_id,
            "group": raw.get("group"),
            "home": home,
            "away": away,
            "status": status,
            "minute": max(0.0, float(raw.get("minute", 0.0))),
            "score": [max(0, int(score[0])), max(0, int(score[1]))],
            "winner": raw.get("winner"),
            "leg": max(1, int(raw.get("leg", 1))),
            "tie_id": raw.get("tie_id"),
            "simultaneous_key": raw.get("simultaneous_key"),
            "pre_match": deepcopy(raw.get("pre_match", {})),
            "metadata": deepcopy(raw.get("metadata", {})),
        }

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "competition_id": self.competition_id,
            "teams": list(self.teams),
            "stages": deepcopy(self.stages),
            "fixtures": [deepcopy(self.fixtures[key]) for key in sorted(self.fixtures)],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TournamentStateV13":
        return cls(
            competition_id=data["competition_id"],
            teams=data["teams"],
            stages=data["stages"],
            fixtures=data["fixtures"],
        )

    def fixture(self, fixture_id: str) -> dict:
        return self.fixtures[str(fixture_id)]

    def update_live(self, fixture_id: str, home_goals: int, away_goals: int, minute: float) -> None:
        fixture = self.fixture(fixture_id)
        if fixture["status"] == "final":
            raise ValueError("Cannot update a final fixture")
        fixture["status"] = "live"
        fixture["score"] = [max(0, int(home_goals)), max(0, int(away_goals))]
        fixture["minute"] = max(0.0, float(minute))
        fixture["winner"] = None

    def finalize_fixture(
        self,
        fixture_id: str,
        home_goals: int,
        away_goals: int,
        *,
        winner: str | None = None,
    ) -> None:
        fixture = self.fixture(fixture_id)
        home_goals = max(0, int(home_goals))
        away_goals = max(0, int(away_goals))
        if winner is not None and winner not in {fixture["home"], fixture["away"]}:
            raise ValueError("winner must be one of the fixture teams")
        if winner is None and home_goals != away_goals:
            winner = fixture["home"] if home_goals > away_goals else fixture["away"]
        fixture["status"] = "final"
        fixture["score"] = [home_goals, away_goals]
        fixture["minute"] = max(90.0, float(fixture.get("minute", 0.0)))
        fixture["winner"] = winner

    def _fixture_score(self, fixture: dict, overrides: dict[str, list[int]] | None = None):
        if overrides and fixture["id"] in overrides:
            score = overrides[fixture["id"]]
            return int(score[0]), int(score[1])
        if fixture["status"] not in {"live", "final"}:
            return None
        return int(fixture["score"][0]), int(fixture["score"][1])

    def _stage_teams(self, stage_id: str, group: str | None = None) -> list[str]:
        stage = self.stages[stage_id]
        if group is not None and isinstance(stage.get("groups"), dict) and group in stage["groups"]:
            return [str(team) for team in stage["groups"][group]]
        teams: list[str] = []
        for fixture in self.fixtures.values():
            if fixture["stage_id"] != stage_id:
                continue
            if group is not None and fixture.get("group") != group:
                continue
            for team in (fixture["home"], fixture["away"]):
                if team not in teams:
                    teams.append(team)
        return teams

    def standings(
        self,
        stage_id: str,
        *,
        group: str | None = None,
        overrides: dict[str, list[int]] | None = None,
    ) -> list[dict]:
        stage_id = str(stage_id)
        stage = self.stages[stage_id]
        if stage["kind"] not in {"league", "group"}:
            raise ValueError("Standings are only defined for league/group stages")
        teams = self._stage_teams(stage_id, group)
        rows = {
            team: {
                "team": team,
                "played": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "goals_for": 0,
                "goals_against": 0,
                "goal_difference": 0,
                "points": 0,
                "remaining": 0,
                "provisional_live_matches": 0,
            }
            for team in teams
        }
        point_rules = stage["points"]
        for fixture in self.fixtures.values():
            if fixture["stage_id"] != stage_id:
                continue
            if group is not None and fixture.get("group") != group:
                continue
            if fixture["home"] not in rows or fixture["away"] not in rows:
                continue
            score = self._fixture_score(fixture, overrides)
            overridden = bool(overrides and fixture["id"] in overrides)
            if score is None:
                rows[fixture["home"]]["remaining"] += 1
                rows[fixture["away"]]["remaining"] += 1
                continue
            hg, ag = score
            home = rows[fixture["home"]]
            away = rows[fixture["away"]]
            for row in (home, away):
                row["played"] += 1
                if fixture["status"] == "live" and not overridden:
                    row["provisional_live_matches"] += 1
            home["goals_for"] += hg
            home["goals_against"] += ag
            away["goals_for"] += ag
            away["goals_against"] += hg
            if hg > ag:
                home["wins"] += 1
                away["losses"] += 1
                home["points"] += point_rules["win"]
                away["points"] += point_rules["loss"]
            elif hg < ag:
                away["wins"] += 1
                home["losses"] += 1
                away["points"] += point_rules["win"]
                home["points"] += point_rules["loss"]
            else:
                home["draws"] += 1
                away["draws"] += 1
                home["points"] += point_rules["draw"]
                away["points"] += point_rules["draw"]
        for row in rows.values():
            row["goal_difference"] = row["goals_for"] - row["goals_against"]
            row["min_points"] = row["points"]
            row["max_points"] = row["points"] + point_rules["win"] * row["remaining"]

        def sort_key(row: dict):
            values = []
            for rule in stage["tiebreakers"]:
                if rule == "team":
                    values.append(str(row["team"]))
                else:
                    values.append(-int(row[rule]))
            return tuple(values)

        ordered = sorted(rows.values(), key=sort_key)
        for index, row in enumerate(ordered, start=1):
            row["position"] = index
        return ordered

    @staticmethod
    def _row(rows: list[dict], team: str) -> dict:
        for row in rows:
            if row["team"] == team:
                return row
        raise KeyError(team)

    @staticmethod
    def _top_n_math(rows: list[dict], team: str, top_n: int) -> dict:
        if top_n <= 0:
            return {"secured": False, "eliminated": False}
        row = TournamentStateV13._row(rows, team)
        others = [item for item in rows if item["team"] != team]
        can_reach_or_pass = sum(1 for item in others if int(item["max_points"]) >= int(row["min_points"]))
        definitely_ahead = sum(1 for item in others if int(item["min_points"]) > int(row["max_points"]))
        return {
            "secured": can_reach_or_pass <= top_n - 1,
            "eliminated": definitely_ahead >= top_n,
        }

    def simultaneous_visible(self, fixture_id: str) -> list[dict]:
        fixture = self.fixture(fixture_id)
        key = fixture.get("simultaneous_key")
        if not key:
            return []
        visible = []
        for other in self.fixtures.values():
            if other["id"] == fixture["id"] or other.get("simultaneous_key") != key:
                continue
            if other["status"] not in {"live", "final"}:
                continue
            visible.append({
                "fixture_id": other["id"],
                "status": other["status"],
                "minute": float(other["minute"]),
                "home": other["home"],
                "away": other["away"],
                "score": list(other["score"]),
            })
        return sorted(visible, key=lambda item: item["fixture_id"])

    def aggregate(self, tie_id: str) -> dict:
        tie_id = str(tie_id)
        fixtures = [f for f in self.fixtures.values() if str(f.get("tie_id")) == tie_id]
        if not fixtures:
            raise KeyError(tie_id)
        teams: list[str] = []
        goals: dict[str, int] = {}
        away_goals: dict[str, int] = {}
        for fixture in fixtures:
            for team in (fixture["home"], fixture["away"]):
                if team not in teams:
                    teams.append(team)
                    goals[team] = 0
                    away_goals[team] = 0
            score = self._fixture_score(fixture)
            if score is None:
                continue
            hg, ag = score
            goals[fixture["home"]] += hg
            goals[fixture["away"]] += ag
            away_goals[fixture["away"]] += ag
        return {
            "tie_id": tie_id,
            "teams": teams,
            "goals": goals,
            "away_goals": away_goals,
            "fixtures": [f["id"] for f in sorted(fixtures, key=lambda f: (f["leg"], f["id"]))],
        }

    def _league_context(self, fixture: dict, team: str) -> dict:
        stage = self.stages[fixture["stage_id"]]
        rows = self.standings(fixture["stage_id"], group=fixture.get("group"))
        row = self._row(rows, team)
        team_count = len(rows)
        qualifying = stage["qualify_positions"]
        promotion = stage["promotion_positions"]
        relegation = stage["relegation_positions"]
        qualify_top = max(qualifying) if qualifying else 0
        promotion_top = max(promotion) if promotion else 0
        safe_top = team_count - len(relegation) if relegation else 0
        qualification_math = self._top_n_math(rows, team, qualify_top) if qualify_top else {"secured": False, "eliminated": False}
        promotion_math = self._top_n_math(rows, team, promotion_top) if promotion_top else {"secured": False, "eliminated": False}
        safety_math = self._top_n_math(rows, team, safe_top) if safe_top else {"secured": False, "eliminated": False}
        champion_math = self._top_n_math(rows, team, 1) if stage.get("champion_position") == 1 else {"secured": False, "eliminated": False}

        score = self._fixture_score(fixture)
        score_diff = 0
        if score is not None:
            hg, ag = score
            score_diff = (hg - ag) if team == fixture["home"] else (ag - hg)
        minute = float(fixture["minute"]) if fixture["status"] == "live" else 0.0
        time_pressure = _clamp01((minute - 45.0) / 45.0)

        outside_target = False
        if qualify_top:
            outside_target = int(row["position"]) > qualify_top
        if promotion_top:
            outside_target = outside_target or int(row["position"]) > promotion_top
        in_relegation = bool(relegation and int(row["position"]) in relegation)

        base_need = 0.0
        if outside_target:
            base_need = max(base_need, 0.78)
        if in_relegation:
            base_need = max(base_need, 0.86)
        if score_diff < 0 and (outside_target or in_relegation):
            base_need = min(1.0, base_need + 0.12)
        elif score_diff > 0:
            base_need *= 0.42
        need_goal = _clamp01(base_need * (0.42 + 0.58 * time_pressure)) if fixture["status"] == "live" else 0.0

        objective_held = bool(
            (qualify_top and int(row["position"]) <= qualify_top)
            or (promotion_top and int(row["position"]) <= promotion_top)
            or (relegation and not in_relegation)
        )
        protect = 0.0
        if fixture["status"] == "live" and objective_held and score_diff >= 0:
            protect = _clamp01((0.18 + 0.52 * time_pressure) * (1.0 if score_diff > 0 else 0.55))

        return {
            "team": team,
            "position": int(row["position"]),
            "points": int(row["points"]),
            "goal_difference": int(row["goal_difference"]),
            "remaining": int(row["remaining"]),
            "min_points": int(row["min_points"]),
            "max_points": int(row["max_points"]),
            "in_qualification_positions": bool(qualifying and int(row["position"]) in qualifying),
            "qualification_secured": bool(qualification_math["secured"]),
            "qualification_eliminated": bool(qualification_math["eliminated"]),
            "in_promotion_positions": bool(promotion and int(row["position"]) in promotion),
            "promotion_secured": bool(promotion_math["secured"]),
            "promotion_eliminated": bool(promotion_math["eliminated"]),
            "in_relegation_positions": in_relegation,
            "relegation_safety_secured": bool(safety_math["secured"]),
            "relegation_confirmed": bool(safety_math["eliminated"]),
            "title_secured": bool(champion_math["secured"]),
            "title_eliminated": bool(champion_math["eliminated"]),
            "need_goal": round(need_goal, 5),
            "protect_result": round(protect, 5),
            "need_win": bool((outside_target or in_relegation) and score_diff <= 0),
            "escape_relegation": bool(in_relegation and not safety_math["eliminated"]),
        }

    def _knockout_context(self, fixture: dict, team: str) -> dict:
        stage = self.stages[fixture["stage_id"]]
        score = self._fixture_score(fixture)
        score_diff = 0
        if score is not None:
            hg, ag = score
            score_diff = (hg - ag) if team == fixture["home"] else (ag - hg)
        minute = float(fixture["minute"]) if fixture["status"] == "live" else 0.0
        time_pressure = _clamp01((minute - 45.0) / 45.0)
        aggregate_diff = score_diff
        aggregate_data = None
        if fixture.get("tie_id"):
            aggregate_data = self.aggregate(str(fixture["tie_id"]))
            opponent = fixture["away"] if team == fixture["home"] else fixture["home"]
            aggregate_diff = int(aggregate_data["goals"].get(team, 0)) - int(aggregate_data["goals"].get(opponent, 0))
            if aggregate_diff == 0 and stage["away_goals"]:
                aggregate_diff = int(aggregate_data["away_goals"].get(team, 0)) - int(aggregate_data["away_goals"].get(opponent, 0))

        decisive_leg = not stage["two_legged"] or int(fixture["leg"]) >= 2
        need_goal = 0.0
        protect = 0.0
        if fixture["status"] == "live":
            if aggregate_diff < 0:
                urgency_base = 0.90 if decisive_leg else 0.45
                need_goal = _clamp01(urgency_base * (0.48 + 0.52 * time_pressure))
            elif aggregate_diff > 0:
                protect = _clamp01((0.18 + 0.48 * time_pressure) * (1.0 if decisive_leg else 0.62))
            elif decisive_leg and minute >= 100.0:
                need_goal = _clamp01(0.18 + 0.24 * _clamp01((minute - 100.0) / 20.0))

        kind = stage["kind"]
        return {
            "team": team,
            "tie_id": fixture.get("tie_id"),
            "leg": int(fixture["leg"]),
            "two_legged": bool(stage["two_legged"]),
            "decisive_leg": decisive_leg,
            "away_goals_enabled": bool(stage["away_goals"]),
            "aggregate": aggregate_data,
            "aggregate_diff": int(aggregate_diff),
            "need_goal": round(need_goal, 5),
            "protect_result": round(protect, 5),
            "need_win": bool(decisive_leg and aggregate_diff < 0),
            "promotion_on_win": bool(stage["promotion_on_win"]),
            "championship_final": kind == "final",
            "third_place_match": kind == "third_place",
            "knockout_stage": kind in {"playoff", "knockout", "final", "third_place"},
        }

    def _outcome_summary(self, fixture: dict, team: str, score: list[int]) -> dict:
        stage = self.stages[fixture["stage_id"]]
        if stage["kind"] not in {"league", "group"}:
            return {}
        rows = self.standings(
            fixture["stage_id"],
            group=fixture.get("group"),
            overrides={fixture["id"]: score},
        )
        row = self._row(rows, team)
        qualifying = stage["qualify_positions"]
        promotion = stage["promotion_positions"]
        relegation = stage["relegation_positions"]
        qualify_top = max(qualifying) if qualifying else 0
        promotion_top = max(promotion) if promotion else 0
        safe_top = len(rows) - len(relegation) if relegation else 0
        return {
            "position": int(row["position"]),
            "points": int(row["points"]),
            "in_qualification_positions": bool(qualifying and int(row["position"]) in qualifying),
            "qualification_secured": bool(self._top_n_math(rows, team, qualify_top)["secured"]) if qualify_top else False,
            "in_promotion_positions": bool(promotion and int(row["position"]) in promotion),
            "promotion_secured": bool(self._top_n_math(rows, team, promotion_top)["secured"]) if promotion_top else False,
            "in_relegation_positions": bool(relegation and int(row["position"]) in relegation),
            "relegation_safety_secured": bool(self._top_n_math(rows, team, safe_top)["secured"]) if safe_top else False,
            "title_secured": bool(self._top_n_math(rows, team, 1)["secured"]) if stage.get("champion_position") == 1 else False,
        }

    def pre_match_conditions(self, fixture_id: str) -> dict:
        fixture = self.fixture(fixture_id)
        stage = self.stages[fixture["stage_id"]]
        result = {
            "fixture_id": fixture["id"],
            "competition_id": self.competition_id,
            "stage_id": fixture["stage_id"],
            "stage_kind": stage["kind"],
            "home": fixture["home"],
            "away": fixture["away"],
            "leg": int(fixture["leg"]),
            "tie_id": fixture.get("tie_id"),
            "pre_match": deepcopy(fixture.get("pre_match", {})),
            "simultaneous_known": self.simultaneous_visible(fixture["id"]),
            "team_conditions": {},
        }
        if stage["kind"] in {"league", "group"}:
            for side, team in ((0, fixture["home"]), (1, fixture["away"])):
                scores = {
                    "win": [1, 0] if side == 0 else [0, 1],
                    "draw": [0, 0],
                    "loss": [0, 1] if side == 0 else [1, 0],
                }
                result["team_conditions"][str(side)] = {
                    outcome: self._outcome_summary(fixture, team, score)
                    for outcome, score in scores.items()
                }
        else:
            for side, team in ((0, fixture["home"]), (1, fixture["away"])):
                context = self._knockout_context(fixture, team)
                result["team_conditions"][str(side)] = {
                    "aggregate_before_match": context.get("aggregate"),
                    "promotion_on_win": context.get("promotion_on_win", False),
                    "championship_final": context.get("championship_final", False),
                    "third_place_match": context.get("third_place_match", False),
                }
        return result

    def context_for_fixture(self, fixture_id: str) -> dict:
        fixture = self.fixture(fixture_id)
        stage = self.stages[fixture["stage_id"]]
        teams_context: dict[str, dict] = {}
        for side, team in ((0, fixture["home"]), (1, fixture["away"])):
            if stage["kind"] in {"league", "group"}:
                context = self._league_context(fixture, team)
            else:
                context = self._knockout_context(fixture, team)
            context["side"] = side
            teams_context[str(side)] = context
        return {
            "version": 1,
            "competition_id": self.competition_id,
            "fixture_id": fixture["id"],
            "stage_id": fixture["stage_id"],
            "stage_name": stage["name"],
            "stage_kind": stage["kind"],
            "group": fixture.get("group"),
            "home_team": fixture["home"],
            "away_team": fixture["away"],
            "fixture_status": fixture["status"],
            "fixture_minute": float(fixture["minute"]),
            "fixture_score": list(fixture["score"]) if fixture["status"] in {"live", "final"} else None,
            "leg": int(fixture["leg"]),
            "tie_id": fixture.get("tie_id"),
            "simultaneous": self.simultaneous_visible(fixture["id"]),
            "pre_match_conditions": self.pre_match_conditions(fixture["id"]),
            "team_context": teams_context,
            "knowledge_policy": "only_final_or_currently_live_results_are_visible",
        }

    def _stage_complete(self, stage_id: str) -> bool:
        fixtures = [f for f in self.fixtures.values() if f["stage_id"] == stage_id]
        return bool(fixtures) and all(f["status"] == "final" for f in fixtures)

    def competition_status(self) -> dict:
        champion = None
        third_place = None
        promoted: list[str] = []
        relegated: list[str] = []

        for stage_id, stage in self.stages.items():
            stage_fixtures = [f for f in self.fixtures.values() if f["stage_id"] == stage_id]
            if stage["kind"] == "final":
                finals = [f for f in stage_fixtures if f["status"] == "final"]
                if finals:
                    fixture = sorted(finals, key=lambda f: f["id"])[-1]
                    champion = fixture.get("winner")
                    if champion is None and fixture["score"][0] != fixture["score"][1]:
                        champion = fixture["home"] if fixture["score"][0] > fixture["score"][1] else fixture["away"]
            elif stage["kind"] == "third_place":
                finals = [f for f in stage_fixtures if f["status"] == "final"]
                if finals:
                    fixture = sorted(finals, key=lambda f: f["id"])[-1]
                    third_place = fixture.get("winner")
                    if third_place is None and fixture["score"][0] != fixture["score"][1]:
                        third_place = fixture["home"] if fixture["score"][0] > fixture["score"][1] else fixture["away"]

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

            if stage["promotion_on_win"]:
                for fixture in stage_fixtures:
                    if fixture["status"] == "final" and fixture.get("winner"):
                        promoted.append(str(fixture["winner"]))

        return {
            "competition_id": self.competition_id,
            "champion": champion,
            "third_place": third_place,
            "promoted": sorted(set(promoted)),
            "relegated": sorted(set(relegated)),
        }


class TournamentMatchBridgeV13:
    """Keeps one live match synchronized with the tournament snapshot."""

    def __init__(self, tournament: TournamentStateV13, fixture_id: str):
        self.tournament = tournament
        self.fixture_id = str(fixture_id)
        self.tournament.fixture(self.fixture_id)

    def attach(self, engine) -> dict:
        context = self.tournament.context_for_fixture(self.fixture_id)
        setter = getattr(engine, "set_tournament_context", None)
        if not callable(setter):
            raise TypeError("engine does not support tournament context")
        setter(context)
        return context

    def sync_live_engine(self, engine) -> dict:
        home, away = engine.score
        self.tournament.update_live(self.fixture_id, home, away, engine.minute)
        return self.attach(engine)

    def apply_simultaneous_update(
        self,
        engine,
        other_fixture_id: str,
        home_goals: int,
        away_goals: int,
        minute: float,
    ) -> dict:
        if str(other_fixture_id) == self.fixture_id:
            raise ValueError("Use sync_live_engine for the active fixture")
        self.tournament.update_live(other_fixture_id, home_goals, away_goals, minute)
        return self.attach(engine)

    def finalize_from_engine(self, engine, *, winner: str | None = None) -> dict:
        home, away = engine.score
        self.tournament.finalize_fixture(self.fixture_id, home, away, winner=winner)
        return self.attach(engine)


__all__ = ["TournamentStateV13", "TournamentMatchBridgeV13"]
