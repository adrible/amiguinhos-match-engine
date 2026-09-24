from __future__ import annotations

"""Final v1.3 tactical-adaptation refinement: progressive coaching inertia.

The existing hysteresis layer already prevents rapid oscillation and repeated
structural labels. Extended A/B evaluation nevertheless showed that too many
team-matches still reached a third tactical reconfiguration. This layer keeps
all prior evidence rules intact and changes only the *cost of repeated change*:

- the first adaptation is unchanged;
- a second adaptation requires a little more evidence and a longer settling
  period;
- a third adaptation remains possible, especially for a genuine late score
  need, but requires materially stronger evidence and substantially more time
  for the previous plan to take effect.

No future information, team identity, desired scoreline or outcome target is
used. The layer consumes no RNG and changes no player attributes.
"""

from engine_experiment_v13_referee_complete import MatchEngineV13RefereeComplete


VERSION = "1.3-candidate-progressive-tactical-inertia"


class MatchEngineV13AdaptationInertia(MatchEngineV13RefereeComplete):
    """Adds progressive inertia to repeated in-match tactical changes."""

    SECOND_ADAPTATION_COOLDOWN_MINUTES = 18.0
    THIRD_ADAPTATION_COOLDOWN_MINUTES = 24.0

    @staticmethod
    def _stable_threshold(response: str, prior_count: int) -> float:
        """Escalate evidence requirements as the coach has already intervened.

        First-adaptation thresholds are deliberately identical to the previous
        stability layer. Score-state changes remain easier than a third
        structural reconfiguration because chasing/protecting a late score is
        qualitatively different from repeatedly reshaping the same structure.
        """
        count = max(0, int(prior_count))
        if response in {"chase_game", "protect_lead"}:
            base = 0.62
            surcharge = (0.0, 0.025, 0.060)[min(2, count)]
        else:
            base = 0.60
            surcharge = (0.0, 0.045, 0.100)[min(2, count)]
        return base + surcharge

    @classmethod
    def _required_progressive_cooldown(cls, prior_count: int) -> float:
        count = max(0, int(prior_count))
        if count <= 0:
            return 0.0
        if count == 1:
            return cls.SECOND_ADAPTATION_COOLDOWN_MINUTES
        return cls.THIRD_ADAPTATION_COOLDOWN_MINUTES

    def _adaptation_profile(self, team: int) -> dict:
        profile = super()._adaptation_profile(team)
        cooldown = dict(profile.get("cooldown") or {})
        count = int(cooldown.get("count", 0) or 0)
        minutes_since = float(cooldown.get("minutes_since", 999.0))
        required = self._required_progressive_cooldown(count)

        reasons = list(profile.get("blocked_reasons") or [])
        eligible = bool(profile.get("eligible"))
        if count > 0 and minutes_since < required:
            eligible = False
            if "progressive_adaptation_inertia" not in reasons:
                reasons.append("progressive_adaptation_inertia")

        gate = dict(profile.get("stability_gate") or {})
        gate.update(
            {
                "progressive_inertia": True,
                "second_adaptation_cooldown_minutes": self.SECOND_ADAPTATION_COOLDOWN_MINUTES,
                "third_adaptation_cooldown_minutes": self.THIRD_ADAPTATION_COOLDOWN_MINUTES,
                "third_structural_threshold": 0.70,
                "third_score_threshold": 0.68,
            }
        )

        return {
            **profile,
            "eligible": eligible,
            "blocked_reasons": reasons,
            "stability_gate": gate,
            "progressive_inertia": {
                "prior_adaptations": count,
                "required_cooldown_minutes": required,
                "minutes_since_last_adaptation": minutes_since,
            },
        }


MatchEngine = MatchEngineV13AdaptationInertia
