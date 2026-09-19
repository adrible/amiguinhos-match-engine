from __future__ import annotations

"""Richer penalty decisions for regulation and live shootouts in v1.3.

Taker style, target zone and goalkeeper approach are selected independently
from attributes and only previously observed kicks.  Their interaction modifies
an underlying conversion chance; no direction guarantees a goal or save and no
future kick is known in advance.
"""

from copy import deepcopy

from engine import DEF_C, MID_C, EventType, PlayerState, clamp, weighted_choice
from engine_experiment_v13_gk_one_v_one import MatchEngineV13GoalkeeperOneVOne


class MatchEngineV13Penalties(MatchEngineV13GoalkeeperOneVOne):
    PENALTY_STYLES = ("placed", "power", "stutter")
    PENALTY_TARGETS = ("low_left", "low_right", "high_left", "high_right", "center")
    KEEPER_APPROACHES = ("wait", "guess_left", "guess_right", "hold_center")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._v13_penalty_history: list[dict] = []

    def _ensure_penalty_history(self) -> list[dict]:
        if not isinstance(getattr(self, "_v13_penalty_history", None), list):
            self._v13_penalty_history = []
        return self._v13_penalty_history

    def penalty_history_diagnostic(self) -> list[dict]:
        return deepcopy(self._ensure_penalty_history())

    def _penalty_pressure(
        self,
        team: int,
        taker: PlayerState,
        *,
        shootout: bool,
        kick_number: int = 0,
        decisive: bool = False,
    ) -> float:
        mental_pressure = 0.0
        if hasattr(self, "_ensure_mental_row"):
            mental_pressure = float(self._ensure_mental_row(team, taker.player.name)["pressure"])
        late = clamp((self.minute - 70.0) / 25.0)
        score_diff = self.score[team] - self.score[1 - team]
        match_pressure = (0.18 + 0.22 * late) if score_diff <= 0 else 0.10 * late
        shootout_pressure = 0.0
        if shootout:
            shootout_pressure = clamp(0.18 + 0.035 * max(0, kick_number - 1) + (0.18 if decisive else 0.0), 0.0, 0.68)
        composure_relief = 0.18 * clamp(taker.effective("composure") / 100.0)
        return clamp(0.12 + match_pressure + shootout_pressure + 0.34 * mental_pressure - composure_relief, 0.02, 0.88)

    def _observed_team_direction(self, attacking_team: int, defending_team: int) -> dict:
        history = [
            row for row in self._ensure_penalty_history()
            if int(row["attacking_team"]) == int(attacking_team)
            and int(row["defending_team"]) == int(defending_team)
        ]
        left = sum(1 for row in history if str(row["target"]).endswith("left"))
        right = sum(1 for row in history if str(row["target"]).endswith("right"))
        center = sum(1 for row in history if row["target"] == "center")
        total = len(history)
        return {"left": left, "right": right, "center": center, "total": total}

    def penalty_taker_plan_diagnostic(
        self,
        team: int,
        taker: PlayerState,
        keeper: PlayerState,
        *,
        pressure: float,
    ) -> dict:
        finishing = clamp(taker.effective("finishing") / 100.0)
        technique = clamp(taker.effective("technique") / 100.0)
        composure = clamp(taker.effective("composure") / 100.0)
        power = clamp(taker.effective("long_shots") / 100.0)
        keeper_reflex = clamp(keeper.effective("reflexes") / 100.0)
        style_raw = {
            "placed": 0.24 + 0.32 * technique + 0.30 * composure - 0.10 * pressure,
            "power": 0.22 + 0.34 * finishing + 0.24 * power + 0.10 * pressure,
            "stutter": 0.10 + 0.31 * composure + 0.20 * technique + 0.12 * keeper_reflex - 0.16 * pressure,
        }
        style_total = sum(max(0.03, value) for value in style_raw.values())
        styles = {name: max(0.03, value) / style_total for name, value in style_raw.items()}

        preferred = str(getattr(taker.player, "preferred_foot", "R")).upper()
        target_raw = {
            "low_left": 0.22 + 0.15 * technique + (0.035 if preferred in {"R", "B", "BOTH"} else 0.0),
            "low_right": 0.22 + 0.15 * technique + (0.035 if preferred in {"L", "B", "BOTH"} else 0.0),
            "high_left": 0.12 + 0.16 * finishing + 0.13 * power - 0.08 * pressure,
            "high_right": 0.12 + 0.16 * finishing + 0.13 * power - 0.08 * pressure,
            "center": 0.08 + 0.19 * composure + 0.08 * pressure,
        }
        target_total = sum(max(0.02, value) for value in target_raw.values())
        targets = {name: max(0.02, value) / target_total for name, value in target_raw.items()}
        return {"styles": styles, "targets": targets, "pressure": clamp(pressure)}

    def penalty_keeper_plan_diagnostic(
        self,
        defending_team: int,
        keeper: PlayerState,
        attacking_team: int,
    ) -> dict:
        one_v_one = clamp(keeper.effective("one_on_one") / 100.0)
        reflexes = clamp(keeper.effective("reflexes") / 100.0)
        positioning = clamp(keeper.effective("gk_positioning") / 100.0)
        composure = clamp(keeper.effective("composure") / 100.0)
        observed = self._observed_team_direction(attacking_team, defending_team)
        sample = int(observed["total"])
        learned = clamp(sample / 5.0, 0.0, 0.70)
        left_tendency = observed["left"] / sample if sample else 1 / 3
        right_tendency = observed["right"] / sample if sample else 1 / 3
        center_tendency = observed["center"] / sample if sample else 1 / 3
        raw = {
            "wait": 0.22 + 0.26 * reflexes + 0.22 * composure - 0.06 * learned,
            "guess_left": 0.18 + 0.22 * one_v_one + 0.15 * positioning + 0.28 * learned * left_tendency,
            "guess_right": 0.18 + 0.22 * one_v_one + 0.15 * positioning + 0.28 * learned * right_tendency,
            "hold_center": 0.08 + 0.18 * composure + 0.12 * positioning + 0.24 * learned * center_tendency,
        }
        total = sum(max(0.02, value) for value in raw.values())
        return {
            "weights": {name: max(0.02, value) / total for name, value in raw.items()},
            "observed": observed,
            "learned_strength": learned,
        }

    @staticmethod
    def _penalty_target_side(target: str) -> str:
        if str(target).endswith("left"):
            return "left"
        if str(target).endswith("right"):
            return "right"
        return "center"

    def _penalty_duel(
        self,
        team: int,
        taker: PlayerState,
        keeper: PlayerState,
        *,
        shootout: bool,
        kick_number: int = 0,
        decisive: bool = False,
    ) -> dict:
        pressure = self._penalty_pressure(team, taker, shootout=shootout, kick_number=kick_number, decisive=decisive)
        taker_plan = self.penalty_taker_plan_diagnostic(team, taker, keeper, pressure=pressure)
        keeper_plan = self.penalty_keeper_plan_diagnostic(1 - team, keeper, team)
        style = weighted_choice(self.rng, list(taker_plan["styles"].items()))
        target = weighted_choice(self.rng, list(taker_plan["targets"].items()))
        keeper_approach = weighted_choice(self.rng, list(keeper_plan["weights"].items()))

        base = self._penalty_conversion_probability(taker, keeper)
        style_delta = {
            "placed": 0.015,
            "power": 0.004,
            "stutter": 0.010,
        }[style]
        target_delta = {
            "low_left": 0.005,
            "low_right": 0.005,
            "high_left": -0.020,
            "high_right": -0.020,
            "center": -0.005,
        }[target]
        side = self._penalty_target_side(target)
        read_delta = 0.0
        if keeper_approach == "guess_left":
            read_delta = -0.080 if side == "left" else 0.035
        elif keeper_approach == "guess_right":
            read_delta = -0.080 if side == "right" else 0.035
        elif keeper_approach == "hold_center":
            read_delta = -0.075 if side == "center" else 0.025
        else:  # wait
            read_delta = -0.025 if style == "stutter" else -0.010

        if style == "stutter" and keeper_approach in {"guess_left", "guess_right"}:
            read_delta += 0.025
        if style == "power":
            read_delta *= 0.82

        composure = clamp(taker.effective("composure") / 100.0)
        pressure_delta = -0.085 * pressure * (1.05 - 0.45 * composure)
        conversion = clamp(base + style_delta + target_delta + read_delta + pressure_delta, 0.43, 0.94)

        high = target.startswith("high_")
        technique = clamp(taker.effective("technique") / 100.0)
        finishing = clamp(taker.effective("finishing") / 100.0)
        on_target = clamp(
            0.91
            + 0.045 * technique
            + 0.025 * finishing
            - 0.075 * pressure
            - (0.045 if high else 0.0)
            - (0.020 if style == "power" else 0.0),
            0.72,
            0.985,
        )
        return {
            "style": style,
            "target": target,
            "target_side": side,
            "keeper_approach": keeper_approach,
            "pressure": pressure,
            "conversion_probability": conversion,
            "on_target_probability": on_target,
            "keeper_learned_strength": keeper_plan["learned_strength"],
            "keeper_observed": keeper_plan["observed"],
        }

    def _record_penalty_history(self, team: int, keeper_team: int, taker: PlayerState, keeper: PlayerState, duel: dict, scored: bool, shootout: bool) -> None:
        self._ensure_penalty_history().append({
            "attacking_team": int(team),
            "defending_team": int(keeper_team),
            "taker": taker.player.name,
            "keeper": keeper.player.name,
            "style": duel["style"],
            "target": duel["target"],
            "keeper_approach": duel["keeper_approach"],
            "scored": bool(scored),
            "shootout": bool(shootout),
            "minute": round(float(self.minute), 3),
        })

    def _resolve_live_penalty_restart(self, team: int):
        taker = self._best_player(team, ("finishing", "composure", "technique"), exclude_positions={"GK"})
        keeper = self._goalkeeper(1 - team)
        duel = self._penalty_duel(team, taker, keeper, shootout=False)
        xg = float(duel["conversion_probability"])
        self.stats[team].shots += 1
        self.stats[team].xg += xg
        self.stats[team].big_chances += 1
        scored = self.rng.random() < xg
        self._record_penalty_history(team, 1 - team, taker, keeper, duel, scored, False)
        common = {
            "taker": taker.player.name,
            "keeper": keeper.player.name,
            "xg": round(xg, 3),
            "penalty_style": duel["style"],
            "penalty_target": duel["target"],
            "keeper_approach": duel["keeper_approach"],
            "penalty_pressure": round(float(duel["pressure"]), 3),
        }
        if scored:
            self.stats[team].on_target += 1
            self.stats[team].goals += 1
            self.state.restart = "kickoff"
            self.state.restart_team = 1 - team
            self.state.restart_zone = MID_C
            self.state.phase = "restart"
            return self._emit(EventType.GOAL, team, 5, "penalty_goal", scorer=taker.player.name, **common)
        on_target = self.rng.random() < float(duel["on_target_probability"])
        if on_target:
            self.stats[team].on_target += 1
            self.stats[1 - team].saves += 1
            typ, key = EventType.SAVE, "penalty_saved"
        else:
            typ, key = EventType.MISS, "penalty_missed"
        self._switch_possession(1 - team, DEF_C, transition=0.0)
        return self._emit(typ, team, 5, key, **common)

    def _resolve_restart(self):
        if self.state.restart == "penalty" and self.state.restart_team in (0, 1):
            team = int(self.state.restart_team)
            self.state.restart = None
            self.state.restart_team = None
            self.state.restart_zone = None
            return self._resolve_live_penalty_restart(team)
        return super()._resolve_restart()

    def _resolve_shootout_kick(self):
        shootout = self._v13_shootout
        team = int(shootout["next_team"])
        opponent = 1 - team
        taker = self._shootout_taker(team)
        keeper = self._shootout_keeper(opponent)
        kick_number = sum(shootout["kicks"]) + 1
        # A kick is "decisive pressure" when both teams have reached their
        # fifth attempt or when the ordinary winner logic can end the contest
        # immediately after this pair of kicks.
        decisive_pressure = bool(max(shootout["kicks"]) >= 4)
        duel = self._penalty_duel(
            team,
            taker,
            keeper,
            shootout=True,
            kick_number=kick_number,
            decisive=decisive_pressure,
        )
        scored = self.rng.random() < float(duel["conversion_probability"])
        self._record_penalty_history(team, opponent, taker, keeper, duel, scored, True)
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
            conversion_probability=round(float(duel["conversion_probability"]), 4),
            penalty_style=duel["style"],
            penalty_target=duel["target"],
            keeper_approach=duel["keeper_approach"],
            penalty_pressure=round(float(duel["pressure"]), 3),
            keeper_learned_strength=round(float(duel["keeper_learned_strength"]), 3),
            shootout_score=list(shootout["goals"]),
            shootout_kicks=list(shootout["kicks"]),
            kick_number=kick_number,
            decisive=bool(winner is not None),
        )

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["penalty_history"] = self.penalty_history_diagnostic()
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        data["v13_penalty_history"] = self.penalty_history_diagnostic()
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_penalty_history")
        obj._v13_penalty_history = deepcopy(raw) if isinstance(raw, list) else []
        return obj


MatchEngine = MatchEngineV13Penalties

__all__ = ["MatchEngineV13Penalties", "MatchEngine"]
