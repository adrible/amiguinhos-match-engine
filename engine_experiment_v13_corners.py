from __future__ import annotations

"""v1.3 contextual corner-kick layer.

Corners are restarts rather than pre-baked shots. The team first chooses a
contextual pattern, then the existing crossing, box-movement, goalkeeper,
aerial-duel and second-ball systems determine what actually happens.
"""

from engine import Band, EventType, Lane, PendingAction, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_passing_texture import _stable_fraction
from engine_experiment_v13_roles import MatchEngineV13Roles

VERSION = "1.3-candidate-contextual-corners"


class MatchEngineV13Corners(MatchEngineV13Roles):
    CORNER_PATTERNS = ("short_corner", "near_post", "central_delivery", "far_post")

    def _corner_taker(self, team: int) -> PlayerState:
        return self._best_player(
            team,
            ("crossing", "technique", "vision", "composure"),
            exclude_positions={"GK"},
        )

    def _corner_keeper_command(self, defending_team: int) -> float:
        keeper = self._goalkeeper(defending_team)
        return clamp(
            (
                0.30 * keeper.effective("handling")
                + 0.27 * keeper.effective("gk_positioning")
                + 0.16 * keeper.effective("reflexes")
                + 0.14 * keeper.effective("strength")
                + 0.13 * keeper.effective("anticipation")
            )
            / 100.0
        )

    def _corner_attack_aerial_quality(self, team: int, taker: PlayerState) -> float:
        values = []
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position.upper() == "GK" or ps.player.name == taker.player.name:
                continue
            values.append(
                0.34 * ps.effective("heading")
                + 0.22 * ps.effective("strength")
                + 0.22 * ps.effective("off_ball")
                + 0.22 * ps.effective("anticipation")
            )
        best = sorted(values, reverse=True)[:3]
        return clamp(sum(best) / (100.0 * len(best))) if best else 0.50

    def _corner_defense_aerial_quality(self, team: int) -> float:
        values = []
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position.upper() == "GK":
                continue
            values.append(
                0.32 * ps.effective("heading")
                + 0.25 * ps.effective("positioning")
                + 0.22 * ps.effective("strength")
                + 0.21 * ps.effective("anticipation")
            )
        best = sorted(values, reverse=True)[:3]
        return clamp(sum(best) / (100.0 * len(best))) if best else 0.50

    def _corner_short_quality(self, team: int, taker: PlayerState) -> float:
        values = []
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position.upper() == "GK" or ps.player.name == taker.player.name:
                continue
            values.append(
                0.28 * ps.effective("technique")
                + 0.25 * ps.effective("passing")
                + 0.19 * ps.effective("dribbling")
                + 0.16 * ps.effective("composure")
                + 0.12 * ps.effective("vision")
            )
        best = sorted(values, reverse=True)[:3]
        return clamp(sum(best) / (100.0 * len(best))) if best else 0.50

    def corner_plan_diagnostic(self, team: int, zone: Zone | None = None) -> dict:
        """RNG-pure corner-plan preferences for the current match state."""
        zone = zone or self.state.restart_zone or Zone(Band.ATT, Lane.LEFT)
        tactics = self.teams[team].team.tactics
        opponent_tactics = self.teams[1 - team].team.tactics
        taker = self._corner_taker(team)
        delivery_quality = clamp(
            (
                0.40 * taker.effective("crossing")
                + 0.25 * taker.effective("technique")
                + 0.20 * taker.effective("vision")
                + 0.15 * taker.effective("composure")
            )
            / 100.0
        )
        attack_aerial = self._corner_attack_aerial_quality(team, taker)
        defense_aerial = self._corner_defense_aerial_quality(1 - team)
        short_quality = self._corner_short_quality(team, taker)
        keeper_command = self._corner_keeper_command(1 - team)
        h, a = self.score
        score_diff = (h - a) if team == 0 else (a - h)
        late = clamp((self.minute - 65.0) / 25.0)
        chasing = 1.0 if score_diff < 0 else 0.0
        protecting = 1.0 if score_diff > 0 else 0.0
        opponent_pressure = clamp(
            0.48 * opponent_tactics.pressing
            + 0.24 * opponent_tactics.compactness
            + 0.18 * opponent_tactics.defensive_line
            + 0.10 * max(0.0, opponent_tactics.mentality)
        )

        raw = {
            "short_corner": max(
                0.05,
                0.20
                + 0.56 * (1.0 - tactics.directness)
                + 0.28 * (1.0 - tactics.cross_frequency)
                + 0.36 * short_quality
                + 0.18 * tactics.width
                + 0.20 * protecting * late
                - 0.14 * opponent_pressure,
            ),
            "near_post": max(
                0.05,
                0.32
                + 0.34 * tactics.cross_frequency
                + 0.28 * delivery_quality
                + 0.27 * attack_aerial
                + 0.12 * tactics.directness
                + 0.12 * chasing * late
                - 0.12 * defense_aerial
                - 0.08 * keeper_command,
            ),
            "central_delivery": max(
                0.05,
                0.38
                + 0.36 * tactics.cross_frequency
                + 0.34 * delivery_quality
                + 0.33 * attack_aerial
                + 0.12 * chasing * late
                - 0.19 * defense_aerial
                - 0.19 * keeper_command,
            ),
            "far_post": max(
                0.05,
                0.29
                + 0.27 * tactics.cross_frequency
                + 0.31 * delivery_quality
                + 0.28 * attack_aerial
                + 0.18 * tactics.width
                + 0.08 * chasing * late
                - 0.13 * defense_aerial
                - 0.10 * keeper_command,
            ),
        }
        total = sum(raw.values()) or 1.0
        return {
            "zone": self._zone_data(zone),
            "taker": taker.player.name,
            "score_diff": score_diff,
            "late_factor": late,
            "delivery_quality": delivery_quality,
            "attack_aerial_quality": attack_aerial,
            "defense_aerial_quality": defense_aerial,
            "short_quality": short_quality,
            "keeper_command": keeper_command,
            "opponent_pressure": opponent_pressure,
            "weights": {name: value / total for name, value in raw.items()},
        }

    def _corner_short_receiver(self, team: int, taker: PlayerState, zone: Zone) -> PlayerState:
        rows = []
        side_positions = {"LB", "LW"} if zone.lane == Lane.LEFT else {"RB", "RW"}
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position.upper() == "GK" or ps.player.name == taker.player.name:
                continue
            pos = ps.player.position.upper()
            role = self.player_role_profile(ps)
            role_bonus = 0.0
            if role["primary"] in {"touchline_winger", "wide_creator", "overlapping_fullback"}:
                role_bonus = 0.11 * float(role["conviction"])
            quality = clamp(
                (
                    0.29 * ps.effective("technique")
                    + 0.24 * ps.effective("passing")
                    + 0.18 * ps.effective("dribbling")
                    + 0.16 * ps.effective("composure")
                    + 0.13 * ps.effective("vision")
                )
                / 100.0
            )
            side_bonus = 0.18 if pos in side_positions else 0.0
            rows.append((ps, 0.35 + quality + side_bonus + role_bonus))
        return weighted_choice(self.rng, rows)

    def _corner_target(self, team: int, taker: PlayerState, zone: Zone, pattern: str) -> PlayerState:
        context = {
            "pressure": 0.55,
            "space": 0.40,
            "support": 0.62,
            "space_behind": 0.20,
        }
        movement = self.box_movement_diagnostic(team, taker, zone, "cross", context)
        rows = []
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position.upper() == "GK" or ps.player.name == taker.player.name:
                continue
            heading = clamp(ps.effective("heading") / 100.0)
            strength = clamp(ps.effective("strength") / 100.0)
            anticipation = clamp(ps.effective("anticipation") / 100.0)
            off_ball = clamp(ps.effective("off_ball") / 100.0)
            pace = clamp(ps.effective("pace") / 100.0)
            finishing = clamp(ps.effective("finishing") / 100.0)
            if pattern == "near_post":
                score = 0.25 * anticipation + 0.22 * off_ball + 0.17 * pace + 0.19 * heading + 0.17 * finishing
            elif pattern == "far_post":
                score = 0.27 * heading + 0.22 * anticipation + 0.19 * off_ball + 0.17 * strength + 0.15 * finishing
            else:
                score = 0.30 * heading + 0.23 * strength + 0.19 * anticipation + 0.17 * off_ball + 0.11 * finishing
            role = self.player_role_profile(ps)
            if role["primary"] in {"target_forward", "poacher", "shadow_runner", "inside_forward"}:
                score += 0.08 * float(role["conviction"])
            if movement.get("target") == ps.player.name:
                score += 0.08 * float(movement.get("run_quality", 0.5))
            rows.append((ps, max(0.05, score)))
        return weighted_choice(self.rng, rows)

    def _corner_defender(self, defending_team: int) -> PlayerState:
        return self._best_player(
            defending_team,
            ("heading", "positioning", "strength", "anticipation"),
            exclude_positions={"GK"},
        )

    def _corner_run_quality(self, target: PlayerState, pattern: str) -> float:
        if pattern == "near_post":
            score = (
                0.28 * target.effective("anticipation")
                + 0.24 * target.effective("off_ball")
                + 0.18 * target.effective("pace")
                + 0.16 * target.effective("heading")
                + 0.14 * target.effective("finishing")
            )
        elif pattern == "far_post":
            score = (
                0.27 * target.effective("heading")
                + 0.23 * target.effective("anticipation")
                + 0.20 * target.effective("off_ball")
                + 0.16 * target.effective("strength")
                + 0.14 * target.effective("finishing")
            )
        else:
            score = (
                0.30 * target.effective("heading")
                + 0.22 * target.effective("strength")
                + 0.19 * target.effective("anticipation")
                + 0.17 * target.effective("off_ball")
                + 0.12 * target.effective("composure")
            )
        return clamp(score / 100.0)

    def _corner_cross_type(self, taker: PlayerState, target: PlayerState, zone: Zone, pattern: str) -> str:
        fraction = _stable_fraction(
            "corner-delivery-type",
            self.seed,
            round(self.state.second, 3),
            taker.player.name,
            target.player.name,
            pattern,
            zone.lane.value,
        )
        if pattern == "near_post":
            return "driven" if fraction < 0.58 else "whipped"
        if pattern == "far_post":
            return "floated" if fraction < 0.52 else "whipped"
        return "whipped" if fraction < 0.72 else "floated"

    @staticmethod
    def _corner_box_lane(corner_lane: Lane, pattern: str) -> Lane:
        if pattern == "central_delivery":
            return Lane.CENTER
        if pattern == "far_post":
            return Lane.RIGHT if corner_lane == Lane.LEFT else Lane.LEFT
        return corner_lane

    def _corner_delivery_profile(
        self,
        team: int,
        taker: PlayerState,
        target: PlayerState,
        zone: Zone,
        pattern: str,
        plan: dict,
    ) -> dict:
        pressure = clamp(
            0.30
            + 0.24 * float(plan["defense_aerial_quality"])
            + 0.12 * float(plan["keeper_command"])
        )
        base = self.cross_delivery_diagnostic(
            taker,
            target,
            zone,
            "cross",
            {"pressure": pressure, "space": 0.42, "support": 0.62},
        )
        pattern_fit = {
            "near_post": 0.020,
            "central_delivery": 0.000,
            "far_post": 0.012,
        }[pattern]
        quality = clamp(float(base["delivery_quality"]) + pattern_fit)
        return {
            **base,
            "cross_type": self._corner_cross_type(taker, target, zone, pattern),
            "aerial": True,
            "delivery_quality": quality,
            "pressure": pressure,
        }

    def corner_second_ball_diagnostic(
        self,
        team: int,
        taker: PlayerState,
        zone: Zone,
        delivery_quality: float = 0.5,
    ) -> dict:
        attack_rows = self._rebound_attacker_rows(team, taker, zone)
        defend_rows = self._rebound_defender_rows(1 - team, zone)
        attacker, attack_score = max(attack_rows, key=lambda row: row[1]) if attack_rows else (taker, 50.0)
        defender, defend_score = max(defend_rows, key=lambda row: row[1]) if defend_rows else (self._goalkeeper(1 - team), 50.0)
        attacker_win_probability = clamp(
            0.40
            + (attack_score - defend_score) / 180.0
            + 0.08 * (clamp(delivery_quality) - 0.50),
            0.20,
            0.74,
        )
        return {
            "attacker": attacker.player.name,
            "defender": defender.player.name,
            "attack_score": attack_score,
            "defend_score": defend_score,
            "attacker_win_probability": attacker_win_probability,
            "zone": zone,
        }

    def _resolve_corner_second_ball(
        self,
        team: int,
        taker: PlayerState,
        zone: Zone,
        delivery_quality: float,
        pattern: str,
    ):
        diag = self.corner_second_ball_diagnostic(team, taker, zone, delivery_quality)
        attack_rows = self._rebound_attacker_rows(team, taker, zone)
        defend_rows = self._rebound_defender_rows(1 - team, zone)
        attacker = weighted_choice(self.rng, attack_rows) if attack_rows else taker
        defender = weighted_choice(self.rng, defend_rows) if defend_rows else self._goalkeeper(1 - team)
        attack_reaction = clamp(
            (attacker.effective("anticipation") + attacker.effective("off_ball") + attacker.effective("positioning")) / 300.0
        )
        defend_reaction = clamp(
            (defender.effective("anticipation") + defender.effective("positioning") + defender.effective("tackling")) / 300.0
        )
        attacker_win_p = clamp(
            float(diag["attacker_win_probability"]) + 0.10 * (attack_reaction - defend_reaction),
            0.18,
            0.78,
        )
        self._advance_clock(self.rng.uniform(0.55, 1.45), team)
        if self.rng.random() < attacker_win_p:
            danger = clamp(
                0.27
                + 0.14 * attack_reaction
                + 0.09 * clamp(delivery_quality)
                - 0.08 * defend_reaction,
                0.24,
                0.53,
            )
            pressure = clamp(0.40 + 0.24 * defend_reaction - 0.08 * attack_reaction)
            kind = self._rebound_next_action(zone, danger, pressure)
            self.state.possession = team
            self.state.zone = zone
            self.state.phase = "chance_creation"
            self.state.transition_boost = 0.0
            self.state.pending = PendingAction(
                team=team,
                actor=attacker.player.name,
                kind=kind,
                zone=zone,
                danger=danger,
                pressure=pressure,
                defender=defender.player.name,
                origin="second_ball",
            )
            return self._emit(
                EventType.REBOUND,
                team,
                3,
                "corner_second_ball_attacker",
                pattern=pattern,
                taker=taker.player.name,
                next_player=attacker.player.name,
                defender=defender.player.name,
                next_action=kind,
                zone=self._zone_data(zone),
                danger=round(danger, 3),
                attacker_win_probability=round(attacker_win_p, 3),
                second_ball_read=True,
            )

        defending_team = 1 - team
        control_p = clamp(
            0.38
            + 0.23 * defender.effective("composure") / 100.0
            + 0.17 * defender.effective("positioning") / 100.0
            - 0.12 * attack_reaction,
            0.28,
            0.78,
        )
        if self.rng.random() < control_p:
            new_zone = Zone(Band.DEF, zone.mirror().lane)
            transition = 0.0
            key = "corner_second_ball_defender_controls"
        else:
            new_zone = Zone(Band.MID, zone.mirror().lane)
            transition = 0.10
            key = "corner_second_ball_cleared"
        self._switch_possession(defending_team, new_zone, transition=transition)
        return self._emit(
            EventType.REBOUND,
            defending_team,
            2,
            key,
            pattern=pattern,
            taker=taker.player.name,
            attacker=attacker.player.name,
            defender=defender.player.name,
            zone=self._zone_data(new_zone),
            attacker_win_probability=round(attacker_win_p, 3),
            defender_control_probability=round(control_p, 3),
            second_ball_read=True,
        )

    def _resolve_short_corner(self, team: int, taker: PlayerState, zone: Zone, plan: dict):
        receiver = self._corner_short_receiver(team, taker, zone)
        pressure = float(plan["opponent_pressure"])
        success_p = clamp(
            0.63
            + 0.13 * taker.effective("passing") / 100.0
            + 0.12 * taker.effective("technique") / 100.0
            + 0.11 * receiver.effective("technique") / 100.0
            + 0.08 * receiver.effective("composure") / 100.0
            - 0.18 * pressure,
            0.62,
            0.94,
        )
        self._advance_clock(self.rng.uniform(2.2, 4.8), team)
        self._drain(taker, 0.0005)
        if self.rng.random() < success_p:
            new_zone = Zone(Band.ATT, zone.lane)
            self._switch_possession(team, new_zone, transition=0.02)
            return self._emit(
                EventType.PROGRESSION,
                team,
                2,
                "corner_short_combination",
                pattern="short_corner",
                taker=taker.player.name,
                receiver=receiver.player.name,
                success_probability=round(success_p, 3),
                zone=self._zone_data(new_zone),
            )
        new_zone = Zone(Band.ATT, zone.lane).mirror()
        self._switch_possession(1 - team, new_zone, transition=0.26)
        return self._emit(
            EventType.TURNOVER,
            1 - team,
            2,
            "corner_short_intercepted",
            pattern="short_corner",
            taker=taker.player.name,
            receiver=receiver.player.name,
            lost_by_team=team,
            success_probability=round(success_p, 3),
            zone=self._zone_data(new_zone),
        )

    def _arm_corner_contact(
        self,
        team: int,
        taker: PlayerState,
        target: PlayerState,
        defender: PlayerState,
        zone: Zone,
        pattern: str,
        delivery: dict,
        run_quality: float,
        aerial_edge: float,
        defense_aerial: float,
        keeper_command: float,
        contact_probability: float,
    ):
        box_lane = self._corner_box_lane(zone.lane, pattern)
        cross_type = str(delivery["cross_type"])
        body_part = "head"
        if pattern == "near_post" and cross_type == "driven" and target.effective("finishing") > target.effective("heading") + 6.0:
            body_part = "foot"
        danger = clamp(
            {"near_post": 0.42, "central_delivery": 0.43, "far_post": 0.39}[pattern]
            + 0.12 * (float(delivery["delivery_quality"]) - 0.50)
            + 0.10 * (run_quality - 0.50)
            + 0.10 * (aerial_edge - 0.50),
            0.28,
            0.66,
        )
        pressure = clamp(
            0.46
            + 0.18 * defense_aerial
            + 0.10 * keeper_command
            - 0.15 * aerial_edge,
            0.28,
            0.76,
        )
        shot_zone = Zone(Band.BOX, box_lane)
        self.state.possession = team
        self.state.zone = shot_zone
        self.state.phase = "restart"
        self.state.transition_boost = 0.0
        self.state.pending = PendingAction(
            team=team,
            actor=target.player.name,
            kind="shoot",
            zone=shot_zone,
            danger=danger,
            pressure=pressure,
            defender=defender.player.name,
            origin="corner",
            body_part=body_part,
        )
        self._v13_cross_context = {
            "team": team,
            "origin": "corner",
            "target": target.player.name,
            "crosser": taker.player.name,
            "cross_type": cross_type,
            "aerial": body_part == "head",
            "delivery_quality": float(delivery["delivery_quality"]),
            "until_resolution": True,
        }
        return self._emit(
            EventType.CORNER,
            team,
            3,
            "corner_delivery_pending",
            pattern=pattern,
            taker=taker.player.name,
            target=target.player.name,
            defender=defender.player.name,
            cross_type=cross_type,
            delivery_quality=round(float(delivery["delivery_quality"]), 3),
            run_quality=round(run_quality, 3),
            aerial_attacker_edge=round(aerial_edge, 3),
            contact_probability=round(contact_probability, 3),
            danger=round(danger, 3),
            pressure=round(pressure, 3),
            body_part=body_part,
            zone=self._zone_data(shot_zone),
        )

    def _resolve_contextual_corner(self, team: int, zone: Zone):
        self.state.restart = None
        self.state.restart_team = None
        self.state.restart_zone = None
        self.state.possession = team
        self.state.zone = zone
        self.state.transition_boost = 0.0
        self.state.phase = "restart"

        plan = self.corner_plan_diagnostic(team, zone)
        pattern = weighted_choice(self.rng, list(plan["weights"].items()))
        taker = self._corner_taker(team)
        if pattern == "short_corner":
            return self._resolve_short_corner(team, taker, zone, plan)

        target = self._corner_target(team, taker, zone, pattern)
        defender = self._corner_defender(1 - team)
        delivery = self._corner_delivery_profile(team, taker, target, zone, pattern, plan)
        run_quality = self._corner_run_quality(target, pattern)
        aerial = self.aerial_duel_diagnostic(target, defender, float(delivery["delivery_quality"]))
        aerial_edge = float(aerial["attacker_edge"])
        contact_probability = clamp(
            0.18
            + 0.28 * float(delivery["delivery_quality"])
            + 0.22 * run_quality
            + 0.24 * aerial_edge
            - 0.10 * float(plan["keeper_command"]),
            0.22,
            0.80,
        )
        self._advance_clock(self.rng.uniform(4.0, 7.4), team)
        self._drain(taker, 0.0009)
        if self.rng.random() < contact_probability:
            return self._arm_corner_contact(
                team,
                taker,
                target,
                defender,
                zone,
                pattern,
                delivery,
                run_quality,
                aerial_edge,
                float(plan["defense_aerial_quality"]),
                float(plan["keeper_command"]),
                contact_probability,
            )

        loose_probability = clamp(
            0.22
            + 0.27 * float(delivery["delivery_quality"])
            + 0.12 * run_quality
            + 0.10 * (1.0 - float(plan["defense_aerial_quality"])),
            0.24,
            0.66,
        )
        box_zone = Zone(Band.BOX, self._corner_box_lane(zone.lane, pattern))
        if self.rng.random() < loose_probability:
            return self._resolve_corner_second_ball(
                team,
                taker,
                box_zone,
                float(delivery["delivery_quality"]),
                pattern,
            )

        new_zone = box_zone.mirror()
        self._switch_possession(1 - team, new_zone, transition=0.32)
        return self._emit(
            EventType.PROGRESSION,
            1 - team,
            2,
            "corner_cleared_contextual",
            pattern=pattern,
            taker=taker.player.name,
            target=target.player.name,
            defender=defender.player.name,
            cross_type=delivery["cross_type"],
            delivery_quality=round(float(delivery["delivery_quality"]), 3),
            contact_probability=round(contact_probability, 3),
            loose_ball_probability=round(loose_probability, 3),
            zone=self._zone_data(new_zone),
        )

    def _resolve_restart(self):
        if self.state.restart == "corner":
            team = self.state.restart_team
            zone = self.state.restart_zone
            if team in (0, 1) and zone is not None:
                return self._resolve_contextual_corner(int(team), zone)
        return super()._resolve_restart()


MatchEngine = MatchEngineV13Corners
