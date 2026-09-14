from __future__ import annotations

"""v1.3 stage 3: third-man patterns and multi-player combination chains."""

from engine import clamp
from engine_experiment_v13_runs import MatchEngineV13Runs

VERSION = "1.3-candidate-third-man"


class MatchEngineV13ThirdMan(MatchEngineV13Runs):
    def _ensure_third_man_state(self):
        if not hasattr(self, "_v13_third_man_hint"):
            self._v13_third_man_hint = None

    def third_man_diagnostic(self, team: int, actor_name: str) -> dict:
        self._ensure_combination_state()
        link = self._recent_link(team=team, actor_name=actor_name, max_age=12.0)
        if not link:
            return {"available": False, "candidate": None, "probability": 0.0}
        try:
            actor = self.teams[team].by_name(actor_name)
        except KeyError:
            return {"available": False, "candidate": None, "probability": 0.0}
        rows = []
        for ps in self.teams[team].on_field:
            name = ps.player.name
            if name in {actor_name, link["actor"]} or ps.player.position.upper() == "GK" or ps.red:
                continue
            score = clamp(
                0.31 * ps.effective("off_ball") / 100.0
                + 0.24 * ps.effective("anticipation") / 100.0
                + 0.18 * ps.effective("pace") / 100.0
                + 0.12 * ps.effective("technique") / 100.0
                + 0.08 * ps.effective("composure") / 100.0
                + 0.07 * ps.energy
            )
            rows.append((score, name))
        if not rows:
            return {"available": False, "candidate": None, "probability": 0.0}
        score, candidate = max(rows)
        vision = clamp(actor.effective("vision") / 100.0)
        passing = clamp(actor.effective("passing") / 100.0)
        probability = clamp(0.03 + 0.22 * score + 0.12 * vision + 0.08 * passing, 0.05, 0.39)
        return {
            "available": score >= 0.48,
            "candidate": candidate,
            "probability": probability,
            "originator": link["actor"],
            "connector": actor_name,
            "quality": score,
        }

    def _choose_target(self, team, zone, attacking=True, exclude=None):
        self._ensure_third_man_state()
        marker = getattr(self, "_v13_forced_space_target", None)
        if marker and marker.get("team") == team and marker.get("actor") == exclude:
            return super()._choose_target(team, zone, attacking=attacking, exclude=exclude)
        if attacking and exclude:
            diag = self.third_man_diagnostic(team, exclude)
            if diag["available"] and self.rng.random() < diag["probability"]:
                try:
                    candidate = self.teams[team].by_name(diag["candidate"])
                except KeyError:
                    candidate = None
                if candidate is not None:
                    self._v13_third_man_hint = diag
                    return candidate
        return super()._choose_target(team, zone, attacking=attacking, exclude=exclude)

    def _execute_decision(self, team, actor, zone, decision, ctx):
        chain = self.active_pass_chain(team)
        adjusted = dict(ctx)
        if chain and chain[-1]["target"] == actor.player.name and len(chain) >= 2:
            length = len(chain)
            adjusted["support"] = clamp(float(adjusted.get("support", 0.5)) + min(0.055, 0.018 * length))
            adjusted["space"] = clamp(float(adjusted.get("space", 0.5)) + min(0.035, 0.011 * length))
        event = super()._execute_decision(team, actor, zone, decision, adjusted)
        fresh = self.active_pass_chain(team)
        if len(fresh) >= 2:
            players = [fresh[0]["actor"]] + [x["target"] for x in fresh]
            event.data.setdefault("combination_length", len(fresh))
            event.data.setdefault("combination_players", players[-5:])
        hint = self._v13_third_man_hint
        self._v13_third_man_hint = None
        if hint and (event.data.get("target") or event.data.get("receiver")) == hint.get("candidate"):
            event.data["third_man_run"] = True
            event.data["third_man_originator"] = hint["originator"]
            event.data["third_man_connector"] = hint["connector"]
        return event

    def _emit(self, typ, team, relevance, text_key, **data):
        prior = None
        self._ensure_combination_state()
        if self._v13_combination_history:
            prior = dict(self._v13_combination_history[-1])
        event = super()._emit(typ, team, relevance, text_key, **data)
        endpoints = self._pass_endpoints(event)
        if prior and endpoints and prior["team"] == team:
            actor, target = endpoints
            if prior["target"] == actor and target not in {prior["actor"], actor}:
                event.data["third_man"] = True
                event.data["third_man_pattern"] = [prior["actor"], actor, target]
        chain = self.active_pass_chain(team) if team in (0, 1) else []
        if len(chain) >= 2:
            event.data.setdefault("rapid_chain", True)
            event.data.setdefault("rapid_chain_length", min(5, len(chain)))
        return event


MatchEngine = MatchEngineV13ThirdMan
