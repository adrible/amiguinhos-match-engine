from __future__ import annotations

"""Experimental v1.3 layer: local numerical overloads (2v1 / 3v2).

An overload is not a new defensive bonus. It is a local geometry problem:
several meaningful attacking movements arrive in the same threatened channel
while fewer defenders are actually committed there.

The defence therefore redistributes *existing* control between ball, runner and
passing lane. It may split the difference, pull one real helper, or delay and
screen. Every response carries a spatial/pressure cost; no virtual defender is
created and no player attribute is modified.
"""

from typing import Optional

from engine import Band, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_offside import MatchEngineV13Offside


VERSION = (
    "1.3-candidate-spatial-creativity-boldness-offball-body-defense-"
    "marking-cover-communication-offside-overload"
)


class MatchEngineV13Overload(MatchEngineV13Offside):
    """Adds local 2v1 / 3v2 recognition and responsibility redistribution."""

    @staticmethod
    def _zero_overload_effects() -> dict:
        return {
            "pressure_delta": 0.0,
            "space_delta": 0.0,
            "depth_delta": 0.0,
            "wide_space_delta": 0.0,
            "pass_lane_control": 0.0,
            "runner_control": 0.0,
            "dribble_control": 0.0,
            "cross_control": 0.0,
            "box_protection": 0.0,
        }

    @staticmethod
    def _movement_is_local(zone: Zone, movement: dict) -> bool:
        projected_lane = movement.get("projected_lane")
        projected_band = movement.get("projected_band")
        intent = str(movement.get("intent") or "")

        if projected_lane is None or projected_band is None:
            return False

        # Same-lane runs are naturally local. On a wide attack an inside support
        # movement (underlap/diagonal/third-man) also belongs to the same local
        # overload because it forces the wide defender to choose between ball
        # and inside receiver. We deliberately do not count a far-side runner.
        if projected_lane == zone.lane:
            lane_local = True
        elif zone.lane != Lane.CENTER and projected_lane == Lane.CENTER:
            lane_local = intent in {
                "underlap", "diagonal_run", "third_man_run", "between_lines",
                "box_attack", "cutback_support", "late_arrival",
            }
        elif zone.lane == Lane.CENTER and projected_lane == Lane.CENTER:
            lane_local = True
        else:
            lane_local = False

        if not lane_local:
            return False

        order = {Band.DEF: 0, Band.MID: 1, Band.ATT: 2, Band.BOX: 3}
        # A local support run may stay on the same horizontal band or advance by
        # one band. A BOX run from ATT is also local. Anything farther is not
        # treated as part of this immediate 1-2 second numerical problem.
        return abs(order[projected_band] - order[zone.band]) <= 1

    def _local_attacking_threats(
        self,
        attacking_team: int,
        actor: PlayerState,
        zone: Zone,
        ctx: dict,
        *,
        max_support: int = 2,
    ) -> list[dict]:
        rows: list[dict] = []
        for ps in self.teams[attacking_team].on_field:
            if ps.player.name == actor.player.name or ps.player.position.upper() == "GK":
                continue
            try:
                movement = self._best_movement(attacking_team, actor, ps, zone, ctx)
                if not isinstance(movement, dict) or not self._movement_is_local(zone, movement):
                    continue
                quality = float(self._movement_quality(ps, movement, zone, ctx))
            except (AttributeError, KeyError, TypeError, ValueError):
                continue

            # A runner only counts as a numerical threat if the current movement
            # is credible enough that a defender must respect it. The threshold
            # defines local presence; it is not a quota for overload frequency.
            presence = clamp(
                quality
                + 0.06 * clamp(float(ctx.get("support", 0.5)))
                + 0.04 * clamp(float(movement.get("timing", 0.5)))
                - 0.03 * clamp(float(ctx.get("pressure", 0.5)))
            )
            if presence < 0.50:
                continue
            rows.append({
                "player": ps,
                "name": ps.player.name,
                "movement": movement,
                "quality": clamp(quality),
                "presence": presence,
            })

        rows.sort(key=lambda row: (row["presence"], row["quality"]), reverse=True)
        return rows[:max_support]

    @staticmethod
    def _committed_defender_names(plan: dict) -> list[str]:
        names: list[str] = []

        def add(value) -> None:
            if value and str(value) not in names:
                names.append(str(value))

        add(plan.get("defender_name"))
        marking = plan.get("marking") if isinstance(plan.get("marking"), dict) else {}
        add(marking.get("marker_name"))
        coverage = plan.get("coverage") if isinstance(plan.get("coverage"), dict) else {}
        if coverage.get("active"):
            add(coverage.get("defender_name"))
        # Communication coordinates one of the relations above. It does not
        # magically add the communicator as another local defender.
        return names

    def _best_overload_helper(
        self,
        defending_team: int,
        zone: Zone,
        plan: dict,
        *,
        exclude_names: set[str],
    ) -> tuple[Optional[PlayerState], float]:
        marking = plan.get("marking") if isinstance(plan.get("marking"), dict) else {}
        mode = str(marking.get("mode") or "hybrid")
        rows: list[tuple[PlayerState, float]] = []
        for ps in self.teams[defending_team].on_field:
            if ps.player.position.upper() == "GK" or ps.player.name in exclude_names:
                continue
            affinity = self._zone_role_affinity(ps, zone)
            skill = self._marking_skill(ps, mode)
            availability = 0.82 + 0.18 * ps.energy
            # Interior defenders are usually the viable helper on a wide 2v1;
            # fullbacks can be helpers centrally, but not from the far side.
            pos = ps.player.position.upper()
            role = 1.0
            if zone.lane != Lane.CENTER and pos in {"CB", "DM", "CM"}:
                role = 1.08
            elif zone.lane == Lane.LEFT and pos == "LB":
                role = 0.62
            elif zone.lane == Lane.RIGHT and pos == "RB":
                role = 0.62
            score = affinity * (0.58 + 0.42 * skill) * availability * role
            rows.append((ps, score))
        if not rows:
            return None, 0.0
        return max(rows, key=lambda row: row[1])

    @staticmethod
    def _overload_label(attackers: int, defenders: int) -> str:
        return f"{attackers}v{defenders}"

    def _overload_response(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        plan: dict,
        attackers: int,
        defenders: int,
        helper: Optional[PlayerState],
        helper_score: float,
    ) -> tuple[str, dict[str, float]]:
        defending_team = 1 - attacking_team
        tactics = self.teams[defending_team].team.tactics
        primary = plan.get("defender")
        if isinstance(primary, PlayerState):
            primary_quality = clamp(
                0.42 * primary.effective("positioning") / 100.0
                + 0.32 * primary.effective("anticipation") / 100.0
                + 0.16 * primary.effective("tackling") / 100.0
                + 0.10 * primary.effective("composure") / 100.0
            )
        else:
            primary_quality = clamp(float(plan.get("quality", 0.5)))

        transition = clamp(float(getattr(self.state, "transition_boost", 0.0)))
        depth = clamp(float(ctx.get("space_behind", 0.45)))
        pressure = clamp(float(ctx.get("pressure", 0.50)))
        severity = clamp((attackers - defenders) / max(1.0, float(attackers)))
        helper_quality = 0.0
        if helper is not None:
            marking = plan.get("marking") if isinstance(plan.get("marking"), dict) else {}
            helper_quality = self._marking_skill(helper, str(marking.get("mode") or "hybrid"))

        split = (
            0.34
            + 0.28 * primary_quality
            + 0.12 * (1.0 - transition)
            + 0.10 * pressure
            + 0.08 * (1.0 if attackers == 2 else 0.0)
            - 0.08 * depth
        )
        pull = (
            0.24
            + 0.28 * tactics.compactness
            + 0.18 * helper_quality
            + 0.09 * clamp(helper_score)
            + 0.10 * severity
            + 0.07 * (1.0 if attackers >= 3 else 0.0)
            - 0.14 * transition
        )
        if helper is None:
            pull = -1.0
        delay = (
            0.31
            + 0.25 * transition
            + 0.16 * depth
            + 0.14 * (1.0 - primary_quality)
            + 0.09 * severity
            + 0.05 * (1.0 - pressure)
        )
        scores = {
            "split_difference": split,
            "pull_helper": pull,
            "delay_and_screen": delay,
        }
        return max(scores.items(), key=lambda row: row[1])[0], scores

    @classmethod
    def _redistribute_overload_effects(cls, base: dict, overload: dict) -> dict:
        """Redistribute existing defensive capacity under numerical stress.

        Positive control that was previously allocated independently to runner,
        lane, dribble or box is first weakened by scarcity. The chosen response
        can then reallocate a small part of that capacity, but every response
        worsens pressure and/or space somewhere. Thus an overload cannot make all
        defensive dimensions simultaneously better.
        """
        merged = dict(base)
        if not overload.get("active"):
            return merged

        attackers = max(1, int(overload["attackers_count"]))
        defenders = max(1, int(overload["defenders_count"]))
        response = str(overload["response"])
        primary_quality = clamp(float(overload.get("primary_quality", 0.5)))

        ratio = clamp(defenders / float(attackers))
        scarcity = 1.0 - ratio

        # Numerical inferiority weakens simultaneous control. Pulling a helper
        # preserves a little more of the old structure, but does not exceed it.
        weakening = 1.0 - scarcity * (0.13 if response == "pull_helper" else 0.24)
        for key in (
            "pass_lane_control", "runner_control", "dribble_control",
            "cross_control", "box_protection",
        ):
            value = float(merged.get(key, 0.0))
            if value > 0.0:
                merged[key] = value * weakening

        base_lane = max(0.0, float(merged.get("pass_lane_control", 0.0)))
        base_runner = max(0.0, float(merged.get("runner_control", 0.0)))
        available = base_lane + base_runner + 0.012 * primary_quality * (0.55 + 0.45 * ratio)
        extra = min(0.010, available * 0.22)

        if response == "split_difference":
            merged["pass_lane_control"] = base_lane + 0.58 * extra
            merged["runner_control"] = base_runner + 0.42 * extra
            merged["pressure_delta"] = float(merged.get("pressure_delta", 0.0)) - (0.007 + 0.010 * scarcity)
            merged["space_delta"] = float(merged.get("space_delta", 0.0)) + 0.006 * scarcity
        elif response == "pull_helper":
            # The helper is a real uncommitted defender. Local structure improves
            # but the adjacent zone he left becomes slightly more vulnerable.
            merged["pass_lane_control"] = base_lane + 0.48 * extra
            merged["runner_control"] = base_runner + 0.52 * extra
            merged["pressure_delta"] = float(merged.get("pressure_delta", 0.0)) - (0.004 + 0.006 * scarcity)
            merged["space_delta"] = float(merged.get("space_delta", 0.0)) + 0.006 + 0.005 * scarcity
            merged["depth_delta"] = float(merged.get("depth_delta", 0.0)) + 0.004 * scarcity
            if overload.get("zone_lane") != Lane.CENTER.value:
                merged["wide_space_delta"] = float(merged.get("wide_space_delta", 0.0)) + 0.006
        else:  # delay_and_screen
            merged["pass_lane_control"] = base_lane + 0.64 * extra
            merged["runner_control"] = base_runner + 0.36 * extra
            merged["pressure_delta"] = float(merged.get("pressure_delta", 0.0)) - (0.010 + 0.010 * scarcity)
            merged["space_delta"] = float(merged.get("space_delta", 0.0)) + 0.008 + 0.006 * scarcity

        return merged

    def _overload_plan(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        plan: dict,
        *,
        actor_name: Optional[str],
    ) -> dict:
        inactive = {
            "active": False,
            "label": None,
            "attackers_count": 1,
            "defenders_count": len(self._committed_defender_names(plan)),
            "attacking_names": [],
            "supporting_threats": [],
            "defending_names": self._committed_defender_names(plan),
            "response": None,
            "response_scores": {},
            "helper": None,
            "helper_name": None,
            "helper_score": 0.0,
            "primary_quality": clamp(float(plan.get("quality", 0.5))),
            "effects": self._zero_overload_effects(),
            "zone_lane": zone.lane.value,
        }
        if not actor_name:
            return inactive
        try:
            actor = self.teams[attacking_team].by_name(actor_name)
        except KeyError:
            return inactive

        threats = self._local_attacking_threats(attacking_team, actor, zone, ctx)
        attackers_count = 1 + len(threats)
        committed = self._committed_defender_names(plan)
        defenders_count = len(committed)
        # At least one defender is geometrically present in any defended action;
        # this guard avoids classifying an implementation detail as a 2v0.
        defenders_count = max(1, defenders_count)

        if attackers_count < 2 or attackers_count <= defenders_count:
            inactive.update({
                "attackers_count": attackers_count,
                "defenders_count": defenders_count,
                "attacking_names": [actor.player.name] + [r["name"] for r in threats],
                "supporting_threats": threats,
                "defending_names": committed,
            })
            return inactive

        defending_team = 1 - attacking_team
        helper, helper_score = self._best_overload_helper(
            defending_team, zone, plan, exclude_names=set(committed)
        )
        response, scores = self._overload_response(
            attacking_team, zone, ctx, plan,
            attackers_count, defenders_count, helper, helper_score,
        )
        primary = plan.get("defender")
        if isinstance(primary, PlayerState):
            primary_quality = clamp(
                0.42 * primary.effective("positioning") / 100.0
                + 0.32 * primary.effective("anticipation") / 100.0
                + 0.16 * primary.effective("tackling") / 100.0
                + 0.10 * primary.effective("composure") / 100.0
            )
        else:
            primary_quality = clamp(float(plan.get("quality", 0.5)))

        overload = {
            "active": True,
            "label": self._overload_label(attackers_count, defenders_count),
            "attackers_count": attackers_count,
            "defenders_count": defenders_count,
            "attacking_names": [actor.player.name] + [r["name"] for r in threats],
            "supporting_threats": threats,
            "defending_names": committed,
            "response": response,
            "response_scores": scores,
            "helper": helper,
            "helper_name": None if helper is None else helper.player.name,
            "helper_score": helper_score,
            "primary_quality": primary_quality,
            "zone_lane": zone.lane.value,
        }
        redistributed = self._redistribute_overload_effects(plan["effects"], overload)
        overload["effects"] = {
            key: float(redistributed.get(key, 0.0)) - float(plan["effects"].get(key, 0.0))
            for key in self._zero_overload_effects()
        }
        return overload

    def _build_defensive_plan(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        *,
        kind: Optional[str] = None,
        target: Optional[str] = None,
    ) -> dict:
        plan = super()._build_defensive_plan(
            attacking_team, zone, ctx, kind=kind, target=target
        )
        hint = self._current_defensive_hint()
        overload = self._overload_plan(
            attacking_team, zone, ctx, plan, actor_name=hint.get("actor")
        )
        if overload["active"]:
            plan["effects"] = self._redistribute_overload_effects(plan["effects"], overload)
        plan["overload"] = overload
        return plan

    @staticmethod
    def _apply_plan_effects(ctx: dict, plan: dict) -> dict:
        adjusted = MatchEngineV13Offside._apply_plan_effects(ctx, plan)
        overload = plan.get("overload")
        if isinstance(overload, dict):
            adjusted["overload_active"] = bool(overload.get("active"))
            adjusted["overload_label"] = overload.get("label")
            adjusted["overload_response"] = overload.get("response")
            adjusted["overload_helper"] = overload.get("helper_name")
            adjusted["overload_attackers"] = int(overload.get("attackers_count", 1))
            adjusted["overload_defenders"] = int(overload.get("defenders_count", 1))
        return adjusted

    def overload_diagnostic(
        self,
        attacking_team: int,
        actor_name: str,
        zone: Zone,
        ctx: Optional[dict] = None,
        *,
        kind: Optional[str] = None,
        target: Optional[str] = None,
    ) -> dict:
        context = dict(ctx or {
            "pressure": 0.48,
            "space": 0.52,
            "space_behind": 0.45,
            "support": 0.58,
            "wide_space": 0.12,
            "defending_availability": 1.0,
        })
        old = getattr(self, "_v13_defense_hint", None)
        self._v13_defense_hint = {
            "kind": kind,
            "target": target,
            "actor": actor_name,
        }
        try:
            plan = self._build_defensive_plan(
                attacking_team, zone, context, kind=kind, target=target
            )
        finally:
            self._v13_defense_hint = old

        overload = plan["overload"]
        adjusted = self._apply_plan_effects(context, plan)
        threats = []
        for row in overload.get("supporting_threats", []):
            mv = row.get("movement", {})
            threats.append({
                "name": row.get("name"),
                "movement": mv.get("intent"),
                "projected_band": getattr(mv.get("projected_band"), "value", None),
                "projected_lane": getattr(mv.get("projected_lane"), "value", None),
                "quality": row.get("quality"),
                "presence": row.get("presence"),
            })
        return {
            "active": overload["active"],
            "label": overload["label"],
            "attackers_count": overload["attackers_count"],
            "defenders_count": overload["defenders_count"],
            "attacking_names": list(overload.get("attacking_names", [])),
            "defending_names": list(overload.get("defending_names", [])),
            "supporting_threats": threats,
            "response": overload["response"],
            "response_scores": dict(overload.get("response_scores", {})),
            "helper": overload.get("helper_name"),
            "primary_quality": overload.get("primary_quality"),
            "effects": dict(overload.get("effects", {})),
            "base": context,
            "adjusted": adjusted,
        }


MatchEngine = MatchEngineV13Overload
