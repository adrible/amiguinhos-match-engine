from __future__ import annotations

"""Candidate-only historical fixture data for Brazil x Germany, 8 July 2014.

This module is intentionally isolated from frozen v1.2 data. Ratings are a
senior historical scale for the 2014 squads and are NOT calibrated to reproduce
the real 7-1 scoreline. Every engine attribute is explicitly defined.
"""

from engine import Player, Team, Tactics
from team_loader_v13 import load_team_v13

ATTRIBUTE_ORDER = (
    "pace", "passing", "vision", "technique", "dribbling", "crossing",
    "finishing", "long_shots", "heading", "strength", "tackling",
    "positioning", "anticipation", "composure", "off_ball", "stamina",
    "aggression", "discipline", "reflexes", "handling", "gk_positioning",
    "one_on_one",
)

# name, shirt, primary position, semifinal status, overall, foot, 22 ratings,
# creativity, boldness, determination, note
BRAZIL_2014_PLAYERS = [
    ('Jefferson',1,'GK','bench',84,'R',[51,69,67,68,60,54,44,49,56,79,49,84,84,84,52,74,59,74,88,85,86,86],79,82,85,''),
    ('Dani Alves',2,'RB','bench',89,'R',[90,88,87,92,91,93,75,84,71,75,83,80,87,89,92,92,82,77,39,39,39,39],91,91,89,''),
    ('Thiago Silva',3,'CB','unavailable',93,'R',[84,84,82,84,72,65,55,68,91,89,94,95,95,94,66,86,82,91,43,43,43,43],77,80,94,'Suspenso para a semifinal. Cadastrado, mas indisponível.'),
    ('David Luiz',4,'CB','starter',89,'R',[82,86,84,85,76,78,70,92,89,88,88,84,85,85,70,88,88,72,39,39,39,39],84,91,94,''),
    ('Fernandinho',5,'DM','starter',86,'R',[82,87,86,87,83,78,73,85,72,80,87,86,89,87,80,92,82,80,36,36,36,36],85,82,90,''),
    ('Marcelo',6,'LB','starter',90,'L',[89,90,88,94,93,93,77,85,72,78,82,82,87,88,91,90,80,76,40,40,40,40],93,92,91,''),
    ('Hulk',7,'RW','starter',87,'L',[89,83,81,87,88,88,87,93,82,95,56,72,84,83,88,90,87,72,37,37,37,37],83,91,91,''),
    ('Paulinho',8,'CM','bench',85,'R',[82,84,82,83,80,76,82,83,84,86,84,84,86,84,88,92,82,84,35,35,35,35],80,84,90,''),
    ('Fred',9,'ST','starter',83,'R',[68,75,74,83,76,65,88,80,89,88,40,70,89,87,88,77,78,78,33,33,33,33],73,81,86,''),
    ('Neymar',10,'LW','unavailable',94,'R',[93,88,91,95,95,87,91,87,65,65,38,70,91,92,94,84,62,78,44,44,44,44],95,94,92,'Lesionado e fora da semifinal. Cadastrado, mas indisponível.'),
    ('Oscar',11,'AM','starter',88,'R',[85,90,91,92,91,86,85,86,68,70,72,78,89,89,91,90,72,83,38,38,38,38],92,86,91,''),
    ('Júlio César',12,'GK','starter',86,'R',[53,72,69,70,62,56,46,51,58,82,51,87,87,88,54,76,61,76,90,88,89,90],65,82,92,''),
    ('Dante',13,'CB','starter',87,'L',[76,82,79,82,70,67,57,67,90,88,89,89,89,87,67,84,81,86,37,37,37,37],74,78,89,''),
    ('Maxwell',14,'LB','bench',84,'L',[79,85,84,86,84,88,68,75,68,73,82,84,84,87,84,83,69,90,34,34,34,34],84,75,84,''),
    ('Henrique',15,'CB','bench',82,'R',[74,74,70,74,65,62,52,62,85,87,85,84,82,80,62,82,82,82,32,32,32,32],66,76,84,''),
    ('Ramires',16,'CM','bench',86,'R',[91,83,82,84,84,79,78,80,74,77,84,83,87,83,88,95,84,82,36,36,36,36],82,86,92,''),
    ('Luiz Gustavo',17,'DM','starter',87,'L',[78,85,83,84,78,73,70,83,83,89,92,91,91,87,75,91,86,82,37,37,37,37],78,81,92,''),
    ('Hernanes',18,'CM','bench',85,'R',[76,88,88,90,86,84,81,90,75,80,78,80,85,89,84,84,72,87,35,35,35,35],89,84,86,''),
    ('Willian',19,'RW','bench',87,'R',[91,87,87,91,92,88,80,84,62,68,62,72,86,87,90,91,68,85,37,37,37,37],90,88,89,''),
    ('Bernard',20,'LW','starter',84,'R',[91,83,84,90,92,84,79,78,55,55,55,68,83,82,89,84,60,82,34,34,34,34],88,88,86,''),
    ('Jô',21,'ST','bench',80,'L',[72,70,68,77,73,62,82,74,88,91,38,67,82,80,83,78,78,77,30,30,30,30],68,79,83,''),
    ('Victor',22,'GK','bench',83,'R',[50,67,66,67,59,53,43,48,55,78,48,84,84,84,51,73,58,73,88,84,85,88],61,80,87,''),
    ('Maicon',23,'RB','starter',86,'R',[82,83,80,84,82,90,75,84,84,88,84,83,84,84,84,84,82,78,36,36,36,36],83,85,87,''),
]

GERMANY_2014_PLAYERS = [
    ('Manuel Neuer',1,'GK','starter',94,'R',[69,92,86,86,78,64,54,59,66,91,59,94,94,95,62,88,76,91,95,93,95,95],82,94,95,''),
    ('Kevin Großkreutz',2,'RB','bench',84,'R',[85,80,77,80,81,83,72,76,75,79,81,81,82,80,84,94,82,82,34,34,34,34],77,83,90,''),
    ('Matthias Ginter',3,'CB','bench',82,'R',[76,78,75,77,68,62,52,62,84,83,84,83,84,82,62,84,76,87,32,32,32,32],70,74,86,''),
    ('Benedikt Höwedes',4,'LB','starter',86,'R',[77,78,75,77,70,74,60,70,91,90,90,91,90,86,70,89,83,87,36,36,36,36],72,79,91,''),
    ('Mats Hummels',5,'CB','starter',91,'R',[74,88,86,87,75,67,61,74,93,90,93,94,95,93,66,86,82,89,41,41,41,41],84,82,93,''),
    ('Sami Khedira',6,'DM','starter',88,'R',[81,85,84,84,78,78,76,81,87,91,88,88,89,86,87,94,88,84,38,38,38,38],82,87,93,''),
    ('Bastian Schweinsteiger',7,'CM','starter',91,'R',[76,94,94,93,86,89,83,93,82,87,87,89,92,95,85,91,86,89,41,41,41,41],94,88,95,''),
    ('Mesut Özil',8,'AM','starter',91,'L',[84,95,95,95,94,92,84,84,61,65,50,70,92,93,91,86,50,90,41,41,41,41],95,84,88,''),
    ('André Schürrle',9,'LW','bench',88,'R',[93,84,82,88,89,85,87,90,75,76,55,68,86,84,91,89,72,83,38,38,38,38],84,90,91,''),
    ('Lukas Podolski',10,'LW','bench',87,'L',[87,83,80,87,85,88,90,95,78,89,50,67,85,88,87,86,80,82,37,37,37,37],81,92,92,''),
    ('Miroslav Klose',11,'ST','starter',88,'R',[76,78,79,85,81,68,93,84,94,87,43,72,95,94,95,82,78,89,38,38,38,38],78,84,95,''),
    ('Ron-Robert Zieler',12,'GK','bench',84,'R',[51,70,67,68,60,54,44,49,56,79,49,84,84,83,52,74,59,74,87,85,85,86],62,79,86,''),
    ('Thomas Müller',13,'RW','starter',92,'R',[86,88,91,88,85,87,93,88,90,82,60,78,95,93,95,94,80,88,42,42,42,42],91,91,95,''),
    ('Julian Draxler',14,'AM','bench',85,'R',[87,85,86,89,90,84,82,85,72,74,54,69,84,84,87,84,60,85,35,35,35,35],89,87,84,''),
    ('Erik Durm',15,'LB','bench',82,'R',[87,77,74,79,80,82,65,68,75,76,80,79,80,78,82,89,76,84,32,32,32,32],73,80,86,''),
    ('Philipp Lahm',16,'RB','starter',92,'R',[88,93,92,94,92,91,69,82,60,70,94,95,95,95,89,95,76,94,42,42,42,42],93,86,95,''),
    ('Per Mertesacker',17,'CB','bench',87,'R',[59,78,76,76,62,67,57,67,95,94,91,93,91,90,67,79,80,90,37,37,37,37],69,75,92,''),
    ('Toni Kroos',18,'CM','starter',92,'R',[74,95,95,95,89,93,84,94,70,79,78,84,93,95,87,91,65,93,42,42,42,42],95,88,93,''),
    ('Mario Götze',19,'AM','bench',89,'R',[87,91,92,94,94,84,87,84,68,70,58,72,90,91,92,86,59,89,39,39,39,39],94,88,91,''),
    ('Jérôme Boateng',20,'CB','starter',89,'R',[84,85,80,82,72,80,58,84,90,95,91,89,90,88,65,89,87,78,39,39,39,39],75,84,92,''),
    ('Shkodran Mustafi',21,'CB','unavailable',81,'R',[78,75,71,74,66,61,51,61,84,84,82,80,81,78,61,82,80,80,31,31,31,31],66,76,84,'Lesionado e fora do restante da Copa após as oitavas. Cadastrado, mas indisponível.'),
    ('Roman Weidenfeller',22,'GK','bench',87,'R',[54,72,70,71,63,57,47,52,59,82,52,88,87,88,55,77,62,77,91,89,89,90],63,83,91,''),
    ('Christoph Kramer',23,'CM','bench',85,'R',[80,85,84,85,81,76,72,78,78,82,86,86,87,84,82,93,80,87,35,35,35,35],82,80,90,''),
]

HISTORICAL_2014 = {
    "brazil_2014": {
        "name": "🇧🇷 Brasil 2014",
        "coach": "Luiz Felipe Scolari",
        "overall": 87,
        "context": "Semifinal da Copa do Mundo de 2014; Neymar lesionado e Thiago Silva suspenso.",
        "tactics": dict(formation="4-2-3-1", mentality=0.16, tempo=0.63, width=0.60,
                        pressing=0.66, defensive_line=0.58, compactness=0.57,
                        directness=0.52, counter=0.64, overlap_left=0.70,
                        overlap_right=0.50, cross_frequency=0.51, risk=0.61),
        "players": BRAZIL_2014_PLAYERS,
    },
    "germany_2014": {
        "name": "🇩🇪 Alemanha 2014",
        "coach": "Joachim Löw",
        "overall": 90,
        "context": "Semifinal da Copa do Mundo de 2014; Mustafi cadastrado, porém lesionado.",
        "tactics": dict(formation="4-2-3-1", mentality=0.24, tempo=0.66, width=0.57,
                        pressing=0.65, defensive_line=0.62, compactness=0.66,
                        directness=0.43, counter=0.58, overlap_left=0.34,
                        overlap_right=0.58, cross_frequency=0.40, risk=0.55),
        "players": GERMANY_2014_PLAYERS,
    },
}


def is_historical_2014_team(team_key: str) -> bool:
    return team_key in HISTORICAL_2014


def historical_roster(team_key: str):
    try:
        return HISTORICAL_2014[team_key]["players"]
    except KeyError as exc:
        raise KeyError(f"Unknown historical team {team_key!r}") from exc


def _build_historical_player(row) -> Player:
    name, number, position, _status, overall, foot, ratings, creativity, boldness, determination, _note = row
    if len(ratings) != len(ATTRIBUTE_ORDER):
        raise ValueError(f"Historical attribute vector for {name} has wrong length")
    kwargs = dict(zip(ATTRIBUTE_ORDER, map(int, ratings)))
    player = Player(name=name, position=position, overall=int(overall), preferred_foot=foot, **kwargs)
    player.number = int(number)
    player.creativity = float(creativity)
    player.boldness = float(boldness)
    player.determination = float(determination)
    return player


def load_historical_2014_team(team_key: str) -> Team:
    try:
        raw = HISTORICAL_2014[team_key]
    except KeyError as exc:
        raise KeyError(f"Unknown historical team {team_key!r}") from exc

    starters = []
    bench = []
    unavailable = []
    for row in raw["players"]:
        status = row[3]
        if status == "unavailable":
            unavailable.append({"name": row[0], "number": row[1], "note": row[-1]})
            continue
        p = _build_historical_player(row)
        if status == "starter":
            starters.append(p)
        elif status == "bench":
            bench.append(p)
        else:
            raise ValueError(f"Unsupported historical squad status {status!r} for {row[0]}")

    if len(starters) != 11:
        raise ValueError(f"{team_key} historical fixture requires exactly 11 starters")

    team = Team(
        name=raw["name"],
        starters=starters,
        bench=bench,
        tactics=Tactics(**raw["tactics"]).normalized(),
    )
    team.historical_key = team_key
    team.historical_context = raw["context"]
    team.coach = raw["coach"]
    team.unavailable = unavailable
    team.declared_overall = int(raw["overall"])
    return team


def load_team_for_v13(team_key: str) -> Team:
    """Load candidate tournament teams or isolated historical 2014 test teams."""
    if is_historical_2014_team(team_key):
        return load_historical_2014_team(team_key)
    return load_team_v13(team_key)


__all__ = [
    "ATTRIBUTE_ORDER", "BRAZIL_2014_PLAYERS", "GERMANY_2014_PLAYERS",
    "HISTORICAL_2014", "is_historical_2014_team", "historical_roster",
    "load_historical_2014_team", "load_team_for_v13",
]
