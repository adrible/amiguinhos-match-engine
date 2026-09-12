from __future__ import annotations

"""Experimental v1.3 layer: coordinated offside line.

The frozen engine uses a compact through-ball offside probability based on the
raw defensive-line setting and runner intelligence.  This v1.3 layer replaces
that one calculation *only for the candidate* with a structural decision:

    defensive height + line coordination + passer pressure + match state
    versus runner timing / pace / hiddenness
    -> drop, hold, or step
    -> offside chance, or real space conceded when a step is beaten

The offside line is not a generic defensive bonus.  A successful step can catch
a runner; a failed step exposes depth.  Dropping protects against that specific
risk but deliberately creates almost no offside benefit.  No player attributes
are modified and the stable v1.2 files are untouched.
"""

from typing import Optional

from engine import Band, EventType, Lane, PendingAction, PlayerState, Zone, clamp
from engine_experiment_v13_communication import MatchEngineV13Communication


VERSION = (
    "1.3-candidate-spatial-creativity-boldness-offball-body-defense-"
    "marking-cover-communication-offside"
)


class MatchEngineV13Offside(MatchEngineV13Communication):
    """Adds contextual line height / offside-trap behaviour to through balls."""

    # ---------------------------- line structure ----------------------------

    def _line_members(self, defending_team: int) -> list[PlayerState]:
        primary = [
            ps for ps in self.teams[defending_team].on_field
            if ps.player.position.upper() in {"CB", "LB", "RB"}
        ]
        if len(primary) >= 3:
            return primary
        support = [
            ps for ps in self.teams[defending_team].on_field
            if ps.player.position.upper() == "DM" and ps not in primary
        ]
        return primary + support

    @staticmethod
    def _line_member_quality(ps: PlayerState) -> float:
        raw = (
            0.34 * ps.effective("positioning")
            + 0.27 * ps.effective("anticipation")
            + 0.18 * ps.effective("composure")
            + 0.13 * ps.effective("discipline")
            + 0.08 * ps.effective("pace")
        )
        return clamp((raw / 100.0) * (0.88 + 0.12 * ps.energy))

    def _line_coordination(self, defending_team: int, zone: Zone, ctx: dict) -> dict:
        members = self._line_members(defending_team)
        if not members:
            return {
                "members": [],
                "average": 0.0,
                "weak_link": 0.0,
                "spread": 1.0,
                "coordination": 0.0,
                "caller": None,
                "caller_quality": 0.0,
            }

        qualities = [self._line_member_quality(ps) for ps in members]
        average = sum(qualities) / len(qualities)
        weak_link = min(qualities)
        spread = max(qualities) - min(qualities)

        gk = self._goalkeeper(defending_team)
        callers = list(members) + [gk]
        caller_rows = []
        for ps in callers:
            pos = ps.player.position.upper()
            skill = self._communication_skill(ps, "cover_call")
            affinity = {"CB": 1.18, "GK": 1.12, "DM": 0.94, "LB": 0.88, "RB": 0.88}.get(pos, 0.55)
            caller_rows.append((ps, affinity * (0.58 + 0.42 * skill) * (0.88 + 0.12 * ps.energy)))
        caller, caller_score = max(caller_rows, key=lambda row: row[1])
        caller_quality = self._communication_skill(caller, "cover_call")

        tactics = self.teams[defending_team].team.tactics
        availability = clamp(float(ctx.get("defending_availability", 1.0)))
        coordination = (
            0.36 * average
            + 0.22 * weak_link
            + 0.18 * caller_quality
            + 0.16 * tactics.compactness
            + 0.08 * availability
            - 0.18 * spread
        )
        return {
            "members": [ps.player.name for ps in members],
            "average": clamp(average),
            "weak_link": clamp(weak_link),
            "spread": clamp(spread),
            "coordination": clamp(coordination),
            "caller": caller.player.name,
            "caller_quality": clamp(caller_quality),
        }

    @staticmethod
    def _runner_timing(target: PlayerState, movement: Optional[dict]) -> dict:
        base = clamp(
            0.46 * target.effective("off_ball") / 100.0
            + 0.31 * target.effective("anticipation") / 100.0
            + 0.17 * target.effective("pace") / 100.0
            + 0.06 * target.effective("composure") / 100.0
        )
        if isinstance(movement, dict):
            movement_timing = clamp(float(movement.get("timing", base)))
            hiddenness = clamp(float(movement.get("hiddenness", 0.0)))
            projection_seconds = float(movement.get("projection_seconds", 1.5))
            timing = clamp(0.70 * base + 0.30 * movement_timing)
        else:
            hiddenness = 0.0
            projection_seconds = 1.5
            timing = base
        return {
            "timing": timing,
            "hiddenness": hiddenness,
            "projection_seconds": projection_seconds,
        }

    def _offside_line_plan(
        self,
        attacking_team: int,
        actor: PlayerState,
        target: PlayerState,
        zone: Zone,
        ctx: dict,
        defensive_plan: dict,
    ) -> dict:
        defending_team = 1 - attacking_team
        tactics = self.teams[defending_team].team.tactics
        line = self._line_coordination(defending_team, zone, ctx)

        marking = defensive_plan.get("marking") if isinstance(defensive_plan.get("marking"), dict) else {}
        movement = marking.get("movement") if isinstance(marking.get("movement"), dict) else None
        runner = self._runner_timing(target, movement)

        line_height = clamp(float(tactics.defensive_line))
        compactness = clamp(float(tactics.compactness))
        pressure = clamp(float(ctx.get("pressure", 0.5)))
        depth = clamp(float(ctx.get("space_behind", 0.45)))
        transition = clamp(float(getattr(self.state, "transition_boost", 0.0)))
        coordination = line["coordination"]
        hiddenness = runner["hiddenness"]
        timing = runner["timing"]

        # Organisation preferences.  They are not probabilities and therefore
        # do not create an arbitrary number of traps per match.
        step = (
            0.22
            + 0.31 * line_height
            + 0.24 * coordination
            + 0.12 * compactness
            + 0.10 * pressure
            - 0.20 * transition
            - 0.13 * hiddenness
            - 0.07 * depth
        )
        hold = (
            0.36
            + 0.17 * coordination
            + 0.14 * compactness
            + 0.08 * pressure
            + 0.05 * (1.0 - line_height)
            - 0.05 * transition
        )
        drop = (
            0.20
            + 0.27 * (1.0 - line_height)
            + 0.16 * transition
            + 0.11 * hiddenness
            + 0.11 * timing
            + 0.08 * depth
            - 0.08 * coordination
        )

        scores = {"step_up": step, "hold_line": hold, "drop_and_track": drop}
        response = max(scores.items(), key=lambda row: row[1])[0]

        if response == "step_up":
            offside_probability = clamp(
                0.020
                + 0.090 * line_height
                + 0.075 * coordination
                + 0.045 * pressure
                + 0.025 * compactness
                - 0.100 * timing
                - 0.040 * hiddenness,
                0.015,
                0.22,
            )
            onside_exposure = clamp(
                0.014
                + 0.038 * (1.0 - coordination)
                + 0.030 * hiddenness
                + 0.020 * timing
                + 0.012 * transition,
                0.010,
                0.085,
            )
        elif response == "hold_line":
            offside_probability = clamp(
                0.012
                + 0.045 * line_height
                + 0.030 * coordination
                + 0.015 * pressure
                - 0.060 * timing
                - 0.018 * hiddenness,
                0.006,
                0.11,
            )
            onside_exposure = 0.0
        else:
            offside_probability = clamp(
                0.006
                + 0.020 * line_height
                + 0.010 * coordination
                - 0.035 * timing,
                0.003,
                0.055,
            )
            onside_exposure = 0.0

        return {
            "response": response,
            "scores": scores,
            "line_height": line_height,
            "compactness": compactness,
            "coordination": coordination,
            "line_members": line["members"],
            "weak_link": line["weak_link"],
            "spread": line["spread"],
            "caller": line["caller"],
            "caller_quality": line["caller_quality"],
            "runner": target.player.name,
            "runner_timing": timing,
            "runner_hiddenness": hiddenness,
            "projection_seconds": runner["projection_seconds"],
            "passer_pressure": pressure,
            "transition": transition,
            "offside_probability": offside_probability,
            "onside_exposure": onside_exposure,
        }

    @staticmethod
    def _apply_onside_tradeoff(ctx: dict, offside_plan: dict) -> dict:
        adjusted = dict(ctx)
        if offside_plan.get("response") != "step_up":
            return adjusted
        exposure = clamp(float(offside_plan.get("onside_exposure", 0.0)), 0.0, 0.10)
        # A beaten step has a real cost: more depth and slightly less immediate
        # pressure.  This is the opposite of stacking another defensive bonus.
        adjusted["space_behind"] = clamp(float(adjusted.get("space_behind", 0.45)) + exposure)
        adjusted["space"] = clamp(float(adjusted.get("space", 0.50)) + 0.45 * exposure)
        adjusted["pressure"] = clamp(float(adjusted.get("pressure", 0.50)) - 0.30 * exposure)
        adjusted["offside_trap_beaten"] = True
        adjusted["offside_exposure"] = exposure
        return adjusted

    # ---------------------------- diagnostics ----------------------------

    def offside_line_diagnostic(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: Optional[dict] = None,
        *,
        actor: Optional[str] = None,
        target: Optional[str] = None,
    ) -> dict:
        context = dict(ctx or {
            "pressure": 0.48,
            "space": 0.52,
            "space_behind": 0.48,
            "support": 0.50,
            "wide_space": 0.10,
            "defending_availability": 1.0,
        })
        actor_ps = self.teams[attacking_team].by_name(actor) if actor else self._choose_actor(attacking_team, zone)
        if target:
            target_ps = self.teams[attacking_team].by_name(target)
        else:
            candidates = [
                ps for ps in self.teams[attacking_team].on_field
                if ps.player.name != actor_ps.player.name and ps.player.position.upper() != "GK"
            ]
            target_ps = max(
                candidates,
                key=lambda ps: (
                    0.46 * ps.effective("off_ball")
                    + 0.31 * ps.effective("anticipation")
                    + 0.17 * ps.effective("pace")
                    + 0.06 * ps.effective("composure")
                ),
            )

        old = getattr(self, "_v13_defense_hint", None)
        self._v13_defense_hint = {
            "kind": "through_ball",
            "target": target_ps.player.name,
            "actor": actor_ps.player.name,
        }
        try:
            adjusted, defensive_plan = self._context_for_action(
                attacking_team,
                zone,
                context,
                "through_ball",
                target=target_ps.player.name,
            )
        finally:
            self._v13_defense_hint = old

        adjusted["space_behind"] = clamp(
            adjusted["space_behind"] - adjusted.get("runner_control", 0.0) * 0.60
        )
        adjusted["pressure"] = clamp(
            adjusted["pressure"] + adjusted.get("pass_lane_control", 0.0) * 0.35
        )
        plan = self._offside_line_plan(
            attacking_team, actor_ps, target_ps, zone, adjusted, defensive_plan
        )
        return {
            **plan,
            "actor": actor_ps.player.name,
            "base_context": context,
            "defensive_context": adjusted,
            "onside_context": self._apply_onside_tradeoff(adjusted, plan),
        }

    # ---------------------------- live integration ----------------------------

    def _create_or_resolve_danger(self, team, actor, zone, kind, ctx):
        if kind != "through_ball":
            return super()._create_or_resolve_danger(team, actor, zone, kind, ctx)

        # Choose the concrete receiver first.  This consumes a creativity-bound
        # receiver when one was selected during the decision beat, so the line
        # reacts to the actual run rather than to a generic attacker.
        target = self._choose_target(team, zone, attacking=True, exclude=actor.player.name)

        old = getattr(self, "_v13_defense_hint", None)
        self._v13_defense_hint = {
            "kind": kind,
            "target": target.player.name,
            "actor": actor.player.name,
        }
        try:
            adjusted, defensive_plan = self._context_for_action(
                team, zone, ctx, kind, target=target.player.name
            )
            adjusted["space_behind"] = clamp(
                adjusted["space_behind"] - adjusted.get("runner_control", 0.0) * 0.60
            )
            adjusted["pressure"] = clamp(
                adjusted["pressure"] + adjusted.get("pass_lane_control", 0.0) * 0.35
            )

            offside = self._offside_line_plan(
                team, actor, target, zone, adjusted, defensive_plan
            )
            if self.rng.random() < offside["offside_probability"]:
                self.stats[team].offsides += 1
                self._switch_possession(1 - team, Zone(Band.DEF, zone.lane), transition=0.0)
                return self._emit(
                    EventType.OFFSIDE,
                    team,
                    2,
                    "offside",
                    passer=actor.player.name,
                    runner=target.player.name,
                    line_response=offside["response"],
                    line_caller=offside["caller"],
                    line_coordination=round(offside["coordination"], 3),
                    offside_probability=round(offside["offside_probability"], 3),
                )

            live_ctx = self._apply_onside_tradeoff(adjusted, offside)
            defender = self._choose_defender(1 - team, zone)
            danger = self._danger_score(team, actor, target, zone, kind, live_ctx)
            execution = (
                0.40 * actor.effective("passing")
                + 0.20 * actor.effective("vision")
                + 0.20 * actor.effective("technique")
                + 0.20 * actor.effective("passing")
            )
            defending = (
                0.45 * defender.effective("positioning")
                + 0.35 * defender.effective("anticipation")
                + 0.20 * defender.effective("tackling")
            )
            p_create = clamp(
                0.20
                + (execution - defending) / 210.0
                + 0.10 * live_ctx["space"]
                + 0.07 * live_ctx["space_behind"]
                - 0.18 * live_ctx["pressure"],
                0.05,
                0.56,
            )
            self._drain(actor, 0.0020)
            if self.rng.random() >= p_create:
                if self.rng.random() < self._foul_probability(defender, actor, live_ctx):
                    return self._commit_foul(1 - team, defender, actor, zone)
                return self._turnover(team, actor, zone, "through_ball_stopped", live_ctx, severity=0.50)

            new_zone = self._danger_zone(zone, kind)
            self.state.zone = new_zone
            if new_zone.band == Band.ATT and zone.band != Band.ATT:
                self.stats[team].final_third_entries += 1
            self.state.pending = PendingAction(
                team=team,
                actor=target.player.name,
                kind=self._natural_next_action(new_zone, source=kind),
                zone=new_zone,
                danger=danger,
                pressure=self._spatial_context(team, new_zone)["pressure"],
                target=None,
                defender=defender.player.name,
                origin=kind,
                body_part="foot",
            )
            relevance = 4 if danger >= 0.76 else 3 if danger >= 0.58 else 2
            return self._emit(
                EventType.DANGER,
                team,
                relevance,
                "danger_created",
                creator=actor.player.name,
                receiver=target.player.name,
                kind=kind,
                zone=self._zone_data(new_zone),
                danger=round(danger, 3),
                line_response=offside["response"],
                line_caller=offside["caller"],
                offside_trap_beaten=bool(live_ctx.get("offside_trap_beaten", False)),
                offside_exposure=round(float(live_ctx.get("offside_exposure", 0.0)), 3),
            )
        finally:
            self._v13_defense_hint = old


MatchEngine = MatchEngineV13Offside
