from __future__ import annotations

"""v1.3 canonical top layer: goalkeeper decisions on crosses plus contextual kick-offs.

Match-intelligence and final-third layers sit below it so the external v1.3
entrypoint stays stable.  Kick-offs are resolved only when play is explicitly
advanced; constructing a live match remains pristine at 0:00.
"""

from engine import (
    Band,
    DEF_C,
    EventType,
    Lane,
    MID_C,
    PendingAction,
    PlayerState,
    Zone,
    clamp,
    weighted_choice,
)
from engine_experiment_v13_transition_choice import MatchEngineV13TransitionChoice
from engine_experiment_v13_passing_texture import _stable_fraction

VERSION = "1.3-candidate-keeper-crosses"


class MatchEngineV13KeeperCrosses(MatchEngineV13TransitionChoice):
    # ----------------------- kick-off intelligence -----------------------
    def _initial_kickoff_due(self) -> bool:
        """A fresh match has a kick-off to resolve, but no pre-simulated state."""
        return bool(
            self.state.second <= 0.0
            and not self.state.event_log
            and self.state.pending is None
            and self.state.restart is None
            and self.state.period_index == 0
            and self.state.possession == self.state.kickoff_team
            and self.state.zone == MID_C
        )

    def step(self):
        if self._initial_kickoff_due():
            return self._resolve_v13_kickoff(self.state.kickoff_team, reason="match_start")
        return super().step()

    def _check_period_boundary(self):
        event = super()._check_period_boundary()
        if event is not None and event.type == EventType.PERIOD_END and not self.state.ended:
            self.state.restart = "kickoff"
            self.state.restart_team = self.state.possession
            self.state.restart_zone = MID_C
            self.state.phase = "restart"
        return event

    def start_extra_time(self) -> None:
        super().start_extra_time()
        self.state.restart = "kickoff"
        self.state.restart_team = self.state.possession
        self.state.restart_zone = MID_C
        self.state.phase = "restart"

    def _resolve_restart(self):
        if self.state.restart != "kickoff":
            return super()._resolve_restart()
        team = self.state.possession if self.state.restart_team is None else int(self.state.restart_team)
        reason = self._kickoff_reason()
        self.state.restart = None
        self.state.restart_team = None
        self.state.restart_zone = None
        return self._resolve_v13_kickoff(team, reason=reason)

    def _kickoff_reason(self) -> str:
        if not self.state.event_log and self.minute <= 0.01:
            return "match_start"
        if self.state.event_log:
            last = self.state.event_log[-1]
            if last.type == EventType.GOAL:
                return "after_goal"
            if last.type == EventType.PERIOD_END:
                return "period_restart"
        return "restart"

    def _kickoff_build_quality(self, team: int) -> float:
        players = [ps for ps in self.teams[team].on_field if ps.player.position.upper() != "GK"]
        if not players:
            return 0.50
        ranked = sorted(
            players,
            key=lambda ps: 0.38 * ps.effective("passing")
            + 0.34 * ps.effective("composure")
            + 0.28 * ps.effective("vision"),
            reverse=True,
        )[:4]
        return clamp(
            sum(
                0.38 * ps.effective("passing")
                + 0.34 * ps.effective("composure")
                + 0.28 * ps.effective("vision")
                for ps in ranked
            )
            / (100.0 * len(ranked))
        )

    def _kickoff_aerial_quality(self, team: int) -> float:
        players = [ps for ps in self.teams[team].on_field if ps.player.position.upper() != "GK"]
        if not players:
            return 0.50
        return clamp(
            max(
                0.42 * ps.effective("heading")
                + 0.33 * ps.effective("strength")
                + 0.25 * ps.effective("off_ball")
                for ps in players
            )
            / 100.0
        )

    def kickoff_plan_diagnostic(self, team: int) -> dict:
        """Return contextual kick-off preferences without consuming RNG."""
        tactics = self.teams[team].team.tactics
        opponent = self.teams[1 - team].team.tactics
        h, a = self.score
        score_diff = (h - a) if team == 0 else (a - h)
        late = clamp((self.minute - 55.0) / 35.0)
        chasing = 1.0 if score_diff < 0 else 0.0
        protecting = 1.0 if score_diff > 0 else 0.0
        pressure = clamp(
            0.08
            + 0.54 * opponent.pressing
            + 0.13 * opponent.defensive_line
            + 0.07 * max(0.0, opponent.mentality)
        )
        build_quality = self._kickoff_build_quality(team)
        aerial_quality = self._kickoff_aerial_quality(team)
        overlap = 0.5 * (tactics.overlap_left + tactics.overlap_right)

        raw = {
            "short_recycle": max(
                0.05,
                0.62
                + 0.78 * (1.0 - tactics.directness)
                + 0.42 * (1.0 - tactics.risk)
                + 0.30 * build_quality
                + 0.55 * protecting * late
                + 0.15 * max(0.0, -tactics.mentality)
                - 0.16 * pressure * max(0.0, 0.68 - build_quality),
            ),
            "wide_release": max(
                0.05,
                0.42
                + 0.82 * tactics.width
                + 0.26 * overlap
                + 0.18 * tactics.tempo
                + 0.12 * (1.0 - pressure),
            ),
            "vertical_probe": max(
                0.05,
                0.34
                + 0.64 * tactics.tempo
                + 0.68 * tactics.risk
                + 0.44 * max(0.0, tactics.mentality)
                + 0.66 * chasing * late
                + 0.16 * tactics.counter,
            ),
            "direct_launch": max(
                0.05,
                0.16
                + 0.98 * tactics.directness
                + 0.34 * tactics.counter
                + 0.34 * pressure
                + 0.40 * chasing * late
                + 0.22 * aerial_quality,
            ),
        }
        total = sum(raw.values()) or 1.0
        weights = {key: value / total for key, value in raw.items()}
        return {
            "reason": self._kickoff_reason(),
            "score_diff": score_diff,
            "late_factor": late,
            "opponent_pressure": pressure,
            "build_quality": build_quality,
            "aerial_quality": aerial_quality,
            "weights": weights,
        }

    def _kickoff_taker(self, team: int) -> PlayerState:
        role_weight = {
            "ST": 1.20,
            "AM": 1.12,
            "CM": 1.05,
            "RW": 0.88,
            "LW": 0.88,
            "DM": 0.82,
            "RB": 0.30,
            "LB": 0.30,
            "CB": 0.12,
        }
        candidates = []
        for ps in self.teams[team].on_field:
            pos = ps.player.position.upper()
            if pos == "GK":
                continue
            quality = clamp(
                (0.40 * ps.effective("technique")
                + 0.34 * ps.effective("composure")
                + 0.26 * ps.effective("passing"))
                / 100.0
            )
            candidates.append((ps, role_weight.get(pos, 0.45) * (0.65 + 0.55 * quality)))
        if not candidates:
            return self._best_player(team, ("technique", "composure", "passing"))
        return weighted_choice(self.rng, candidates)

    def _kickoff_receiver(self, team: int, taker: PlayerState, pattern: str) -> PlayerState:
        role_profiles = {
            "short_recycle": {
                "DM": 1.55, "CM": 1.45, "CB": 1.20, "LB": 0.85, "RB": 0.85,
                "AM": 0.60, "LW": 0.30, "RW": 0.30, "ST": 0.18,
            },
            "wide_release": {
                "LB": 1.35, "RB": 1.35, "LW": 1.30, "RW": 1.30, "CM": 0.72,
                "AM": 0.62, "DM": 0.55, "ST": 0.40, "CB": 0.22,
            },
            "vertical_probe": {
                "AM": 1.45, "ST": 1.30, "LW": 1.18, "RW": 1.18, "CM": 0.80,
                "DM": 0.35, "LB": 0.28, "RB": 0.28, "CB": 0.10,
            },
            "direct_launch": {
                "ST": 1.65, "LW": 1.05, "RW": 1.05, "AM": 0.78, "CM": 0.42,
                "DM": 0.18, "LB": 0.15, "RB": 0.15, "CB": 0.08,
            },
        }
        candidates = []
        for ps in self.teams[team].on_field:
            if ps.player.name == taker.player.name or ps.player.position.upper() == "GK":
                continue
            pos = ps.player.position.upper()
            if pattern == "direct_launch":
                quality = (
                    0.42 * ps.effective("heading")
                    + 0.31 * ps.effective("strength")
                    + 0.27 * ps.effective("off_ball")
                ) / 100.0
            elif pattern == "vertical_probe":
                quality = (
                    0.40 * ps.effective("off_ball")
                    + 0.32 * ps.effective("anticipation")
                    + 0.28 * ps.effective("technique")
                ) / 100.0
            elif pattern == "wide_release":
                quality = (
                    0.36 * ps.effective("positioning")
                    + 0.34 * ps.effective("technique")
                    + 0.30 * ps.effective("pace")
                ) / 100.0
            else:
                quality = (
                    0.38 * ps.effective("positioning")
                    + 0.33 * ps.effective("composure")
                    + 0.29 * ps.effective("passing")
                ) / 100.0
            base = role_profiles[pattern].get(pos, 0.25)
            candidates.append((ps, base * (0.62 + 0.62 * clamp(quality))))
        if not candidates:
            return self._best_player(team, ("positioning", "composure", "passing"), exclude_names={taker.player.name})
        return weighted_choice(self.rng, candidates)

    def _kickoff_lane(self, receiver: PlayerState, pattern: str) -> Lane:
        pos = receiver.player.position.upper()
        if pos in {"LB", "LW"}:
            return Lane.LEFT
        if pos in {"RB", "RW"}:
            return Lane.RIGHT
        if pattern == "wide_release":
            tactics = self.teams[self.state.possession].team.tactics
            return weighted_choice(
                self.rng,
                [
                    (Lane.LEFT, 0.55 + tactics.overlap_left),
                    (Lane.RIGHT, 0.55 + tactics.overlap_right),
                ],
            )
        return Lane.CENTER

    def _kickoff_success_probability(
        self,
        team: int,
        taker: PlayerState,
        receiver: PlayerState,
        pattern: str,
        pressure: float,
    ) -> float:
        tactics = self.teams[team].team.tactics
        taker_quality = clamp(
            (0.42 * taker.effective("passing")
            + 0.33 * taker.effective("technique")
            + 0.25 * taker.effective("composure"))
            / 100.0
        )
        if pattern == "direct_launch":
            receiver_quality = clamp(
                (0.42 * receiver.effective("heading")
                + 0.31 * receiver.effective("strength")
                + 0.27 * receiver.effective("anticipation"))
                / 100.0
            )
            base, press_cost = 0.53, 0.07
            tactical_fit = 0.10 * tactics.directness + 0.05 * tactics.counter
            bounds = (0.34, 0.80)
        elif pattern == "vertical_probe":
            receiver_quality = clamp(
                (0.40 * receiver.effective("off_ball")
                + 0.32 * receiver.effective("anticipation")
                + 0.28 * receiver.effective("technique"))
                / 100.0
            )
            base, press_cost = 0.64, 0.13
            tactical_fit = 0.05 * tactics.tempo + 0.05 * tactics.risk
            bounds = (0.43, 0.88)
        elif pattern == "wide_release":
            receiver_quality = clamp(
                (0.36 * receiver.effective("positioning")
                + 0.34 * receiver.effective("technique")
                + 0.30 * receiver.effective("pace"))
                / 100.0
            )
            base, press_cost = 0.75, 0.10
            tactical_fit = 0.06 * tactics.width
            bounds = (0.58, 0.94)
        else:
            receiver_quality = clamp(
                (0.38 * receiver.effective("positioning")
                + 0.33 * receiver.effective("composure")
                + 0.29 * receiver.effective("passing"))
                / 100.0
            )
            base, press_cost = 0.84, 0.12
            tactical_fit = 0.08 * (1.0 - tactics.directness)
            bounds = (0.68, 0.98)
        value = (
            base
            + 0.24 * (taker_quality - 0.70)
            + 0.18 * (receiver_quality - 0.70)
            + tactical_fit
            - press_cost * pressure
        )
        return clamp(value, bounds[0], bounds[1])

    def _resolve_v13_kickoff(self, team: int, *, reason: str) -> object:
        self.state.possession = team
        self.state.zone = MID_C
        self.state.transition_boost = 0.0
        self.state.phase = "restart"

        diag = self.kickoff_plan_diagnostic(team)
        pattern = weighted_choice(self.rng, list(diag["weights"].items()))
        taker = self._kickoff_taker(team)
        receiver = self._kickoff_receiver(team, taker, pattern)
        lane = self._kickoff_lane(receiver, pattern)
        pressure = float(diag["opponent_pressure"])
        success_probability = self._kickoff_success_probability(
            team, taker, receiver, pattern, pressure
        )
        opponent_response = (
            "jump_press" if pressure >= 0.62 else
            "screen_and_step" if pressure >= 0.42 else
            "mid_block"
        )
        duration_ranges = {
            "short_recycle": (6.5, 11.5),
            "wide_release": (5.5, 10.0),
            "vertical_probe": (4.5, 8.5),
            "direct_launch": (4.0, 7.5),
        }
        lo, hi = duration_ranges[pattern]
        self._advance_clock(self.rng.uniform(lo, hi), team)
        success = self.rng.random() < success_probability

        common = {
            "kickoff_team": team,
            "pattern": pattern,
            "taker": taker.player.name,
            "receiver": receiver.player.name,
            "reason": reason,
            "opponent_response": opponent_response,
            "pressure": round(pressure, 3),
            "success_probability": round(success_probability, 3),
            "score_diff": int(diag["score_diff"]),
        }

        if success:
            if pattern == "short_recycle":
                zone = Zone(Band.DEF, lane if lane != Lane.CENTER else Lane.CENTER)
                transition = 0.0
                text_key = "kickoff_short_recycle"
                event_type = EventType.INFO
            elif pattern == "wide_release":
                zone = Zone(Band.MID, lane)
                transition = 0.03
                text_key = "kickoff_wide_release"
                event_type = EventType.PROGRESSION
            elif pattern == "vertical_probe":
                zone = Zone(Band.MID, lane)
                transition = 0.07
                text_key = "kickoff_vertical_probe"
                event_type = EventType.PROGRESSION
            else:
                zone = Zone(Band.MID, lane)
                transition = 0.10
                text_key = "kickoff_direct_launch"
                event_type = EventType.PROGRESSION
            self._switch_possession(team, zone, transition=transition)
            return self._emit(
                event_type,
                team,
                2,
                text_key,
                **common,
                zone=self._zone_data(zone),
            )

        turnover_zone = Zone(Band.MID, lane).mirror()
        transition = {
            "short_recycle": 0.24,
            "wide_release": 0.17,
            "vertical_probe": 0.22,
            "direct_launch": 0.10,
        }[pattern]
        self._switch_possession(1 - team, turnover_zone, transition=transition)
        return self._emit(
            EventType.TURNOVER,
            1 - team,
            2,
            "kickoff_turnover",
            **common,
            lost_by_team=team,
            zone=self._zone_data(turnover_zone),
        )

    # ----------------------- goalkeeper on crosses -----------------------
    def keeper_cross_diagnostic(
        self,
        keeper: PlayerState,
        p: PendingAction,
        attacker: PlayerState,
        *,
        cross_context: dict | None = None,
    ) -> dict:
        handling = clamp(keeper.effective("handling") / 100.0)
        positioning = clamp(keeper.effective("gk_positioning") / 100.0)
        reflexes = clamp(keeper.effective("reflexes") / 100.0)
        strength = clamp(keeper.effective("strength") / 100.0)
        anticipation = clamp(keeper.effective("anticipation") / 100.0)
        command_score = clamp(
            0.30 * handling
            + 0.27 * positioning
            + 0.16 * reflexes
            + 0.14 * strength
            + 0.13 * anticipation
        )
        cross_type = (cross_context or {}).get("cross_type")
        high_ball = p.body_part == "head" or cross_type in {"whipped", "floated", "driven"}
        crowd = clamp(float(p.pressure) + (0.10 if p.origin == "corner" else 0.0))
        come_probability = clamp(
            0.07
            + 0.54 * command_score
            + (0.10 if high_ball else -0.08)
            - 0.22 * crowd
            - 0.12 * float(p.danger),
            0.04,
            0.72,
        )
        fraction = _stable_fraction(
            "keeper-cross",
            self.seed,
            round(self.state.second, 3),
            keeper.player.name,
            attacker.player.name,
            p.origin,
            cross_type or "unknown",
        )
        if fraction >= come_probability:
            decision = "hold_line"
        elif handling >= 0.66 and command_score >= 0.60:
            decision = "claim"
        else:
            decision = "punch"
        success_probability = clamp(
            0.28
            + 0.46 * command_score
            + 0.08 * handling
            - 0.18 * crowd
            - 0.14 * float(p.danger),
            0.18,
            0.84,
        )
        return {
            "decision": decision,
            "command_score": command_score,
            "come_probability": come_probability,
            "success_probability": success_probability,
            "cross_type": cross_type,
            "high_ball": high_ball,
        }

    def _resolve_shot(self, p):
        relevant = p.origin in {"cross", "corner", "free_kick"} and p.zone.band == Band.BOX
        diag = None
        failed_command = False
        if relevant:
            keeper = self._goalkeeper(1 - p.team)
            try:
                attacker = self.teams[p.team].by_name(p.actor)
            except KeyError:
                attacker = self._named_or_fallback(p.team, p.actor, role="actor", zone=p.zone)
            marker = self._v13_cross_context if isinstance(getattr(self, "_v13_cross_context", None), dict) else None
            diag = self.keeper_cross_diagnostic(keeper, p, attacker, cross_context=marker)
            if diag["decision"] in {"claim", "punch"}:
                success = self.rng.random() < float(diag["success_probability"])
                self._drain(keeper, 0.0015 if diag["decision"] == "claim" else 0.0020)
                if success:
                    defending = 1 - p.team
                    self._v13_cross_context = None
                    if diag["decision"] == "claim":
                        self._switch_possession(defending, DEF_C, transition=0.0)
                        return self._emit(
                            EventType.INFO,
                            defending,
                            2,
                            "keeper_claims_cross",
                            keeper=keeper.player.name,
                            target=attacker.player.name,
                            keeper_cross_decision="claim",
                            keeper_command_score=round(float(diag["command_score"]), 3),
                            cross_type=diag.get("cross_type"),
                        )
                    self._switch_possession(defending, DEF_C, transition=0.14)
                    return self._emit(
                        EventType.PROGRESSION,
                        defending,
                        2,
                        "keeper_punches_cross_clear",
                        keeper=keeper.player.name,
                        target=attacker.player.name,
                        keeper_cross_decision="punch",
                        keeper_command_score=round(float(diag["command_score"]), 3),
                        cross_type=diag.get("cross_type"),
                    )
                failed_command = True
                p.danger = clamp(float(p.danger) + 0.045)
                p.pressure = clamp(float(p.pressure) - 0.030)

        event = super()._resolve_shot(p)
        if diag is not None:
            event.data.setdefault("keeper_cross_decision", diag["decision"])
            event.data.setdefault("keeper_command_score", round(float(diag["command_score"]), 3))
            event.data.setdefault("keeper_cross_success_probability", round(float(diag["success_probability"]), 3))
            if failed_command:
                event.data.setdefault("keeper_cross_failed", True)
            self._v13_cross_context = None
        return event


MatchEngine = MatchEngineV13KeeperCrosses
