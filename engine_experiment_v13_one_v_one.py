from __future__ import annotations

"""v1.3 duel/box stage 2: richer one-versus-one defending."""

from engine import Lane, PlayerState, Zone, clamp
from engine_experiment_v13_dribbling import MatchEngineV13AdvancedDribbling
from engine_experiment_v13_passing_texture import _stable_fraction

VERSION = "1.3-candidate-one-v-one-defense"


class MatchEngineV13OneVOne(MatchEngineV13AdvancedDribbling):
    def one_v_one_defense_diagnostic(
        self,
        defender: PlayerState,
        attacker: PlayerState,
        zone: Zone,
        ctx: dict,
    ) -> dict:
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        space = clamp(float(ctx.get("space", 0.5)))
        tackling = clamp(defender.effective("tackling") / 100.0)
        positioning = clamp(defender.effective("positioning") / 100.0)
        anticipation = clamp(defender.effective("anticipation") / 100.0)
        pace = clamp(defender.effective("pace") / 100.0)
        strength = clamp(defender.effective("strength") / 100.0)
        discipline = clamp(defender.effective("discipline") / 100.0)
        attacker_pace = clamp(attacker.effective("pace") / 100.0)
        attacker_dribble = clamp(attacker.effective("dribbling") / 100.0)

        quality = clamp(
            0.29 * tackling
            + 0.25 * positioning
            + 0.18 * anticipation
            + 0.12 * pace
            + 0.08 * strength
            + 0.08 * discipline
        )
        threat = clamp(0.52 * attacker_dribble + 0.32 * attacker_pace + 0.16 * space)
        foot = str(getattr(attacker.player, "preferred_foot", "R")).strip().upper()
        can_show_weak = foot in {"R", "L"}
        fraction = _stable_fraction(
            "one-v-one-defense",
            self.seed,
            round(self.state.second, 3),
            defender.player.name,
            attacker.player.name,
            zone.lane.value,
        )

        if defender.yellow:
            stance = "contain"
        elif space >= 0.66 and attacker_pace > pace + 0.05:
            stance = "drop_jockey"
        elif zone.lane != Lane.CENTER and positioning >= 0.62:
            stance = "show_touchline"
        elif can_show_weak and anticipation >= 0.60 and fraction < 0.48:
            stance = "show_weak_foot"
        elif pressure >= 0.64 and tackling >= 0.68 and discipline >= 0.58:
            stance = "step_in"
        else:
            stance = "jockey"

        weak_side = None
        if stance == "show_weak_foot":
            weak_side = "left" if foot == "R" else "right"

        stance_effect = {
            "contain": (0.020, -0.018, 0.010),
            "drop_jockey": (-0.012, -0.026, 0.055),
            "show_touchline": (0.014, -0.028, 0.040),
            "show_weak_foot": (0.018, -0.030, 0.035),
            "step_in": (0.052, -0.038, 0.090),
            "jockey": (0.025, -0.024, 0.028),
        }[stance]
        pressure_delta, danger_delta, space_tradeoff = stance_effect
        control = clamp(0.54 + 0.55 * (quality - threat) + 0.10 * pressure, 0.16, 0.86)
        return {
            "stance": stance,
            "quality": quality,
            "attacker_threat": threat,
            "control": control,
            "pressure_delta": pressure_delta * quality,
            "danger_delta": danger_delta * quality,
            "space_tradeoff": space_tradeoff,
            "weak_side": weak_side,
            "can_show_weak_foot": can_show_weak,
        }

    def _resolve_pending(self):
        p = self.state.pending
        diag = None
        if p is not None and p.kind == "dribble" and p.defender:
            try:
                attacker = self.teams[p.team].by_name(p.actor)
                defender = self.teams[1 - p.team].by_name(p.defender)
            except KeyError:
                attacker = defender = None
            if attacker is not None and defender is not None:
                ctx = self._pending_duel_context(p)
                diag = self.one_v_one_defense_diagnostic(defender, attacker, p.zone, ctx)
                p.pressure = clamp(float(p.pressure) + float(diag["pressure_delta"]))
                p.danger = clamp(float(p.danger) + float(diag["danger_delta"]))
                if diag["stance"] == "step_in":
                    p.danger = clamp(float(p.danger) + 0.020 * (1.0 - float(diag["control"])))

        event = super()._resolve_pending()
        if diag is not None:
            event.data.setdefault("defensive_1v1_stance", diag["stance"])
            event.data.setdefault("defensive_1v1_quality", round(float(diag["quality"]), 3))
            event.data.setdefault("defensive_1v1_control", round(float(diag["control"]), 3))
            event.data.setdefault("defensive_1v1_space_tradeoff", round(float(diag["space_tradeoff"]), 3))
            if diag["weak_side"]:
                event.data.setdefault("defensive_steering_side", diag["weak_side"])
        return event


MatchEngine = MatchEngineV13OneVOne
