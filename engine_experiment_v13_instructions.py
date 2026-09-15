from __future__ import annotations

"""v1.3 contextual individual instructions.

Instructions are persistent match-state preferences. They change tendencies to
choose actions or occupy/offer for space; they never alter a player's technical,
mental or physical ratings. Conflicting instructions are rejected explicitly.
"""

from copy import deepcopy

from engine import Band, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_rotations import MatchEngineV13Rotations


class MatchEngineV13IndividualInstructions(MatchEngineV13Rotations):
    BOOL_INSTRUCTIONS = {
        "stay_back",
        "attack_depth",
        "move_inside",
        "hold_width",
        "avoid_dribble",
        "take_more_risks",
        "cross_more",
    }
    STRING_INSTRUCTIONS = {"press_target"}
    SUPPORTED_INSTRUCTIONS = BOOL_INSTRUCTIONS | STRING_INSTRUCTIONS

    def _ensure_instruction_state(self) -> None:
        if not hasattr(self, "_v13_individual_instructions"):
            self._v13_individual_instructions: dict[str, dict] = {}

    @staticmethod
    def _instruction_key(team: int, player_name: str) -> str:
        return f"{int(team)}:{player_name}"

    def _instruction_player(self, team: int, player_name: str) -> PlayerState:
        if int(team) not in {0, 1}:
            raise ValueError("team must be 0 or 1")
        return self.teams[int(team)].by_name(str(player_name))

    def _validate_instruction_bundle(self, team: int, player_name: str, bundle: dict) -> dict:
        unknown = sorted(set(bundle) - self.SUPPORTED_INSTRUCTIONS)
        if unknown:
            raise KeyError(f"Unsupported individual instruction(s): {unknown}")

        validated: dict = {}
        for key, value in bundle.items():
            if key in self.BOOL_INSTRUCTIONS:
                if not isinstance(value, bool):
                    raise TypeError(f"{key} must be boolean")
                if value:
                    validated[key] = True
            elif key == "press_target":
                if value is None or str(value).strip() == "":
                    continue
                target = str(value).strip()
                opponent = 1 - int(team)
                self.teams[opponent].by_name(target)
                validated[key] = target

        if validated.get("stay_back") and validated.get("attack_depth"):
            raise ValueError("stay_back and attack_depth cannot be active together")
        if validated.get("move_inside") and validated.get("hold_width"):
            raise ValueError("move_inside and hold_width cannot be active together")
        return validated

    def set_player_instruction(self, team: int, player_name: str, **changes) -> dict:
        """Set/clear instructions without consuming RNG or changing attributes."""
        self._instruction_player(team, player_name)
        self._ensure_instruction_state()
        key = self._instruction_key(team, player_name)
        current = dict(self._v13_individual_instructions.get(key, {}))

        unknown = sorted(set(changes) - self.SUPPORTED_INSTRUCTIONS)
        if unknown:
            raise KeyError(f"Unsupported individual instruction(s): {unknown}")
        for name, value in changes.items():
            if name in self.BOOL_INSTRUCTIONS:
                if not isinstance(value, bool):
                    raise TypeError(f"{name} must be boolean")
                if value:
                    current[name] = True
                else:
                    current.pop(name, None)
            else:
                if value is None or str(value).strip() == "":
                    current.pop(name, None)
                else:
                    current[name] = str(value).strip()

        validated = self._validate_instruction_bundle(team, player_name, current)
        if validated:
            self._v13_individual_instructions[key] = validated
        else:
            self._v13_individual_instructions.pop(key, None)
        return self.individual_instruction_diagnostic(team, player_name)

    def clear_player_instructions(self, team: int, player_name: str) -> dict:
        self._instruction_player(team, player_name)
        self._ensure_instruction_state()
        self._v13_individual_instructions.pop(self._instruction_key(team, player_name), None)
        return self.individual_instruction_diagnostic(team, player_name)

    def _instructions_for(self, team: int, player_name: str) -> dict:
        self._ensure_instruction_state()
        return dict(
            self._v13_individual_instructions.get(
                self._instruction_key(team, player_name), {}
            )
        )

    def individual_instruction_diagnostic(self, team: int, player_name: str) -> dict:
        player = self._instruction_player(team, player_name)
        return {
            "team": int(team),
            "player": player.player.name,
            "position": player.player.position.upper(),
            "instructions": self._instructions_for(team, player_name),
        }

    def _decision_weights(self, actor, zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        team = self._team_for_player_state(actor)
        if team is None:
            return items
        inst = self._instructions_for(team, actor.player.name)
        if not inst:
            return items

        factors: dict[str, float] = {}

        def mul(action: str, value: float) -> None:
            factors[action] = factors.get(action, 1.0) * float(value)

        if inst.get("stay_back"):
            for action, factor in {
                "safe_pass": 1.12,
                "progressive_pass": 0.94,
                "carry": 0.80,
                "dribble": 0.72,
                "shoot": 0.76,
                "cross": 0.87,
                "cutback": 0.88,
            }.items():
                mul(action, factor)
        if inst.get("attack_depth"):
            for action, factor in {
                "safe_pass": 0.92,
                "progressive_pass": 1.06,
                "carry": 1.10,
                "dribble": 1.09,
                "shoot": 1.10,
            }.items():
                mul(action, factor)
        if inst.get("avoid_dribble"):
            mul("carry", 0.68)
            mul("dribble", 0.48)
            mul("safe_pass", 1.08)
        if inst.get("take_more_risks"):
            for action, factor in {
                "safe_pass": 0.86,
                "progressive_pass": 1.11,
                "through_ball": 1.15,
                "long_ball": 1.11,
                "switch": 1.07,
                "shoot": 1.08,
            }.items():
                mul(action, factor)
        if inst.get("cross_more"):
            mul("cross", 1.17)
            mul("cutback", 1.05)
            mul("shoot", 0.96)
        if inst.get("move_inside"):
            mul("through_ball", 1.07)
            mul("shoot", 1.07)
            mul("cross", 0.90)
        if inst.get("hold_width"):
            mul("cross", 1.09)
            mul("carry", 1.04)
            mul("shoot", 0.95)

        return [
            (
                action,
                max(0.001, float(weight) * clamp(factors.get(action, 1.0), 0.45, 1.28)),
            )
            for action, weight in items
        ]

    def _base_target_weights(
        self,
        team: int,
        zone: Zone,
        actor: PlayerState | None,
        ctx: dict | None = None,
    ):
        weights = super()._base_target_weights(team, zone, actor, ctx)
        context = ctx or {}
        space_behind = clamp(float(context.get("space_behind", 0.45)))
        opponent = 1 - int(team)
        opponent_press_targets = {
            str(inst.get("press_target"))
            for key, inst in getattr(self, "_v13_individual_instructions", {}).items()
            if str(key).startswith(f"{opponent}:") and inst.get("press_target")
        }

        out = []
        for ps, weight in weights:
            inst = self._instructions_for(team, ps.player.name)
            factor = 1.0
            if inst.get("attack_depth"):
                if zone.band in {Band.ATT, Band.BOX}:
                    factor *= 1.08 + 0.08 * space_behind
                elif zone.band == Band.MID:
                    factor *= 1.04
            if inst.get("stay_back"):
                if zone.band in {Band.ATT, Band.BOX}:
                    factor *= 0.82
                elif zone.band in {Band.DEF, Band.MID}:
                    factor *= 1.05

            pos = ps.player.position.upper()
            if inst.get("move_inside") and pos in {"LW", "RW", "LB", "RB"}:
                if zone.lane == Lane.CENTER:
                    factor *= 1.12
                else:
                    factor *= 0.94
            if inst.get("hold_width") and pos in {"LW", "RW", "LB", "RB"}:
                same_side = (
                    zone.lane == Lane.LEFT and pos in {"LW", "LB"}
                ) or (
                    zone.lane == Lane.RIGHT and pos in {"RW", "RB"}
                )
                factor *= 1.13 if same_side else 0.94

            # A targeted opponent is less freely available as a receiver. This
            # represents shadowing/pressure, not a tackling or pace bonus.
            if ps.player.name in opponent_press_targets:
                factor *= 0.90

            out.append((ps, float(weight) * clamp(factor, 0.72, 1.24)))
        return out

    def export_state(self) -> dict:
        data = super().export_state()
        self._ensure_instruction_state()
        data["v13_individual_instructions"] = deepcopy(
            self._v13_individual_instructions
        )
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_individual_instructions", {})
        obj._v13_individual_instructions = (
            deepcopy(raw) if isinstance(raw, dict) else {}
        )
        return obj


MatchEngine = MatchEngineV13IndividualInstructions

__all__ = ["MatchEngineV13IndividualInstructions", "MatchEngine"]
