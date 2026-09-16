from __future__ import annotations

"""Attacker-versus-goalkeeper one-on-one decision layer for v1.3.

This sits above the existing defender 1v1 and finishing systems.  In a genuine
box breakaway the attacker and goalkeeper independently select an approach.
The interaction changes shot pressure/danger modestly; ordinary finishing and
keeper attributes still resolve the shot afterwards.
"""

from dataclasses import replace

from engine import Band, PendingAction, PlayerState, clamp, weighted_choice
from engine_experiment_v13_load_injuries import MatchEngineV13LoadInjuries


class MatchEngineV13GoalkeeperOneVOne(MatchEngineV13LoadInjuries):
    ATTACKER_CHOICES = ("shoot_early", "placed_finish", "power_finish", "chip", "round_keeper")
    KEEPER_CHOICES = ("hold_line", "rush", "spread", "anticipate")

    @staticmethod
    def _is_keeper_one_v_one(p: PendingAction) -> bool:
        return bool(
            p.kind == "shoot"
            and p.zone.band == Band.BOX
            and p.body_part != "head"
            and p.origin in {"through_ball", "transition", "dribble", "carry", "rebound", "second_ball"}
            and float(p.danger) >= 0.50
            and float(p.pressure) <= 0.67
        )

    def attacker_one_v_one_diagnostic(self, shooter: PlayerState, keeper: PlayerState, p: PendingAction) -> dict:
        finishing = clamp(shooter.effective("finishing") / 100.0)
        composure = clamp(shooter.effective("composure") / 100.0)
        technique = clamp(shooter.effective("technique") / 100.0)
        dribbling = clamp(shooter.effective("dribbling") / 100.0)
        pace = clamp(shooter.effective("pace") / 100.0)
        keeper_1v1 = clamp(keeper.effective("one_on_one") / 100.0)
        keeper_pos = clamp(keeper.effective("gk_positioning") / 100.0)
        pressure = clamp(float(p.pressure))
        confidence = 0.0
        team = self._team_for_player_state(shooter)
        if team is not None and hasattr(self, "_ensure_mental_row"):
            confidence = float(self._ensure_mental_row(team, shooter.player.name)["confidence"])

        raw = {
            "shoot_early": 0.24 + 0.27 * finishing + 0.12 * pace + 0.12 * pressure + 0.07 * max(0.0, confidence),
            "placed_finish": 0.20 + 0.27 * finishing + 0.26 * composure + 0.16 * technique - 0.10 * pressure,
            "power_finish": 0.18 + 0.30 * finishing + 0.14 * pace + 0.10 * pressure,
            "chip": 0.08 + 0.24 * technique + 0.25 * composure + 0.16 * keeper_1v1 - 0.07 * pressure,
            "round_keeper": 0.07 + 0.28 * dribbling + 0.20 * pace + 0.16 * composure - 0.18 * keeper_pos - 0.10 * pressure,
        }
        total = sum(max(0.02, value) for value in raw.values())
        return {
            "weights": {name: max(0.02, value) / total for name, value in raw.items()},
            "finishing": finishing,
            "composure": composure,
            "technique": technique,
            "dribbling": dribbling,
            "pace": pace,
            "pressure": pressure,
            "confidence": confidence,
        }

    def keeper_one_v_one_diagnostic(self, keeper: PlayerState, shooter: PlayerState, p: PendingAction) -> dict:
        one_v_one = clamp(keeper.effective("one_on_one") / 100.0)
        positioning = clamp(keeper.effective("gk_positioning") / 100.0)
        reflexes = clamp(keeper.effective("reflexes") / 100.0)
        composure = clamp(keeper.effective("composure") / 100.0)
        pace = clamp(keeper.effective("pace") / 100.0)
        shooter_pace = clamp(shooter.effective("pace") / 100.0)
        danger = clamp(float(p.danger))
        raw = {
            "hold_line": 0.22 + 0.28 * positioning + 0.18 * reflexes + 0.12 * composure - 0.10 * danger,
            "rush": 0.16 + 0.30 * one_v_one + 0.18 * pace + 0.12 * danger + 0.08 * shooter_pace,
            "spread": 0.16 + 0.28 * one_v_one + 0.25 * reflexes + 0.10 * danger,
            "anticipate": 0.14 + 0.25 * positioning + 0.22 * composure + 0.17 * one_v_one,
        }
        total = sum(max(0.02, value) for value in raw.values())
        return {
            "weights": {name: max(0.02, value) / total for name, value in raw.items()},
            "one_on_one": one_v_one,
            "positioning": positioning,
            "reflexes": reflexes,
            "composure": composure,
        }

    def _one_v_one_interaction(self, attacker_choice: str, keeper_choice: str, shooter: PlayerState, keeper: PlayerState) -> dict:
        danger_delta = 0.0
        pressure_delta = 0.0
        note = "neutral"
        if keeper_choice == "rush":
            pressure_delta += 0.075
            danger_delta -= 0.025
            note = "keeper_closes_angle"
            if attacker_choice == "chip":
                danger_delta += 0.050
                pressure_delta -= 0.020
                note = "chip_attacks_rush"
            elif attacker_choice == "round_keeper":
                edge = (shooter.effective("dribbling") + shooter.effective("pace")) - (keeper.effective("one_on_one") + keeper.effective("pace"))
                danger_delta += clamp(edge / 900.0, -0.035, 0.050)
                note = "round_keeper_vs_rush"
        elif keeper_choice == "spread":
            pressure_delta += 0.055
            danger_delta -= 0.018
            note = "keeper_spreads"
            if attacker_choice == "placed_finish":
                danger_delta += 0.030
                note = "placement_around_spread"
        elif keeper_choice == "anticipate":
            pressure_delta += 0.028
            if attacker_choice == "shoot_early":
                danger_delta += 0.032
                note = "early_shot_beats_read"
            elif attacker_choice == "placed_finish":
                danger_delta -= 0.018
                note = "keeper_reads_placement"
        else:
            if attacker_choice == "round_keeper":
                danger_delta -= 0.025
                note = "keeper_holds_against_round"
            elif attacker_choice == "power_finish":
                danger_delta += 0.018
                note = "power_before_set"

        attacker_delta = {
            "shoot_early": (0.012, -0.012),
            "placed_finish": (0.025, 0.008),
            "power_finish": (0.010, 0.018),
            "chip": (0.012, 0.010),
            "round_keeper": (0.018, 0.028),
        }[attacker_choice]
        danger_delta += attacker_delta[0]
        pressure_delta += attacker_delta[1]
        return {
            "danger_delta": clamp(danger_delta, -0.065, 0.075),
            "pressure_delta": clamp(pressure_delta, -0.035, 0.115),
            "interaction": note,
        }

    def _resolve_shot(self, p: PendingAction):
        if not self._is_keeper_one_v_one(p):
            return super()._resolve_shot(p)
        try:
            shooter = self.teams[p.team].by_name(p.actor)
        except KeyError:
            return super()._resolve_shot(p)
        keeper = self._goalkeeper(1 - p.team)
        attack = self.attacker_one_v_one_diagnostic(shooter, keeper, p)
        defend = self.keeper_one_v_one_diagnostic(keeper, shooter, p)
        attacker_choice = weighted_choice(self.rng, list(attack["weights"].items()))
        keeper_choice = weighted_choice(self.rng, list(defend["weights"].items()))
        interaction = self._one_v_one_interaction(attacker_choice, keeper_choice, shooter, keeper)
        tuned = replace(
            p,
            danger=clamp(float(p.danger) + float(interaction["danger_delta"])),
            pressure=clamp(float(p.pressure) + float(interaction["pressure_delta"])),
        )
        event = super()._resolve_shot(tuned)
        event.data.setdefault("goalkeeper_one_v_one", True)
        event.data.setdefault("attacker_1v1_choice", attacker_choice)
        event.data.setdefault("keeper_1v1_choice", keeper_choice)
        event.data.setdefault("one_v_one_interaction", interaction["interaction"])
        event.data.setdefault("one_v_one_danger_delta", round(float(interaction["danger_delta"]), 3))
        event.data.setdefault("one_v_one_pressure_delta", round(float(interaction["pressure_delta"]), 3))
        return event


MatchEngine = MatchEngineV13GoalkeeperOneVOne

__all__ = ["MatchEngineV13GoalkeeperOneVOne", "MatchEngine"]
