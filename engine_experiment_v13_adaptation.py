from __future__ import annotations

"""Experimental v1.3 layer: contextual in-match tactical adaptation.

The stable engine already has an optional score-only auto-adaptation hook.  This
candidate replaces that hook only in v1.3 with a deterministic, evidence-based
coach reaction.  The coach reads a short recent event window plus the current
score/minute, selects at most one primary tactical response per team, applies
small bounded changes, and then observes a cooldown.

Adaptation never sees future events, never targets a desired scoreline/stat
count, and consumes no RNG.  A response changes real tactical trade-offs rather
than giving the team a generic quality bonus.
"""

from typing import Optional

from engine import Event, EventType, clamp
from engine_experiment_v13_chemistry import MatchEngineV13Chemistry


VERSION = (
    "1.3-candidate-spatial-creativity-boldness-offball-body-defense-"
    "marking-cover-communication-offside-overload-errors-chemistry-adaptation"
)


class MatchEngineV13Adaptation(MatchEngineV13Chemistry):
    """Adds bounded tactical reactions to recent, observable match evidence."""

    ADAPTATION_WINDOW_MINUTES = 12.0
    ADAPTATION_COOLDOWN_MINUTES = 9.0
    SAME_RESPONSE_COOLDOWN_MINUTES = 14.0
    MAX_ADAPTATIONS_PER_TEAM = 4

    # ---------------------------- recent evidence ----------------------------

    @staticmethod
    def _event_threat_weight(ev: Event) -> float:
        return {
            EventType.GOAL: 1.30,
            EventType.PENALTY: 1.05,
            EventType.DANGER: 0.78,
            EventType.SHOT: 0.50,
            EventType.SAVE: 0.48,
            EventType.BLOCK: 0.43,
            EventType.POST: 0.58,
            EventType.MISS: 0.38,
            EventType.REBOUND: 0.36,
            EventType.CORNER: 0.24,
            EventType.FREE_KICK: 0.18,
            EventType.PROGRESSION: 0.12,
        }.get(ev.type, 0.0)

    @staticmethod
    def _event_kind(ev: Event) -> str:
        data = ev.data if isinstance(ev.data, dict) else {}
        return str(data.get("kind") or data.get("origin") or ev.text_key or "").lower()

    @staticmethod
    def _event_zone_data(ev: Event) -> tuple[Optional[str], Optional[str]]:
        data = ev.data if isinstance(ev.data, dict) else {}
        zone = data.get("zone")
        if isinstance(zone, dict):
            return zone.get("band"), zone.get("lane")
        return None, None

    def _recent_tactical_evidence(
        self,
        team: int,
        *,
        window_minutes: Optional[float] = None,
    ) -> dict:
        window = float(window_minutes or self.ADAPTATION_WINDOW_MINUTES)
        start = max(0.0, self.minute - window)
        opponent = 1 - team
        rows = [
            ev for ev in self.state.event_log
            if start <= float(ev.minute) <= self.minute
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
                if ev.type == EventType.PROGRESSION:
                    progressions += 1

                if kind in {"cross", "cutback"} or lane in {"left", "right"}:
                    wide += weight * (1.0 if kind in {"cross", "cutback"} else 0.55)
                if kind in {"through_ball", "long_ball"} or ev.type == EventType.OFFSIDE:
                    depth += max(0.16, weight)
                if band == "box" or ev.type in {
                    EventType.SHOT, EventType.SAVE, EventType.BLOCK,
                    EventType.MISS, EventType.POST, EventType.GOAL,
                    EventType.PENALTY, EventType.REBOUND,
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
            "team": team,
            "opponent": opponent,
            "window_minutes": window,
            "window_start": start,
            "events_in_window": len(rows),
            "own": own,
            "opponent_recent": opp,
            "threat_gap": opp["threat"] - own["threat"],
            "wide_gap": opp["wide_threat"] - own["wide_threat"],
            "depth_gap": opp["depth_threat"] - own["depth_threat"],
            "box_gap": opp["box_threat"] - own["box_threat"],
        }

    # ---------------------------- response selection ----------------------------

    def _adaptation_history(self) -> list[dict]:
        history = getattr(self, "_v13_adaptation_history", None)
        return history if isinstance(history, list) else []

    def _adaptation_cooldown(self, team: int) -> dict:
        rows = [r for r in self._adaptation_history() if int(r.get("team", -1)) == team]
        last_minute = max((float(r.get("minute", -999.0)) for r in rows), default=-999.0)
        return {
            "count": len(rows),
            "last_minute": last_minute,
            "minutes_since": self.minute - last_minute,
            "history": rows,
        }

    def _adaptation_profile(self, team: int) -> dict:
        evidence = self._recent_tactical_evidence(team)
        cooldown = self._adaptation_cooldown(team)
        opponent = 1 - team
        score_diff = self.stats[team].goals - self.stats[opponent].goals
        minute = self.minute
        own = evidence["own"]
        opp = evidence["opponent_recent"]
        threat_gap = float(evidence["threat_gap"])
        wide_gap = float(evidence["wide_gap"])
        depth_gap = float(evidence["depth_gap"])

        scores = {
            "chase_game": -1.0,
            "protect_lead": -1.0,
            "protect_depth": -1.0,
            "protect_wide": -1.0,
            "regain_control": -1.0,
        }

        # Score context matters, but is not the only observation. Urgency grows
        # continuously rather than at a scripted "make something happen" minute.
        if score_diff < 0 and minute >= 58.0:
            urgency = clamp((minute - 58.0) / 32.0)
            deficit = min(3, abs(score_diff))
            scores["chase_game"] = (
                0.56 + 0.07 * deficit + 0.16 * urgency
                + 0.035 * max(0.0, threat_gap)
            )

        if score_diff > 0 and minute >= 68.0:
            urgency = clamp((minute - 68.0) / 22.0)
            lead = min(3, score_diff)
            scores["protect_lead"] = (
                0.54 + 0.055 * lead + 0.15 * urgency
                + 0.035 * max(0.0, threat_gap)
            )

        # Pattern reactions are allowed earlier, but require actual recent
        # evidence. They do not infer anything from future possession or xG.
        if minute >= 24.0 and evidence["events_in_window"] >= 3:
            if opp["depth_threat"] >= 0.62 and depth_gap >= 0.22:
                scores["protect_depth"] = (
                    0.47 + 0.18 * clamp(depth_gap / 1.5)
                    + 0.08 * clamp(opp["depth_threat"] / 2.0)
                    + 0.05 * clamp(threat_gap / 2.0)
                )
            if opp["wide_threat"] >= 0.72 and wide_gap >= 0.24:
                scores["protect_wide"] = (
                    0.46 + 0.18 * clamp(wide_gap / 1.6)
                    + 0.08 * clamp(opp["wide_threat"] / 2.2)
                    + 0.04 * clamp(threat_gap / 2.0)
                )
            if opp["threat"] >= 1.35 and threat_gap >= 0.90:
                scores["regain_control"] = (
                    0.46 + 0.17 * clamp(threat_gap / 2.5)
                    + 0.07 * clamp(opp["box_threat"] / 2.0)
                    + 0.04 * clamp(opp["dangerous_events"] / 5.0)
                )

        response, response_score = max(scores.items(), key=lambda row: row[1])
        threshold = 0.58 if response in {"chase_game", "protect_lead"} else 0.55
        eligible = bool(response_score >= threshold)
        reasons = []

        if minute < 20.0:
            eligible = False
            reasons.append("too_early")
        if cooldown["count"] >= self.MAX_ADAPTATIONS_PER_TEAM:
            eligible = False
            reasons.append("team_adaptation_limit")
        if cooldown["minutes_since"] < self.ADAPTATION_COOLDOWN_MINUTES:
            eligible = False
            reasons.append("cooldown")

        same = [r for r in cooldown["history"] if r.get("response") == response]
        if same:
            last_same = max(float(r.get("minute", -999.0)) for r in same)
            if minute - last_same < self.SAME_RESPONSE_COOLDOWN_MINUTES:
                eligible = False
                reasons.append("same_response_cooldown")

        return {
            "team": team,
            "minute": minute,
            "score_diff": score_diff,
            "response": response if response_score >= 0.0 else None,
            "response_score": response_score,
            "threshold": threshold,
            "eligible": eligible,
            "blocked_reasons": reasons,
            "scores": scores,
            "evidence": evidence,
            "cooldown": {
                "count": cooldown["count"],
                "last_minute": cooldown["last_minute"],
                "minutes_since": cooldown["minutes_since"],
            },
        }

    # ---------------------------- bounded tactical trade-offs ----------------------------

    @staticmethod
    def _response_deltas(response: str) -> dict[str, float]:
        return {
            "chase_game": {
                "mentality": 0.070,
                "tempo": 0.040,
                "risk": 0.050,
                "pressing": 0.035,
                "defensive_line": 0.020,
                "compactness": -0.015,
            },
            "protect_lead": {
                "mentality": -0.055,
                "tempo": -0.020,
                "risk": -0.045,
                "compactness": 0.035,
                "defensive_line": -0.025,
                "pressing": -0.015,
                "counter": 0.020,
            },
            "protect_depth": {
                "defensive_line": -0.045,
                "pressing": -0.025,
                "compactness": 0.025,
                "directness": 0.015,
                "risk": -0.010,
            },
            "protect_wide": {
                "width": 0.040,
                "compactness": -0.025,
                "pressing": -0.015,
                "risk": -0.010,
            },
            "regain_control": {
                "tempo": -0.030,
                "risk": -0.035,
                "directness": -0.030,
                "mentality": -0.015,
                "pressing": 0.015,
                "compactness": 0.015,
            },
        }.get(response, {})

    def _adaptation_preview(self, team: int, response: Optional[str]) -> dict:
        tactics = self.teams[team].team.tactics
        before = dict(tactics.__dict__)
        if not response:
            return {"before": before, "after": dict(before), "changes": {}}
        after = dict(before)
        for key, delta in self._response_deltas(response).items():
            low = -1.0 if key == "mentality" else 0.0
            after[key] = clamp(float(after[key]) + float(delta), low, 1.0)
        changes = {
            key: {"before": before[key], "after": after[key]}
            for key in after
            if after[key] != before[key]
        }
        return {"before": before, "after": after, "changes": changes}

    def _apply_tactical_adaptation(self, team: int, profile: dict) -> Optional[dict]:
        if not profile.get("eligible") or not profile.get("response"):
            return None
        response = str(profile["response"])
        preview = self._adaptation_preview(team, response)
        if not preview["changes"]:
            return None

        self.set_tactics(
            team,
            **{key: row["after"] for key, row in preview["changes"].items()},
        )
        history = getattr(self, "_v13_adaptation_history", None)
        if not isinstance(history, list):
            history = []
            self._v13_adaptation_history = history
        record = {
            "minute": round(self.minute, 4),
            "team": team,
            "response": response,
            "response_score": float(profile["response_score"]),
            "score_diff": int(profile["score_diff"]),
            "changes": preview["changes"],
            "evidence": profile["evidence"],
        }
        history.append(record)
        return record

    def _maybe_auto_adapt(self) -> None:
        # The stable _open_play_step invokes this hook only when the config flag
        # is enabled; keep the guard as well so direct calls remain safe.
        if not getattr(self.config, "auto_tactical_adaptation", False):
            return
        for team in (0, 1):
            profile = self._adaptation_profile(team)
            self._apply_tactical_adaptation(team, profile)

    # ---------------------------- diagnostics ----------------------------

    def tactical_adaptation_diagnostic(self, team: int) -> dict:
        """Pure recommendation/preview; consumes no RNG and changes no tactics."""
        profile = self._adaptation_profile(team)
        return {
            **profile,
            "preview": self._adaptation_preview(team, profile.get("response")),
        }

    def adaptation_history(self, team: Optional[int] = None) -> list[dict]:
        rows = [dict(r) for r in self._adaptation_history()]
        if team is None:
            return rows
        return [r for r in rows if int(r.get("team", -1)) == int(team)]


MatchEngine = MatchEngineV13Adaptation
