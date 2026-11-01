from __future__ import annotations

"""v1.3 positional familiarity and deployment layer.

A player's natural position, current deployment and secondary-position
familiarity are deliberately separate concepts. Familiarity changes whether a
coach is willing to deploy the player in a slot; it never boosts technical or
physical execution ratings.
"""

import json
from pathlib import Path
from typing import Optional

from engine import Player
from engine_experiment_v13_throwins import MatchEngineV13ThrowIns


POSITION_DATA = Path(__file__).resolve().parent / "data" / "v13_position_familiarity.json"
SUPPORTED_POSITIONS = {"GK", "RB", "CB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"}


class MatchEngineV13Positions(MatchEngineV13ThrowIns):
    """Adds explicit multi-position knowledge without creating ability buffs."""

    _position_profiles_cache: Optional[dict[str, dict]] = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_initial_deployments()

    @classmethod
    def _position_profiles(cls) -> dict[str, dict]:
        cached = cls._position_profiles_cache
        if isinstance(cached, dict):
            return cached
        data = json.loads(POSITION_DATA.read_text(encoding="utf-8"))
        teams = data.get("teams", {})
        if not isinstance(teams, dict):
            raise ValueError("Invalid v1.3 position database: missing teams object")

        flattened: dict[str, dict] = {}
        for team_raw in teams.values():
            if not isinstance(team_raw, dict):
                continue
            players = team_raw.get("players", {})
            if not isinstance(players, dict):
                continue
            for name, raw in players.items():
                if not isinstance(raw, dict):
                    raise ValueError(f"Invalid positional profile for {name}")
                primary = str(raw.get("primary", "")).upper().strip()
                if primary not in SUPPORTED_POSITIONS:
                    raise ValueError(f"Unsupported primary position for {name}: {primary!r}")
                familiarity_raw = raw.get("familiarity", {})
                if not isinstance(familiarity_raw, dict):
                    raise ValueError(f"Invalid positional familiarity for {name}")
                familiarity: dict[str, float] = {}
                for pos, value in familiarity_raw.items():
                    pos = str(pos).upper().strip()
                    value = float(value)
                    if pos not in SUPPORTED_POSITIONS:
                        raise ValueError(f"Unsupported secondary position for {name}: {pos!r}")
                    if not 0.0 <= value <= 1.0:
                        raise ValueError(f"Position familiarity for {name}/{pos} must be 0..1")
                    familiarity[pos] = value
                familiarity.setdefault(primary, 1.0)
                starting = raw.get("starting_position")
                if starting is not None:
                    starting = str(starting).upper().strip()
                    if starting not in SUPPORTED_POSITIONS:
                        raise ValueError(f"Unsupported starting position for {name}: {starting!r}")
                    if familiarity.get(starting, 0.0) < 0.50:
                        raise ValueError(f"Starting position for {name} is not familiar enough: {starting}")
                if str(name) in flattened:
                    raise ValueError(f"Duplicate positional profile name: {name}")
                flattened[str(name)] = {
                    "primary": primary,
                    "starting_position": starting,
                    "familiarity": familiarity,
                }
        cls._position_profiles_cache = flattened
        return flattened

    @classmethod
    def _explicit_position_profile(cls, player: Player) -> Optional[dict]:
        return cls._position_profiles().get(player.name)

    @classmethod
    def natural_position(cls, player: Player) -> str:
        profile = cls._explicit_position_profile(player)
        if profile is not None:
            return str(profile["primary"])
        return str(player.position).upper()

    @classmethod
    def position_familiarity(cls, player: Player, position: str) -> float:
        desired = str(position).upper().strip()
        if desired not in SUPPORTED_POSITIONS:
            return 0.0
        profile = cls._explicit_position_profile(player)
        if profile is None:
            return 1.0 if str(player.position).upper() == desired else 0.0
        return float(profile["familiarity"].get(desired, 0.0))

    @classmethod
    def position_profile_diagnostic(cls, player: Player) -> dict:
        profile = cls._explicit_position_profile(player)
        familiarity = (
            dict(profile["familiarity"])
            if profile is not None
            else {str(player.position).upper(): 1.0}
        )
        return {
            "player": player.name,
            "natural_position": cls.natural_position(player),
            "current_position": str(player.position).upper(),
            "starting_position": None if profile is None else profile.get("starting_position"),
            "familiarity": familiarity,
        }

    def _apply_initial_deployments(self) -> None:
        """Put known starters in their match slot without changing natural role metadata."""
        for rt in self.teams:
            for ps in rt.on_field:
                profile = self._explicit_position_profile(ps.player)
                if profile is None:
                    continue
                starting = profile.get("starting_position")
                if starting is None:
                    continue
                if self.position_familiarity(ps.player, str(starting)) >= 0.50:
                    ps.player.position = str(starting)

    def position_assignment_fit(self, outgoing_position: str, incoming: Player) -> float:
        """Compatibility of an incoming player with a concrete vacated slot."""
        desired = str(outgoing_position).upper().strip()
        if desired not in SUPPORTED_POSITIONS:
            return 0.0
        if str(incoming.position).upper() == desired:
            return 1.0

        explicit = self._explicit_position_profile(incoming)
        legacy = float(self._substitution_role_fit(desired, incoming.position))
        if explicit is None:
            return legacy

        familiar = self.position_familiarity(incoming, desired)
        # Known player data takes precedence. Generic adjacency remains only a
        # small emergency allowance so an explicitly single-position player is
        # not silently treated as fully versatile.
        return max(familiar, 0.72 * legacy)

    def _replacement_profile(self, team, outgoing, incoming, reason):
        desired = str(outgoing.player.position).upper()
        fit = self.position_assignment_fit(desired, incoming)
        if fit < 0.52:
            return None

        original_position = incoming.position
        profile = super()._replacement_profile(team, outgoing, incoming, reason)
        if profile is None and self.position_familiarity(incoming, desired) >= 0.52:
            # Let the existing substitution evaluator price the candidate as if
            # placed in the intended slot, then restore the roster object. No
            # match state is mutated by this diagnostic path.
            incoming.position = desired
            try:
                profile = super()._replacement_profile(team, outgoing, incoming, reason)
            finally:
                incoming.position = original_position
        if profile is None:
            return None

        old_fit = float(profile.get("role_fit", fit))
        profile["score"] = float(profile["score"]) + 1.30 * (fit - old_fit)
        profile["role_fit"] = fit
        profile["position_familiarity"] = self.position_familiarity(incoming, desired)
        profile["assigned_position"] = desired
        profile["natural_position"] = self.natural_position(incoming)
        return profile

    def substitute(
        self,
        team: int,
        out_name: str,
        in_name: str,
        position: Optional[str] = None,
    ):
        rt = self.teams[team]
        outgoing = rt.by_name(out_name)
        incoming = next((p for p in rt.bench if p.name == in_name), None)
        if incoming is None:
            raise KeyError(f"{in_name} is not on the bench.")

        desired = str(position or outgoing.player.position).upper().strip()
        if desired not in SUPPORTED_POSITIONS:
            raise ValueError(f"Unsupported deployment position: {desired}")

        explicit = self._explicit_position_profile(incoming)
        fit = self.position_assignment_fit(desired, incoming)
        if position is not None and fit < 0.52 and str(incoming.position).upper() != desired:
            raise ValueError(
                f"{incoming.name} is not sufficiently familiar with {desired} "
                f"(fit={fit:.2f})."
            )

        # Automatic/straight substitutions preserve the vacated tactical slot
        # only when we actually know the player's positional profile. Unknown
        # opposition reserves retain their old behaviour and primary position.
        assign_slot = (
            str(incoming.position).upper() == desired
            or (explicit is not None and fit >= 0.52)
            or position is not None
        )
        natural = self.natural_position(incoming)
        original_position = incoming.position
        assigned = desired if assign_slot else str(incoming.position).upper()
        incoming.position = assigned
        try:
            event = super().substitute(team, out_name, in_name)
        except Exception:
            incoming.position = original_position
            raise

        event.data.update(
            {
                "natural_position": natural,
                "assigned_position": assigned,
                "position_familiarity": round(self.position_familiarity(incoming, assigned), 3),
                "position_fit": round(float(fit), 3),
            }
        )
        return event


MatchEngine = MatchEngineV13Positions

__all__ = ["MatchEngineV13Positions", "MatchEngine"]
