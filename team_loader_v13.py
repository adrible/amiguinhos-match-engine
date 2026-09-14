from __future__ import annotations

"""v1.3-only roster loader for evolved ratings and behavioural traits.

Stable v1.2 continues to load ``data/teams.json`` through ``team_loader.py``.
The candidate v1.3 starts from that frozen roster to preserve the known team
structure, then replaces explicitly listed player ratings with the literal
current values stored in ``data/v13_player_traits.json``.

Those values are NOT runtime boosts or deltas. They are the players' new
ratings after their progression during the tournament. Creativity, boldness
and determination remain separate behavioural traits.

Some explicit tournament opponents were originally stored with only eleven
starters.  v1.3 needs a usable bench for the autonomous substitution coach, so
teams with *no bench data at all* receive a deterministic neutral reserve pool.
Known benches are never supplemented or replaced.  Stable v1.2 is unaffected.
"""

import hashlib
import json
from pathlib import Path
from typing import Optional

from engine import Team, make_generic_team
from team_loader import load_team as load_stable_team


DEFAULT_V13_TRAITS = Path(__file__).resolve().parent / "data" / "v13_player_traits.json"
_ALLOWED_TRAITS = {"creativity", "boldness", "determination"}
_ALLOWED_ATTRIBUTES = {
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
    "aggression",
    "discipline",
}


def load_v13_trait_database(path: Optional[str | Path] = None) -> dict:
    db_path = Path(path) if path is not None else DEFAULT_V13_TRAITS
    with db_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    teams = data.get("teams")
    if not isinstance(teams, dict):
        raise ValueError("Invalid v1.3 player database: missing 'teams' object.")
    return data


def _validated_traits(player_name: str, raw: dict) -> dict[str, float]:
    if not isinstance(raw, dict):
        raise ValueError(f"v1.3 data for {player_name} must be an object.")
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


def _validated_attributes(player_name: str, raw: dict) -> dict[str, int]:
    attributes = raw.get("attributes", {}) if isinstance(raw, dict) else {}
    if attributes is None:
        return {}
    if not isinstance(attributes, dict):
        raise ValueError(f"v1.3 attributes for {player_name} must be an object.")

    unknown = sorted(set(attributes) - _ALLOWED_ATTRIBUTES)
    if unknown:
        raise ValueError(
            f"v1.3 attributes for {player_name} contains unsupported fields: {unknown}"
        )

    validated: dict[str, int] = {}
    for key, raw_value in attributes.items():
        value = float(raw_value)
        if not value.is_integer():
            raise ValueError(
                f"v1.3 attribute {key} for {player_name} must be an integer rating."
            )
        integer = int(value)
        if not 1 <= integer <= 95:
            raise ValueError(
                f"v1.3 attribute {key} for {player_name} must be between 1 and 95."
            )
        validated[key] = integer
    return validated


def _candidate_reserve_seed(team_key: str) -> int:
    """Stable per-team seed; independent from Python hash randomization."""
    digest = hashlib.sha256(f"v13-reserve-pool|{team_key}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _ensure_candidate_bench(team: Team, team_key: str) -> Team:
    """Provide a neutral deterministic bench only when the source has none.

    The generated pool is intentionally generic and one strength step below the
    team's rounded starting-XI average.  It is a data-completeness fallback,
    not a team-specific buff.  Any explicitly supplied bench wins completely.
    """
    if team.bench:
        return team
    if not team.starters:
        return team

    average_overall = round(
        sum(float(player.overall) for player in team.starters) / len(team.starters)
    )
    generated = make_generic_team(
        name=f"{team.name} Reserva",
        strength=int(average_overall),
        style="balanced",
        seed=_candidate_reserve_seed(team_key),
    )
    team.bench = list(generated.bench)
    return team


def apply_v13_traits(
    team: Team,
    team_key: str,
    *,
    traits_path: Optional[str | Path] = None,
) -> Team:
    """Apply literal v1.3 ratings plus optional behavioural traits.

    No arithmetic is performed against the v1.2 ratings. If the JSON says
    ``passing: 88``, the candidate player's passing is exactly 88.
    """
    database = load_v13_trait_database(traits_path)
    team_raw = database["teams"].get(team_key, {})
    if not isinstance(team_raw, dict):
        raise ValueError(f"v1.3 team entry for {team_key} must be an object.")

    players_raw = team_raw.get("players", {})
    if not isinstance(players_raw, dict):
        raise ValueError(f"v1.3 players for {team_key} must be an object.")

    roster = {p.name: p for p in [*team.starters, *team.bench]}
    unknown = sorted(set(players_raw) - set(roster))
    if unknown:
        raise ValueError(
            f"v1.3 player database references unknown players for {team_key}: {unknown}"
        )

    for player_name, raw in players_raw.items():
        player = roster[player_name]
        for key, value in _validated_attributes(player_name, raw).items():
            setattr(player, key, value)
        for key, value in _validated_traits(player_name, raw).items():
            setattr(player, key, value)
    return team


def load_team_v13(
    team_key: str,
    teams_path: Optional[str | Path] = None,
    *,
    traits_path: Optional[str | Path] = None,
) -> Team:
    """Load frozen v1.2 structure, evolve ratings, then ensure candidate depth."""
    team = load_stable_team(team_key, teams_path)
    team = apply_v13_traits(team, team_key, traits_path=traits_path)
    return _ensure_candidate_bench(team, team_key)


load_team = load_team_v13

__all__ = [
    "DEFAULT_V13_TRAITS",
    "load_v13_trait_database",
    "apply_v13_traits",
    "load_team_v13",
    "load_team",
]
