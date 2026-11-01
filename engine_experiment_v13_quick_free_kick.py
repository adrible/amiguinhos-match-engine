from __future__ import annotations

"""v1.3 final-third stage 6: contextual quick free kicks."""

from engine import Band, EventType, PendingAction, PlayerState, Zone, clamp
from engine_experiment_v13_pressing_traps import MatchEngineV13PressingTraps
from engine_experiment_v13_passing_texture import _stable_fraction

VERSION = "1.3-candidate-quick-free-kick"


class MatchEngineV13QuickFreeKick(MatchEngineV13PressingTraps):
    def _quick_free_kick_target(self, team: int, taker: PlayerState, zone: Zone) -> PlayerState | None:
        candidates = []
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position.upper() == "GK" or ps.player.name == taker.player.name:
                continue
            score = (
                0.40 * ps.effective("off_ball")
                + 0.26 * ps.effective("anticipation")
                + 0.20 * ps.effective("pace")
                + 0.14 * ps.effective("technique")
            )
            pos = ps.player.position.upper()
            if zone.band == Band.ATT and pos in {"ST", "AM", "LW", "RW"}:
                score += 9.0
            elif zone.band == Band.MID and pos in {"AM", "CM", "LW", "RW", "ST"}:
                score += 5.0
            candidates.append((score, ps))
        if not candidates:
            return None
        return max(candidates, key=lambda row: row[0])[1]

    def quick_free_kick_diagnostic(
        self,
        team: int,
        zone: Zone,
        taker: PlayerState,
        target: PlayerState | None,
    ) -> dict:
        tactics = self.teams[team].team.tactics
        vision = clamp(taker.effective("vision") / 100.0)
        passing = clamp(taker.effective("passing") / 100.0)
        composure = clamp(taker.effective("composure") / 100.0)
        target_quality = 0.0 if target is None else clamp(
            0.45 * target.effective("off_ball") / 100.0
            + 0.30 * target.effective("anticipation") / 100.0
            + 0.25 * target.effective("pace") / 100.0
        )
        opp = self.teams[1 - team].team.tactics
        recent_card_or_injury = bool(
            self.state.event_log
            and self.state.event_log[-1].type in {EventType.CARD, EventType.INJURY}
        )
        referee_busy = bool(
            getattr(self, "_referee_event_queue", None)
            or getattr(self, "_deferred_discipline", None)
            or getattr(self, "_review_queue", None)
        )
        direct_shot_zone = zone.band == Band.ATT and zone.lane.value == "center"
        score_context = self.score[team] - self.score[1 - team]
        urgency = 0.08 if score_context < 0 and self.minute >= 60.0 else 0.0
        advantage = clamp(
            0.10
            + 0.18 * tactics.tempo
            + 0.12 * tactics.risk
            + 0.18 * vision
            + 0.16 * passing
            + 0.10 * composure
            + 0.14 * target_quality
            + urgency
            + 0.08 * opp.defensive_line
            - 0.12 * opp.compactness
            - (0.18 if direct_shot_zone else 0.0)
        )
        fraction = _stable_fraction(
            "quick-free-kick",
            self.seed,
            round(self.state.second, 3),
            team,
            taker.player.name,
            "" if target is None else target.player.name,
            zone.band.value,
            zone.lane.value,
        )
        attempt_probability = clamp(0.03 + 0.34 * advantage, 0.03, 0.38)
        active = (
            target is not None
            and not referee_busy
            and not recent_card_or_injury
            and zone.band in {Band.DEF, Band.MID, Band.ATT}
            and fraction < attempt_probability
        )
        return {
            "active": active,
            "advantage": advantage,
            "attempt_probability": attempt_probability,
            "target_quality": target_quality,
            "referee_busy": referee_busy,
            "direct_shot_zone": direct_shot_zone,
        }

    def _resolve_restart(self):
        if self.state.restart != "free_kick":
            return super()._resolve_restart()

        team = self.state.restart_team
        zone = self.state.restart_zone
        if team not in (0, 1) or zone is None:
            return super()._resolve_restart()

        taker = self._best_player(
            team,
            ("passing", "vision", "composure", "technique"),
            exclude_positions={"GK"},
        )
        target = self._quick_free_kick_target(team, taker, zone)
        diag = self.quick_free_kick_diagnostic(team, zone, taker, target)
        if not diag["active"] or target is None:
            return super()._resolve_restart()

        ctx = self._spatial_context(team, zone)
        lane = self.passing_lane_diagnostic(team, taker, target, zone, "progressive_pass", ctx)
        success_p = clamp(
            0.42
            + 0.22 * taker.effective("passing") / 100.0
            + 0.14 * taker.effective("vision") / 100.0
            + 0.10 * float(diag["target_quality"])
            + 0.10 * float(diag["advantage"])
            + 0.10 * float(lane["openness"])
            - 0.24 * float(lane["interception_risk"]),
            0.28,
            0.88,
        )

        self.state.restart = None
        self.state.restart_team = None
        self.state.restart_zone = None
        self.state.phase = "normal"
        self._advance_clock(1.15, team)
        self._drain(taker, 0.0008)

        if self.rng.random() >= success_p:
            event = self._turnover(
                team,
                taker,
                zone,
                "quick_free_kick_intercepted",
                ctx,
                severity=0.46,
            )
            event.data.setdefault("quick_free_kick", True)
            event.data.setdefault("quick_free_kick_taker", taker.player.name)
            event.data.setdefault("quick_free_kick_target", target.player.name)
            event.data.setdefault("quick_free_kick_success_probability", round(success_p, 3))
            event.data.setdefault("passing_lane", lane["status"])
            return event

        new_zone = self._progress_zone(zone, "progressive_pass")
        self.state.possession = team
        self.state.zone = new_zone
        self.state.phase = self._phase_for_zone(new_zone)
        danger = clamp(
            0.18
            + 0.26 * float(diag["advantage"])
            + 0.16 * float(diag["target_quality"])
            + 0.12 * float(lane["openness"])
        )
        if new_zone.band in {Band.ATT, Band.BOX} and danger >= 0.42:
            self.state.pending = PendingAction(
                team=team,
                actor=target.player.name,
                kind=self._natural_next_action(new_zone),
                zone=new_zone,
                danger=danger,
                pressure=self._spatial_context(team, new_zone)["pressure"],
                origin="quick_free_kick",
            )
            return self._emit(
                EventType.DANGER,
                team,
                3 if danger >= 0.62 else 2,
                "quick_free_kick_creates_danger",
                taker=taker.player.name,
                target=target.player.name,
                zone=self._zone_data(new_zone),
                danger=round(danger, 3),
                quick_free_kick=True,
                quick_free_kick_success_probability=round(success_p, 3),
                passing_lane=lane["status"],
                passing_lane_openness=round(float(lane["openness"]), 3),
            )

        return self._emit(
            EventType.PROGRESSION,
            team,
            2,
            "quick_free_kick",
            taker=taker.player.name,
            target=target.player.name,
            zone=self._zone_data(new_zone),
            quick_free_kick=True,
            quick_free_kick_success_probability=round(success_p, 3),
            passing_lane=lane["status"],
            passing_lane_openness=round(float(lane["openness"]), 3),
        )


MatchEngine = MatchEngineV13QuickFreeKick
