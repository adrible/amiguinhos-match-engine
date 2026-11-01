from __future__ import annotations

"""v1.3 injury-management layer.

The referee system already decides whether contact produces a knock, minor,
moderate or severe injury.  This layer connects that medical outcome to the
rest of the football simulation: body region, temporary functional limitation,
recovery over match time, contact-surface execution and public medical events.

No new permanent player rating is introduced.  The state belongs to the match
and is fully serialised so save/load remains deterministic.
"""

from typing import Optional

from engine import EventType, PlayerState, clamp
from engine_experiment_v13_rebounds import MatchEngineV13Rebounds

VERSION = "1.3-candidate-injury-management"


class MatchEngineV13Injuries(MatchEngineV13Rebounds):
    BODY_AREA_TO_REGION = {
        "ankle_knee_or_lower_leg": "lower_body",
        "lower_leg": "lower_body",
        "upper_body": "upper_body",
        "soft_tissue": "torso",
        "head_or_face": "head",
        "lower_body": "lower_body",
        "torso": "torso",
        "head": "head",
    }

    def _ensure_injury_management_state(self) -> None:
        if not hasattr(self, "_v13_injury_state"):
            self._v13_injury_state: dict[str, dict] = {}

    @staticmethod
    def _injury_key(team: int, player_name: str) -> str:
        return f"{int(team)}:{player_name}"

    def _team_for_player_state(self, player: PlayerState) -> Optional[int]:
        for team, runtime in enumerate(self.teams):
            if any(ps is player for ps in runtime.on_field):
                return team
        for team, runtime in enumerate(self.teams):
            if any(ps.player.name == player.player.name for ps in runtime.on_field):
                return team
        return None

    def _injury_region(self, body_area: str | None) -> str:
        return self.BODY_AREA_TO_REGION.get(str(body_area or ""), "torso")

    @staticmethod
    def _injury_profile(result: dict) -> dict:
        grade = str(result.get("grade", "knock"))
        impact = clamp(float(result.get("impact", 0.5)))
        suspected = bool(result.get("suspected_concussion"))
        forced_off = bool(result.get("forced_off")) or suspected or grade in {"moderate", "severe"}

        if suspected:
            limitation = clamp(0.34 + 0.12 * impact, 0.34, 0.48)
            recovery_minutes = None
            medical_action = "concussion_substitution"
        elif grade == "severe":
            limitation = clamp(0.40 + 0.12 * impact, 0.40, 0.54)
            recovery_minutes = None
            medical_action = "forced_substitution"
        elif grade == "moderate":
            limitation = clamp(0.25 + 0.10 * impact, 0.25, 0.35)
            recovery_minutes = None
            medical_action = "forced_substitution"
        elif grade == "minor":
            limitation = clamp(0.085 + 0.105 * impact, 0.09, 0.19)
            recovery_minutes = round(23.0 + 23.0 * impact, 3)
            medical_action = "continue_under_observation"
        elif grade == "head_check":
            limitation = clamp(0.030 + 0.045 * impact, 0.03, 0.075)
            recovery_minutes = round(6.0 + 10.0 * impact, 3)
            medical_action = "head_check_monitoring"
        else:
            limitation = clamp(0.035 + 0.070 * impact, 0.04, 0.105)
            recovery_minutes = round(9.0 + 13.0 * impact, 3)
            medical_action = "continue_after_treatment"

        return {
            "initial_limitation": limitation,
            "recovery_minutes": recovery_minutes,
            "forced_off": forced_off,
            "can_continue": not forced_off,
            "medical_action": medical_action,
        }

    def _register_injury_state(self, team: int, player: PlayerState, result: dict) -> dict:
        self._ensure_injury_management_state()
        self._ensure_contact_state()
        region = self._injury_region(result.get("body_area"))
        profile = self._injury_profile(result)
        key = self._injury_key(team, player.player.name)
        state = {
            "team": int(team),
            "player": player.player.name,
            "grade": str(result.get("grade", "knock")),
            "region": region,
            "body_area": str(result.get("body_area", "soft_tissue")),
            "impact": round(float(result.get("impact", 0.5)), 4),
            "onset_minute": round(float(self.minute), 4),
            "concussion_protocol": bool(result.get("concussion_protocol")),
            "suspected_concussion": bool(result.get("suspected_concussion")),
            **profile,
        }
        self._v13_injury_state[key] = state
        # The legal-body layer uses this map for region-specific execution.
        self._v13_injury_locations[player.player.name] = region
        return state

    def current_injury_status(self, team: int, player_name: str) -> Optional[dict]:
        """Return current limitation without RNG draws or state mutation."""
        self._ensure_injury_management_state()
        state = self._v13_injury_state.get(self._injury_key(team, player_name))
        if state is None:
            return None
        out = dict(state)
        recovery = state.get("recovery_minutes")
        initial = float(state.get("initial_limitation", 0.0))
        if recovery is None or bool(state.get("forced_off")):
            limitation = initial
            recovered = False
        else:
            elapsed = max(0.0, float(self.minute) - float(state.get("onset_minute", self.minute)))
            ratio = clamp(elapsed / max(float(recovery), 1e-9))
            # Symptoms ease quickly at first but never disappear instantly.
            limitation = initial * ((1.0 - ratio) ** 1.18)
            recovered = ratio >= 1.0 or limitation <= 0.003
            if recovered:
                limitation = 0.0
        out["current_limitation"] = round(limitation, 6)
        out["recovered"] = recovered
        return out

    def injury_management_diagnostic(self, team: int, player_name: str) -> Optional[dict]:
        status = self.current_injury_status(team, player_name)
        if status is None:
            return None
        return {
            "grade": status["grade"],
            "region": status["region"],
            "body_area": status["body_area"],
            "current_limitation": status["current_limitation"],
            "recovered": status["recovered"],
            "can_continue": status["can_continue"],
            "forced_off": status["forced_off"],
            "medical_action": status["medical_action"],
            "recovery_minutes": status["recovery_minutes"],
        }

    def _injury_outcome(self, defender, attacker, incident):
        result = super()._injury_outcome(defender, attacker, incident)
        if result is None:
            return None
        team = self._team_for_player_state(attacker)
        if team is None:
            return result
        state = self._register_injury_state(team, attacker, result)
        result = dict(result)
        result.update(
            {
                "injury_region": state["region"],
                "functional_limitation": round(float(state["initial_limitation"]), 4),
                "recovery_minutes": state["recovery_minutes"],
                "can_continue": bool(state["can_continue"]),
                "medical_action": state["medical_action"],
            }
        )
        return result

    def _record_injury_event(
        self,
        team: int,
        player: PlayerState,
        caused_by: Optional[PlayerState] = None,
    ) -> None:
        # Preserve the older generic injury hook, but make its state compatible
        # with the contextual referee injury model.
        super()._record_injury_event(team, player, caused_by)
        self._ensure_contact_state()
        region = self._v13_injury_locations.get(player.player.name, "torso")
        result = {
            "grade": "moderate" if player.injured else "minor",
            "body_area": region,
            "impact": 0.62 if player.injured else 0.50,
            "forced_off": bool(player.injured),
        }
        self._register_injury_state(team, player, result)

    def _injury_part_modifier(self, actor: PlayerState, part: str) -> float:
        base = super()._injury_part_modifier(actor, part)
        # Moderate/severe injuries already use the stronger legacy region table
        # and are forced off; do not stack a second hidden penalty on them.
        if actor.injured:
            return base
        team = self._team_for_player_state(actor)
        if team is None:
            return base
        status = self.current_injury_status(team, actor.player.name)
        if status is None or status["recovered"]:
            return base
        limitation = float(status["current_limitation"])
        region = str(status["region"])
        susceptibility = {
            "lower_body": {
                "right_foot": 1.00,
                "left_foot": 1.00,
                "thigh": 0.88,
                "knee": 1.10,
                "shin": 1.04,
                "head": 0.08,
                "chest": 0.12,
                "shoulder": 0.12,
            },
            "upper_body": {
                "right_foot": 0.08,
                "left_foot": 0.08,
                "thigh": 0.10,
                "knee": 0.10,
                "shin": 0.10,
                "head": 0.42,
                "chest": 0.78,
                "shoulder": 1.05,
            },
            "torso": {
                "right_foot": 0.28,
                "left_foot": 0.28,
                "thigh": 0.34,
                "knee": 0.30,
                "shin": 0.30,
                "head": 0.42,
                "chest": 1.05,
                "shoulder": 0.72,
            },
            "head": {
                "right_foot": 0.18,
                "left_foot": 0.18,
                "thigh": 0.24,
                "knee": 0.24,
                "shin": 0.24,
                "head": 1.30,
                "chest": 0.48,
                "shoulder": 0.58,
            },
        }.get(region, {})
        exposure = float(susceptibility.get(part, 0.35))
        return clamp(base * (1.0 - limitation * exposure), 0.68, 1.0)

    def _decision_weights(self, actor, zone, tactics, ctx):
        weights = super()._decision_weights(actor, zone, tactics, ctx)
        team = self._team_for_player_state(actor)
        if team is None:
            return weights
        status = self.current_injury_status(team, actor.player.name)
        if status is None or status["recovered"] or actor.injured:
            return weights
        limitation = float(status["current_limitation"])
        if limitation <= 0.0:
            return weights
        region = str(status["region"])
        dynamic = {
            "lower_body": {
                "carry": 0.90,
                "dribble": 1.00,
                "shoot": 0.68,
                "cross": 0.42,
                "long_ball": 0.35,
                "through_ball": 0.18,
                "safe_pass": -0.24,
            },
            "upper_body": {
                "carry": 0.22,
                "dribble": 0.28,
                "shoot": 0.16,
                "cross": 0.18,
                "safe_pass": -0.08,
            },
            "torso": {
                "carry": 0.54,
                "dribble": 0.58,
                "shoot": 0.34,
                "cross": 0.24,
                "safe_pass": -0.14,
            },
            "head": {
                "carry": 0.16,
                "dribble": 0.18,
                "shoot": 0.14,
                "safe_pass": -0.10,
            },
        }.get(region, {})
        adjusted = []
        for action, weight in weights:
            sensitivity = float(dynamic.get(action, 0.12))
            if sensitivity < 0.0:
                factor = 1.0 + limitation * abs(sensitivity)
            else:
                factor = 1.0 - limitation * sensitivity
            adjusted.append((action, max(0.001, float(weight) * factor)))
        return adjusted

    def _queue_event(self, event_type, team, relevance, text_key, **data) -> None:
        if event_type == EventType.INJURY and data.get("player"):
            status = self.current_injury_status(int(team), str(data["player"]))
            if status is not None:
                data.setdefault("injury_region", status["region"])
                data.setdefault("functional_limitation", status["current_limitation"])
                data.setdefault("recovery_minutes", status["recovery_minutes"])
                data.setdefault("can_continue", status["can_continue"])
                data.setdefault("medical_action", status["medical_action"])
        super()._queue_event(event_type, team, relevance, text_key, **data)

    def export_state(self) -> dict:
        data = super().export_state()
        self._ensure_injury_management_state()
        data["v13_injury_state"] = {
            key: dict(value) for key, value in sorted(self._v13_injury_state.items())
        }
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        obj._v13_injury_state = {
            str(key): dict(value)
            for key, value in (data.get("v13_injury_state") or {}).items()
        }
        obj._ensure_contact_state()
        for value in obj._v13_injury_state.values():
            player_name = value.get("player")
            region = value.get("region")
            if player_name and region:
                obj._v13_injury_locations[str(player_name)] = str(region)
        return obj


MatchEngine = MatchEngineV13Injuries
