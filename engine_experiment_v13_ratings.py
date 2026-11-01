from __future__ import annotations

"""v1.3 event-derived individual match ratings.

Ratings are reconstructed from the public event log. No OVR-based bonus is
applied: a strong player who has a quiet or poor match is not protected by his
reputation. Because the calculation is event-derived and RNG-free, save/load
reproduces the same rating without additional persistent state.
"""

from collections import defaultdict

from engine import EventType, clamp
from engine_experiment_v13_instructions import MatchEngineV13IndividualInstructions


class MatchEngineV13Ratings(MatchEngineV13IndividualInstructions):
    BASE_MATCH_RATING = 6.0

    @staticmethod
    def _rating_delta(store: dict, player: str | None, amount: float, reason: str) -> None:
        if not player:
            return
        row = store.setdefault(str(player), {"impact": 0.0, "events": 0, "contributions": defaultdict(float)})
        row["impact"] += float(amount)
        row["events"] += 1
        row["contributions"][str(reason)] += float(amount)

    def _rating_event_impacts(self, team: int) -> dict[str, dict]:
        store: dict[str, dict] = {}
        for event in self.state.event_log:
            if bool(event.data.get("shootout")):
                # Shootout performance is reported separately by knockout state;
                # it does not overwrite the player's regulation/ET match rating.
                continue
            data = event.data if isinstance(event.data, dict) else {}
            xg = clamp(float(data.get("xg", data.get("shot_xg", 0.0)) or 0.0))
            danger = clamp(float(data.get("danger", 0.0) or 0.0))

            if event.type == EventType.GOAL and int(event.team) == int(team):
                scorer = data.get("scorer") or data.get("taker")
                self._rating_delta(store, scorer, 1.20 + 0.16 * (1.0 - xg), "goal")

            elif event.type == EventType.SAVE:
                shooter = data.get("shooter")
                keeper = data.get("keeper")
                if int(event.team) == int(team):
                    self._rating_delta(store, shooter, 0.025 + 0.04 * xg, "shot_on_target")
                else:
                    self._rating_delta(store, keeper, 0.16 + 0.46 * xg, "save")

            elif event.type == EventType.BLOCK:
                if int(event.team) == int(team):
                    self._rating_delta(store, data.get("shooter"), -0.015, "shot_blocked")
                else:
                    self._rating_delta(store, data.get("defender"), 0.10 + 0.28 * xg, "block")

            elif event.type == EventType.MISS and int(event.team) == int(team):
                penalty = 0.035 + 0.26 * xg
                if data.get("big_chance"):
                    penalty += 0.07
                self._rating_delta(store, data.get("shooter"), -penalty, "miss")

            elif event.type == EventType.POST and int(event.team) == int(team):
                self._rating_delta(store, data.get("shooter"), 0.015 - 0.05 * xg, "post")

            elif event.type == EventType.DANGER and int(event.team) == int(team):
                creator = data.get("creator") or data.get("actor")
                receiver = data.get("receiver") or data.get("target")
                self._rating_delta(store, creator, 0.09 + 0.19 * danger, "chance_creation")
                self._rating_delta(store, receiver, 0.025 + 0.035 * danger, "dangerous_movement")

            elif event.type == EventType.PROGRESSION and int(event.team) == int(team):
                self._rating_delta(store, data.get("actor"), 0.025, "progression")
                self._rating_delta(store, data.get("target"), 0.010, "support")

            elif event.type == EventType.TURNOVER and int(event.team) == int(team):
                severity = clamp(float(data.get("severity", 0.45) or 0.45))
                actor = data.get("actor") or data.get("player")
                self._rating_delta(store, actor, -(0.035 + 0.09 * severity), "turnover")

            elif event.type == EventType.OFFSIDE and int(event.team) == int(team):
                self._rating_delta(store, data.get("runner"), -0.055, "offside")
                self._rating_delta(store, data.get("passer"), -0.010, "offside_pass")

            elif event.type == EventType.FOUL:
                severity = clamp(float(data.get("severity", 0.45) or 0.45))
                # Foul events use event.team as the fouled/attacking side.
                if int(event.team) != int(team):
                    self._rating_delta(store, data.get("defender"), -(0.035 + 0.11 * severity), "foul")
                else:
                    self._rating_delta(store, data.get("fouled"), 0.015 + 0.025 * severity, "foul_won")

            elif event.type == EventType.CARD and int(event.team) == int(team):
                card = str(data.get("card") or "yellow")
                penalty = {
                    "yellow": -0.12,
                    "second_yellow_red": -0.62,
                    "direct_red": -0.78,
                }.get(card, -0.12)
                self._rating_delta(store, data.get("player"), penalty, f"card_{card}")

            elif event.type == EventType.PENALTY:
                if str(event.text_key).startswith("shootout_"):
                    continue
                if int(event.team) == int(team):
                    self._rating_delta(store, data.get("fouled"), 0.16, "penalty_won")
                else:
                    self._rating_delta(store, data.get("defender"), -0.34, "penalty_conceded")

            elif event.type == EventType.REBOUND and int(event.team) == int(team):
                self._rating_delta(store, data.get("next_player"), 0.035, "second_ball")

            elif event.type == EventType.CORNER and int(event.team) == int(team):
                self._rating_delta(store, data.get("creator"), 0.018, "corner_created")

            # Defensive errors can be attached to almost any resulting event.
            error = data.get("defensive_error")
            if isinstance(error, dict) and int(event.team) == 1 - int(team):
                severity = clamp(float(error.get("severity", 0.60) or 0.60))
                self._rating_delta(
                    store,
                    error.get("defender"),
                    -(0.09 + 0.20 * severity),
                    f"defensive_error_{error.get('type', 'unknown')}",
                )

            # A completed low-risk circulation action counts only very slightly,
            # avoiding possession volume becoming a rating farm.
            if event.type == EventType.INFO and int(event.team) == int(team):
                if event.text_key == "safe_pass":
                    self._rating_delta(store, data.get("actor"), 0.006, "safe_circulation")
                elif event.text_key in {"throw_in_completed", "goal_kick_completed", "free_kick_completed"}:
                    self._rating_delta(store, data.get("actor") or data.get("taker"), 0.008, "restart_execution")

        return store

    def _participant_names(self, team: int) -> set[str]:
        names = {ps.player.name for ps in self.teams[team].on_field}
        for event in self.state.event_log:
            if int(event.team) != int(team):
                continue
            if event.type == EventType.SUBSTITUTION:
                if event.data.get("out"):
                    names.add(str(event.data["out"]))
                if event.data.get("in_player"):
                    names.add(str(event.data["in_player"]))
            elif event.type in {EventType.CARD, EventType.INJURY}:
                # Red-carded players can disappear from on_field; medical events
                # can precede a forced substitution. Both are still participants.
                if event.data.get("player"):
                    names.add(str(event.data["player"]))
        return names

    def player_match_rating(self, team: int, player_name: str) -> dict:
        name = str(player_name)
        participants = self._participant_names(team)
        if name not in participants:
            # Allow a past participant recoverable only through event history.
            appeared = any(
                int(ev.team) == int(team)
                and name in {str(value) for value in ev.data.values() if isinstance(value, str)}
                for ev in self.state.event_log
            )
            if not appeared:
                raise KeyError(name)

        row = self._rating_event_impacts(team).get(
            name,
            {"impact": 0.0, "events": 0, "contributions": defaultdict(float)},
        )
        raw = float(row["impact"])
        # Compression keeps one isolated event from creating absurd 10/10s,
        # while sustained excellent or poor play can still reach the extremes.
        compressed = raw / (1.0 + 0.16 * abs(raw))
        rating = clamp(self.BASE_MATCH_RATING + compressed, 3.0, 10.0)
        contributions = {
            key: round(float(value), 4)
            for key, value in sorted(row["contributions"].items())
        }
        return {
            "team": int(team),
            "player": name,
            "rating": round(rating, 2),
            "raw_impact": round(raw, 4),
            "rated_events": int(row["events"]),
            "contributions": contributions,
        }

    def match_ratings(self, team: int | None = None) -> dict:
        teams = (0, 1) if team is None else (int(team),)
        out = {}
        for index in teams:
            rows = [
                self.player_match_rating(index, name)
                for name in sorted(self._participant_names(index))
            ]
            out[str(index)] = rows
        return out


MatchEngine = MatchEngineV13Ratings

__all__ = ["MatchEngineV13Ratings", "MatchEngine"]
