from __future__ import annotations

"""Cumulative match-load muscular injuries for v1.3.

The existing injury system remains authoritative for medical state.  This layer
adds a second causal source: sustained running load, low energy and difficult
environmental conditions.  Risk is evaluated sparsely with a dedicated RNG,
never from score targets, and no permanent injury-proneness rating is added.
"""

from copy import deepcopy
import ast
import hashlib
import random

from engine import EventType, PlayerState, clamp
from engine_experiment_v13_numerical_advantage import MatchEngineV13NumericalAdvantage


class MatchEngineV13LoadInjuries(MatchEngineV13NumericalAdvantage):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._v13_load_injury_rng = random.Random(self._load_injury_seed())
        self._v13_load_state: dict[str, dict] = {}
        self._v13_next_load_check_second = 24.0 * 60.0
        self._ensure_load_rows()

    def _load_injury_seed(self) -> int:
        payload = f"{getattr(self, 'seed', None)}|v13-load-injury".encode("utf-8")
        return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")

    @staticmethod
    def _load_key(team: int, name: str) -> str:
        return f"{int(team)}::{name}"

    def _ensure_load_rows(self) -> None:
        if not isinstance(getattr(self, "_v13_load_state", None), dict):
            self._v13_load_state = {}
        for team, rt in enumerate(self.teams):
            for ps in rt.on_field:
                self._v13_load_state.setdefault(
                    self._load_key(team, ps.player.name),
                    {"load": 0.0, "peak": 0.0, "occurred": False, "checks": 0},
                )
            for player in rt.bench:
                self._v13_load_state.setdefault(
                    self._load_key(team, player.name),
                    {"load": 0.0, "peak": 0.0, "occurred": False, "checks": 0},
                )

    @staticmethod
    def _position_load(position: str) -> float:
        return {
            "GK": 0.34,
            "CB": 0.78,
            "LB": 1.08,
            "RB": 1.08,
            "DM": 0.92,
            "CM": 1.04,
            "AM": 1.06,
            "LW": 1.12,
            "RW": 1.12,
            "ST": 0.98,
        }.get(str(position).upper(), 1.0)

    def _load_environment_multiplier(self) -> float:
        effects_fn = getattr(self, "_environment_effects", None)
        if not callable(effects_fn):
            return 1.0
        effects = effects_fn()
        return 1.0 + 0.16 * float(effects.get("heat_load", 0.0)) + 0.13 * float(effects.get("heavy_ground_load", 0.0))

    def _player_load_intensity(self, team: int, ps: PlayerState, possession_team: int) -> float:
        tactics = self.teams[int(team)].team.tactics
        position = self._position_load(ps.player.position)
        tactical = 0.78 + 0.18 * float(tactics.tempo) + 0.18 * float(tactics.pressing)
        phase = 1.06 if int(team) != int(possession_team) and float(tactics.pressing) >= 0.60 else 1.0
        low_energy = 1.0 + 0.30 * clamp((0.62 - float(ps.energy)) / 0.44)
        stamina_relief = 1.08 - 0.16 * clamp((ps.player.stamina - 45.0) / 50.0)
        return max(0.10, position * tactical * phase * low_energy * stamina_relief * self._load_environment_multiplier())

    def _advance_clock(self, seconds: float, possession_team: int):
        result = super()._advance_clock(seconds, possession_team)
        self._ensure_load_rows()
        minutes = max(0.0, float(seconds)) / 60.0
        if minutes <= 0.0:
            return result
        for team, rt in enumerate(self.teams):
            for ps in rt.on_field:
                if ps.red:
                    continue
                key = self._load_key(team, ps.player.name)
                row = self._v13_load_state[key]
                increment = minutes * self._player_load_intensity(team, ps, possession_team)
                row["load"] = float(row["load"]) + increment
                row["peak"] = max(float(row["peak"]), float(row["load"]))
        return result

    def _advance_dead_clock(self, elapsed_seconds: float, recoverable_seconds: float, *, reason: str) -> None:
        super()._advance_dead_clock(elapsed_seconds, recoverable_seconds, reason=reason)
        # Dead-ball pauses provide only slight relief; accumulated match load is
        # not erased by a short stoppage.
        relief = max(0.0, float(elapsed_seconds)) / 60.0 * 0.025
        if relief <= 0.0:
            return
        self._ensure_load_rows()
        on_field = {
            self._load_key(team, ps.player.name)
            for team, rt in enumerate(self.teams)
            for ps in rt.on_field
        }
        for key in on_field:
            row = self._v13_load_state.get(key)
            if row:
                row["load"] = max(0.0, float(row["load"]) - relief)

    def load_injury_diagnostic(self, team: int | None = None) -> dict:
        self._ensure_load_rows()
        if team is None:
            return deepcopy(self._v13_load_state)
        prefix = f"{int(team)}::"
        return {
            key[len(prefix):]: deepcopy(row)
            for key, row in self._v13_load_state.items()
            if key.startswith(prefix)
        }

    def _load_injury_risk(self, team: int, ps: PlayerState) -> float:
        row = self._v13_load_state[self._load_key(team, ps.player.name)]
        if bool(row.get("occurred")) or ps.red or ps.player.position.upper() == "GK":
            return 0.0
        load = float(row.get("load", 0.0))
        if load < 34.0:
            return 0.0
        exposure = clamp((load - 34.0) / 58.0)
        fatigue = clamp((0.70 - float(ps.energy)) / 0.52)
        stamina = clamp((78.0 - float(ps.player.stamina)) / 42.0)
        environment = self._load_environment_multiplier() - 1.0
        # This is a sparse 3-minute check on only the highest-risk candidate per
        # team, not a per-second or per-player lottery.
        return clamp(
            0.00035 + 0.0032 * exposure + 0.0019 * fatigue + 0.0009 * stamina + 0.0020 * environment,
            0.0,
            0.010,
        )

    def _highest_load_candidate(self, team: int) -> tuple[PlayerState | None, float]:
        rows = []
        for ps in self.teams[int(team)].on_field:
            risk = self._load_injury_risk(team, ps)
            if risk > 0.0:
                rows.append((ps, risk))
        return max(rows, key=lambda item: (item[1], item[0].player.name)) if rows else (None, 0.0)

    def _muscular_result(self, team: int, ps: PlayerState, risk: float) -> dict:
        load = float(self._v13_load_state[self._load_key(team, ps.player.name)]["load"])
        severity_roll = self._v13_load_injury_rng.random()
        if severity_roll < 0.08:
            grade = "moderate"
            impact = 0.62 + 0.18 * clamp((load - 45.0) / 40.0)
            forced_off = True
        elif severity_roll < 0.38:
            grade = "minor"
            impact = 0.44 + 0.18 * clamp((load - 40.0) / 45.0)
            forced_off = False
        else:
            grade = "knock"
            impact = 0.35 + 0.14 * clamp((load - 38.0) / 48.0)
            forced_off = False
        body_area = "lower_leg" if self._v13_load_injury_rng.random() < 0.58 else "soft_tissue"
        return {
            "grade": grade,
            "body_area": body_area,
            "impact": clamp(impact),
            "forced_off": forced_off,
            "load_related": True,
            "load": round(load, 3),
            "risk": round(float(risk), 6),
        }

    def _maybe_load_injury(self):
        if self.state.ended or self.state.pending is not None or self.state.restart is not None:
            return None
        if self.state.second + 1e-9 < float(self._v13_next_load_check_second):
            return None
        self._v13_next_load_check_second = float(self.state.second) + 180.0
        self._ensure_load_rows()
        for team in (0, 1):
            ps, risk = self._highest_load_candidate(team)
            if ps is None:
                continue
            row = self._v13_load_state[self._load_key(team, ps.player.name)]
            row["checks"] = int(row.get("checks", 0)) + 1
            if self._v13_load_injury_rng.random() >= risk:
                continue
            result = self._muscular_result(team, ps, risk)
            state = self._register_injury_state(team, ps, result)
            row["occurred"] = True
            if bool(state.get("forced_off")):
                ps.injured = True
            return self._emit(
                EventType.INJURY,
                team,
                3 if state.get("forced_off") else 2,
                "muscular_load_injury",
                player=ps.player.name,
                grade=state["grade"],
                body_area=state["body_area"],
                injury_region=state["region"],
                functional_limitation=round(float(state["initial_limitation"]), 4),
                recovery_minutes=state["recovery_minutes"],
                can_continue=state["can_continue"],
                medical_action=state["medical_action"],
                load_related=True,
                accumulated_load=result["load"],
                check_probability=result["risk"],
            )
        return None

    def step(self):
        injury = self._maybe_load_injury()
        if injury is not None:
            return injury
        return super().step()

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["load_injuries"] = {
            "next_check_second": round(float(self._v13_next_load_check_second), 3),
            "players": self.load_injury_diagnostic(),
        }
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        data["v13_load_state"] = deepcopy(self.load_injury_diagnostic())
        data["v13_next_load_check_second"] = float(self._v13_next_load_check_second)
        data["v13_load_injury_rng_state"] = repr(self._v13_load_injury_rng.getstate())
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_load_state")
        obj._v13_load_state = deepcopy(raw) if isinstance(raw, dict) else {}
        obj._v13_next_load_check_second = float(data.get("v13_next_load_check_second", 24.0 * 60.0))
        obj._v13_load_injury_rng = random.Random(obj._load_injury_seed())
        if data.get("v13_load_injury_rng_state"):
            obj._v13_load_injury_rng.setstate(ast.literal_eval(data["v13_load_injury_rng_state"]))
        obj._ensure_load_rows()
        return obj


MatchEngine = MatchEngineV13LoadInjuries

__all__ = ["MatchEngineV13LoadInjuries", "MatchEngine"]
