from __future__ import annotations

"""Individualized defensive set-piece organization for v1.3.

The attacking corner model already chooses a delivery, target and second-ball
path.  This layer gives the defending team a contextual scheme and concrete
assignments instead of always asking the same generic best aerial defender to
handle everything.  Schemes redistribute responsibilities and keep an explicit
counter-outlet trade-off; they do not increase player ratings.
"""

from copy import deepcopy

from engine import Band, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_second_balls import MatchEngineV13SecondBalls


class MatchEngineV13SetPieceDefense(MatchEngineV13SecondBalls):
    DEFENSIVE_CORNER_SCHEMES = ("zonal", "man_mark", "hybrid", "near_post_guard")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._v13_corner_defense_context: dict | None = None

    def _corner_defensive_candidates(self, team: int) -> list[PlayerState]:
        return [
            ps for ps in self.teams[int(team)].on_field
            if not ps.red and ps.player.position.upper() != "GK"
        ]

    def _corner_counter_outlet(self, team: int) -> PlayerState | None:
        candidates = self._corner_defensive_candidates(team)
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda ps: (
                0.34 * ps.effective("pace")
                + 0.28 * ps.effective("dribbling")
                + 0.22 * ps.effective("off_ball")
                + 0.16 * ps.effective("composure"),
                ps.player.name,
            ),
        )

    def defensive_corner_plan_diagnostic(
        self,
        defending_team: int,
        *,
        target: PlayerState | None = None,
        pattern: str | None = None,
        corner_lane: Lane | None = None,
    ) -> dict:
        defending_team = int(defending_team)
        candidates = self._corner_defensive_candidates(defending_team)
        keeper = self._goalkeeper(defending_team)
        tactics = self.teams[defending_team].team.tactics
        if not candidates:
            return {
                "scheme": "zonal",
                "marker": keeper.player.name,
                "near_post_guard": keeper.player.name,
                "edge_guard": keeper.player.name,
                "counter_outlet": None,
                "weights": {"zonal": 1.0, "man_mark": 0.0, "hybrid": 0.0, "near_post_guard": 0.0},
            }

        aerial_values = [
            clamp((0.36 * ps.effective("heading") + 0.27 * ps.effective("strength") + 0.22 * ps.effective("positioning") + 0.15 * ps.effective("anticipation")) / 100.0)
            for ps in candidates
        ]
        positioning_values = [
            clamp((0.44 * ps.effective("positioning") + 0.34 * ps.effective("anticipation") + 0.22 * ps.effective("composure")) / 100.0)
            for ps in candidates
        ]
        aerial = sum(sorted(aerial_values, reverse=True)[:4]) / max(1, min(4, len(aerial_values)))
        positional = sum(sorted(positioning_values, reverse=True)[:4]) / max(1, min(4, len(positioning_values)))
        keeper_command = self._corner_keeper_command(defending_team)
        target_aerial = 0.55
        if target is not None:
            target_aerial = clamp(
                (
                    0.36 * target.effective("heading")
                    + 0.24 * target.effective("strength")
                    + 0.22 * target.effective("off_ball")
                    + 0.18 * target.effective("anticipation")
                ) / 100.0
            )
        h, a = self.score
        diff = (h - a) if defending_team == 0 else (a - h)
        late = clamp((self.minute - 70.0) / 22.0)
        protect = (1.0 if diff > 0 else 0.0) * late
        chase = (1.0 if diff < 0 else 0.0) * late

        raw = {
            "zonal": max(
                0.05,
                0.30 + 0.42 * positional + 0.22 * keeper_command + 0.16 * tactics.compactness - 0.10 * target_aerial,
            ),
            "man_mark": max(
                0.05,
                0.24 + 0.44 * aerial + 0.24 * target_aerial + 0.10 * tactics.pressing - 0.08 * keeper_command,
            ),
            "hybrid": max(
                0.05,
                0.38 + 0.25 * aerial + 0.25 * positional + 0.12 * keeper_command + 0.10 * protect,
            ),
            "near_post_guard": max(
                0.05,
                0.20 + 0.18 * positional + 0.16 * keeper_command + (0.32 if pattern == "near_post" else 0.0) + 0.08 * protect,
            ),
        }
        total = sum(raw.values()) or 1.0
        weights = {name: value / total for name, value in raw.items()}
        scheme = max(weights, key=lambda name: (weights[name], name))

        def marker_score(ps: PlayerState) -> float:
            if scheme == "man_mark":
                score = 0.34 * ps.effective("heading") + 0.26 * ps.effective("strength") + 0.22 * ps.effective("positioning") + 0.18 * ps.effective("anticipation")
            elif scheme == "zonal":
                score = 0.36 * ps.effective("positioning") + 0.30 * ps.effective("anticipation") + 0.20 * ps.effective("heading") + 0.14 * ps.effective("composure")
            elif scheme == "near_post_guard":
                score = 0.30 * ps.effective("anticipation") + 0.25 * ps.effective("heading") + 0.20 * ps.effective("pace") + 0.15 * ps.effective("positioning") + 0.10 * ps.effective("strength")
            else:
                score = 0.28 * ps.effective("heading") + 0.25 * ps.effective("positioning") + 0.20 * ps.effective("anticipation") + 0.16 * ps.effective("strength") + 0.11 * ps.effective("composure")
            if target is not None:
                pace_match = 1.0 - abs(ps.effective("pace") - target.effective("pace")) / 100.0
                strength_match = 1.0 - abs(ps.effective("strength") - target.effective("strength")) / 100.0
                score += 5.0 * clamp(0.55 * pace_match + 0.45 * strength_match)
            return score

        marker = max(candidates, key=lambda ps: (marker_score(ps), ps.player.name))
        remaining = [ps for ps in candidates if ps.player.name != marker.player.name]
        near_post_guard = max(
            remaining or candidates,
            key=lambda ps: (0.38 * ps.effective("anticipation") + 0.27 * ps.effective("positioning") + 0.20 * ps.effective("heading") + 0.15 * ps.effective("pace"), ps.player.name),
        )
        remaining2 = [ps for ps in remaining if ps.player.name != near_post_guard.player.name]
        edge_guard = max(
            remaining2 or candidates,
            key=lambda ps: (0.35 * ps.effective("anticipation") + 0.25 * ps.effective("positioning") + 0.20 * ps.effective("tackling") + 0.20 * ps.effective("composure"), ps.player.name),
        )
        outlet = self._corner_counter_outlet(defending_team)
        # When chasing late, preserve the outlet more aggressively; when
        # protecting, the outlet is still present but is less strongly held out.
        outlet_commitment = clamp(0.44 + 0.30 * chase - 0.20 * protect)
        return {
            "scheme": scheme,
            "weights": weights,
            "marker": marker.player.name,
            "near_post_guard": near_post_guard.player.name,
            "edge_guard": edge_guard.player.name,
            "counter_outlet": None if outlet is None else outlet.player.name,
            "counter_outlet_commitment": outlet_commitment,
            "aerial_quality": aerial,
            "positioning_quality": positional,
            "keeper_command": keeper_command,
            "target_aerial": target_aerial,
            "pattern": pattern,
            "corner_lane": None if corner_lane is None else corner_lane.value,
        }

    def _corner_target(self, team: int, taker: PlayerState, zone: Zone, pattern: str) -> PlayerState:
        target = super()._corner_target(team, taker, zone, pattern)
        defending_team = 1 - int(team)
        self._v13_corner_defense_context = self.defensive_corner_plan_diagnostic(
            defending_team,
            target=target,
            pattern=pattern,
            corner_lane=zone.lane,
        )
        return target

    def _corner_defender(self, defending_team: int) -> PlayerState:
        context = getattr(self, "_v13_corner_defense_context", None)
        if isinstance(context, dict):
            marker = context.get("marker")
            if marker:
                try:
                    return self.teams[int(defending_team)].by_name(str(marker))
                except KeyError:
                    pass
        return super()._corner_defender(defending_team)

    def _resolve_contextual_corner(self, team: int, zone: Zone):
        self._v13_corner_defense_context = None
        event = super()._resolve_contextual_corner(team, zone)
        context = getattr(self, "_v13_corner_defense_context", None)
        if isinstance(context, dict):
            event.data.setdefault("defensive_corner_scheme", context["scheme"])
            event.data.setdefault("defensive_marker", context["marker"])
            event.data.setdefault("near_post_guard", context["near_post_guard"])
            event.data.setdefault("edge_guard", context["edge_guard"])
            event.data.setdefault("counter_outlet", context["counter_outlet"])
            event.data.setdefault("counter_outlet_commitment", round(float(context["counter_outlet_commitment"]), 3))
        self._v13_corner_defense_context = None
        return event

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["corner_defense_context"] = deepcopy(getattr(self, "_v13_corner_defense_context", None))
        return data


MatchEngine = MatchEngineV13SetPieceDefense

__all__ = ["MatchEngineV13SetPieceDefense", "MatchEngine"]
