from __future__ import annotations

"""v1.3 determination / grit layer.

Determination is not a hidden execution buff and is not a synonym for
boldness.  It represents willingness to keep acting under adversity: fatigue,
pressure and adverse score/time context.  High determination can make a player
persist with proactive actions and slightly resist fatigue-driven defensive
mistakes.  Technique, passing, finishing, pace, etc. still determine whether
the action succeeds.

A team feels "raçudo" when several of its players have high determination;
there is no team-name special case in the engine.
"""

from engine import PlayerState, clamp
from engine_experiment_v13_knockout import MatchEngineV13Knockout


VERSION = (
    "1.3-candidate-spatial-creativity-boldness-determination-offball-body-"
    "defense-marking-cover-communication-offside-overload-errors-chemistry-"
    "adaptation-stability-persistence-knockout"
)


class MatchEngineV13Determination(MatchEngineV13Knockout):
    """Adds contextual persistence/will without granting generic skill."""

    def _determination(self, actor: PlayerState) -> float:
        explicit = getattr(actor.player, "determination", None)
        if explicit is not None:
            return clamp(float(explicit) / 100.0)

        # Neutral fallback for every team/player, so the mechanic is universal.
        return clamp(
            0.28 * actor.effective("composure") / 100.0
            + 0.25 * actor.effective("stamina") / 100.0
            + 0.20 * actor.effective("anticipation") / 100.0
            + 0.17 * actor.effective("aggression") / 100.0
            + 0.10 * actor.effective("discipline") / 100.0
        )

    def _adversity_intensity(self, team: int, actor: PlayerState, ctx: dict) -> float:
        h, a = self.score
        diff = (h - a) if team == 0 else (a - h)
        late = clamp((self.minute - 50.0) / 40.0)
        trailing = clamp(max(0.0, float(-diff)) / 2.0)
        fatigue = clamp(1.0 - actor.energy)
        pressure = clamp(float(ctx.get("pressure", 0.50)))
        return clamp(
            0.42 * trailing * late
            + 0.25 * fatigue
            + 0.20 * pressure
            + 0.13 * late
        )

    def determination_diagnostic(self, team: int, actor: PlayerState, ctx: dict) -> dict:
        determination = self._determination(actor)
        adversity = self._adversity_intensity(team, actor, ctx)
        drive = (determination - 0.50) * 2.0 * adversity
        return {
            "determination": determination,
            "adversity": adversity,
            "drive": max(-1.0, min(1.0, drive)),
            "energy": actor.energy,
        }

    @staticmethod
    def _player_to_dict(player):
        data = MatchEngineV13Knockout._player_to_dict(player)
        if hasattr(player, "determination"):
            data["determination"] = getattr(player, "determination")
        return data

    @staticmethod
    def _player_from_dict(data):
        payload = dict(data)
        determination = payload.pop("determination", None)
        player = MatchEngineV13Knockout._player_from_dict(payload)
        if determination is not None:
            setattr(player, "determination", determination)
        return player

    def _decision_weights(self, actor, zone, tactics, ctx):
        items = list(super()._decision_weights(actor, zone, tactics, ctx))
        team = self._team_index_for_actor(actor)
        if team is None:
            return items

        diag = self.determination_diagnostic(team, actor, ctx)
        drive = float(diag["drive"])
        if abs(drive) < 1e-9:
            return items

        proactive = {
            "progressive_pass": 0.10,
            "carry": 0.09,
            "through_ball": 0.10,
            "dribble": 0.11,
            "shoot": 0.10,
            "cross": 0.06,
            "cutback": 0.07,
            "long_ball": 0.05,
            "switch": 0.04,
        }
        adjusted = []
        for action, weight in items:
            weight = float(weight)
            if action == "safe_pass":
                # Under adversity, determination resists passivity. Low
                # determination can have the opposite effect. This changes
                # willingness only, never action execution probability.
                factor = 1.0 - 0.10 * drive
            else:
                factor = 1.0 + proactive.get(action, 0.0) * drive
            adjusted.append((action, max(0.0, weight * max(0.75, factor))))
        return adjusted

    def _defensive_error_profile(
        self,
        attacking_team,
        zone,
        ctx,
        plan,
        *,
        kind,
        target,
    ):
        profile = super()._defensive_error_profile(
            attacking_team, zone, ctx, plan, kind=kind, target=target
        )
        defender = plan.get("defender") if isinstance(plan, dict) else None
        if not isinstance(defender, PlayerState):
            profile["determination"] = None
            profile["determination_resilience"] = 0.0
            return profile

        defending_team = 1 - int(attacking_team)
        determination = self._determination(defender)
        h, a = self.score
        diff = (h - a) if defending_team == 0 else (a - h)
        late = clamp((self.minute - 55.0) / 35.0)
        trailing = clamp(max(0.0, float(-diff)) / 2.0)
        fatigue = clamp(float(profile.get("fatigue", 0.0)))
        overload = clamp(float(profile.get("overload_severity", 0.0)))

        # Only above-neutral determination earns resilience, and only when
        # there is actual adversity. It cannot erase structural mistakes.
        will = clamp((determination - 0.50) * 2.0)
        adversity = clamp(0.48 * fatigue + 0.22 * overload + 0.18 * late + 0.12 * trailing * late)
        resilience = will * adversity

        profile["risk"] = clamp(
            float(profile["risk"]) * (1.0 - 0.18 * resilience),
            0.001,
            0.14,
        )
        profile["severity"] = clamp(
            float(profile["severity"]) * (1.0 - 0.06 * resilience),
            0.46,
            1.0,
        )
        profile["determination"] = determination
        profile["determination_resilience"] = resilience
        return profile

    def _penalty_conversion_probability(self, taker, keeper):
        base = super()._penalty_conversion_probability(taker, keeper)
        # Very small pressure-resilience term; composure/technique remain the
        # dominant shootout attributes.
        determination = self._determination(taker)
        return clamp(base + 0.018 * (determination - 0.50), 0.54, 0.93)

    def export_state(self) -> dict:
        data = super().export_state()
        data["engine_version"] = VERSION
        return data


MatchEngine = MatchEngineV13Determination
