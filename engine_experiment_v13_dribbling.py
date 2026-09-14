from __future__ import annotations

"""v1.3 duel/box stage 1: advanced contextual dribbling.

Dribble moves are solutions to a matchup, not special moves or execution
bonuses. Existing dribbling, technique, pace, strength and composure interact
with defender quality, pressure, space, lane and body context.
"""

from engine import Lane, PlayerState, Zone, clamp
from engine_experiment_v13_space_manipulation import MatchEngineV13SpaceManipulation
from engine_experiment_v13_passing_texture import _stable_fraction

VERSION = "1.3-candidate-advanced-dribbling"


class MatchEngineV13AdvancedDribbling(MatchEngineV13SpaceManipulation):
    def dribble_move_diagnostic(
        self,
        actor: PlayerState,
        defender: PlayerState,
        zone: Zone,
        ctx: dict,
    ) -> dict:
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        space = clamp(float(ctx.get("space", 0.5)))
        dribbling = clamp(actor.effective("dribbling") / 100.0)
        technique = clamp(actor.effective("technique") / 100.0)
        pace = clamp(actor.effective("pace") / 100.0)
        strength = clamp(actor.effective("strength") / 100.0)
        composure = clamp(actor.effective("composure") / 100.0)

        defending = clamp(
            0.34 * defender.effective("tackling") / 100.0
            + 0.24 * defender.effective("positioning") / 100.0
            + 0.18 * defender.effective("pace") / 100.0
            + 0.12 * defender.effective("strength") / 100.0
            + 0.12 * defender.effective("anticipation") / 100.0
        )
        attacking = clamp(
            0.31 * dribbling
            + 0.23 * technique
            + 0.18 * pace
            + 0.14 * composure
            + 0.14 * strength
        )
        base_edge = clamp(
            0.50 + 0.72 * (attacking - defending) + 0.12 * space - 0.10 * pressure,
            0.14,
            0.86,
        )

        fraction = _stable_fraction(
            "advanced-dribble",
            self.seed,
            round(self.state.second, 3),
            actor.player.name,
            defender.player.name,
            zone.band.value,
            zone.lane.value,
        )
        if pressure >= 0.68 and strength >= pace - 0.05:
            move = "shield_turn"
            fit = 0.48 * strength + 0.30 * technique + 0.22 * composure
            risk = 0.22
        elif space >= 0.66 and pace >= 0.68:
            move = "acceleration"
            fit = 0.50 * pace + 0.30 * dribbling + 0.20 * technique
            risk = 0.34
        elif zone.lane != Lane.CENTER and fraction < 0.34:
            move = "outside_touch"
            fit = 0.42 * dribbling + 0.33 * pace + 0.25 * technique
            risk = 0.38
        elif fraction < 0.58:
            move = "body_cut"
            fit = 0.44 * dribbling + 0.36 * technique + 0.20 * composure
            risk = 0.31
        elif fraction < 0.79:
            move = "stop_go"
            fit = 0.38 * dribbling + 0.30 * technique + 0.22 * pace + 0.10 * composure
            risk = 0.37
        else:
            move = "step_over"
            fit = 0.46 * dribbling + 0.34 * technique + 0.20 * composure
            risk = 0.43

        move_edge = clamp(base_edge + 0.16 * (fit - 0.50) - 0.07 * risk, 0.12, 0.88)
        return {
            "move": move,
            "attacking_quality": attacking,
            "defending_quality": defending,
            "move_fit": clamp(fit),
            "risk": risk,
            "attacker_edge": move_edge,
            "pressure": pressure,
            "space": space,
        }

    @staticmethod
    def _pending_duel_context(p) -> dict:
        pressure = clamp(float(p.pressure))
        return {
            "pressure": pressure,
            "space": clamp(0.66 - 0.48 * pressure + 0.10 * float(p.danger)),
            "space_behind": clamp(0.34 + 0.24 * float(p.danger)),
            "support": 0.50,
            "defensive_quality": 0.55,
        }

    def _resolve_pending(self):
        p = self.state.pending
        diag = None
        if p is not None and p.kind == "dribble" and p.defender:
            try:
                actor = self.teams[p.team].by_name(p.actor)
                defender = self.teams[1 - p.team].by_name(p.defender)
            except KeyError:
                actor = defender = None
            if actor is not None and defender is not None:
                diag = self.dribble_move_diagnostic(
                    actor,
                    defender,
                    p.zone,
                    self._pending_duel_context(p),
                )
                edge = float(diag["attacker_edge"]) - 0.50
                p.danger = clamp(float(p.danger) + 0.10 * edge)
                p.pressure = clamp(float(p.pressure) - 0.08 * edge + 0.018 * float(diag["risk"]))

        event = super()._resolve_pending()
        if diag is not None:
            event.data.setdefault("dribble_move", diag["move"])
            event.data.setdefault("dribble_move_fit", round(float(diag["move_fit"]), 3))
            event.data.setdefault("dribble_risk", round(float(diag["risk"]), 3))
            event.data.setdefault("dribble_attacker_edge", round(float(diag["attacker_edge"]), 3))
        return event


MatchEngine = MatchEngineV13AdvancedDribbling
