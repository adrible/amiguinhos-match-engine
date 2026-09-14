from __future__ import annotations

"""v1.3-only roster loader for corrected U20 squads, evolved ratings and traits.

Stable v1.2 continues to load ``data/teams.json`` through ``team_loader.py``.
The v1.3 candidate starts from that frozen structure, then applies an optional
candidate-only roster overlay from ``data/v13_rosters.json`` before replacing
explicit Amiguinhos ratings with the literal current values stored in
``data/v13_player_traits.json``.

The legacy ``*_u21`` keys remain unchanged because they are part of the final
protocol and reserved-seed identity.  They do *not* imply that v1.3 must field
a senior/U21-strength roster: the candidate roster overlay explicitly models
the Amiguinhos and Flamengo squads on the same U20 internal rating scale.

Those values are NOT runtime boosts or deltas. Creativity, boldness and
determination remain separate behavioural traits.

Opponent teams that still have no explicit candidate bench may receive a
neutral deterministic reserve pool as a data-completeness fallback.  Teams
with real/known benches (including the corrected Flamengo U20 roster) are never
supplemented or replaced. Stable v1.2 is unaffected.
"""

import hashlib
import json
from pathlib import Path
from typing import Optional

from engine import Player, POSITION_TEMPLATE, Team
from engine import make_generic_team
from team_loader import load_team as load_stable_team


DEFAULT_V13_TRAITS = Path(__file__).resolve().parent / "data" / "v13_player_traits.json"
DEFAULT_V13_ROSTERS = Path(__file__).resolve().parent / "data" / "v13_rosters.json"
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


def load_v13_roster_database(path: Optional[str | Path] = None) -> dict:
    db_path = Path(path) if path is not None else DEFAULT_V13_ROSTERS
    with db_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    teams = data.get("teams")
    if not isinstance(teams, dict):
        raise ValueError("Invalid v1.3 roster database: missing 'teams' object.")
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


def _build_candidate_player(raw: dict) -> Player:
    """Create one candidate player from a U20 roster entry.

    A position template supplies neutral youth-football defaults around the
    declared OVR; explicit JSON attributes then replace those values.  This is
    deterministic and contains no fixture/result feedback.
    """
    if not isinstance(raw, dict):
        raise ValueError("v1.3 roster player entry must be an object.")
    name = str(raw.get("name", "")).strip()
    position = str(raw.get("position", "")).upper().strip()
    if not name or position not in POSITION_TEMPLATE:
        raise ValueError(f"Invalid v1.3 roster player: name={name!r}, position={position!r}")

    overall_value = float(raw.get("overall", 75))
    if not overall_value.is_integer() or not 1 <= int(overall_value) <= 95:
        raise ValueError(f"Invalid v1.3 overall for {name}: {overall_value}")
    overall = int(overall_value)

    delta = overall - 75
    kwargs: dict[str, object] = {
        "name": name,
        "position": position,
        "overall": overall,
    }
    for attr, base in POSITION_TEMPLATE[position].items():
        kwargs[attr] = int(max(20, min(95, round(float(base) + delta * 0.72))))

    explicit = _validated_attributes(name, raw)
    explicit.pop("overall", None)
    kwargs.update(explicit)
    if raw.get("preferred_foot") is not None:
        foot = str(raw["preferred_foot"]).upper().strip()
        if foot not in {"L", "R"}:
            raise ValueError(f"Invalid preferred foot for {name}: {foot!r}")
        kwargs["preferred_foot"] = foot
    return Player(**kwargs)


def _apply_tactics_overlay(team: Team, raw: dict) -> None:
    tactics_raw = raw.get("tactics", {})
    if not isinstance(tactics_raw, dict):
        raise ValueError("v1.3 roster tactics must be an object.")
    for key, value in tactics_raw.items():
        if not hasattr(team.tactics, key):
            raise ValueError(f"Unsupported v1.3 tactic field: {key}")
        setattr(team.tactics, key, value)
    team.tactics = team.tactics.normalized()


def apply_v13_roster(
    team: Team,
    team_key: str,
    *,
    roster_path: Optional[str | Path] = None,
) -> Team:
    """Apply candidate-only lineup/roster corrections without touching v1.2."""
    database = load_v13_roster_database(roster_path)
    raw = database["teams"].get(team_key)
    if raw is None:
        return team
    if not isinstance(raw, dict):
        raise ValueError(f"v1.3 roster entry for {team_key} must be an object.")

    if raw.get("name"):
        team.name = str(raw["name"])
    _apply_tactics_overlay(team, raw)

    players_raw = raw.get("players")
    if players_raw is not None:
        if not isinstance(players_raw, list):
            raise ValueError(f"v1.3 roster players for {team_key} must be a list.")
        starters: list[Player] = []
        bench: list[Player] = []
        seen: set[str] = set()
        for player_raw in players_raw:
            player = _build_candidate_player(player_raw)
            if player.name in seen:
                raise ValueError(f"Duplicate v1.3 roster player for {team_key}: {player.name}")
            seen.add(player.name)
            squad = str(player_raw.get("squad", "bench")).lower().strip()
            if squad == "starter":
                starters.append(player)
            elif squad == "bench":
                bench.append(player)
            else:
                raise ValueError(f"Invalid squad marker for {player.name}: {squad!r}")
        if len(starters) != 11:
            raise ValueError(
                f"v1.3 explicit roster for {team_key} must contain exactly 11 starters; "
                f"got {len(starters)}"
            )
        team.starters = starters
        team.bench = bench
        return team

    starter_names = raw.get("starter_names")
    bench_names = raw.get("bench_names")
    if starter_names is None and bench_names is None:
        return team
    if not isinstance(starter_names, list) or not isinstance(bench_names, list):
        raise ValueError(
            f"v1.3 roster for {team_key} must provide both starter_names and bench_names"
        )

    roster = {p.name: p for p in [*team.starters, *team.bench]}
    requested = [str(name) for name in [*starter_names, *bench_names]]
    unknown = sorted(set(requested) - set(roster))
    if unknown:
        raise ValueError(f"v1.3 roster for {team_key} references unknown players: {unknown}")
    if len(set(requested)) != len(requested):
        raise ValueError(f"v1.3 roster for {team_key} contains duplicate player names")
    if len(starter_names) != 11:
        raise ValueError(f"v1.3 roster for {team_key} must contain exactly 11 starters")

    team.starters = [roster[str(name)] for name in starter_names]
    team.bench = [roster[str(name)] for name in bench_names]
    return team


def _candidate_reserve_seed(team_key: str) -> int:
    """Stable per-team seed; independent from Python hash randomization."""
    digest = hashlib.sha256(f"v13-reserve-pool|{team_key}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _ensure_candidate_bench(team: Team, team_key: str) -> Team:
    """Provide a neutral deterministic bench only when candidate data has none."""
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
    roster_path: Optional[str | Path] = None,
) -> Team:
    """Load frozen v1.2 data, apply U20 roster correction, then evolved traits."""
    team = load_stable_team(team_key, teams_path)
    team = apply_v13_roster(team, team_key, roster_path=roster_path)
    team = apply_v13_traits(team, team_key, traits_path=traits_path)
    return _ensure_candidate_bench(team, team_key)


load_team = load_team_v13

__all__ = [
    "DEFAULT_V13_TRAITS",
    "DEFAULT_V13_ROSTERS",
    "load_v13_trait_database",
    "load_v13_roster_database",
    "apply_v13_roster",
    "apply_v13_traits",
    "load_team_v13",
    "load_team",
]
