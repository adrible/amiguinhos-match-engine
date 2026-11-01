from __future__ import annotations

"""v1.3 strategic substitution layer.

This layer deepens the existing autonomous substitution coach without adding
quotas or outcome knowledge. It can react to meaningful continuing injuries,
prices positional familiarity through the multi-position layer, and considers
penalty-taking quality only very late in a tied extra-time match.
"""

from engine import Player, PlayerState, clamp
from engine_experiment_v13_positions import MatchEngineV13Positions


class MatchEngineV13SubstitutionStrategy(MatchEngineV13Positions):
    CONTINUING_INJURY_SUB_MINUTE = 55.0
    CONTINUING_INJURY_THRESHOLD = 0.105
    SHOOTOUT_PREP_MINUTE = 116.0
    SHOOTOUT_PREP_MIN_GAIN = 0.065

    @staticmethod
    def _raw_penalty_quality(player: Player) -> float:
        return clamp(
            0.32 * float(player.finishing) / 100.0
            + 0.28 * float(player.composure) / 100.0
            + 0.20 * float(player.technique) / 100.0
            + 0.10 * float(player.overall) / 100.0
            + 0.10 * float(player.long_shots) / 100.0
        )

    def _effective_penalty_quality(self, player: PlayerState) -> float:
        inherited = getattr(self, "_penalty_taker_quality", None)
        if callable(inherited):
            return float(inherited(player))
        return clamp(
            0.32 * player.effective("finishing") / 100.0
            + 0.28 * player.effective("composure") / 100.0
            + 0.20 * player.effective("technique") / 100.0
            + 0.10 * float(player.player.overall) / 100.0
            + 0.10 * player.effective("long_shots") / 100.0
        )

    def _continuing_injury_reason(self, team: int, player: PlayerState):
        if self.minute < self.CONTINUING_INJURY_SUB_MINUTE or player.red or player.injured:
            return None
        getter = getattr(self, "current_injury_status", None)
        if not callable(getter):
            return None
        status = getter(team, player.player.name)
        if not isinstance(status, dict):
            return None
        if status.get("recovered") or not status.get("can_continue", False):
            return None
        limitation = float(status.get("current_limitation", 0.0))
        if limitation < self.CONTINUING_INJURY_THRESHOLD:
            return None
        recovery = status.get("recovery_minutes")
        urgency = 1.08 + 3.6 * limitation
        if recovery is not None:
            remaining = max(
                0.0,
                float(recovery)
                - max(0.0, float(self.minute) - float(status.get("onset_minute", self.minute))),
            )
            urgency += 0.18 * clamp(remaining / 30.0)
        return {
            "reason": "injury_management",
            "urgency": urgency,
            "functional_limitation": limitation,
            "injury_region": status.get("region"),
            "medical_action": status.get("medical_action"),
        }

    def _shootout_preparation_context(self) -> bool:
        return bool(
            self.config.allow_extra_time
            and self.state.period_markers == [105, 120]
            and self.minute >= self.SHOOTOUT_PREP_MINUTE
            and self.score[0] == self.score[1]
            and not self.state.ended
        )

    def _outgoing_reason(self, team: int, player: PlayerState):
        existing = super()._outgoing_reason(team, player)
        if existing is not None and str(existing.get("reason")) == "injury":
            return existing

        managed = self._continuing_injury_reason(team, player)
        if managed is not None:
            return managed

        if existing is not None:
            return existing

        if self._shootout_preparation_context() and player.player.position.upper() != "GK":
            quality = self._effective_penalty_quality(player)
            # This only nominates a player for evaluation. The incoming player
            # must still provide a material penalty improvement and positional fit.
            return {
                "reason": "shootout_preparation",
                "urgency": 0.58 + 0.35 * (1.0 - quality),
                "penalty_quality": quality,
            }
        return None

    def _replacement_profile(self, team, outgoing, incoming, reason):
        profile = super()._replacement_profile(team, outgoing, incoming, reason)
        if profile is None:
            return None

        outgoing_pen = self._effective_penalty_quality(outgoing)
        incoming_pen = self._raw_penalty_quality(incoming)
        penalty_gain = incoming_pen - outgoing_pen

        if reason == "shootout_preparation":
            if penalty_gain < self.SHOOTOUT_PREP_MIN_GAIN:
                return None
            profile["score"] = float(profile["score"]) + 1.65 * penalty_gain
        elif self.state.period_markers == [105, 120] and self.minute >= 108.0 and self.score[0] == self.score[1]:
            # In a tied extra-time match penalty ability is a mild tiebreaker,
            # never the main reason for replacing a better football fit.
            profile["score"] = float(profile["score"]) + 0.35 * penalty_gain

        if reason == "injury_management":
            limitation = float(
                self.current_injury_status(team, outgoing.player.name).get("current_limitation", 0.0)
            )
            profile["score"] = float(profile["score"]) + 1.10 * limitation

        profile["penalty_gain"] = penalty_gain
        profile["incoming_penalty_quality"] = incoming_pen
        profile["outgoing_penalty_quality"] = outgoing_pen
        return profile

    def auto_substitution_diagnostic(self):
        candidate = self._best_auto_substitution()
        if candidate is None:
            return None
        outgoing = candidate["outgoing"]
        incoming = candidate["incoming"]
        data = {
            "team": int(candidate["team"]),
            "out": outgoing.player.name,
            "in": incoming.name,
            "reason": candidate["reason"],
            "out_energy": float(outgoing.energy),
            "role_fit": float(candidate["role_fit"]),
            "fresh_gain": float(candidate["fresh_gain"]),
            "context_gain": float(candidate["context_gain"]),
            "candidate_score": float(candidate["candidate_score"]),
        }
        for key in (
            "position_familiarity",
            "assigned_position",
            "natural_position",
            "penalty_gain",
            "incoming_penalty_quality",
            "outgoing_penalty_quality",
        ):
            if key in candidate:
                value = candidate[key]
                data[key] = float(value) if isinstance(value, (int, float)) else value
        return data

    def _maybe_auto_substitution(self):
        event = super()._maybe_auto_substitution()
        if event is None:
            return None
        if self.state.period_markers == [105, 120] and self.minute >= 90.0:
            event.data["extra_time_context"] = True
            event.data["substitution_limit"] = int(self._substitution_limit())
        return event


MatchEngine = MatchEngineV13SubstitutionStrategy

__all__ = ["MatchEngineV13SubstitutionStrategy", "MatchEngine"]
