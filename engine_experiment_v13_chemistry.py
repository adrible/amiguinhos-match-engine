from __future__ import annotations

"""Experimental v1.3 layer: pairwise chemistry / shared understanding.

Chemistry is deliberately relational, not a team-wide modifier.  It only
matters when two concrete defenders already have to coordinate an existing
football action: a marking hand-off, a cover relationship, a communication
call, an overload helper movement, or the organisation of the offside line.

No player attribute is changed and no new defender, mark, cover or pressure
source is created.  Familiarity is symmetric by pair and defaults to neutral.
The relation combines that familiarity with the players' mental reading and
role compatibility.  High understanding can preserve a little more of the
already-existing relation; low understanding can erode it.
"""

from typing import Optional

from engine import PlayerState, Zone, clamp
from engine_experiment_v13_errors import MatchEngineV13Errors


VERSION = (
    "1.3-candidate-spatial-creativity-boldness-offball-body-defense-"
    "marking-cover-communication-offside-overload-errors-chemistry"
)


class MatchEngineV13Chemistry(MatchEngineV13Errors):
    """Adds bounded pair familiarity to concrete defensive relationships."""

    # ---------------------------- pair familiarity ----------------------------

    @staticmethod
    def _pair_key(team: int, first: str, second: str) -> tuple[int, str, str]:
        a, b = sorted((str(first), str(second)))
        return int(team), a, b

    def set_pair_familiarity(self, team: int, first: str, second: str, value: float) -> None:
        """Set symmetric familiarity for one pair without changing player data."""
        if int(team) not in (0, 1):
            raise ValueError("team must be 0 or 1")
        if not first or not second or str(first) == str(second):
            raise ValueError("pair familiarity requires two distinct player names")
        store = getattr(self, "_v13_pair_familiarity", None)
        if not isinstance(store, dict):
            store = {}
            self._v13_pair_familiarity = store
        store[self._pair_key(team, first, second)] = clamp(float(value))

    def pair_familiarity(self, team: int, first: str, second: str) -> float:
        if not first or not second or str(first) == str(second):
            return 0.50
        store = getattr(self, "_v13_pair_familiarity", None)
        if not isinstance(store, dict):
            return 0.50
        return clamp(float(store.get(self._pair_key(team, first, second), 0.50)))

    def _pair_team(self, first: PlayerState, second: PlayerState) -> Optional[int]:
        for idx, runtime in enumerate(self.teams):
            first_here = any(ps is first for ps in runtime.on_field)
            second_here = any(ps is second for ps in runtime.on_field)
            if first_here and second_here:
                return idx
        return None

    @staticmethod
    def _mental_sync(first: PlayerState, second: PlayerState) -> float:
        """Stable cognitive compatibility; fatigue is handled elsewhere."""
        def reading(ps: PlayerState) -> float:
            raw = (
                0.31 * ps.player.attr("anticipation")
                + 0.29 * ps.player.attr("positioning")
                + 0.22 * ps.player.attr("composure")
                + 0.18 * ps.player.attr("discipline")
            )
            return clamp(raw / 100.0)

        a = reading(first)
        b = reading(second)
        # A pair is limited partly by its weaker reader: coordination is not the
        # same thing as simply averaging two individual ratings.
        return clamp(0.64 * ((a + b) / 2.0) + 0.36 * min(a, b))

    @staticmethod
    def _role_fit(first: PlayerState, second: PlayerState, relation: str) -> float:
        a = first.player.position.upper()
        b = second.player.position.upper()
        pair = {a, b}
        back = {"CB", "LB", "RB"}

        if relation == "line":
            if a == "CB" and b == "CB":
                return 0.94
            if "CB" in pair and pair & {"LB", "RB"}:
                return 0.86
            if "CB" in pair and "DM" in pair:
                return 0.84
            if "GK" in pair and "CB" in pair:
                return 0.80
            if a in back and b in back:
                return 0.76
            return 0.58

        if relation == "handoff":
            if a in back and b in back:
                return 0.88
            if "CB" in pair and "DM" in pair:
                return 0.86
            if pair & back and pair & {"DM", "CM"}:
                return 0.76
            return 0.60

        if relation == "cover":
            if "CB" in pair and pair & {"LB", "RB", "DM"}:
                return 0.90
            if "DM" in pair and pair & {"LB", "RB", "CM"}:
                return 0.84
            if a in back and b in back:
                return 0.82
            return 0.62

        if relation == "overload_help":
            if pair & {"CB", "DM"} and pair & {"LB", "RB", "CB", "DM"}:
                return 0.88
            if "CM" in pair and pair & {"DM", "CB"}:
                return 0.78
            return 0.60

        # Communication is broad, but still benefits from defensive adjacency.
        if a in back and b in back:
            return 0.84
        if pair & back and pair & {"DM", "GK"}:
            return 0.82
        if "DM" in pair and "CM" in pair:
            return 0.74
        return 0.64

    def _shared_understanding(
        self,
        team: int,
        first: PlayerState,
        second: PlayerState,
        relation: str,
    ) -> dict:
        familiarity = self.pair_familiarity(
            team, first.player.name, second.player.name
        )
        mental = self._mental_sync(first, second)
        role_fit = self._role_fit(first, second, relation)

        # Centred around 0.50 so a neutral familiarity setting does not become a
        # hidden global buff. Familiarity matters most, while mental reading and
        # role complementarity move the relation modestly around that baseline.
        score = clamp(
            0.50
            + 0.62 * (familiarity - 0.50)
            + 0.22 * (mental - 0.70)
            + 0.16 * (role_fit - 0.68)
        )
        return {
            "team": int(team),
            "first": first.player.name,
            "second": second.player.name,
            "relation": relation,
            "familiarity": familiarity,
            "mental_sync": mental,
            "role_fit": role_fit,
            "score": score,
        }

    def _shared_for_names(
        self,
        team: int,
        first_name: Optional[str],
        second_name: Optional[str],
        relation: str,
    ) -> Optional[dict]:
        if not first_name or not second_name or first_name == second_name:
            return None
        try:
            first = self.teams[team].by_name(str(first_name))
            second = self.teams[team].by_name(str(second_name))
        except KeyError:
            return None
        return self._shared_understanding(team, first, second, relation)

    # ---------------------------- relationship hooks ----------------------------

    def _handoff_quality(self, first: PlayerState, second: PlayerState, hiddenness: float) -> float:
        base = super()._handoff_quality(first, second, hiddenness)
        team = self._pair_team(first, second)
        if team is None:
            return base
        shared = self._shared_understanding(team, first, second, "handoff")
        # Bounded ±0.05 correction to the existing handoff quality.
        return clamp(base + 0.10 * (shared["score"] - 0.50))

    def _coverage_plan(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        plan: dict,
        *,
        kind: Optional[str] = None,
    ) -> dict:
        coverage = super()._coverage_plan(
            attacking_team, zone, ctx, plan, kind=kind
        )
        defender = coverage.get("defender")
        primary = plan.get("defender")
        if not isinstance(defender, PlayerState) or not isinstance(primary, PlayerState):
            coverage["shared_understanding"] = None
            return coverage

        team = 1 - attacking_team
        shared = self._shared_understanding(team, primary, defender, "cover")
        activation = clamp(
            float(coverage.get("activation", 0.0))
            + 0.08 * (shared["score"] - 0.50)
        )
        active = bool(defender is not None and activation >= 0.56)
        quality = float(coverage.get("quality", 0.0))
        cover_type = str(coverage.get("type") or "cover_depth")
        effects = (
            self._coverage_effects(cover_type, quality, activation)
            if active else self._coverage_effects(cover_type, 0.0, 0.0)
        )
        coverage.update({
            "activation": activation,
            "active": active,
            "effects": effects,
            "shared_understanding": shared,
        })
        return coverage

    def _communication_quality(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: dict,
        plan: dict,
        call_type: str,
        communicator: Optional[PlayerState],
        receiver: Optional[PlayerState],
    ) -> float:
        base = super()._communication_quality(
            attacking_team, zone, ctx, plan, call_type, communicator, receiver
        )
        if communicator is None or receiver is None:
            return base
        team = 1 - attacking_team
        shared = self._shared_understanding(
            team, communicator, receiver, "communication"
        )
        return clamp(base + 0.10 * (shared["score"] - 0.50))

    def _line_coordination(self, defending_team: int, zone: Zone, ctx: dict) -> dict:
        line = dict(super()._line_coordination(defending_team, zone, ctx))
        caller_name = line.get("caller")
        members = [str(name) for name in line.get("members", []) if name]
        values = []
        details = []
        if caller_name:
            for member in members:
                if member == caller_name:
                    continue
                shared = self._shared_for_names(
                    defending_team, str(caller_name), member, "line"
                )
                if shared is not None:
                    values.append(float(shared["score"]))
                    details.append(shared)
        group = sum(values) / len(values) if values else 0.50
        line["base_coordination"] = float(line.get("coordination", 0.0))
        line["shared_understanding"] = clamp(group)
        line["shared_pairs"] = details
        line["coordination"] = clamp(
            line["base_coordination"] + 0.10 * (group - 0.50)
        )
        return line

    def _offside_line_plan(self, *args, **kwargs) -> dict:
        plan = dict(super()._offside_line_plan(*args, **kwargs))
        defending_team = 1 - int(args[0] if args else kwargs["attacking_team"])
        caller = plan.get("caller")
        values = []
        for member in plan.get("line_members", []):
            if not caller or member == caller:
                continue
            shared = self._shared_for_names(
                defending_team, str(caller), str(member), "line"
            )
            if shared is not None:
                values.append(float(shared["score"]))
        plan["line_shared_understanding"] = (
            sum(values) / len(values) if values else 0.50
        )
        return plan

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
        response, scores = super()._overload_response(
            attacking_team, zone, ctx, plan,
            attackers, defenders, helper, helper_score,
        )
        scores = dict(scores)
        primary = plan.get("defender")
        if helper is not None and isinstance(primary, PlayerState):
            team = 1 - attacking_team
            shared = self._shared_understanding(
                team, primary, helper, "overload_help"
            )
            # Familiar helpers are easier to pull without hesitation; unfamiliar
            # pairs make split/delay comparatively more attractive. This changes
            # the response selection, not the number of defenders available.
            scores["pull_helper"] = float(scores["pull_helper"]) + 0.12 * (
                shared["score"] - 0.50
            )
        return max(scores.items(), key=lambda row: row[1])[0], scores

    def _overload_plan(self, *args, **kwargs) -> dict:
        overload = dict(super()._overload_plan(*args, **kwargs))
        if args:
            attacking_team = int(args[0])
            plan = args[3]
        else:
            attacking_team = int(kwargs["attacking_team"])
            plan = kwargs["plan"]
        primary = plan.get("defender") if isinstance(plan, dict) else None
        helper = overload.get("helper")
        shared = None
        if isinstance(primary, PlayerState) and isinstance(helper, PlayerState):
            shared = self._shared_understanding(
                1 - attacking_team, primary, helper, "overload_help"
            )
        overload["shared_understanding"] = shared
        return overload

    # ---------------------------- plan diagnostics ----------------------------

    def _active_relationship(self, attacking_team: int, plan: dict) -> Optional[dict]:
        defending_team = 1 - attacking_team
        marking = plan.get("marking") if isinstance(plan.get("marking"), dict) else {}
        if marking.get("switched"):
            shared = self._shared_for_names(
                defending_team,
                marking.get("initial_marker"),
                marking.get("marker_name"),
                "handoff",
            )
            if shared is not None:
                return shared

        coverage = plan.get("coverage") if isinstance(plan.get("coverage"), dict) else {}
        if coverage.get("active"):
            shared = coverage.get("shared_understanding")
            if isinstance(shared, dict):
                return dict(shared)

        overload = plan.get("overload") if isinstance(plan.get("overload"), dict) else {}
        if overload.get("active") and overload.get("response") == "pull_helper":
            shared = overload.get("shared_understanding")
            if isinstance(shared, dict):
                return dict(shared)

        communication = plan.get("communication") if isinstance(plan.get("communication"), dict) else {}
        if communication.get("active"):
            shared = self._shared_for_names(
                defending_team,
                communication.get("communicator_name"),
                communication.get("receiver_name"),
                "communication",
            )
            if shared is not None:
                return shared
        return None

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
        plan["shared_understanding"] = self._active_relationship(
            attacking_team, plan
        )
        return plan

    @staticmethod
    def _apply_plan_effects(ctx: dict, plan: dict) -> dict:
        adjusted = MatchEngineV13Errors._apply_plan_effects(ctx, plan)
        shared = plan.get("shared_understanding")
        if isinstance(shared, dict):
            adjusted["shared_understanding_active"] = True
            adjusted["shared_understanding_relation"] = shared.get("relation")
            adjusted["shared_understanding_pair"] = [
                shared.get("first"), shared.get("second")
            ]
            adjusted["shared_understanding_score"] = round(
                float(shared.get("score", 0.50)), 6
            )
        else:
            adjusted["shared_understanding_active"] = False
            adjusted["shared_understanding_relation"] = None
            adjusted["shared_understanding_pair"] = None
            adjusted["shared_understanding_score"] = 0.50
        return adjusted

    def shared_understanding_diagnostic(
        self,
        team: int,
        first: str,
        second: str,
        *,
        relation: str = "communication",
    ) -> dict:
        a = self.teams[team].by_name(first)
        b = self.teams[team].by_name(second)
        return dict(self._shared_understanding(team, a, b, relation))

    def relationship_diagnostic(
        self,
        attacking_team: int,
        zone: Zone,
        ctx: Optional[dict] = None,
        *,
        kind: Optional[str] = None,
        actor: Optional[str] = None,
        target: Optional[str] = None,
    ) -> dict:
        context = dict(ctx or {
            "pressure": 0.48,
            "space": 0.52,
            "space_behind": 0.45,
            "support": 0.50,
            "wide_space": 0.10,
            "defending_availability": 1.0,
        })
        old = getattr(self, "_v13_defense_hint", None)
        self._v13_defense_hint = {
            "kind": kind, "target": target, "actor": actor
        }
        try:
            plan = self._build_defensive_plan(
                attacking_team, zone, context, kind=kind, target=target
            )
        finally:
            self._v13_defense_hint = old
        adjusted = self._apply_plan_effects(context, plan)
        return {
            "relationship": (
                dict(plan["shared_understanding"])
                if isinstance(plan.get("shared_understanding"), dict) else None
            ),
            "intent": plan.get("intent"),
            "marking_switched": bool(plan.get("marking", {}).get("switched")),
            "coverage_active": bool(plan.get("coverage", {}).get("active")),
            "communication_active": bool(plan.get("communication", {}).get("active")),
            "overload_active": bool(plan.get("overload", {}).get("active")),
            "base": context,
            "adjusted": adjusted,
        }


MatchEngine = MatchEngineV13Chemistry
