from __future__ import annotations

"""v1.3 contextual automatic-substitution layer.

The coach does not substitute because a clock threshold was reached.  A normal
change requires a concrete reason (fatigue, card exposure, tactical chase,
tactical protection or late freshness) and an acceptable bench replacement.
Before half-time, automatic changes are emergency-only, primarily injury.

The stable v1.2 engine is untouched.  This layer only wraps the current v1.3
candidate and emits ordinary substitution events through the existing public
``substitute`` API, so persistence and the live ``p`` runner see the change as
a real match event rather than a hidden roster mutation.
"""

from typing import Optional

from engine import Event, EventType, Player, PlayerState, clamp
from engine_experiment_v13_determination import MatchEngineV13Determination


VERSION = (
    "1.3-candidate-spatial-creativity-boldness-determination-offball-body-"
    "defense-marking-cover-communication-offside-overload-errors-chemistry-"
    "adaptation-stability-persistence-knockout-auto-subs"
)


class MatchEngineV13Substitutions(MatchEngineV13Determination):
    """Adds a conservative, contextual autonomous coach for substitutions."""

    AUTO_SUBSTITUTIONS_DEFAULT = True
    MIN_NORMAL_SUB_MINUTE = 55.0
    NORMAL_SUB_COOLDOWN_MINUTES = 4.5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.auto_substitutions_enabled = self.AUTO_SUBSTITUTIONS_DEFAULT

    @classmethod
    def from_state_dict(cls, data: dict) -> "MatchEngineV13Substitutions":
        obj = super().from_state_dict(data)
        obj.auto_substitutions_enabled = bool(
            data.get("auto_substitutions_enabled", cls.AUTO_SUBSTITUTIONS_DEFAULT)
        )
        return obj

    def export_state(self) -> dict:
        data = super().export_state()
        data["engine_version"] = VERSION
        data["auto_substitutions_enabled"] = bool(
            getattr(self, "auto_substitutions_enabled", self.AUTO_SUBSTITUTIONS_DEFAULT)
        )
        return data

    @staticmethod
    def _role_fit(out_position: str, in_position: str) -> float:
        """0..1 positional compatibility for a straight substitution."""
        out_pos = str(out_position).upper()
        in_pos = str(in_position).upper()
        if out_pos == in_pos:
            return 1.0
        if "GK" in {out_pos, in_pos}:
            return 0.0

        compatibility = {
            "CB": {"DM": 0.72, "LB": 0.62, "RB": 0.62},
            "LB": {"CB": 0.62, "DM": 0.58, "LW": 0.55, "RB": 0.45},
            "RB": {"CB": 0.62, "DM": 0.58, "RW": 0.55, "LB": 0.45},
            "DM": {"CM": 0.86, "CB": 0.72, "LB": 0.62, "RB": 0.62, "AM": 0.55},
            "CM": {"DM": 0.86, "AM": 0.84, "LW": 0.58, "RW": 0.58},
            "AM": {"CM": 0.84, "LW": 0.80, "RW": 0.80, "ST": 0.64, "DM": 0.55},
            "LW": {"AM": 0.80, "RW": 0.72, "ST": 0.68, "LB": 0.55, "CM": 0.58},
            "RW": {"AM": 0.80, "LW": 0.72, "ST": 0.68, "RB": 0.55, "CM": 0.58},
            "ST": {"LW": 0.70, "RW": 0.70, "AM": 0.66},
        }
        return float(compatibility.get(out_pos, {}).get(in_pos, 0.0))

    def _substitution_limit(self) -> int:
        limit = int(self.config.max_substitutions)
        if (
            self.config.allow_extra_time_substitution
            and self.minute >= 90.0
            and self.state.period_markers == [105, 120]
        ):
            limit += 1
        return limit

    def _normal_slot_ceiling(self) -> int:
        """Maximum normal changes considered by this stage of the match.

        This is a pacing ceiling, not a quota.  Reaching 55/63/70/etc. merely
        makes another change *available* if the footballing reasons justify it.
        """
        minute = float(self.minute)
        if minute < self.MIN_NORMAL_SUB_MINUTE:
            return 0
        thresholds = (55.0, 63.0, 70.0, 77.0, 84.0)
        ceiling = sum(1 for threshold in thresholds if minute >= threshold)
        if self.state.period_markers == [105, 120] and minute >= 90.0:
            ceiling = self._substitution_limit()
        return min(self._substitution_limit(), ceiling)

    def _last_substitution_minute(self, team: int) -> Optional[float]:
        for event in reversed(self.state.event_log):
            if event.type == EventType.SUBSTITUTION and int(event.team) == int(team):
                return float(event.minute)
        return None

    def _normal_change_available(self, team: int) -> bool:
        rt = self.teams[team]
        if self.minute < self.MIN_NORMAL_SUB_MINUTE:
            return False
        if rt.substitutions >= self._normal_slot_ceiling():
            return False
        last = self._last_substitution_minute(team)
        if last is not None and self.minute - last < self.NORMAL_SUB_COOLDOWN_MINUTES:
            return False
        return True

    def _substitution_stoppage_open(self) -> bool:
        if self.state.pending is not None or self.state.ended:
            return False
        if self.state.restart is not None:
            return True
        if self.state.event_log and self.state.event_log[-1].type == EventType.PERIOD_END:
            return True
        return False

    @staticmethod
    def _raw_index(player: Player, attributes: tuple[str, ...]) -> float:
        return sum(float(getattr(player, attr)) for attr in attributes) / (100.0 * len(attributes))

    @staticmethod
    def _effective_index(player: PlayerState, attributes: tuple[str, ...]) -> float:
        return sum(float(player.effective(attr)) for attr in attributes) / (100.0 * len(attributes))

    def _attack_index_raw(self, player: Player) -> float:
        return self._raw_index(
            player,
            ("pace", "passing", "vision", "dribbling", "off_ball", "finishing"),
        )

    def _attack_index_effective(self, player: PlayerState) -> float:
        return self._effective_index(
            player,
            ("pace", "passing", "vision", "dribbling", "off_ball", "finishing"),
        )

    def _defense_index_raw(self, player: Player) -> float:
        return self._raw_index(
            player,
            ("tackling", "positioning", "anticipation", "stamina", "strength", "discipline"),
        )

    def _defense_index_effective(self, player: PlayerState) -> float:
        return self._effective_index(
            player,
            ("tackling", "positioning", "anticipation", "stamina", "strength", "discipline"),
        )

    def _score_diff_for(self, team: int) -> int:
        home, away = self.score
        return int(home - away) if team == 0 else int(away - home)

    @staticmethod
    def _fatigue_threshold(minute: float) -> float:
        if minute < 55.0:
            return 0.0
        if minute < 63.0:
            return 0.64
        if minute < 70.0:
            return 0.69
        if minute < 77.0:
            return 0.73
        if minute < 84.0:
            return 0.77
        if minute < 90.0:
            return 0.80
        return 0.83

    def _outgoing_reason(self, team: int, player: PlayerState) -> Optional[dict]:
        if player.red:
            return None
        if player.injured:
            return {"reason": "injury", "urgency": 5.0}

        minute = float(self.minute)
        if minute < self.MIN_NORMAL_SUB_MINUTE:
            return None
        if player.player.position.upper() == "GK":
            return None

        threshold = self._fatigue_threshold(minute)
        if player.energy < threshold:
            severity = clamp((threshold - player.energy) / 0.24)
            return {
                "reason": "fatigue",
                "urgency": 1.35 + 1.35 * severity,
                "fatigue_threshold": threshold,
            }

        if player.yellow and minute >= 60.0:
            aggression = player.effective("aggression") / 100.0
            discipline = player.effective("discipline") / 100.0
            card_exposure = clamp(aggression * (1.0 - discipline))
            if card_exposure >= 0.24:
                return {
                    "reason": "card_risk",
                    "urgency": 1.05 + 1.20 * card_exposure,
                    "card_exposure": card_exposure,
                }

        diff = self._score_diff_for(team)
        if diff < 0 and minute >= 68.0:
            late = clamp((minute - 68.0) / 22.0)
            return {"reason": "tactical_chase", "urgency": 0.72 + 0.58 * late}
        if diff > 0 and minute >= 72.0:
            late = clamp((minute - 72.0) / 18.0)
            return {"reason": "tactical_protect", "urgency": 0.70 + 0.55 * late}
        if minute >= 78.0 and player.energy < 0.84:
            late = clamp((minute - 78.0) / 12.0)
            return {"reason": "freshness", "urgency": 0.62 + 0.45 * late}
        return None

    def _replacement_profile(
        self,
        team: int,
        outgoing: PlayerState,
        incoming: Player,
        reason: str,
    ) -> Optional[dict]:
        fit = self._role_fit(outgoing.player.position, incoming.position)
        if fit < 0.52:
            return None

        outgoing_overall = outgoing.effective("overall") / 100.0
        incoming_overall = float(incoming.overall) / 100.0
        fresh_gain = incoming_overall - outgoing_overall
        diff = self._score_diff_for(team)

        if diff < 0 or reason == "tactical_chase":
            outgoing_context = self._attack_index_effective(outgoing)
            incoming_context = self._attack_index_raw(incoming)
        elif diff > 0 or reason == "tactical_protect":
            outgoing_context = self._defense_index_effective(outgoing)
            incoming_context = self._defense_index_raw(incoming)
        else:
            outgoing_context = 0.5 * (
                self._attack_index_effective(outgoing) + self._defense_index_effective(outgoing)
            )
            incoming_context = 0.5 * (
                self._attack_index_raw(incoming) + self._defense_index_raw(incoming)
            )

        context_gain = incoming_context - outgoing_context

        if reason in {"tactical_chase", "tactical_protect"} and context_gain < 0.025:
            return None
        if reason in {"fatigue", "freshness"} and fresh_gain < -0.13:
            return None
        if reason == "card_risk" and fresh_gain < -0.16:
            return None

        score = (
            1.30 * fit
            + 0.50 * incoming_overall
            + 0.62 * incoming_context
            + 0.82 * max(-0.12, fresh_gain)
            + 0.90 * max(-0.08, context_gain)
        )
        return {
            "score": score,
            "role_fit": fit,
            "fresh_gain": fresh_gain,
            "context_gain": context_gain,
            "incoming_context": incoming_context,
            "outgoing_context": outgoing_context,
        }

    def _best_auto_substitution(self) -> Optional[dict]:
        if not self._substitution_stoppage_open():
            return None

        candidates: list[dict] = []
        limit = self._substitution_limit()
        for team, rt in enumerate(self.teams):
            if rt.substitutions >= limit or not rt.bench:
                continue

            emergency_exists = any(ps.injured and not ps.red for ps in rt.on_field)
            normal_available = self._normal_change_available(team)
            if not emergency_exists and not normal_available:
                continue

            for outgoing in rt.on_field:
                reason_info = self._outgoing_reason(team, outgoing)
                if reason_info is None:
                    continue
                reason = str(reason_info["reason"])
                if reason != "injury" and not normal_available:
                    continue

                for incoming in rt.bench:
                    profile = self._replacement_profile(team, outgoing, incoming, reason)
                    if profile is None:
                        continue
                    candidates.append(
                        {
                            "team": team,
                            "outgoing": outgoing,
                            "incoming": incoming,
                            "reason": reason,
                            "urgency": float(reason_info["urgency"]),
                            "reason_info": reason_info,
                            **profile,
                            "candidate_score": float(reason_info["urgency"]) + float(profile["score"]),
                        }
                    )

        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: (
                float(item["candidate_score"]),
                float(item["role_fit"]),
                int(item["incoming"].overall),
                -int(item["team"]),
                str(item["incoming"].name),
            ),
        )

    def auto_substitution_diagnostic(self) -> Optional[dict]:
        """Return the current best automatic change without mutating match state."""
        candidate = self._best_auto_substitution()
        if candidate is None:
            return None
        outgoing = candidate["outgoing"]
        incoming = candidate["incoming"]
        return {
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

    def _maybe_auto_substitution(self) -> Optional[Event]:
        if not bool(
            getattr(self, "auto_substitutions_enabled", self.AUTO_SUBSTITUTIONS_DEFAULT)
        ):
            return None
        candidate = self._best_auto_substitution()
        if candidate is None:
            return None

        team = int(candidate["team"])
        outgoing = candidate["outgoing"]
        incoming = candidate["incoming"]
        event = self.substitute(team, outgoing.player.name, incoming.name)
        event.data.update(
            {
                "auto": True,
                "reason": candidate["reason"],
                "out_energy": round(float(outgoing.energy), 4),
                "role_fit": round(float(candidate["role_fit"]), 4),
                "fresh_gain": round(float(candidate["fresh_gain"]), 4),
                "context_gain": round(float(candidate["context_gain"]), 4),
            }
        )
        return event

    def step(self) -> Event:
        # Never interrupt a live pending action.  At a stoppage, an autonomous
        # change is itself the next public event; the restart remains waiting for
        # the following engine beat / user ``p`` press.
        if self.state.pending is None and not self.state.ended:
            substitution = self._maybe_auto_substitution()
            if substitution is not None:
                return substitution
        return super().step()


MatchEngine = MatchEngineV13Substitutions
