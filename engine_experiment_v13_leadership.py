from __future__ import annotations

"""v1.3 derived captaincy and leadership context.

Captaincy is derived from existing mental/positional qualities. It never adds a
leadership rating to Player and never boosts technical execution. Its effect is
limited to small decision-tendency stabilisation when the team is under real
match adversity.
"""

from copy import deepcopy

from engine import PlayerState, Zone, clamp
from engine_experiment_v13_set_piece_routines import MatchEngineV13SetPieceRoutines


class MatchEngineV13Leadership(MatchEngineV13SetPieceRoutines):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._v13_captains = {
            "0": self._select_captain_name(0),
            "1": self._select_captain_name(1),
        }
        self._v13_captain_history: list[dict] = []

    def _leadership_index(self, ps: PlayerState) -> float:
        determination = getattr(ps.player, "determination", None)
        if determination is None:
            determination = 0.55 * ps.effective("composure") + 0.45 * ps.effective("discipline")
        value = (
            0.29 * ps.effective("composure")
            + 0.23 * ps.effective("discipline")
            + 0.18 * ps.effective("anticipation")
            + 0.14 * ps.effective("positioning")
            + 0.16 * float(determination)
        ) / 100.0
        return clamp(value)

    def _captain_candidates(self, team: int):
        rows = []
        for ps in self.teams[int(team)].on_field:
            if ps.red:
                continue
            rows.append((ps, self._leadership_index(ps)))
        return rows

    def _select_captain_name(self, team: int) -> str | None:
        rows = self._captain_candidates(team)
        if not rows:
            return None
        ps, _ = max(rows, key=lambda row: (row[1], row[0].player.name))
        return ps.player.name

    def _captain_on_field(self, team: int, name: str | None) -> bool:
        if name is None:
            return False
        return any(ps.player.name == name and not ps.red for ps in self.teams[int(team)].on_field)

    def _refresh_captain(self, team: int, reason: str = "availability") -> dict | None:
        if not hasattr(self, "_v13_captains"):
            self._v13_captains = {"0": self._select_captain_name(0), "1": self._select_captain_name(1)}
        if not hasattr(self, "_v13_captain_history"):
            self._v13_captain_history = []
        key = str(int(team))
        current = self._v13_captains.get(key)
        if self._captain_on_field(team, current):
            return None
        successor = self._select_captain_name(team)
        if successor == current:
            return None
        self._v13_captains[key] = successor
        row = {
            "team": int(team),
            "minute": round(self.minute, 4),
            "from": current,
            "to": successor,
            "reason": str(reason),
        }
        self._v13_captain_history.append(row)
        return row

    def captain_diagnostic(self, team: int) -> dict:
        team = int(team)
        if not hasattr(self, "_v13_captains"):
            self._v13_captains = {"0": self._select_captain_name(0), "1": self._select_captain_name(1)}
        name = self._v13_captains.get(str(team))
        ps = next((p for p in self.teams[team].on_field if p.player.name == name), None)
        return {
            "team": team,
            "captain": name,
            "active": bool(ps is not None and not ps.red),
            "derived_leadership": None if ps is None else self._leadership_index(ps),
            "history": [dict(row) for row in getattr(self, "_v13_captain_history", []) if int(row["team"]) == team],
        }

    def captain_context_diagnostic(self, team: int) -> dict:
        team = int(team)
        captain = self.captain_diagnostic(team)
        diff = self.score[team] - self.score[1 - team]
        late = clamp((self.minute - 65.0) / 30.0)
        trailing = 1.0 if diff < 0 else 0.0
        numerical = self.numerical_context_diagnostic(team)
        energies = [ps.energy for ps in self.teams[team].on_field if not ps.red]
        fatigue = clamp((0.72 - (sum(energies) / len(energies) if energies else 0.72)) / 0.35)
        adversity = clamp(
            0.46 * late * trailing
            + 0.34 * min(1.0, float(numerical["short_handed"]))
            + 0.20 * fatigue
        )
        leadership = float(captain["derived_leadership"] or 0.0) if captain["active"] else 0.0
        return {
            **captain,
            "score_diff": diff,
            "late_factor": late,
            "fatigue_pressure": fatigue,
            "adversity": adversity,
            "stabilisation": clamp(adversity * leadership),
        }

    def _decision_weights(self, actor: PlayerState, zone: Zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        team = self._team_for_player_state(actor)
        if team is None:
            return items
        control = float(self.captain_context_diagnostic(team)["stabilisation"])
        if control <= 0.0:
            return items
        factors = {
            "safe_pass": 1.0 + 0.065 * control,
            "progressive_pass": 1.0 + 0.025 * control,
            "switch": 1.0 + 0.030 * control,
            "carry": 1.0 - 0.035 * control,
            "dribble": 1.0 - 0.060 * control,
            "long_ball": 1.0 - 0.025 * control,
        }
        return [
            (action, max(0.001, float(weight) * clamp(factors.get(action, 1.0), 0.86, 1.10)))
            for action, weight in items
        ]

    def substitute(self, team: int, out_name: str, in_name: str, *args, **kwargs):
        captain_before = None
        if hasattr(self, "_v13_captains"):
            captain_before = self._v13_captains.get(str(int(team)))
        event = super().substitute(team, out_name, in_name, *args, **kwargs)
        if captain_before == out_name:
            transfer = self._refresh_captain(team, reason="substitution")
            if transfer is not None:
                event.data["captaincy_transfer"] = dict(transfer)
        return event

    def _apply_card_state(self, team: int, player: PlayerState, card):
        captain_before = None
        if hasattr(self, "_v13_captains"):
            captain_before = self._v13_captains.get(str(int(team)))
        super()._apply_card_state(team, player, card)
        if card in {"direct_red", "second_yellow_red"} and captain_before == player.player.name:
            self._refresh_captain(team, reason="dismissal")

    def step(self):
        self._refresh_captain(0)
        self._refresh_captain(1)
        return super().step()

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["captains"] = [self.captain_context_diagnostic(0), self.captain_context_diagnostic(1)]
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        data["v13_captains"] = deepcopy(getattr(self, "_v13_captains", {}))
        data["v13_captain_history"] = deepcopy(getattr(self, "_v13_captain_history", []))
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_captains", {})
        obj._v13_captains = deepcopy(raw) if isinstance(raw, dict) else {}
        for team in (0, 1):
            obj._v13_captains.setdefault(str(team), obj._select_captain_name(team))
        history = data.get("v13_captain_history", [])
        obj._v13_captain_history = deepcopy(history) if isinstance(history, list) else []
        return obj


MatchEngine = MatchEngineV13Leadership

__all__ = ["MatchEngineV13Leadership", "MatchEngine"]
