from __future__ import annotations

"""Offensive communication and call signals for v1.3.

Communication changes whether a teammate becomes a clearer option and records
which football cue supported the action. It does not add passing, vision,
finishing or pace. Pair familiarity is reused where available so this layer
connects to the existing shared-understanding system instead of inventing a
second chemistry model.
"""

from engine import Band, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_set_piece_defense import MatchEngineV13SetPieceDefense


class MatchEngineV13OffensiveCommunication(MatchEngineV13SetPieceDefense):
    def offensive_communication_diagnostic(
        self,
        team: int,
        actor: PlayerState,
        receiver: PlayerState,
        zone: Zone,
        *,
        action: str | None = None,
        ctx: dict | None = None,
    ) -> dict:
        context = ctx or {}
        caller = clamp(
            (
                0.36 * actor.effective("vision")
                + 0.28 * actor.effective("composure")
                + 0.20 * actor.effective("anticipation")
                + 0.16 * actor.effective("technique")
            ) / 100.0
        )
        reader = clamp(
            (
                0.34 * receiver.effective("anticipation")
                + 0.31 * receiver.effective("off_ball")
                + 0.21 * receiver.effective("composure")
                + 0.14 * receiver.effective("vision")
            ) / 100.0
        )
        familiarity = 0.50
        pair_fn = getattr(self, "pair_familiarity", None)
        if callable(pair_fn):
            familiarity = clamp(
                float(pair_fn(team, actor.player.name, receiver.player.name))
            )
        pressure = clamp(float(context.get("pressure", 0.45)))
        space_behind = clamp(float(context.get("space_behind", 0.40)))
        quality = clamp(
            0.46
            + 0.25 * (caller - 0.68)
            + 0.25 * (reader - 0.68)
            + 0.18 * (familiarity - 0.50)
            - 0.08 * max(0.0, pressure - 0.55)
        )

        action = str(action or "")
        actor_pos = actor.player.position.upper()
        receiver_pos = receiver.player.position.upper()
        if action == "switch" or (
            zone.lane != Lane.CENTER
            and actor_pos in {"CM", "DM", "AM", "LB", "RB"}
            and receiver_pos in {"LW", "RW", "LB", "RB"}
        ):
            signal = "switch_call"
        elif action in {"through_ball", "progressive_pass"} and space_behind >= 0.48:
            signal = "run_call"
        elif action in {"cutback", "cross"} and receiver_pos in {"ST", "AM", "LW", "RW"}:
            signal = "box_call"
        elif action in {"safe_pass", "progressive_pass"} and receiver_pos in {"CM", "DM", "AM"}:
            signal = "third_man_cue"
        elif zone.band in {Band.ATT, Band.BOX} and actor_pos in {"AM", "ST", "LW", "RW"}:
            signal = "leave_or_dummy"
        else:
            signal = "call_for_ball"
        return {
            "team": int(team),
            "actor": actor.player.name,
            "receiver": receiver.player.name,
            "signal": signal,
            "quality": quality,
            "caller_read": caller,
            "receiver_read": reader,
            "familiarity": familiarity,
            "active": bool(quality >= 0.54),
        }

    def _base_target_weights(
        self,
        team: int,
        zone: Zone,
        actor: PlayerState | None,
        ctx: dict | None = None,
    ):
        rows = super()._base_target_weights(team, zone, actor, ctx)
        if actor is None:
            return rows
        out = []
        for receiver, weight in rows:
            diag = self.offensive_communication_diagnostic(
                team, actor, receiver, zone, ctx=ctx
            )
            # Coordination makes an option clearer; it does not make the pass
            # itself more accurate once selected.
            factor = 1.0 + 0.12 * (float(diag["quality"]) - 0.50)
            out.append((receiver, float(weight) * clamp(factor, 0.96, 1.06)))
        return out

    def _execute_decision(self, team, actor, zone, decision, ctx):
        event = super()._execute_decision(team, actor, zone, decision, ctx)
        data = event.data if isinstance(event.data, dict) else {}
        receiver_name = data.get("receiver") or data.get("target") or data.get("next_player")
        if receiver_name and str(receiver_name) != actor.player.name:
            try:
                receiver = self.teams[int(team)].by_name(str(receiver_name))
            except KeyError:
                receiver = None
            if receiver is not None:
                diag = self.offensive_communication_diagnostic(
                    int(team), actor, receiver, zone, action=str(decision), ctx=ctx
                )
                if diag["active"]:
                    event.data.setdefault("offensive_communication", True)
                    event.data.setdefault("communication_signal", diag["signal"])
                    event.data.setdefault("communication_quality", round(float(diag["quality"]), 3))
                    event.data.setdefault("communication_pair", [actor.player.name, receiver.player.name])
        return event


MatchEngine = MatchEngineV13OffensiveCommunication

__all__ = ["MatchEngineV13OffensiveCommunication", "MatchEngine"]
