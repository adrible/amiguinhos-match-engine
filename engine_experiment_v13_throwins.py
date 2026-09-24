from __future__ import annotations

"""v1.3 contextual throw-in layer.

A throw-in is created only when an existing wide failed action plausibly sends
the ball out. The restart then chooses a footballing option from the current
zone and player/tactical context; there is no throw-in rating or scripted chance.
"""

from engine import Band, EventType, Lane, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_corners import MatchEngineV13Corners

VERSION = "1.3-candidate-contextual-throwins"


class MatchEngineV13ThrowIns(MatchEngineV13Corners):
    THROW_IN_REASONS = {
        "bad_safe_pass": 0.14,
        "progressive_pass_failed": 0.17,
        "switch_failed": 0.15,
        "long_ball_failed": 0.12,
        "dispossessed": 0.24,
        "cross_stopped": 0.34,
        "cutback_stopped": 0.29,
        "dribble_stopped": 0.27,
        "cross_cleared": 0.39,
        "cutback_cleared": 0.31,
        "through_ball_cleared": 0.18,
    }
    DEFENDER_TOUCH_REASONS = {
        "dispossessed",
        "cross_stopped",
        "cutback_stopped",
        "dribble_stopped",
        "cross_cleared",
        "cutback_cleared",
        "through_ball_cleared",
    }
    THROW_PATTERNS = ("short_return", "inside_feed", "down_line", "long_throw")

    def throw_in_from_turnover_diagnostic(self, losing_team: int, zone: Zone, reason: str, ctx: dict) -> dict:
        """RNG-pure diagnostic for whether a wide failed action can leave play."""
        base = self.THROW_IN_REASONS.get(str(reason))
        if base is None or zone.lane == Lane.CENTER:
            return {
                "eligible": False,
                "out_probability": 0.0,
                "retain_throw_probability": 0.0,
                "reason": str(reason),
            }
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        space = clamp(float(ctx.get("space", 0.5)))
        band_bonus = 0.035 if zone.band in {Band.ATT, Band.BOX} else 0.015 if zone.band == Band.MID else 0.0
        out_probability = clamp(
            float(base) + 0.085 * pressure + 0.055 * (1.0 - space) + band_bonus,
            0.08,
            0.54,
        )
        if reason in self.DEFENDER_TOUCH_REASONS:
            retain_throw_probability = clamp(0.54 + 0.11 * pressure, 0.50, 0.69)
        else:
            retain_throw_probability = clamp(0.18 + 0.08 * pressure, 0.16, 0.30)
        return {
            "eligible": True,
            "out_probability": out_probability,
            "retain_throw_probability": retain_throw_probability,
            "reason": str(reason),
            "zone": self._zone_data(zone),
        }

    def _arm_throw_in(
        self,
        losing_team: int,
        actor: PlayerState,
        zone: Zone,
        reason: str,
        awarded_team: int,
        diagnostic: dict,
    ):
        restart_zone = zone if awarded_team == losing_team else zone.mirror()
        self.state.pending = None
        self.state.possession = awarded_team
        self.state.zone = restart_zone
        self.state.restart = "throw_in"
        self.state.restart_team = awarded_team
        self.state.restart_zone = restart_zone
        self.state.transition_boost = 0.0
        self.state.phase = "restart"
        return self._emit(
            EventType.TURNOVER,
            awarded_team,
            1,
            "ball_out_throw_in",
            loser=actor.player.name,
            reason=reason,
            losing_team=losing_team,
            awarded_team=awarded_team,
            retained_by_attacking_team=awarded_team == losing_team,
            out_probability=round(float(diagnostic["out_probability"]), 3),
            retain_throw_probability=round(float(diagnostic["retain_throw_probability"]), 3),
            zone=self._zone_data(restart_zone),
        )

    def _turnover(self, losing_team, actor, zone, reason, ctx, severity=0.5):
        diagnostic = self.throw_in_from_turnover_diagnostic(losing_team, zone, reason, ctx)
        if diagnostic["eligible"] and self.rng.random() < float(diagnostic["out_probability"]):
            retained = self.rng.random() < float(diagnostic["retain_throw_probability"])
            awarded_team = losing_team if retained else 1 - losing_team
            return self._arm_throw_in(
                losing_team,
                actor,
                zone,
                str(reason),
                awarded_team,
                diagnostic,
            )
        return super()._turnover(losing_team, actor, zone, reason, ctx, severity=severity)

    def _throw_in_taker(self, team: int, zone: Zone) -> PlayerState:
        rows = []
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position.upper() == "GK":
                continue
            pos = ps.player.position.upper()
            side_bonus = 0.0
            if zone.lane == Lane.LEFT and pos in {"LB", "LW"}:
                side_bonus = 0.24
            elif zone.lane == Lane.RIGHT and pos in {"RB", "RW"}:
                side_bonus = 0.24
            elif pos in {"LB", "RB"}:
                side_bonus = 0.08
            quality = clamp(
                (
                    0.27 * ps.effective("technique")
                    + 0.23 * ps.effective("passing")
                    + 0.19 * ps.effective("composure")
                    + 0.17 * ps.effective("strength")
                    + 0.14 * ps.effective("positioning")
                )
                / 100.0
            )
            score = quality + side_bonus + 0.04 * ps.energy
            rows.append((score, ps.player.name, ps))
        return max(rows, key=lambda row: (row[0], row[1]))[2]

    def _throw_support_quality(self, team: int, taker: PlayerState, zone: Zone) -> float:
        values = []
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position.upper() == "GK" or ps.player.name == taker.player.name:
                continue
            lane_bonus = 5.0 if (
                (zone.lane == Lane.LEFT and ps.player.position.upper() in {"LB", "LW"})
                or (zone.lane == Lane.RIGHT and ps.player.position.upper() in {"RB", "RW"})
            ) else 0.0
            values.append(
                0.28 * ps.effective("off_ball")
                + 0.25 * ps.effective("technique")
                + 0.20 * ps.effective("passing")
                + 0.15 * ps.effective("composure")
                + 0.12 * ps.effective("anticipation")
                + lane_bonus
            )
        best = sorted(values, reverse=True)[:3]
        return clamp(sum(best) / (100.0 * len(best))) if best else 0.50

    def _throw_aerial_quality(self, team: int, taker: PlayerState) -> float:
        values = []
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position.upper() == "GK" or ps.player.name == taker.player.name:
                continue
            values.append(
                0.34 * ps.effective("heading")
                + 0.27 * ps.effective("strength")
                + 0.21 * ps.effective("anticipation")
                + 0.18 * ps.effective("off_ball")
            )
        best = sorted(values, reverse=True)[:3]
        return clamp(sum(best) / (100.0 * len(best))) if best else 0.50

    def throw_in_plan_diagnostic(self, team: int, zone: Zone) -> dict:
        """RNG-pure option weights for a live throw-in restart."""
        taker = self._throw_in_taker(team, zone)
        tactics = self.teams[team].team.tactics
        opponent = self.teams[1 - team].team.tactics
        support = self._throw_support_quality(team, taker, zone)
        aerial = self._throw_aerial_quality(team, taker)
        long_quality = clamp(
            (
                0.32 * taker.effective("strength")
                + 0.24 * taker.effective("crossing")
                + 0.23 * taker.effective("technique")
                + 0.21 * taker.effective("passing")
            )
            / 100.0
        )
        pressure = clamp(
            0.50 * opponent.pressing
            + 0.25 * opponent.compactness
            + 0.15 * opponent.defensive_line
            + 0.10 * max(0.0, opponent.mentality)
        )
        h, a = self.score
        diff = (h - a) if team == 0 else (a - h)
        late = clamp((self.minute - 65.0) / 25.0)
        chasing = 1.0 if diff < 0 else 0.0
        protecting = 1.0 if diff > 0 else 0.0
        deep = 1.0 if zone.band == Band.DEF else 0.0
        advanced = 1.0 if zone.band in {Band.ATT, Band.BOX} else 0.0

        raw = {
            "short_return": max(
                0.05,
                0.42
                + 0.35 * deep
                + 0.42 * (1.0 - tactics.directness)
                + 0.30 * support
                + 0.18 * protecting * late
                - 0.13 * pressure,
            ),
            "inside_feed": max(
                0.05,
                0.40
                + 0.25 * (1.0 - tactics.directness)
                + 0.28 * support
                + 0.16 * taker.effective("passing") / 100.0
                + 0.12 * taker.effective("vision") / 100.0
                - 0.10 * pressure,
            ),
            "down_line": max(
                0.05,
                0.31
                + 0.38 * tactics.directness
                + 0.25 * tactics.width
                + 0.21 * support
                + 0.10 * chasing * late
                + 0.08 * pressure,
            ),
            "long_throw": max(
                0.03,
                0.08
                + 0.34 * long_quality
                + 0.27 * aerial
                + 0.26 * tactics.directness
                + 0.20 * advanced
                + 0.18 * chasing * late
                - 0.08 * deep
                - 0.05 * pressure,
            ),
        }
        total = sum(raw.values()) or 1.0
        return {
            "taker": taker.player.name,
            "zone": self._zone_data(zone),
            "support_quality": support,
            "aerial_quality": aerial,
            "long_throw_quality": long_quality,
            "opponent_pressure": pressure,
            "score_diff": diff,
            "late_factor": late,
            "weights": {name: value / total for name, value in raw.items()},
        }

    def _throw_in_target(self, team: int, taker: PlayerState, zone: Zone, pattern: str) -> PlayerState:
        rows = []
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position.upper() == "GK" or ps.player.name == taker.player.name:
                continue
            pos = ps.player.position.upper()
            if pattern == "short_return":
                role = {"LB": 1.25, "RB": 1.25, "CB": 1.05, "DM": 1.15, "CM": 0.95, "LW": 0.85, "RW": 0.85}.get(pos, 0.42)
                quality = (
                    0.30 * ps.effective("technique")
                    + 0.25 * ps.effective("composure")
                    + 0.23 * ps.effective("positioning")
                    + 0.22 * ps.effective("passing")
                ) / 100.0
            elif pattern == "inside_feed":
                role = {"DM": 1.15, "CM": 1.35, "AM": 1.28, "ST": 0.68, "LW": 0.72, "RW": 0.72}.get(pos, 0.38)
                quality = (
                    0.30 * ps.effective("off_ball")
                    + 0.25 * ps.effective("technique")
                    + 0.24 * ps.effective("composure")
                    + 0.21 * ps.effective("anticipation")
                ) / 100.0
            elif pattern == "down_line":
                side = (
                    (zone.lane == Lane.LEFT and pos in {"LB", "LW"})
                    or (zone.lane == Lane.RIGHT and pos in {"RB", "RW"})
                )
                role = 1.45 if side else {"ST": 1.10, "AM": 0.75, "CM": 0.55}.get(pos, 0.30)
                quality = (
                    0.31 * ps.effective("off_ball")
                    + 0.25 * ps.effective("pace")
                    + 0.20 * ps.effective("strength")
                    + 0.14 * ps.effective("anticipation")
                    + 0.10 * ps.effective("technique")
                ) / 100.0
            else:
                role = {"ST": 1.45, "AM": 0.95, "CB": 0.82, "LW": 0.78, "RW": 0.78, "CM": 0.55}.get(pos, 0.30)
                quality = (
                    0.34 * ps.effective("heading")
                    + 0.27 * ps.effective("strength")
                    + 0.22 * ps.effective("anticipation")
                    + 0.17 * ps.effective("off_ball")
                ) / 100.0
            role_profile = self.player_role_profile(ps)
            if pattern == "long_throw" and role_profile["primary"] in {"target_forward", "poacher"}:
                quality += 0.08 * float(role_profile["conviction"])
            rows.append((ps, max(0.04, role * (0.52 + 0.70 * clamp(quality)))))
        return weighted_choice(self.rng, rows)

    @staticmethod
    def _throw_destination(zone: Zone, pattern: str) -> Zone:
        if pattern == "short_return":
            return Zone(Band.ATT if zone.band == Band.BOX else zone.band, zone.lane)
        if pattern == "inside_feed":
            return Zone(Band.ATT if zone.band == Band.BOX else zone.band, Lane.CENTER)
        if zone.band == Band.DEF:
            band = Band.MID
        elif zone.band == Band.MID:
            band = Band.ATT
        else:
            band = Band.ATT
        lane = Lane.CENTER if pattern == "long_throw" else zone.lane
        return Zone(band, lane)

    def _throw_success_probability(
        self,
        taker: PlayerState,
        target: PlayerState,
        pattern: str,
        plan: dict,
    ) -> float:
        technique = taker.effective("technique") / 100.0
        passing = taker.effective("passing") / 100.0
        composure = taker.effective("composure") / 100.0
        pressure = float(plan["opponent_pressure"])
        if pattern == "long_throw":
            target_quality = (
                0.38 * target.effective("heading")
                + 0.31 * target.effective("strength")
                + 0.19 * target.effective("anticipation")
                + 0.12 * target.effective("off_ball")
            ) / 100.0
            value = 0.30 + 0.25 * float(plan["long_throw_quality"]) + 0.22 * target_quality - 0.12 * pressure
            return clamp(value, 0.36, 0.72)
        if pattern == "down_line":
            target_quality = (
                0.34 * target.effective("off_ball")
                + 0.25 * target.effective("pace")
                + 0.22 * target.effective("strength")
                + 0.19 * target.effective("anticipation")
            ) / 100.0
            value = 0.49 + 0.15 * technique + 0.10 * passing + 0.17 * target_quality - 0.17 * pressure
            return clamp(value, 0.50, 0.84)
        target_quality = (
            0.35 * target.effective("technique")
            + 0.27 * target.effective("composure")
            + 0.20 * target.effective("positioning")
            + 0.18 * target.effective("off_ball")
        ) / 100.0
        base = 0.67 if pattern == "short_return" else 0.60
        value = base + 0.11 * technique + 0.09 * passing + 0.06 * composure + 0.13 * target_quality - 0.14 * pressure
        return clamp(value, 0.66 if pattern == "short_return" else 0.60, 0.94)

    def _resolve_throw_in(self, team: int, zone: Zone):
        self.state.restart = None
        self.state.restart_team = None
        self.state.restart_zone = None
        self.state.possession = team
        self.state.zone = zone
        self.state.transition_boost = 0.0
        self.state.phase = "restart"

        plan = self.throw_in_plan_diagnostic(team, zone)
        pattern = weighted_choice(self.rng, list(plan["weights"].items()))
        taker = self._throw_in_taker(team, zone)
        target = self._throw_in_target(team, taker, zone, pattern)
        destination = self._throw_destination(zone, pattern)
        success_p = self._throw_success_probability(taker, target, pattern, plan)
        self._advance_clock(
            self.rng.uniform(2.0, 4.2) if pattern != "long_throw" else self.rng.uniform(3.0, 5.3),
            team,
        )
        self._drain(taker, 0.0005 if pattern != "long_throw" else 0.0009)

        if self.rng.random() < success_p:
            transition = 0.0 if pattern in {"short_return", "inside_feed"} else 0.04
            self._switch_possession(team, destination, transition=transition)
            return self._emit(
                EventType.PROGRESSION,
                team,
                1 if pattern in {"short_return", "inside_feed"} else 2,
                "throw_in_completed",
                pattern=pattern,
                taker=taker.player.name,
                target=target.player.name,
                success_probability=round(success_p, 3),
                zone=self._zone_data(destination),
            )

        defending = 1 - team
        transition = {
            "short_return": 0.10,
            "inside_feed": 0.14,
            "down_line": 0.21,
            "long_throw": 0.24,
        }[pattern]
        turnover_zone = destination.mirror()
        self._switch_possession(defending, turnover_zone, transition=transition)
        return self._emit(
            EventType.TURNOVER,
            defending,
            1 if transition < 0.20 else 2,
            "throw_in_lost",
            pattern=pattern,
            taker=taker.player.name,
            target=target.player.name,
            lost_by_team=team,
            success_probability=round(success_p, 3),
            transition=round(transition, 3),
            zone=self._zone_data(turnover_zone),
        )

    def _resolve_restart(self):
        if self.state.restart == "throw_in":
            team = self.state.restart_team
            zone = self.state.restart_zone
            if team in (0, 1) and zone is not None:
                return self._resolve_throw_in(int(team), zone)
        return super()._resolve_restart()


MatchEngine = MatchEngineV13ThrowIns
