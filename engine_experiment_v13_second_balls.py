from __future__ import annotations

"""Live second-ball contests beyond shot rebounds for v1.3.

This layer handles loose balls after aerial/clearance-type failures.  It does
not replace the dedicated shot-rebound system.  A second ball is generated only
from an event that would otherwise turn possession over and is resolved from
positioning, anticipation, strength, heading, energy and local structure.
"""

from engine import Band, EventType, Lane, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_micro_adjustments import MatchEngineV13MicroAdjustments


class MatchEngineV13SecondBalls(MatchEngineV13MicroAdjustments):
    _SECOND_BALL_REASONS = {
        "cross_cleared": 0.66,
        "cutback_cleared": 0.48,
        "through_ball_cleared": 0.34,
        "long_ball_failed": 0.62,
        "cross_stopped": 0.38,
        "cutback_stopped": 0.31,
    }

    @staticmethod
    def _second_ball_role_bonus(position: str, *, attacking: bool, lane: Lane) -> float:
        if attacking:
            base = {
                "DM": 7.0,
                "CM": 8.0,
                "AM": 5.5,
                "ST": 4.5,
                "LW": 3.5,
                "RW": 3.5,
                "CB": 2.0,
                "LB": 2.5,
                "RB": 2.5,
            }.get(position, 0.0)
        else:
            base = {
                "CB": 8.0,
                "DM": 7.0,
                "CM": 5.5,
                "LB": 4.0,
                "RB": 4.0,
                "ST": 1.0,
                "AM": 1.5,
            }.get(position, 0.0)
        if lane == Lane.CENTER and position in {"CB", "DM", "CM", "AM", "ST"}:
            base += 2.0
        if lane == Lane.LEFT and position in {"LB", "LW", "CM", "DM"}:
            base += 1.6
        if lane == Lane.RIGHT and position in {"RB", "RW", "CM", "DM"}:
            base += 1.6
        return base

    def _second_ball_rows(self, team: int, zone: Zone, *, attacking: bool):
        rows = []
        for ps in self.teams[int(team)].on_field:
            if ps.red or ps.player.position.upper() == "GK":
                continue
            pos = ps.player.position.upper()
            if attacking:
                score = (
                    0.30 * ps.effective("anticipation")
                    + 0.22 * ps.effective("positioning")
                    + 0.18 * ps.effective("off_ball")
                    + 0.12 * ps.effective("strength")
                    + 0.10 * ps.effective("heading")
                    + 0.08 * ps.effective("composure")
                )
            else:
                score = (
                    0.30 * ps.effective("anticipation")
                    + 0.26 * ps.effective("positioning")
                    + 0.16 * ps.effective("strength")
                    + 0.13 * ps.effective("heading")
                    + 0.09 * ps.effective("tackling")
                    + 0.06 * ps.effective("composure")
                )
            score += 4.0 * ps.energy + self._second_ball_role_bonus(pos, attacking=attacking, lane=zone.lane)
            rows.append((ps, max(1.0, score)))
        return rows

    def _second_ball_zone(self, original_zone: Zone, reason: str) -> Zone:
        if reason in {"cross_cleared", "cutback_cleared", "cross_stopped", "cutback_stopped"}:
            lane = original_zone.lane
            if lane != Lane.CENTER and self.rng.random() < 0.42:
                lane = Lane.CENTER
            return Zone(Band.ATT, lane)
        if original_zone.band in {Band.ATT, Band.BOX}:
            return Zone(Band.MID, original_zone.lane)
        return Zone(Band.MID, original_zone.lane)

    def second_ball_diagnostic(self, attacking_team: int, zone: Zone) -> dict:
        attack_rows = self._second_ball_rows(attacking_team, zone, attacking=True)
        defend_rows = self._second_ball_rows(1 - attacking_team, zone, attacking=False)
        attacker, attack_score = max(attack_rows, key=lambda row: row[1]) if attack_rows else (self._goalkeeper(attacking_team), 50.0)
        defender, defend_score = max(defend_rows, key=lambda row: row[1]) if defend_rows else (self._goalkeeper(1 - attacking_team), 50.0)
        atk_tactics = self.teams[attacking_team].team.tactics
        def_tactics = self.teams[1 - attacking_team].team.tactics
        structure = 0.035 * (atk_tactics.compactness - def_tactics.compactness)
        p_attack = clamp(0.47 + (attack_score - defend_score) / 210.0 + structure, 0.22, 0.76)
        return {
            "zone": zone,
            "attacker": attacker.player.name,
            "defender": defender.player.name,
            "attack_score": attack_score,
            "defend_score": defend_score,
            "attacker_win_probability": p_attack,
        }

    def _resolve_general_second_ball(self, attacking_team: int, actor: PlayerState, zone: Zone, reason: str):
        diag = self.second_ball_diagnostic(attacking_team, zone)
        attack_rows = self._second_ball_rows(attacking_team, zone, attacking=True)
        defend_rows = self._second_ball_rows(1 - attacking_team, zone, attacking=False)
        attacker = weighted_choice(self.rng, attack_rows) if attack_rows else actor
        defender = weighted_choice(self.rng, defend_rows) if defend_rows else self._goalkeeper(1 - attacking_team)
        p_attack = clamp(
            float(diag["attacker_win_probability"])
            + 0.05 * ((attacker.effective("anticipation") - defender.effective("anticipation")) / 100.0),
            0.20,
            0.78,
        )
        if hasattr(self, "_advance_live_detail_clock"):
            self._advance_live_detail_clock(1.8, attacking_team)
        else:
            self._advance_clock(1.8, attacking_team)

        if self.rng.random() < p_attack:
            self.state.possession = attacking_team
            self.state.zone = zone
            self.state.transition_boost = 0.0
            self.state.phase = "final_third" if zone.band == Band.ATT else "progression"
            danger = clamp(0.22 + 0.18 * p_attack + (0.08 if zone.band == Band.ATT else 0.0))
            if zone.band == Band.ATT and self.rng.random() < 0.42 + 0.18 * p_attack:
                self.state.pending = self._pending_from_second_ball(
                    attacking_team, attacker, defender, zone, danger
                )
                relevance = 3
                text_key = "second_ball_attack_continues"
            else:
                self.state.pending = None
                relevance = 2
                text_key = "second_ball_attack_recovers"
            return self._emit(
                EventType.REBOUND,
                attacking_team,
                relevance,
                text_key,
                player=attacker.player.name,
                defender=defender.player.name,
                source_reason=reason,
                zone=self._zone_data(zone),
                attacker_win_probability=round(p_attack, 3),
                danger=round(danger, 3),
                second_ball_live=True,
            )

        defending_team = 1 - attacking_team
        control = clamp(
            0.43
            + (defender.effective("composure") - 70.0) / 300.0
            + 0.10 * defender.effective("positioning") / 100.0,
            0.30,
            0.76,
        )
        clean = self.rng.random() < control
        new_zone = Zone(Band.DEF if clean else Band.MID, zone.mirror().lane)
        self._switch_possession(defending_team, new_zone, transition=0.0 if clean else 0.12)
        self.state.pending = None
        return self._emit(
            EventType.REBOUND,
            defending_team,
            2,
            "second_ball_defender_controls" if clean else "second_ball_defender_clears",
            player=defender.player.name,
            opponent=attacker.player.name,
            source_reason=reason,
            zone=self._zone_data(new_zone),
            attacker_win_probability=round(p_attack, 3),
            defender_control_probability=round(control, 3),
            second_ball_live=True,
        )

    def _pending_from_second_ball(self, team: int, attacker: PlayerState, defender: PlayerState, zone: Zone, danger: float):
        from engine import PendingAction
        kind = self._natural_next_action(zone, source="second_ball")
        return PendingAction(
            team=team,
            actor=attacker.player.name,
            kind=kind,
            zone=zone,
            danger=danger,
            pressure=self._spatial_context(team, zone)["pressure"],
            defender=defender.player.name,
            origin="second_ball",
        )

    def _turnover(self, losing_team, actor, zone, reason, ctx, severity=0.5):
        loose_probability = self._SECOND_BALL_REASONS.get(str(reason))
        if loose_probability is not None:
            structure = clamp(0.5 * float(ctx.get("support", 0.5)) + 0.5 * (1.0 - float(ctx.get("pressure", 0.5))))
            p_loose = clamp(loose_probability * (0.78 + 0.32 * structure), 0.18, 0.72)
            if self.rng.random() < p_loose:
                loose_zone = self._second_ball_zone(zone, str(reason))
                return self._resolve_general_second_ball(int(losing_team), actor, loose_zone, str(reason))
        return super()._turnover(losing_team, actor, zone, reason, ctx, severity=severity)


MatchEngine = MatchEngineV13SecondBalls

__all__ = ["MatchEngineV13SecondBalls", "MatchEngine"]
