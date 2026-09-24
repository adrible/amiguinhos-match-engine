from __future__ import annotations

"""v1.3 knockout continuation: extra time plus live penalty shootout.

The stable v1.2 engine is intentionally untouched.  In the candidate, a tied
knockout match with ``allow_extra_time=True`` now continues through 105' and
120'.  If still tied, the shootout is stateful: every public ``step()`` (and
therefore every runner ``p``) resolves at most one penalty kick.  No shootout is
precomputed.
"""

from copy import deepcopy

from engine import EventType, MID_C, PlayerState, clamp
from engine_experiment_v13_persistence import MatchEngineV13Persistence


VERSION = (
    "1.3-candidate-spatial-creativity-boldness-offball-body-defense-"
    "marking-cover-communication-offside-overload-errors-chemistry-"
    "adaptation-stability-persistence-knockout"
)


class MatchEngineV13Knockout(MatchEngineV13Persistence):
    """Adds deterministic live knockout continuation above v1.3 persistence."""

    # ---------------------------- period continuation ----------------------------

    def _start_extra_time(self):
        self.state.pending = None
        self.state.restart = None
        self.state.restart_team = None
        self.state.restart_zone = None
        self.state.transition_boost = 0.0
        self.state.ended = False
        self.state.period_markers = [105, 120]
        self.state.period_index = 0
        self.state.extra_time_kickoff_team = self.rng.randrange(2)
        self.state.possession = int(self.state.extra_time_kickoff_team)
        self.state.zone = MID_C
        self.state.phase = "build_up"
        return self._emit(
            EventType.PERIOD_END,
            self.state.possession,
            5,
            "regulation_end_tied",
            extra_time=True,
            next_marker=105,
        )

    def _start_shootout(self):
        first_team = self.rng.randrange(2)
        self.state.pending = None
        self.state.restart = None
        self.state.restart_team = None
        self.state.restart_zone = None
        self.state.transition_boost = 0.0
        self.state.ended = False
        self.state.phase = "penalty_shootout"
        self._v13_shootout = {
            "active": True,
            "complete": False,
            "first_team": int(first_team),
            "next_team": int(first_team),
            "kicks": [0, 0],
            "goals": [0, 0],
            "winner": None,
        }
        return self._emit(
            EventType.PERIOD_END,
            first_team,
            5,
            "extra_time_end_tied",
            shootout=True,
            first_team=first_team,
        )

    def _check_period_boundary(self):
        if self.state.period_index >= len(self.state.period_markers):
            return None
        marker = self.state.period_markers[self.state.period_index]
        if self.minute < marker:
            return None

        if (
            marker == 90
            and self.state.period_markers == [45, 90]
            and self.config.allow_extra_time
            and self.score[0] == self.score[1]
        ):
            return self._start_extra_time()

        if (
            marker == 120
            and self.state.period_markers == [105, 120]
            and self.score[0] == self.score[1]
        ):
            return self._start_shootout()

        return super()._check_period_boundary()

    # ---------------------------- shootout model ----------------------------

    @staticmethod
    def _penalty_taker_quality(ps: PlayerState) -> float:
        return clamp(
            0.32 * ps.effective("finishing") / 100.0
            + 0.28 * ps.effective("composure") / 100.0
            + 0.20 * ps.effective("technique") / 100.0
            + 0.10 * ps.player.overall / 100.0
            + 0.10 * ps.effective("long_shots") / 100.0
        )

    @staticmethod
    def _keeper_penalty_quality(ps: PlayerState) -> float:
        return clamp(
            0.32 * ps.effective("one_on_one") / 100.0
            + 0.28 * ps.effective("reflexes") / 100.0
            + 0.22 * ps.effective("gk_positioning") / 100.0
            + 0.18 * ps.effective("handling") / 100.0
        )

    def _shootout_taker(self, team: int) -> PlayerState:
        eligible = [
            ps for ps in self.teams[team].on_field
            if not ps.red and not ps.injured and ps.player.position.upper() != "GK"
        ]
        if not eligible:
            eligible = [ps for ps in self.teams[team].on_field if not ps.red and not ps.injured]
        if not eligible:
            eligible = list(self.teams[team].on_field)
        ordered = sorted(
            eligible,
            key=lambda ps: (-self._penalty_taker_quality(ps), ps.player.name),
        )
        kick_index = int(self._v13_shootout["kicks"][team])
        return ordered[kick_index % len(ordered)]

    def _shootout_keeper(self, defending_team: int) -> PlayerState:
        keepers = [
            ps for ps in self.teams[defending_team].on_field
            if not ps.red and not ps.injured and ps.player.position.upper() == "GK"
        ]
        pool = keepers or [
            ps for ps in self.teams[defending_team].on_field
            if not ps.red and not ps.injured
        ] or list(self.teams[defending_team].on_field)
        return max(
            pool,
            key=lambda ps: (self._keeper_penalty_quality(ps), ps.player.name),
        )

    def _penalty_conversion_probability(
        self,
        taker: PlayerState,
        keeper: PlayerState,
    ) -> float:
        tq = self._penalty_taker_quality(taker)
        gq = self._keeper_penalty_quality(keeper)
        composure = clamp(taker.effective("composure") / 100.0)
        energy = clamp(taker.energy)
        return clamp(
            0.755
            + 0.25 * (tq - 0.75)
            - 0.20 * (gq - 0.75)
            + 0.06 * (composure - 0.75)
            + 0.035 * (energy - 0.70),
            0.54,
            0.93,
        )

    @staticmethod
    def _shootout_winner(shootout: dict):
        kicks = shootout["kicks"]
        goals = shootout["goals"]

        if kicks[0] <= 5 and kicks[1] <= 5:
            remaining0 = max(0, 5 - kicks[0])
            remaining1 = max(0, 5 - kicks[1])
            if goals[0] > goals[1] + remaining1:
                return 0
            if goals[1] > goals[0] + remaining0:
                return 1

        if kicks[0] >= 5 and kicks[1] >= 5 and kicks[0] == kicks[1]:
            if goals[0] != goals[1]:
                return 0 if goals[0] > goals[1] else 1
        return None

    def _resolve_shootout_kick(self):
        shootout = self._v13_shootout
        team = int(shootout["next_team"])
        opponent = 1 - team
        taker = self._shootout_taker(team)
        keeper = self._shootout_keeper(opponent)
        probability = self._penalty_conversion_probability(taker, keeper)
        scored = self.rng.random() < probability

        shootout["kicks"][team] += 1
        if scored:
            shootout["goals"][team] += 1

        winner = self._shootout_winner(shootout)
        if winner is not None:
            shootout["winner"] = int(winner)
            shootout["complete"] = True
        else:
            shootout["next_team"] = opponent

        return self._emit(
            EventType.PENALTY,
            team,
            5,
            "shootout_goal" if scored else "shootout_miss",
            shootout=True,
            taker=taker.player.name,
            keeper=keeper.player.name,
            scored=bool(scored),
            conversion_probability=round(probability, 4),
            shootout_score=list(shootout["goals"]),
            shootout_kicks=list(shootout["kicks"]),
            kick_number=sum(shootout["kicks"]),
            decisive=bool(winner is not None),
        )

    def _finish_shootout(self):
        shootout = self._v13_shootout
        winner = int(shootout["winner"])
        shootout["active"] = False
        self.state.ended = True
        self.state.phase = "ended"
        return self._emit(
            EventType.MATCH_END,
            winner,
            5,
            "match_end_shootout",
            shootout=True,
            winner=winner,
            shootout_score=list(shootout["goals"]),
            shootout_kicks=list(shootout["kicks"]),
        )

    def step(self):
        shootout = getattr(self, "_v13_shootout", None)
        if isinstance(shootout, dict) and shootout.get("active"):
            if shootout.get("complete"):
                return self._finish_shootout()
            return self._resolve_shootout_kick()
        return super().step()

    # ---------------------------- persistence ----------------------------

    def _v13_state_to_dict(self) -> dict:
        data = super()._v13_state_to_dict()
        shootout = getattr(self, "_v13_shootout", None)
        data["shootout"] = deepcopy(shootout) if isinstance(shootout, dict) else None
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        data["engine_version"] = VERSION
        return data

    @classmethod
    def from_state_dict(cls, data: dict) -> "MatchEngineV13Knockout":
        obj = super().from_state_dict(data)
        candidate = data.get("v13", {}) if isinstance(data.get("v13", {}), dict) else {}
        shootout = candidate.get("shootout")
        obj._v13_shootout = deepcopy(shootout) if isinstance(shootout, dict) else None
        return obj


MatchEngine = MatchEngineV13Knockout
