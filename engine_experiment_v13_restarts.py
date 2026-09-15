from __future__ import annotations

"""Contextual dead-ball restarts for the v1.3 candidate.

This layer adds real goal-kick decisions and deliberate free-kick structure
without replacing the existing quick-free-kick intelligence below it.
"""

from engine import Band, DEF_C, EventType, Lane, PendingAction, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_keeper_crosses import MatchEngineV13KeeperCrosses

VERSION = "1.3-candidate-restarts"


class MatchEngineV13Restarts(MatchEngineV13KeeperCrosses):
    # ----------------------------- goal kicks -----------------------------
    def _arm_goal_kick(self, defending_team: int) -> None:
        self.state.pending = None
        self.state.possession = defending_team
        self.state.zone = DEF_C
        self.state.transition_boost = 0.0
        self.state.restart = "goal_kick"
        self.state.restart_team = defending_team
        self.state.restart_zone = DEF_C
        self.state.phase = "restart"

    def _resolve_shot(self, p):
        event = super()._resolve_shot(p)
        if (
            event.type in {EventType.MISS, EventType.POST}
            and self.state.pending is None
            and not self.state.ended
        ):
            self._arm_goal_kick(1 - p.team)
            event.data.setdefault("restart_after", "goal_kick")
        return event

    def goal_kick_plan_diagnostic(self, team: int) -> dict:
        tactics = self.teams[team].team.tactics
        opponent = self.teams[1 - team].team.tactics
        keeper = self._goalkeeper(team)
        keeper_distribution = clamp(
            (0.45 * keeper.effective("passing")
            + 0.30 * keeper.effective("technique")
            + 0.25 * keeper.effective("composure"))
            / 100.0
        )
        build_quality = self._kickoff_build_quality(team)
        aerial_quality = self._kickoff_aerial_quality(team)
        pressure = clamp(
            0.10
            + 0.56 * opponent.pressing
            + 0.14 * opponent.defensive_line
            + 0.06 * max(0.0, opponent.mentality)
        )
        score_diff = self.score[team] - self.score[1 - team]
        late = clamp((self.minute - 60.0) / 30.0)
        chasing = 1.0 if score_diff < 0 else 0.0
        protecting = 1.0 if score_diff > 0 else 0.0

        raw = {
            "short_build": max(
                0.05,
                0.58
                + 0.82 * (1.0 - tactics.directness)
                + 0.40 * build_quality
                + 0.30 * keeper_distribution
                + 0.42 * protecting * late
                - 0.20 * pressure * max(0.0, 0.70 - build_quality),
            ),
            "fullback_release": max(
                0.05,
                0.36
                + 0.62 * tactics.width
                + 0.24 * keeper_distribution
                + 0.20 * (tactics.overlap_left + tactics.overlap_right)
                + 0.10 * (1.0 - pressure),
            ),
            "midfield_clip": max(
                0.05,
                0.28
                + 0.46 * tactics.tempo
                + 0.42 * tactics.directness
                + 0.22 * aerial_quality
                + 0.18 * keeper_distribution,
            ),
            "long_target": max(
                0.05,
                0.16
                + 0.92 * tactics.directness
                + 0.38 * tactics.counter
                + 0.42 * pressure
                + 0.42 * chasing * late
                + 0.34 * aerial_quality,
            ),
        }
        total = sum(raw.values()) or 1.0
        return {
            "score_diff": score_diff,
            "late_factor": late,
            "opponent_pressure": pressure,
            "keeper_distribution": keeper_distribution,
            "build_quality": build_quality,
            "aerial_quality": aerial_quality,
            "weights": {key: value / total for key, value in raw.items()},
        }

    def _goal_kick_receiver(self, team: int, pattern: str) -> PlayerState:
        profiles = {
            "short_build": {"CB": 1.60, "LB": 1.22, "RB": 1.22, "DM": 1.10, "CM": 0.45, "AM": 0.15, "LW": 0.10, "RW": 0.10, "ST": 0.05},
            "fullback_release": {"LB": 1.70, "RB": 1.70, "DM": 0.72, "CB": 0.60, "CM": 0.58, "LW": 0.42, "RW": 0.42, "AM": 0.20, "ST": 0.08},
            "midfield_clip": {"DM": 1.35, "CM": 1.45, "AM": 0.90, "LB": 0.62, "RB": 0.62, "LW": 0.55, "RW": 0.55, "ST": 0.42, "CB": 0.20},
            "long_target": {"ST": 1.75, "LW": 1.05, "RW": 1.05, "AM": 0.72, "CM": 0.40, "DM": 0.18, "LB": 0.12, "RB": 0.12, "CB": 0.06},
        }
        choices = []
        for ps in self.teams[team].on_field:
            pos = ps.player.position.upper()
            if pos == "GK":
                continue
            if pattern == "long_target":
                quality = (0.42 * ps.effective("heading") + 0.32 * ps.effective("strength") + 0.26 * ps.effective("off_ball")) / 100.0
            elif pattern == "midfield_clip":
                quality = (0.36 * ps.effective("anticipation") + 0.34 * ps.effective("composure") + 0.30 * ps.effective("positioning")) / 100.0
            else:
                quality = (0.38 * ps.effective("positioning") + 0.34 * ps.effective("composure") + 0.28 * ps.effective("technique")) / 100.0
            choices.append((ps, profiles[pattern].get(pos, 0.12) * (0.62 + 0.62 * clamp(quality))))
        return weighted_choice(self.rng, choices)

    @staticmethod
    def _restart_lane_for_player(player: PlayerState) -> Lane:
        pos = player.player.position.upper()
        if pos in {"LB", "LW"}:
            return Lane.LEFT
        if pos in {"RB", "RW"}:
            return Lane.RIGHT
        return Lane.CENTER

    def _goal_kick_success_probability(
        self,
        team: int,
        keeper: PlayerState,
        receiver: PlayerState,
        pattern: str,
        pressure: float,
    ) -> float:
        tactics = self.teams[team].team.tactics
        keeper_quality = clamp(
            (0.46 * keeper.effective("passing")
            + 0.30 * keeper.effective("technique")
            + 0.24 * keeper.effective("composure"))
            / 100.0
        )
        if pattern == "long_target":
            receiver_quality = clamp((0.43 * receiver.effective("heading") + 0.32 * receiver.effective("strength") + 0.25 * receiver.effective("anticipation")) / 100.0)
            value = 0.44 + 0.18 * (keeper_quality - 0.65) + 0.24 * (receiver_quality - 0.65) + 0.08 * tactics.directness - 0.05 * pressure
            return clamp(value, 0.30, 0.72)
        if pattern == "midfield_clip":
            receiver_quality = clamp((0.38 * receiver.effective("anticipation") + 0.34 * receiver.effective("composure") + 0.28 * receiver.effective("positioning")) / 100.0)
            value = 0.64 + 0.22 * (keeper_quality - 0.65) + 0.16 * (receiver_quality - 0.65) + 0.05 * tactics.tempo - 0.11 * pressure
            return clamp(value, 0.46, 0.88)
        receiver_quality = clamp((0.40 * receiver.effective("positioning") + 0.34 * receiver.effective("composure") + 0.26 * receiver.effective("technique")) / 100.0)
        base = 0.84 if pattern == "short_build" else 0.78
        pressure_cost = 0.17 if pattern == "short_build" else 0.13
        value = base + 0.24 * (keeper_quality - 0.65) + 0.18 * (receiver_quality - 0.65) + 0.06 * (1.0 - tactics.directness) - pressure_cost * pressure
        return clamp(value, 0.58 if pattern == "short_build" else 0.55, 0.97)

    def _resolve_goal_kick(self, team: int):
        self.state.restart = None
        self.state.restart_team = None
        self.state.restart_zone = None
        self.state.possession = team
        self.state.zone = DEF_C
        self.state.transition_boost = 0.0

        diag = self.goal_kick_plan_diagnostic(team)
        pattern = weighted_choice(self.rng, list(diag["weights"].items()))
        keeper = self._goalkeeper(team)
        receiver = self._goal_kick_receiver(team, pattern)
        lane = self._restart_lane_for_player(receiver)
        pressure = float(diag["opponent_pressure"])
        success_p = self._goal_kick_success_probability(team, keeper, receiver, pattern, pressure)
        duration = {
            "short_build": (6.0, 11.0),
            "fullback_release": (6.0, 10.0),
            "midfield_clip": (5.0, 9.0),
            "long_target": (4.5, 8.0),
        }[pattern]
        self._advance_clock(self.rng.uniform(*duration), team)
        self._drain(keeper, 0.0008)

        common = {
            "pattern": pattern,
            "keeper": keeper.player.name,
            "receiver": receiver.player.name,
            "pressure": round(pressure, 3),
            "success_probability": round(success_p, 3),
        }
        if self.rng.random() < success_p:
            if pattern == "short_build":
                zone, transition, key, typ = Zone(Band.DEF, lane), 0.0, "goal_kick_short_build", EventType.INFO
            elif pattern == "fullback_release":
                zone, transition, key, typ = Zone(Band.DEF, lane), 0.03, "goal_kick_fullback_release", EventType.PROGRESSION
            elif pattern == "midfield_clip":
                zone, transition, key, typ = Zone(Band.MID, lane), 0.06, "goal_kick_midfield_clip", EventType.PROGRESSION
            else:
                zone, transition, key, typ = Zone(Band.MID, lane), 0.08, "goal_kick_long_target", EventType.PROGRESSION
            self._switch_possession(team, zone, transition=transition)
            return self._emit(typ, team, 2, key, **common, zone=self._zone_data(zone))

        if pattern in {"short_build", "fullback_release"}:
            losing_zone = Zone(Band.DEF, lane)
            turnover_zone = losing_zone.mirror()
            transition = 0.48 if pattern == "short_build" else 0.36
            relevance = 3
        else:
            turnover_zone = Zone(Band.MID, lane).mirror()
            transition = 0.15 if pattern == "midfield_clip" else 0.08
            relevance = 2
        self._switch_possession(1 - team, turnover_zone, transition=transition)
        return self._emit(
            EventType.TURNOVER,
            1 - team,
            relevance,
            "goal_kick_turnover",
            **common,
            lost_by_team=team,
            zone=self._zone_data(turnover_zone),
            transition=round(transition, 3),
        )

    # ------------------------- deliberate free kicks -------------------------
    def free_kick_plan_diagnostic(self, team: int, zone: Zone) -> dict:
        tactics = self.teams[team].team.tactics
        opponent = self.teams[1 - team].team.tactics
        delivery_taker = self._best_player(team, ("crossing", "technique", "vision"), exclude_positions={"GK"})
        shot_taker = self._best_player(team, ("long_shots", "technique", "composure"), exclude_positions={"GK"})
        delivery_quality = clamp((0.40 * delivery_taker.effective("crossing") + 0.32 * delivery_taker.effective("technique") + 0.28 * delivery_taker.effective("vision")) / 100.0)
        shot_quality = clamp((0.44 * shot_taker.effective("long_shots") + 0.31 * shot_taker.effective("technique") + 0.25 * shot_taker.effective("composure")) / 100.0)
        block_density = clamp(0.52 * opponent.compactness + 0.28 * opponent.defensive_line + 0.20 * opponent.pressing)

        if zone.band == Band.DEF:
            raw = {
                "short_restart": 1.10 + 0.62 * (1.0 - tactics.directness) + 0.22 * (1.0 - tactics.risk),
                "delivery": 0.20 + 0.55 * tactics.directness + 0.20 * tactics.tempo + 0.16 * delivery_quality,
                "direct_shot": 0.0,
            }
        elif zone.band == Band.MID:
            raw = {
                "short_restart": 0.72 + 0.46 * (1.0 - tactics.directness) + 0.18 * (1.0 - tactics.risk),
                "delivery": 0.54 + 0.48 * tactics.directness + 0.24 * tactics.tempo + 0.20 * delivery_quality,
                "direct_shot": 0.0,
            }
        else:
            central = zone.lane == Lane.CENTER
            raw = {
                "short_restart": 0.24 + 0.30 * (1.0 - tactics.directness) + 0.18 * tactics.risk,
                "delivery": 0.74 + 0.38 * delivery_quality + 0.18 * tactics.width + (0.16 if not central else 0.0),
                "direct_shot": (0.24 + 0.64 * shot_quality + 0.20 * tactics.risk - 0.12 * block_density) if central else 0.0,
            }
        total = sum(max(0.0, value) for value in raw.values()) or 1.0
        return {
            "delivery_quality": delivery_quality,
            "shot_quality": shot_quality,
            "block_density": block_density,
            "weights": {key: max(0.0, value) / total for key, value in raw.items()},
        }

    def _free_kick_safe_target(self, team: int, taker: PlayerState, zone: Zone) -> PlayerState:
        choices = []
        for ps in self.teams[team].on_field:
            if ps.player.name == taker.player.name or ps.player.position.upper() == "GK":
                continue
            pos = ps.player.position.upper()
            if zone.band == Band.DEF:
                role = {"CB": 1.30, "DM": 1.35, "LB": 1.00, "RB": 1.00, "CM": 0.90}.get(pos, 0.28)
            elif zone.band == Band.MID:
                role = {"DM": 1.05, "CM": 1.35, "AM": 1.05, "LB": 0.62, "RB": 0.62, "LW": 0.58, "RW": 0.58}.get(pos, 0.35)
            else:
                role = {"CM": 1.05, "AM": 1.30, "LW": 1.05, "RW": 1.05, "ST": 0.82}.get(pos, 0.32)
            quality = (0.38 * ps.effective("positioning") + 0.34 * ps.effective("composure") + 0.28 * ps.effective("technique")) / 100.0
            choices.append((ps, role * (0.62 + 0.58 * clamp(quality))))
        return weighted_choice(self.rng, choices)

    def _resolve_deliberate_free_kick(self, team: int, zone: Zone):
        diag = self.free_kick_plan_diagnostic(team, zone)
        plan = weighted_choice(self.rng, list(diag["weights"].items()))
        self.state.restart = None
        self.state.restart_team = None
        self.state.restart_zone = None
        self.state.possession = team
        self.state.zone = zone
        self.state.transition_boost = 0.0

        if plan == "direct_shot":
            taker = self._best_player(team, ("long_shots", "technique", "composure"), exclude_positions={"GK"})
            self._advance_clock(self.rng.uniform(4.0, 7.0), team)
            self._drain(taker, 0.0010)
            return self._resolve_shot(
                PendingAction(
                    team,
                    taker.player.name,
                    "shoot",
                    zone,
                    danger=clamp(0.26 + 0.22 * float(diag["shot_quality"])),
                    pressure=0.05 + 0.10 * float(diag["block_density"]),
                    origin="free_kick",
                )
            )

        if plan == "delivery":
            taker = self._best_player(team, ("crossing", "technique", "vision"), exclude_positions={"GK"})
            target = self._best_player(team, ("heading", "strength", "off_ball"), exclude_positions={"GK"}, exclude_names={taker.player.name})
            self._advance_clock(self.rng.uniform(4.5, 8.0), team)
            self._drain(taker, 0.0009)
            if zone.band == Band.ATT:
                danger = clamp(0.34 + 0.20 * float(diag["delivery_quality"]) - 0.08 * float(diag["block_density"]), 0.28, 0.62)
                self.state.pending = PendingAction(
                    team,
                    taker.player.name,
                    "cross",
                    zone,
                    danger=danger,
                    pressure=clamp(0.14 + 0.18 * float(diag["block_density"])),
                    target=target.player.name,
                    origin="free_kick",
                )
                self.state.phase = "restart"
                return self._emit(
                    EventType.FREE_KICK,
                    team,
                    3,
                    "free_kick_delivery_pending",
                    taker=taker.player.name,
                    target=target.player.name,
                    plan=plan,
                    danger=round(danger, 3),
                )

            execution = clamp(
                0.50
                + 0.20 * taker.effective("passing") / 100.0
                + 0.14 * taker.effective("vision") / 100.0
                + 0.10 * target.effective("off_ball") / 100.0
                - 0.16 * float(diag["block_density"]),
                0.42,
                0.88,
            )
            if self.rng.random() >= execution:
                turnover_zone = zone.mirror()
                self._switch_possession(1 - team, turnover_zone, transition=0.16)
                return self._emit(EventType.TURNOVER, 1 - team, 2, "free_kick_delivery_lost", taker=taker.player.name, target=target.player.name, plan=plan, zone=self._zone_data(turnover_zone))
            new_band = Band.MID if zone.band == Band.DEF else Band.ATT
            new_zone = Zone(new_band, self._restart_lane_for_player(target))
            self._switch_possession(team, new_zone, transition=0.03)
            return self._emit(EventType.PROGRESSION, team, 2, "free_kick_delivery_progression", taker=taker.player.name, target=target.player.name, plan=plan, zone=self._zone_data(new_zone))

        taker = self._best_player(team, ("passing", "vision", "composure", "technique"), exclude_positions={"GK"})
        target = self._free_kick_safe_target(team, taker, zone)
        pressure = self._spatial_context(team, zone)["pressure"]
        success_p = clamp(
            0.76
            + 0.12 * taker.effective("passing") / 100.0
            + 0.08 * taker.effective("composure") / 100.0
            + 0.08 * target.effective("positioning") / 100.0
            - 0.13 * pressure,
            0.68,
            0.97,
        )
        self._advance_clock(self.rng.uniform(3.0, 6.5), team)
        self._drain(taker, 0.0006)
        if self.rng.random() >= success_p:
            turnover_zone = zone.mirror()
            transition = 0.30 if zone.band == Band.DEF else 0.18
            self._switch_possession(1 - team, turnover_zone, transition=transition)
            return self._emit(EventType.TURNOVER, 1 - team, 3 if zone.band == Band.DEF else 2, "free_kick_short_intercepted", taker=taker.player.name, target=target.player.name, plan=plan, zone=self._zone_data(turnover_zone))
        self._switch_possession(team, zone, transition=0.0)
        return self._emit(EventType.PROGRESSION, team, 2, "free_kick_short_restart", taker=taker.player.name, target=target.player.name, plan=plan, zone=self._zone_data(zone), success_probability=round(success_p, 3))

    def _resolve_restart(self):
        if self.state.restart == "goal_kick":
            team = self.state.possession if self.state.restart_team is None else int(self.state.restart_team)
            return self._resolve_goal_kick(team)

        if self.state.restart == "free_kick":
            team = self.state.restart_team
            zone = self.state.restart_zone
            if team in (0, 1) and zone is not None:
                quick_taker = self._best_player(team, ("passing", "vision", "composure", "technique"), exclude_positions={"GK"})
                quick_target = self._quick_free_kick_target(team, quick_taker, zone)
                quick_diag = self.quick_free_kick_diagnostic(team, zone, quick_taker, quick_target)
                if not quick_diag["active"]:
                    return self._resolve_deliberate_free_kick(team, zone)
        return super()._resolve_restart()


MatchEngine = MatchEngineV13Restarts
