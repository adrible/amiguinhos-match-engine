from __future__ import annotations

"""v1.3 refinement: tactical adaptation hysteresis.

The first contextual adaptation layer correctly reacted to observable evidence,
but broad fixture calibration showed that it was willing to change plan almost
at every available cooldown boundary.  This layer does not tune to a scoreline
or result rate.  It adds football-like inertia: a coach needs a persistent
pattern, waits longer after a change, and cannot keep reconfiguring the side.
"""

from engine_experiment_v13_adaptation import MatchEngineV13Adaptation


VERSION = (
    "1.3-candidate-spatial-creativity-boldness-offball-body-defense-"
    "marking-cover-communication-offside-overload-errors-chemistry-"
    "adaptation-hysteresis"
)


class MatchEngineV13AdaptationStability(MatchEngineV13Adaptation):
    """Requires persistent evidence and adds inertia between tactical changes."""

    ADAPTATION_COOLDOWN_MINUTES = 16.0
    SAME_RESPONSE_COOLDOWN_MINUTES = 24.0
    MAX_ADAPTATIONS_PER_TEAM = 3

    @staticmethod
    def _persistent_pattern(response: str, evidence: dict) -> bool:
        opp = evidence["opponent_recent"]
        if response == "protect_depth":
            return bool(
                opp["depth_threat"] >= 0.90
                and evidence["depth_gap"] >= 0.35
                and evidence["events_in_window"] >= 4
            )
        if response == "protect_wide":
            return bool(
                opp["wide_threat"] >= 1.00
                and evidence["wide_gap"] >= 0.38
                and evidence["events_in_window"] >= 4
            )
        if response == "regain_control":
            return bool(
                opp["threat"] >= 1.75
                and evidence["threat_gap"] >= 1.10
                and opp["dangerous_events"] >= 2
                and evidence["events_in_window"] >= 4
            )
        return True

    @staticmethod
    def _stable_threshold(response: str, prior_count: int) -> float:
        if response in {"chase_game", "protect_lead"}:
            base = 0.62
            repeat_cost = 0.020
        else:
            base = 0.60
            repeat_cost = 0.035
        return base + repeat_cost * min(2, int(prior_count))

    def _adaptation_profile(self, team: int) -> dict:
        raw = super()._adaptation_profile(team)
        scores = dict(raw["scores"])
        evidence = raw["evidence"]
        cooldown = self._adaptation_cooldown(team)
        minute = self.minute

        # Re-rank under the stricter stability gate. If the strongest pattern is
        # not persistent, a legitimate late score response can still be chosen.
        selected = None
        selected_score = -1.0
        selected_threshold = 1.0
        for response, score in sorted(scores.items(), key=lambda row: row[1], reverse=True):
            score = float(score)
            if score < 0.0:
                continue
            threshold = self._stable_threshold(response, cooldown["count"])
            if score < threshold:
                continue
            if response not in {"chase_game", "protect_lead"}:
                if minute < 28.0 or not self._persistent_pattern(response, evidence):
                    continue
            selected = response
            selected_score = score
            selected_threshold = threshold
            break

        reasons: list[str] = []
        eligible = selected is not None
        if selected is None:
            reasons.append("insufficient_persistent_evidence")
        if minute < 20.0:
            eligible = False
            reasons.append("too_early")
        if cooldown["count"] >= self.MAX_ADAPTATIONS_PER_TEAM:
            eligible = False
            reasons.append("team_adaptation_limit")
        if cooldown["minutes_since"] < self.ADAPTATION_COOLDOWN_MINUTES:
            eligible = False
            reasons.append("cooldown")

        if selected is not None:
            same = [r for r in cooldown["history"] if r.get("response") == selected]
            if same:
                last_same = max(float(r.get("minute", -999.0)) for r in same)
                if minute - last_same < self.SAME_RESPONSE_COOLDOWN_MINUTES:
                    eligible = False
                    reasons.append("same_response_cooldown")

        return {
            **raw,
            "response": selected,
            "response_score": selected_score,
            "threshold": selected_threshold,
            "eligible": eligible,
            "blocked_reasons": reasons,
            "stability_gate": {
                "cooldown_minutes": self.ADAPTATION_COOLDOWN_MINUTES,
                "same_response_cooldown_minutes": self.SAME_RESPONSE_COOLDOWN_MINUTES,
                "max_adaptations_per_team": self.MAX_ADAPTATIONS_PER_TEAM,
                "persistent_pattern_required": True,
            },
            "cooldown": {
                "count": cooldown["count"],
                "last_minute": cooldown["last_minute"],
                "minutes_since": cooldown["minutes_since"],
            },
        }


MatchEngine = MatchEngineV13AdaptationStability
