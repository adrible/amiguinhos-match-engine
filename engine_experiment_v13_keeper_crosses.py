from __future__ import annotations

"""v1.3 duel/box stage 5: goalkeeper decisions on crosses."""

from engine import Band, DEF_C, EventType, PendingAction, PlayerState, clamp
from engine_experiment_v13_crossing_aerial import MatchEngineV13CrossingAerial
from engine_experiment_v13_passing_texture import _stable_fraction

VERSION = "1.3-candidate-keeper-crosses"


class MatchEngineV13KeeperCrosses(MatchEngineV13CrossingAerial):
    def keeper_cross_diagnostic(
        self,
        keeper: PlayerState,
        p: PendingAction,
        attacker: PlayerState,
        *,
        cross_context: dict | None = None,
    ) -> dict:
        handling = clamp(keeper.effective("handling") / 100.0)
        positioning = clamp(keeper.effective("gk_positioning") / 100.0)
        reflexes = clamp(keeper.effective("reflexes") / 100.0)
        strength = clamp(keeper.effective("strength") / 100.0)
        anticipation = clamp(keeper.effective("anticipation") / 100.0)
        command_score = clamp(
            0.30 * handling
            + 0.27 * positioning
            + 0.16 * reflexes
            + 0.14 * strength
            + 0.13 * anticipation
        )
        cross_type = (cross_context or {}).get("cross_type")
        high_ball = p.body_part == "head" or cross_type in {"whipped", "floated", "driven"}
        crowd = clamp(float(p.pressure) + (0.10 if p.origin == "corner" else 0.0))
        come_probability = clamp(
            0.07
            + 0.54 * command_score
            + (0.10 if high_ball else -0.08)
            - 0.22 * crowd
            - 0.12 * float(p.danger),
            0.04,
            0.72,
        )
        fraction = _stable_fraction(
            "keeper-cross",
            self.seed,
            round(self.state.second, 3),
            keeper.player.name,
            attacker.player.name,
            p.origin,
            cross_type or "unknown",
        )
        if fraction >= come_probability:
            decision = "hold_line"
        elif handling >= 0.66 and command_score >= 0.60:
            decision = "claim"
        else:
            decision = "punch"
        success_probability = clamp(
            0.28
            + 0.46 * command_score
            + 0.08 * handling
            - 0.18 * crowd
            - 0.14 * float(p.danger),
            0.18,
            0.84,
        )
        return {
            "decision": decision,
            "command_score": command_score,
            "come_probability": come_probability,
            "success_probability": success_probability,
            "cross_type": cross_type,
            "high_ball": high_ball,
        }

    def _resolve_shot(self, p):
        relevant = p.origin in {"cross", "corner", "free_kick"} and p.zone.band == Band.BOX
        diag = None
        failed_command = False
        if relevant:
            keeper = self._goalkeeper(1 - p.team)
            try:
                attacker = self.teams[p.team].by_name(p.actor)
            except KeyError:
                attacker = self._named_or_fallback(p.team, p.actor, role="actor", zone=p.zone)
            marker = self._v13_cross_context if isinstance(getattr(self, "_v13_cross_context", None), dict) else None
            diag = self.keeper_cross_diagnostic(keeper, p, attacker, cross_context=marker)
            if diag["decision"] in {"claim", "punch"}:
                success = self.rng.random() < float(diag["success_probability"])
                self._drain(keeper, 0.0015 if diag["decision"] == "claim" else 0.0020)
                if success:
                    defending = 1 - p.team
                    self._v13_cross_context = None
                    if diag["decision"] == "claim":
                        self._switch_possession(defending, DEF_C, transition=0.0)
                        return self._emit(
                            EventType.INFO,
                            defending,
                            2,
                            "keeper_claims_cross",
                            keeper=keeper.player.name,
                            target=attacker.player.name,
                            keeper_cross_decision="claim",
                            keeper_command_score=round(float(diag["command_score"]), 3),
                            cross_type=diag.get("cross_type"),
                        )
                    self._switch_possession(defending, DEF_C, transition=0.14)
                    return self._emit(
                        EventType.PROGRESSION,
                        defending,
                        2,
                        "keeper_punches_cross_clear",
                        keeper=keeper.player.name,
                        target=attacker.player.name,
                        keeper_cross_decision="punch",
                        keeper_command_score=round(float(diag["command_score"]), 3),
                        cross_type=diag.get("cross_type"),
                    )
                failed_command = True
                p.danger = clamp(float(p.danger) + 0.045)
                p.pressure = clamp(float(p.pressure) - 0.030)

        event = super()._resolve_shot(p)
        if diag is not None:
            event.data.setdefault("keeper_cross_decision", diag["decision"])
            event.data.setdefault("keeper_command_score", round(float(diag["command_score"]), 3))
            event.data.setdefault("keeper_cross_success_probability", round(float(diag["success_probability"]), 3))
            if failed_command:
                event.data.setdefault("keeper_cross_failed", True)
            self._v13_cross_context = None
        return event


MatchEngine = MatchEngineV13KeeperCrosses
