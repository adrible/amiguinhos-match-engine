from __future__ import annotations

"""v1.3 rebound and second-ball continuity.

Rebounds remain consequences of shots.  This layer gives the loose ball a
trajectory, lets attackers, defenders and (after a save) the goalkeeper contest
it, and consumes a small amount of real match time before the next action.
"""

from engine import Band, EventType, Lane, PendingAction, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_passing_texture import _stable_fraction
from engine_experiment_v13_restarts import MatchEngineV13Restarts

VERSION = "1.3-candidate-rebounds"


class MatchEngineV13Rebounds(MatchEngineV13Restarts):
    def _rebound_ball_zone(self, p: PendingAction, *, blocked: bool, post: bool) -> Zone:
        """Keep rebound geometry connected to the shot instead of random teleporting."""
        fraction = _stable_fraction(
            "rebound-trajectory",
            self.seed,
            round(self.state.second, 3),
            p.team,
            p.actor,
            p.zone.lane.value,
            p.origin,
            p.rebound_depth,
            blocked,
            post,
        )
        lane = p.zone.lane
        if lane == Lane.CENTER:
            if fraction < 0.16:
                lane = Lane.LEFT
            elif fraction > 0.84:
                lane = Lane.RIGHT
        else:
            # Wide shots/blocks mostly stay on that side; some spill centrally.
            central_threshold = 0.36 if blocked else 0.30 if post else 0.42
            if fraction < central_threshold:
                lane = Lane.CENTER
        return Zone(Band.BOX, lane)

    @staticmethod
    def _attacking_role_bonus(position: str, lane: Lane) -> float:
        base = {
            "ST": 8.0,
            "AM": 6.0,
            "LW": 4.5,
            "RW": 4.5,
            "CM": 2.5,
            "DM": 0.5,
            "LB": 0.5,
            "RB": 0.5,
            "CB": -2.0,
        }.get(position, 0.0)
        if lane == Lane.LEFT and position == "LW":
            base += 3.5
        if lane == Lane.RIGHT and position == "RW":
            base += 3.5
        if lane == Lane.CENTER and position in {"ST", "AM"}:
            base += 2.5
        return base

    @staticmethod
    def _defending_role_bonus(position: str, lane: Lane) -> float:
        base = {
            "CB": 8.0,
            "DM": 5.0,
            "LB": 4.0,
            "RB": 4.0,
            "CM": 2.0,
            "AM": -1.0,
            "LW": -1.0,
            "RW": -1.0,
            "ST": -2.0,
        }.get(position, 0.0)
        if lane == Lane.LEFT and position in {"RB", "CB"}:
            base += 3.0
        if lane == Lane.RIGHT and position in {"LB", "CB"}:
            base += 3.0
        if lane == Lane.CENTER and position in {"CB", "DM"}:
            base += 2.5
        return base

    def _rebound_attacker_rows(self, team: int, shooter: PlayerState, zone: Zone):
        rows = []
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position.upper() == "GK" or ps.player.name == shooter.player.name:
                continue
            score = (
                0.31 * ps.effective("anticipation")
                + 0.25 * ps.effective("off_ball")
                + 0.16 * ps.effective("pace")
                + 0.13 * ps.effective("positioning")
                + 0.10 * ps.effective("composure")
                + 5.0 * ps.energy
                + self._attacking_role_bonus(ps.player.position.upper(), zone.lane)
            )
            rows.append((ps, max(1.0, score)))
        return rows

    def _rebound_defender_rows(self, team: int, zone: Zone):
        rows = []
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position.upper() == "GK":
                continue
            score = (
                0.30 * ps.effective("anticipation")
                + 0.27 * ps.effective("positioning")
                + 0.17 * ps.effective("tackling")
                + 0.13 * ps.effective("strength")
                + 0.08 * ps.effective("pace")
                + 5.0 * ps.energy
                + self._defending_role_bonus(ps.player.position.upper(), zone.lane)
            )
            rows.append((ps, max(1.0, score)))
        return rows

    def rebound_contest_diagnostic(
        self,
        team: int,
        p: PendingAction,
        shooter: PlayerState,
        xg: float,
        *,
        blocked: bool = False,
        post: bool = False,
    ) -> dict:
        zone = self._rebound_ball_zone(p, blocked=blocked, post=post)
        attack_rows = self._rebound_attacker_rows(team, shooter, zone)
        defend_rows = self._rebound_defender_rows(1 - team, zone)
        attacker, attack_score = max(attack_rows, key=lambda row: row[1]) if attack_rows else (shooter, 50.0)
        defender, defend_score = max(defend_rows, key=lambda row: row[1]) if defend_rows else (self._goalkeeper(1 - team), 50.0)
        source_bonus = 0.035 if post else 0.020 if blocked else 0.055
        attacker_win_probability = clamp(
            0.43
            + (attack_score - defend_score) / 175.0
            + source_bonus
            + 0.08 * clamp(xg)
            - 0.045 * p.rebound_depth,
            0.20,
            0.76,
        )

        keeper_recovery_probability = 0.0
        if not blocked and not post:
            keeper = self._goalkeeper(1 - team)
            handling = clamp(keeper.effective("handling") / 100.0)
            reflexes = clamp(keeper.effective("reflexes") / 100.0)
            positioning = clamp(keeper.effective("gk_positioning") / 100.0)
            keeper_recovery_probability = clamp(
                0.06
                + 0.30 * handling
                + 0.14 * reflexes
                + 0.10 * positioning
                - 0.17 * float(p.danger)
                - 0.10 * float(p.pressure)
                - 0.04 * p.rebound_depth,
                0.05,
                0.48,
            )

        return {
            "zone": zone,
            "attacker": attacker.player.name,
            "defender": defender.player.name,
            "attack_score": attack_score,
            "defend_score": defend_score,
            "attacker_win_probability": attacker_win_probability,
            "keeper_recovery_probability": keeper_recovery_probability,
            "source": "post" if post else "block" if blocked else "save_spill",
        }

    def _rebound_next_action(self, zone: Zone, danger: float, pressure: float) -> str:
        if zone.lane == Lane.CENTER:
            return weighted_choice(
                self.rng,
                [
                    ("shoot", 0.64 + 0.24 * danger),
                    ("cutback", 0.16 + 0.12 * pressure),
                    ("dribble", 0.10),
                ],
            )
        return weighted_choice(
            self.rng,
            [
                ("shoot", 0.38 + 0.20 * danger),
                ("cutback", 0.34 + 0.16 * pressure),
                ("dribble", 0.14),
            ],
        )

    def _create_rebound(self, team, p, shooter, xg, blocked=False, post=False):
        diag = self.rebound_contest_diagnostic(
            team,
            p,
            shooter,
            xg,
            blocked=blocked,
            post=post,
        )
        zone = diag["zone"]
        # The ball is genuinely loose for a moment; do not stack events at one timestamp.
        self._advance_clock(self.rng.uniform(0.65, 1.75), team)

        if diag["keeper_recovery_probability"] > 0.0:
            keeper = self._goalkeeper(1 - team)
            if self.rng.random() < float(diag["keeper_recovery_probability"]):
                self._switch_possession(1 - team, Zone(Band.DEF, zone.mirror().lane), transition=0.0)
                return self._emit(
                    EventType.REBOUND,
                    1 - team,
                    3,
                    "keeper_recovers_rebound",
                    keeper=keeper.player.name,
                    shooter=shooter.player.name,
                    source=diag["source"],
                    zone=self._zone_data(zone),
                    keeper_recovery_probability=round(float(diag["keeper_recovery_probability"]), 3),
                    second_ball_read=True,
                )

        attack_rows = self._rebound_attacker_rows(team, shooter, zone)
        defend_rows = self._rebound_defender_rows(1 - team, zone)
        attacker = weighted_choice(self.rng, attack_rows) if attack_rows else shooter
        defender = weighted_choice(self.rng, defend_rows) if defend_rows else self._goalkeeper(1 - team)
        attack_reaction = clamp(
            (attacker.effective("anticipation") + attacker.effective("off_ball") + attacker.effective("positioning")) / 300.0
        )
        defend_reaction = clamp(
            (defender.effective("anticipation") + defender.effective("positioning") + defender.effective("tackling")) / 300.0
        )
        attacker_win_p = clamp(
            float(diag["attacker_win_probability"])
            + 0.10 * (attack_reaction - defend_reaction),
            0.18,
            0.78,
        )

        if self.rng.random() < attacker_win_p:
            danger = clamp(
                0.34
                + 0.30 * clamp(xg)
                + 0.15 * attack_reaction
                - 0.10 * defend_reaction
                - 0.10 * p.rebound_depth
                + (0.04 if post else 0.0)
            )
            pressure = clamp(
                0.34
                + 0.28 * defend_reaction
                + 0.10 * float(p.pressure)
                - 0.08 * attack_reaction
            )
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
                origin="rebound",
                rebound_depth=p.rebound_depth + 1,
            )
            return self._emit(
                EventType.REBOUND,
                team,
                4 if danger >= 0.56 else 3,
                "rebound_attacker_wins",
                shooter=shooter.player.name,
                next_player=attacker.player.name,
                defender=defender.player.name,
                next_action=kind,
                source=diag["source"],
                previous_xg=round(float(xg), 3),
                zone=self._zone_data(zone),
                danger=round(danger, 3),
                pressure=round(pressure, 3),
                attacker_win_probability=round(attacker_win_p, 3),
                second_ball_read=True,
                second_ball_reaction=round(attack_reaction, 3),
                defender_reaction=round(defend_reaction, 3),
            )

        defender_control = clamp(
            0.38
            + 0.24 * defender.effective("composure") / 100.0
            + 0.16 * defender.effective("technique") / 100.0
            + 0.12 * defender.effective("positioning") / 100.0
            - 0.14 * attack_reaction,
            0.28,
            0.78,
        )
        defending_team = 1 - team
        if self.rng.random() < defender_control:
            new_zone = Zone(Band.DEF, zone.mirror().lane)
            self._switch_possession(defending_team, new_zone, transition=0.0)
            key = "rebound_defender_controls"
            transition = 0.0
        else:
            new_zone = Zone(Band.MID, zone.mirror().lane)
            transition = 0.08
            self._switch_possession(defending_team, new_zone, transition=transition)
            key = "rebound_defender_clears"
        return self._emit(
            EventType.REBOUND,
            defending_team,
            3,
            key,
            shooter=shooter.player.name,
            defender=defender.player.name,
            attacker=attacker.player.name,
            source=diag["source"],
            zone=self._zone_data(new_zone),
            attacker_win_probability=round(attacker_win_p, 3),
            defender_control_probability=round(defender_control, 3),
            transition=round(transition, 3),
            second_ball_read=True,
            second_ball_reaction=round(attack_reaction, 3),
            defender_reaction=round(defend_reaction, 3),
        )


MatchEngine = MatchEngineV13Rebounds
