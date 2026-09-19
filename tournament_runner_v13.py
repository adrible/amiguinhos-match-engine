from __future__ import annotations

"""Live tournament-aware facade around the strict v1.3 match runner.

The wrapper synchronizes only the current match and explicitly supplied live
updates from simultaneous fixtures. It does not simulate other matches and it
never advances the active match except through the ordinary live runner.
"""

import json

from engine import Event, EventType
from competition_state_v13 import TournamentStateV13
from runner_v13 import MatchSessionV13
from tournament_state_v13 import TournamentMatchBridgeV13


class TournamentMatchSessionV13:
    def __init__(
        self,
        tournament: TournamentStateV13,
        fixture_id: str,
        *,
        seed: int = 0,
        auto_adapt: bool = True,
    ) -> None:
        self.tournament = tournament
        self.fixture_id = str(fixture_id)
        fixture = tournament.fixture(self.fixture_id)
        if fixture["status"] == "final":
            raise ValueError("Cannot start a match session for a final fixture")
        stage = tournament.stages[fixture["stage_id"]]
        decisive_leg = not bool(stage.get("two_legged")) or int(fixture.get("leg", 1)) >= 2
        allow_extra_time = bool(stage.get("allow_extra_time")) and decisive_leg
        self.pre_match_conditions = tournament.pre_match_conditions(self.fixture_id)
        self.session = MatchSessionV13.from_fixture(
            fixture["home"],
            fixture["away"],
            seed=int(seed),
            auto_adapt=bool(auto_adapt),
            allow_extra_time=allow_extra_time,
        )
        self.bridge = TournamentMatchBridgeV13(tournament, self.fixture_id)
        # 0:00 is now a known live state; no match beat is simulated here.
        self.bridge.sync_live_engine(self.session.engine)

    @property
    def engine(self):
        return self.session.engine

    @property
    def pristine(self) -> bool:
        return self.session.pristine

    def _winner_key_from_event(self, event: Event) -> tuple[str | None, str | None]:
        fixture = self.tournament.fixture(self.fixture_id)
        winner_side = event.data.get("winner") if isinstance(event.data, dict) else None
        if winner_side in (0, 1):
            return (fixture["home"] if int(winner_side) == 0 else fixture["away"], "penalties" if event.data.get("shootout") else "match")
        home_goals, away_goals = self.engine.score
        if home_goals > away_goals:
            return fixture["home"], "match"
        if away_goals > home_goals:
            return fixture["away"], "match"
        return None, None

    def _finalize_live_fixture(self, event: Event) -> None:
        fixture = self.tournament.fixture(self.fixture_id)
        winner, decided_by = self._winner_key_from_event(event)
        self.bridge.finalize_from_engine(self.engine, winner=winner)
        stage = self.tournament.stages[fixture["stage_id"]]
        tie_id = fixture.get("tie_id")
        if tie_id and bool(stage.get("two_legged")):
            resolution = self.tournament.tie_resolution(str(tie_id))
            if resolution.get("unresolved_after_rules") and winner is not None and decided_by == "penalties":
                self.tournament.record_tie_winner(str(tie_id), winner, decided_by="penalties")
                self.bridge.attach(self.engine)

    def press_p(self, *, min_relevance: int | None = None) -> Event:
        # Refresh competition context from the score/minute known before this
        # public advance. Goals are relevant events, so aggregate context is
        # refreshed before the next press can cross a knockout boundary.
        if self.tournament.fixture(self.fixture_id)["status"] != "final":
            self.bridge.sync_live_engine(self.engine)
        event = self.session.press_p(min_relevance=min_relevance)
        if event.type == EventType.MATCH_END:
            self._finalize_live_fixture(event)
        else:
            self.bridge.sync_live_engine(self.engine)
        return event

    def step_once(self) -> Event:
        if self.tournament.fixture(self.fixture_id)["status"] != "final":
            self.bridge.sync_live_engine(self.engine)
        event = self.session.step_once()
        if event.type == EventType.MATCH_END:
            self._finalize_live_fixture(event)
        else:
            self.bridge.sync_live_engine(self.engine)
        return event

    def update_simultaneous(
        self,
        fixture_id: str,
        home_goals: int,
        away_goals: int,
        minute: float,
    ) -> dict:
        return self.bridge.apply_simultaneous_update(
            self.engine,
            fixture_id,
            home_goals,
            away_goals,
            minute,
        )

    def finalize_simultaneous(
        self,
        fixture_id: str,
        home_goals: int,
        away_goals: int,
        *,
        winner: str | None = None,
    ) -> dict:
        if str(fixture_id) == self.fixture_id:
            raise ValueError("The active fixture is finalized by the live match")
        self.tournament.finalize_fixture(
            fixture_id,
            home_goals,
            away_goals,
            winner=winner,
        )
        return self.bridge.attach(self.engine)

    def snapshot(self) -> dict:
        return {
            "match": self.session.snapshot(),
            "competition": self.tournament.context_for_fixture(self.fixture_id),
            "pre_match_conditions": self.pre_match_conditions,
            "competition_status": self.tournament.competition_status(),
        }

    def export_state(self) -> dict:
        return {
            "version": 1,
            "fixture_id": self.fixture_id,
            "pre_match_conditions": self.pre_match_conditions,
            "match_json": self.session.export_json(),
            "tournament": self.tournament.to_dict(),
        }

    def export_json(self) -> str:
        return json.dumps(self.export_state(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_state(cls, data: dict) -> "TournamentMatchSessionV13":
        obj = cls.__new__(cls)
        obj.fixture_id = str(data["fixture_id"])
        obj.tournament = TournamentStateV13.from_dict(data["tournament"])
        obj.session = MatchSessionV13.from_json(data["match_json"])
        obj.bridge = TournamentMatchBridgeV13(obj.tournament, obj.fixture_id)
        obj.pre_match_conditions = data.get(
            "pre_match_conditions",
            obj.tournament.pre_match_conditions(obj.fixture_id),
        )
        if obj.tournament.fixture(obj.fixture_id)["status"] != "final":
            obj.bridge.sync_live_engine(obj.session.engine)
        else:
            obj.bridge.attach(obj.session.engine)
        return obj

    @classmethod
    def from_json(cls, payload: str) -> "TournamentMatchSessionV13":
        return cls.from_state(json.loads(payload))


__all__ = ["TournamentMatchSessionV13"]
