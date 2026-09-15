from __future__ import annotations

"""v1.3 stage 1: quick combinations and short play memory.

A give-and-go is not a scripted action. It can emerge when a pass receiver is
selected again quickly and contextual technique, vision and anticipation make a
fast continuation or return pass plausible.
"""

from engine import EventType, PlayerState, Zone, clamp
from engine_experiment_v13_adaptation_inertia import MatchEngineV13AdaptationInertia

VERSION = "1.3-candidate-quick-combinations"

_PASS_KEYS = {"safe_pass", "progression", "progression_creates_danger", "danger_created"}
_BREAK_TYPES = {EventType.TURNOVER, EventType.FOUL, EventType.OFFSIDE, EventType.PERIOD_END, EventType.MATCH_END}


class MatchEngineV13Combinations(MatchEngineV13AdaptationInertia):
    def _ensure_combination_state(self) -> None:
        if not hasattr(self, "_v13_combination_history"):
            self._v13_combination_history = []
        if not hasattr(self, "_v13_current_open_actor"):
            self._v13_current_open_actor = None
        if not hasattr(self, "_v13_combo_target_hint"):
            self._v13_combo_target_hint = None

    def export_state(self) -> dict:
        data = super().export_state()
        self._ensure_combination_state()
        data["v13_combination_history"] = [dict(x) for x in self._v13_combination_history]
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        obj._v13_combination_history = [dict(x) for x in data.get("v13_combination_history", [])]
        obj._v13_current_open_actor = None
        obj._v13_combo_target_hint = None
        return obj

    @staticmethod
    def _pass_endpoints(event):
        actor = event.data.get("actor") or event.data.get("creator")
        target = event.data.get("target") or event.data.get("receiver")
        if event.text_key not in _PASS_KEYS or not actor or not target or actor == target:
            return None
        return actor, target

    def _recent_link(self, *, team=None, actor_name=None, max_age=10.0):
        self._ensure_combination_state()
        if not self._v13_combination_history:
            return None
        row = self._v13_combination_history[-1]
        if team is not None and row["team"] != team:
            return None
        if actor_name is not None and row["target"] != actor_name:
            return None
        if self.state.second - float(row["second"]) > max_age:
            return None
        return row

    def active_pass_chain(self, team=None, max_age=18.0) -> list[dict]:
        self._ensure_combination_state()
        rows = self._v13_combination_history
        if not rows:
            return []
        chain = [rows[-1]]
        if team is not None and chain[0]["team"] != team:
            return []
        for row in reversed(rows[:-1]):
            newest = chain[0]
            if row["team"] != newest["team"]:
                break
            if float(newest["second"]) - float(row["second"]) > max_age:
                break
            if row["target"] != newest["actor"]:
                break
            chain.insert(0, row)
        return chain

    def quick_combination_diagnostic(self, actor: PlayerState, team: int) -> dict:
        link = self._recent_link(team=team, actor_name=actor.player.name, max_age=12.0)
        if not link:
            return {"active": False, "return_target": None, "continuity": 0.0}
        technique = clamp(actor.effective("technique") / 100.0)
        vision = clamp(actor.effective("vision") / 100.0)
        anticipation = clamp(actor.effective("anticipation") / 100.0)
        composure = clamp(actor.effective("composure") / 100.0)
        continuity = clamp(0.26 + 0.20 * technique + 0.18 * vision + 0.16 * anticipation + 0.12 * composure)
        return {
            "active": True,
            "return_target": link["actor"],
            "source_kind": link.get("kind", "pass"),
            "age": max(0.0, self.state.second - float(link["second"])),
            "continuity": continuity,
        }

    def _choose_actor(self, team: int, zone: Zone):
        self._ensure_combination_state()
        link = self._recent_link(team=team, max_age=12.0)
        if link:
            try:
                receiver = self.teams[team].by_name(link["target"])
            except KeyError:
                receiver = None
            if receiver is not None and not receiver.red:
                technique = clamp(receiver.effective("technique") / 100.0)
                anticipation = clamp(receiver.effective("anticipation") / 100.0)
                continuity_p = clamp(0.48 + 0.18 * technique + 0.12 * anticipation, 0.48, 0.78)
                if self.rng.random() < continuity_p:
                    self._v13_current_open_actor = receiver.player.name
                    return receiver
        actor = super()._choose_actor(team, zone)
        self._v13_current_open_actor = actor.player.name
        return actor

    def _first_time_probability(self, actor: PlayerState, action: str, diag: dict) -> float:
        base = super()._first_time_probability(actor, action, diag)
        quick = self.quick_combination_diagnostic(actor, self.state.possession)
        if not quick["active"] or base <= 0.0:
            return base
        technique = clamp(actor.effective("technique") / 100.0)
        passing = clamp(actor.effective("passing") / 100.0)
        return clamp(base + 0.035 + 0.075 * technique + 0.045 * passing, 0.0, 0.72)

    def _choose_target(self, team, zone, attacking=True, exclude=None):
        self._ensure_combination_state()
        if attacking and exclude:
            try:
                actor = self.teams[team].by_name(exclude)
            except KeyError:
                actor = None
            if actor is not None:
                quick = self.quick_combination_diagnostic(actor, team)
                return_name = quick.get("return_target")
                if quick.get("active") and return_name and return_name != exclude:
                    try:
                        candidate = self.teams[team].by_name(return_name)
                    except KeyError:
                        candidate = None
                    if candidate is not None and candidate.player.position.upper() != "GK":
                        off_ball = clamp(candidate.effective("off_ball") / 100.0)
                        p = clamp(0.05 + 0.30 * quick["continuity"] + 0.12 * off_ball, 0.08, 0.43)
                        if self.rng.random() < p:
                            self._v13_combo_target_hint = {"actor": exclude, "target": return_name, "kind": "give_and_go", "probability": p}
                            return candidate
        return super()._choose_target(team, zone, attacking=attacking, exclude=exclude)

    def _execute_decision(self, team, actor, zone, decision, ctx):
        self._ensure_combination_state()
        quick = self.quick_combination_diagnostic(actor, team)
        adjusted = dict(ctx)
        if quick["active"]:
            adjusted["support"] = clamp(float(adjusted.get("support", 0.5)) + 0.035 * quick["continuity"])
            adjusted["space"] = clamp(float(adjusted.get("space", 0.5)) + 0.018 * quick["continuity"])
        try:
            event = super()._execute_decision(team, actor, zone, decision, adjusted)
        finally:
            hint = self._v13_combo_target_hint
            self._v13_combo_target_hint = None
        if quick["active"]:
            event.data.setdefault("quick_combination", True)
            event.data.setdefault("combination_return_option", quick.get("return_target"))
        if hint and (event.data.get("target") or event.data.get("receiver")) == hint.get("target"):
            event.data["give_and_go"] = True
            event.data["give_and_go_probability"] = round(float(hint["probability"]), 3)
        return event

    def _emit(self, typ, team, relevance, text_key, **data):
        self._ensure_combination_state()
        prior = self._v13_combination_history[-1] if self._v13_combination_history else None
        event = super()._emit(typ, team, relevance, text_key, **data)
        endpoints = self._pass_endpoints(event)
        if endpoints and team in (0, 1):
            actor, target = endpoints
            quick = bool(prior and prior["team"] == team and prior["target"] == actor and self.state.second - float(prior["second"]) <= 12.0)
            self._v13_combination_history.append({
                "team": team, "actor": actor, "target": target,
                "second": float(self.state.second), "kind": event.data.get("kind") or text_key,
                "first_time": bool(event.data.get("first_time")),
            })
            self._v13_combination_history = self._v13_combination_history[-8:]
            if quick:
                event.data["quick_sequence"] = True
                event.data["quick_sequence_link"] = f"{actor}->{target}"
        elif typ in _BREAK_TYPES:
            self._v13_combination_history = []
        return event


MatchEngine = MatchEngineV13Combinations
