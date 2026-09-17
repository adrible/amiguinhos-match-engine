from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Optional

from engine import Player, Team, Tactics, POSITION_TEMPLATE, make_generic_team


DEFAULT_DATABASE = Path(__file__).resolve().parent / "data" / "teams.json"
V12_FROZEN_AMIGUINHOS = Path(__file__).resolve().parent / "data" / "v12_amiguinhos_frozen.json"
_PLAYER_FIELDS = {f.name for f in fields(Player)}


def load_database(path: Optional[str | Path] = None) -> dict:
    db_path = Path(path) if path is not None else DEFAULT_DATABASE
    with db_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "teams" not in data or not isinstance(data["teams"], dict):
        raise ValueError("Invalid teams database: missing 'teams' object.")

    # Stable v1.2 must not drift when candidate-only tournament progression is
    # edited in data/teams.json. Keep the Amiguinhos baseline literally frozen
    # for the default stable loader; explicit custom database paths remain
    # untouched so tests/tools can still load caller-supplied data normally.
    if path is None:
        with V12_FROZEN_AMIGUINHOS.open("r", encoding="utf-8") as fh:
            frozen = json.load(fh)
        raw_team = frozen.get("team")
        if not isinstance(raw_team, dict):
            raise ValueError("Invalid frozen v1.2 Amiguinhos snapshot.")
        data["teams"]["amiguinhos_u21"] = raw_team
    return data


def list_teams(path: Optional[str | Path] = None) -> list[str]:
    return sorted(load_database(path)["teams"])


def _scaled_template(position: str, overall: int) -> dict:
    position = position.upper()
    if position not in POSITION_TEMPLATE:
        raise ValueError(f"Unsupported engine position: {position}")
    delta = overall - 75
    return {
        attr: int(max(20, min(95, round(base + delta * 0.72))))
        for attr, base in POSITION_TEMPLATE[position].items()
    }


def _build_player(raw: dict, team_overall: int) -> Player:
    if "name" not in raw or "position" not in raw:
        raise ValueError("Every explicit player needs 'name' and 'position'.")

    position = str(raw["position"]).upper()
    overall = int(raw.get("overall", team_overall))
    kwargs = _scaled_template(position, overall)

    overrides = raw.get("attributes", {})
    if not isinstance(overrides, dict):
        raise ValueError(f"attributes for {raw['name']} must be an object.")

    invalid = set(overrides) - _PLAYER_FIELDS
    if invalid:
        raise ValueError(
            f"Unknown player attributes for {raw['name']}: {sorted(invalid)}"
        )
    kwargs.update({k: int(v) for k, v in overrides.items()})

    return Player(
        name=str(raw["name"]),
        position=position,
        overall=overall,
        preferred_foot=str(raw.get("preferred_foot", "R")).upper(),
        **kwargs,
    )


def load_team(team_key: str, path: Optional[str | Path] = None) -> Team:
    database = load_database(path)
    try:
        raw = database["teams"][team_key]
    except KeyError as exc:
        available = ", ".join(sorted(database["teams"]))
        raise KeyError(f"Unknown team {team_key!r}. Available: {available}") from exc

    name = str(raw.get("name", team_key))
    overall = int(raw.get("overall", 75))
    mode = raw.get("mode", "explicit")

    if mode == "generic":
        generator = raw.get("generator", {})
        team = make_generic_team(
            name=name,
            strength=int(generator.get("strength", overall)),
            style=str(generator.get("style", "balanced")),
            seed=int(generator.get("seed", 1)),
        )
        if raw.get("tactics"):
            merged = team.tactics.__dict__.copy()
            merged.update(raw["tactics"])
            team.tactics = Tactics(**merged).normalized()
        return team

    if mode != "explicit":
        raise ValueError(f"Unsupported roster mode for {team_key}: {mode!r}")

    raw_players = raw.get("players", [])
    starters = [
        _build_player(p, overall)
        for p in raw_players
        if p.get("squad", "starter") == "starter"
    ]
    bench = [
        _build_player(p, overall)
        for p in raw_players
        if p.get("squad", "starter") == "bench"
    ]

    if len(starters) != 11:
        raise ValueError(
            f"{team_key} must have exactly 11 explicit starters; got {len(starters)}."
        )

    tactics = Tactics(**raw.get("tactics", {})).normalized()
    return Team(name=name, starters=starters, bench=bench, tactics=tactics)
