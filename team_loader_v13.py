from __future__ import annotations

"""v1.3-only roster loader for behavioural traits and candidate boosts.

The stable ``team_loader.py`` remains the authoritative v1.2 loader.  This
module calls it first and then attaches optional dynamic v1.3 traits plus
explicit candidate-only attribute boosts from a separate data file.  The base
``Player`` dataclass is therefore not changed and stable loading remains
byte-for-byte compatible with v1.2.
"""

import json
from pathlib import Path
from typing import Optional

from engine import Team
from team_loader import load_team as load_stable_team


DEFAULT_V13_TRAITS = Path(__file__).resolve().parent / "data" / "v13_player_traits.json"
_ALLOWED_TRAITS = {"creativity", "boldness", "determination"}
_ALLOWED_BOOST_ATTRIBUTES = {
    "overall",
    "pace",
    "passing",
    "vision",
    "technique",
    "dribbling",
    "crossing",
    "finishing",
    "long_shots",
    "heading",
    "strength",
    "tackling",
    "positioning",
    "anticipation",
    "composure",
    "off_ball",
    "stamina",
    "reflexes",
    "handling",
    "gk_positioning",
    "one_on_one",
}


def load_v13_trait_database(path: Optional[str | Path] = None) -> dict:
    db_path = Path(path) if path is not None else DEFAULT_V13_TRAITS
    with db_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    teams = data.get("teams")
    if not isinstance(teams, dict):
        raise ValueError("Invalid v1.3 trait database: missing 'teams' object.")
    return data


def _validated_traits(player_name: str, raw: dict) -> dict[str, float]:
    if not isinstance(raw, dict):
        raise ValueError(f"v1.3 traits for {player_name} must be an object.")
    values = {}
    for key in _ALLOWED_TRAITS:
        if key not in raw:
            continue
        value = float(raw[key])
        if not 0.0 <= value <= 100.0:
            raise ValueError(
                f"v1.3 trait {key} for {player_name} must be between 0 and 100."
            )
        values[key] = value
    return values


def _validated_attribute_boosts(team_key: str, raw: dict) -> dict[str, float]:
    boosts = raw.get("attribute_boosts", {}) if isinstance(raw, dict) else {}
    if boosts is None:
        return {}
    if not isinstance(boosts, dict):
        raise ValueError(f"v1.3 attribute_boosts for {team_key} must be an object.")

    unknown = sorted(set(boosts) - _ALLOWED_BOOST_ATTRIBUTES)
    if unknown:
        raise ValueError(
            f"v1.3 attribute_boosts for {team_key} contains unsupported attributes: {unknown}"
        )

    validated: dict[str, float] = {}
    for key, raw_value in boosts.items():
        value = float(raw_value)
        if not -10.0 <= value <= 10.0:
            raise ValueError(
                f"v1.3 attribute boost {key} for {team_key} must be between -10 and 10."
            )
        validated[key] = value
    return validated


def _apply_attribute_boosts(team: Team, team_key: str, team_raw: dict) -> None:
    boosts = _validated_attribute_boosts(team_key, team_raw)
    if not boosts:
        return

    for player in [*team.starters, *team.bench]:
        for attr, boost in boosts.items():
            current = float(getattr(player, attr))
            # Keep the candidate within the same rating scale as the stable DB.
            boosted = max(1.0, min(95.0, current + boost))
            setattr(player, attr, int(round(boosted)))


def apply_v13_traits(
    team: Team,
    team_key: str,
    *,
    traits_path: Optional[str | Path] = None,
) -> Team:
    database = load_v13_trait_database(traits_path)
    team_raw = database["teams"].get(team_key, {})
    if not isinstance(team_raw, dict):
        raise ValueError(f"v1.3 team entry for {team_key} must be an object.")

    # Candidate boosts are explicit data, not an engine-side team-name bonus.
    # Any team could receive the same mechanism through the v1.3 data file.
    _apply_attribute_boosts(team, team_key, team_raw)

    players_raw = team_raw.get("players", {})
    if not isinstance(players_raw, dict):
        raise ValueError(f"v1.3 players for {team_key} must be an object.")

    roster = {p.name: p for p in [*team.starters, *team.bench]}
    unknown = sorted(set(players_raw) - set(roster))
    if unknown:
        raise ValueError(
            f"v1.3 trait database references unknown players for {team_key}: {unknown}"
        )

    for player_name, raw in players_raw.items():
        player = roster[player_name]
        for key, value in _validated_traits(player_name, raw).items():
            setattr(player, key, value)
    return team


def load_team_v13(
    team_key: str,
    teams_path: Optional[str | Path] = None,
    *,
    traits_path: Optional[str | Path] = None,
) -> Team:
    """Load the stable roster, then apply optional v1.3-only data."""
    team = load_stable_team(team_key, teams_path)
    return apply_v13_traits(team, team_key, traits_path=traits_path)


# Friendly alias for v1.3 scripts.  We intentionally do not replace the stable
# ``team_loader.load_team`` symbol anywhere.
load_team = load_team_v13

__all__ = [
    "DEFAULT_V13_TRAITS",
    "load_v13_trait_database",
    "apply_v13_traits",
    "load_team_v13",
    "load_team",
]
