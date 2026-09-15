from __future__ import annotations

"""v1.3 contextual on-field positional rotations.

Rotations are tactical redeployments between two players already on the pitch.
They happen only at stoppages, require reciprocal positional familiarity and
use hysteresis so the same team does not oscillate between shapes every few
minutes. No execution attribute is modified.
"""

from copy import deepcopy

from engine import EventType, PlayerState, clamp
from engine_experiment_v13_substitution_strategy import MatchEngineV13SubstitutionStrategy


class MatchEngineV13Rotations(MatchEngineV13SubstitutionStrategy):
    ROTATION_MIN_MINUTE = 60.0
    ROTATION_COOLDOWN_MINUTES = 14.0
    ROTATION_MIN_FAMILIARITY = 0.68
    ROTATION_MIN_SCORE = 0.032

    _ATTACK_RANK = {
        "GK": 0.0,
        "CB": 0.8,
        "LB": 1.7,
        "RB": 1.7,
        "DM": 2.0,
        "CM": 2.8,
        "LW": 3.9,
        "RW": 3.9,
        "AM": 4.2,
        "ST": 5.0,
    }

    def _ensure_rotation_state(self) -> None:
        if not hasattr(self, "_v13_position_rotations"):
            self._v13_position_rotations: list[dict] = []

    def _rotation_stoppage_open(self) -> bool:
        if self.state.pending is not None or self.state.ended:
            return False
        if self.state.restart is not None:
            return True
        return bool(
            self.state.event_log
            and self.state.event_log[-1].type == EventType.PERIOD_END
        )

    def _last_rotation_minute(self, team: int):
        self._ensure_rotation_state()
        for row in reversed(self._v13_position_rotations):
            if int(row.get("team", -1)) == int(team):
                return float(row.get("minute", 0.0))
        return None

    def _rotation_context(self, team: int):
        if self.minute < self.ROTATION_MIN_MINUTE:
            return None
        if self._shootout_preparation_context():
            return None
        last = self._last_rotation_minute(team)
        if last is not None and self.minute - last < self.ROTATION_COOLDOWN_MINUTES:
            return None
        diff = self._score_diff_for(team)
        if diff < 0 and self.minute >= 65.0:
            return "chase_game"
        if diff > 0 and self.minute >= 70.0:
            return "protect_lead"
        return None

    @staticmethod
    def _natural_wide_side_score(player: PlayerState, position: str) -> float:
        pos = str(position).upper()
        foot = str(player.player.preferred_foot).upper()
        if pos == "RW":
            return 1.0 if foot == "R" else 0.0
        if pos == "LW":
            return 1.0 if foot == "L" else 0.0
        return 0.0

    def _pair_rotation_profile(
        self,
        team: int,
        first: PlayerState,
        second: PlayerState,
        context: str,
    ):
        pos_a = str(first.player.position).upper()
        pos_b = str(second.player.position).upper()
        if pos_a == pos_b or "GK" in {pos_a, pos_b}:
            return None
        if self._explicit_position_profile(first.player) is None:
            return None
        if self._explicit_position_profile(second.player) is None:
            return None

        fam_a = self.position_familiarity(first.player, pos_b)
        fam_b = self.position_familiarity(second.player, pos_a)
        fit = min(fam_a, fam_b)
        if fit < self.ROTATION_MIN_FAMILIARITY:
            return None

        rank_a = float(self._ATTACK_RANK.get(pos_a, 2.5))
        rank_b = float(self._ATTACK_RANK.get(pos_b, 2.5))
        attack_a = self._attack_index_effective(first)
        attack_b = self._attack_index_effective(second)
        defense_a = self._defense_index_effective(first)
        defense_b = self._defense_index_effective(second)

        if context == "chase_game":
            current = attack_a * rank_a + attack_b * rank_b
            swapped = attack_a * rank_b + attack_b * rank_a
            structural_gain = (swapped - current) / 5.0
        else:
            def_rank_a = 5.0 - rank_a
            def_rank_b = 5.0 - rank_b
            current = defense_a * def_rank_a + defense_b * def_rank_b
            swapped = defense_a * def_rank_b + defense_b * def_rank_a
            structural_gain = (swapped - current) / 5.0

        wide_delivery_gain = 0.0
        if context == "chase_game" and {pos_a, pos_b} == {"LW", "RW"}:
            current_side = (
                self._natural_wide_side_score(first, pos_a)
                + self._natural_wide_side_score(second, pos_b)
            )
            swapped_side = (
                self._natural_wide_side_score(first, pos_b)
                + self._natural_wide_side_score(second, pos_a)
            )
            side_gain = swapped_side - current_side
            if side_gain > 0:
                target = self._best_player(
                    team,
                    ("heading", "strength", "off_ball"),
                    exclude_positions={"GK"},
                )
                aerial = (
                    target.effective("heading")
                    + target.effective("strength")
                    + target.effective("off_ball")
                ) / 300.0
                cross_frequency = float(self.teams[team].team.tactics.cross_frequency)
                wide_delivery_gain = 0.055 * side_gain * cross_frequency * aerial

        score = structural_gain + wide_delivery_gain + 0.06 * max(0.0, fit - 0.68)
        reason = (
            "wide_delivery"
            if wide_delivery_gain > max(0.0, structural_gain)
            else context
        )
        return {
            "team": int(team),
            "first": first,
            "second": second,
            "first_from": pos_a,
            "first_to": pos_b,
            "second_from": pos_b,
            "second_to": pos_a,
            "first_familiarity": fam_a,
            "second_familiarity": fam_b,
            "fit": fit,
            "structural_gain": structural_gain,
            "wide_delivery_gain": wide_delivery_gain,
            "score": score,
            "reason": reason,
        }

    def position_rotation_diagnostic(self, team: int):
        context = self._rotation_context(team)
        if context is None or not self._rotation_stoppage_open():
            return None
        rt = self.teams[team]
        candidates = []
        for index, first in enumerate(rt.on_field):
            if first.red or first.injured:
                continue
            for second in rt.on_field[index + 1 :]:
                if second.red or second.injured:
                    continue
                profile = self._pair_rotation_profile(team, first, second, context)
                if profile is not None and float(profile["score"]) >= self.ROTATION_MIN_SCORE:
                    candidates.append(profile)
        if not candidates:
            return None
        best = max(
            candidates,
            key=lambda row: (
                float(row["score"]),
                float(row["fit"]),
                str(row["first"].player.name),
                str(row["second"].player.name),
            ),
        )
        return {
            "team": int(team),
            "first": best["first"].player.name,
            "second": best["second"].player.name,
            "first_from": best["first_from"],
            "first_to": best["first_to"],
            "second_from": best["second_from"],
            "second_to": best["second_to"],
            "first_familiarity": float(best["first_familiarity"]),
            "second_familiarity": float(best["second_familiarity"]),
            "score": float(best["score"]),
            "structural_gain": float(best["structural_gain"]),
            "wide_delivery_gain": float(best["wide_delivery_gain"]),
            "reason": best["reason"],
        }

    def _maybe_position_rotation(self):
        if not self._rotation_stoppage_open():
            return None

        # A medical or shootout-specific substitution has priority over a shape
        # rotation at the same stoppage.
        sub = self._best_auto_substitution()
        if sub is not None and str(sub.get("reason")) in {
            "injury",
            "injury_management",
            "shootout_preparation",
        }:
            return None

        options = [
            diag
            for team in (0, 1)
            if (diag := self.position_rotation_diagnostic(team)) is not None
        ]
        if not options:
            return None
        best = max(options, key=lambda row: (float(row["score"]), -int(row["team"])))
        team = int(best["team"])
        first = self.teams[team].by_name(str(best["first"]))
        second = self.teams[team].by_name(str(best["second"]))
        first.player.position, second.player.position = best["first_to"], best["second_to"]

        self._ensure_rotation_state()
        record = {
            key: value
            for key, value in best.items()
            if key not in {"structural_gain", "wide_delivery_gain"}
        }
        record["minute"] = round(float(self.minute), 4)
        self._v13_position_rotations.append(deepcopy(record))
        return self._emit(
            EventType.INFO,
            team,
            1,
            "position_rotation",
            **{key: value for key, value in best.items() if key != "team"},
        )

    def step(self):
        if self.state.pending is None and not self.state.ended:
            event = self._maybe_position_rotation()
            if event is not None:
                return event
        return super().step()

    def export_state(self) -> dict:
        data = super().export_state()
        self._ensure_rotation_state()
        data["v13_position_rotations"] = deepcopy(self._v13_position_rotations)
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        rows = data.get("v13_position_rotations", [])
        obj._v13_position_rotations = deepcopy(rows) if isinstance(rows, list) else []
        return obj


MatchEngine = MatchEngineV13Rotations

__all__ = ["MatchEngineV13Rotations", "MatchEngine"]
