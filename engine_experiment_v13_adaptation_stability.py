from __future__ import annotations

"""v1.3 refinement: tactical adaptation hysteresis.

The first contextual adaptation layer correctly reacted to observable evidence,
but broad fixture calibration showed that it was willing to change plan almost
at every available cooldown boundary.  This layer does not tune to a scoreline
or result rate.  It adds football-like inertia: a coach needs a persistent
pattern, waits longer after a change, and cannot keep re-applying the same
adjustment as though each occurrence were a new tactical idea.
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
    MAX_ADAPTATIONS_PER_TEAM = 3  # failsafe, not the normal control mechanism
    STRUCTURAL_RESPONSES = frozenset({"protect_depth", "protect_wide", "regain_control"})

    def _evidence_between(self, team: int, start: float, end: float) -> dict:
        """Pure evidence summary for a fixed historical slice.

        This mirrors the base evidence vocabulary but lets the stability layer
        distinguish a sustained pattern from several events clustered together.
        """
        opponent = 1 - team
        rows = [
            ev for ev in self.state.event_log
            if float(start) <= float(ev.minute) <= float(end)
        ]

        def side(side_team: int) -> dict:
            threat = 0.0
            wide = 0.0
            depth = 0.0
            box = 0.0
            progressions = 0
            dangerous_events = 0
            for ev in rows:
                if int(ev.team) != side_team:
                    continue
                weight = self._event_threat_weight(ev)
                threat += weight
                kind = self._event_kind(ev)
                band, lane = self._event_zone_data(ev)
                if weight >= 0.38:
                    dangerous_events += 1
                if ev.type.value == "progression":
                    progressions += 1
                if kind in {"cross", "cutback"} or lane in {"left", "right"}:
                    wide += weight * (1.0 if kind in {"cross", "cutback"} else 0.55)
                if kind in {"through_ball", "long_ball"} or ev.type.value == "offside":
                    depth += max(0.16, weight)
                if band == "box" or ev.type.value in {
                    "shot", "save", "block", "miss", "post", "goal",
                    "penalty", "rebound",
                }:
                    box += weight
            return {
                "threat": threat,
                "wide_threat": wide,
                "depth_threat": depth,
                "box_threat": box,
                "progressions": progressions,
                "dangerous_events": dangerous_events,
            }

        own = side(team)
        opp = side(opponent)
        return {
            "events": len(rows),
            "own": own,
            "opponent_recent": opp,
            "threat_gap": opp["threat"] - own["threat"],
            "wide_gap": opp["wide_threat"] - own["wide_threat"],
            "depth_gap": opp["depth_threat"] - own["depth_threat"],
        }

    def _pattern_spans_window(self, team: int, response: str, evidence: dict) -> bool:
        """Require structural evidence in both halves of the observation window."""
        if response not in self.STRUCTURAL_RESPONSES:
            return True
        window = float(evidence.get("window_minutes", self.ADAPTATION_WINDOW_MINUTES))
        end = float(self.minute)
        start = max(0.0, end - window)
        midpoint = start + (end - start) / 2.0
        first = self._evidence_between(team, start, midpoint)
        second = self._evidence_between(team, midpoint, end)

        if response == "protect_depth":
            return bool(
                first["opponent_recent"]["depth_threat"] > 0.0
                and second["opponent_recent"]["depth_threat"] > 0.0
            )
        if response == "protect_wide":
            return bool(
                first["opponent_recent"]["wide_threat"] > 0.0
                and second["opponent_recent"]["wide_threat"] > 0.0
            )
        return bool(
            first["opponent_recent"]["dangerous_events"] >= 1
            and second["opponent_recent"]["dangerous_events"] >= 1
        )

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

    def _response_used(self, team: int, response: str) -> bool:
        return any(
            int(row.get("team", -1)) == int(team) and row.get("response") == response
            for row in self._adaptation_history()
        )

    def _adaptation_profile(self, team: int) -> dict:
        raw = super()._adaptation_profile(team)
        scores = dict(raw["scores"])
        evidence = raw["evidence"]
        cooldown = self._adaptation_cooldown(team)
        minute = self.minute

        # Re-rank under the stricter stability gate. An already-applied response
        # is not treated as a fresh idea: its tactical deltas are already present.
        # A later adaptation therefore needs a genuinely different observed need.
        selected = None
        selected_score = -1.0
        selected_threshold = 1.0
        skipped_used: list[str] = []
        skipped_clustered: list[str] = []
        for response, score in sorted(scores.items(), key=lambda row: row[1], reverse=True):
            score = float(score)
            if score < 0.0:
                continue
            if self._response_used(team, response):
                skipped_used.append(response)
                continue
            threshold = self._stable_threshold(response, cooldown["count"])
            if score < threshold:
                continue
            if response in self.STRUCTURAL_RESPONSES:
                if minute < 28.0 or not self._persistent_pattern(response, evidence):
                    continue
                if not self._pattern_spans_window(team, response, evidence):
                    skipped_clustered.append(response)
                    continue
            selected = response
            selected_score = score
            selected_threshold = threshold
            break

        reasons: list[str] = []
        eligible = selected is not None
        if selected is None:
            reasons.append("insufficient_persistent_evidence")
            if skipped_used:
                reasons.append("response_already_applied")
            if skipped_clustered:
                reasons.append("pattern_not_temporally_persistent")
        if minute < 20.0:
            eligible = False
            reasons.append("too_early")
        if cooldown["count"] >= self.MAX_ADAPTATIONS_PER_TEAM:
            eligible = False
            reasons.append("team_adaptation_limit")
        if cooldown["minutes_since"] < self.ADAPTATION_COOLDOWN_MINUTES:
            eligible = False
            reasons.append("cooldown")

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
                "pattern_must_span_window": True,
                "same_response_reapplication": False,
            },
            "cooldown": {
                "count": cooldown["count"],
                "last_minute": cooldown["last_minute"],
                "minutes_since": cooldown["minutes_since"],
            },
        }


MatchEngine = MatchEngineV13AdaptationStability
