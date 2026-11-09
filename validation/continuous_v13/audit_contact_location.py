"""Audit the saved foul-contact point against the later resolution position."""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from engine import make_generic_team
from engine_experiment_v13_continuous import MatchEngine


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    e = MatchEngine(make_generic_team('A', 80, seed=151001),
                    make_generic_team('B', 80, seed=151002), seed=a.seed,
                    venue_context='home_away',
                    environment={'weather': 'clear', 'pitch': 'normal', 'wind': .2, 'temperature_c': 22.})
    original = e._resolve_continuous_foul
    rows = []

    def box(x, y):
        return x >= 88.5 and abs(y-34.) <= 20.16

    def inspect_foul(defending, defender, attacker, point):
        team = 1-defending
        contact = e._to_team(team, *point)
        later = e._to_team(team, attacker.x, attacker.y)
        event = original(defending, defender, attacker, point)
        rows.append({'contact': contact, 'resolution': later,
                     'distance_m': math.hypot(contact[0]-later[0], contact[1]-later[1]),
                     'contact_in_box': box(*contact), 'resolution_in_box': box(*later),
                     'restart': e.state.restart, 'advantage': event.data.get('advantage')})
        return event

    e._resolve_continuous_foul = inspect_foul
    for _ in range(20000):
        if e.state.ended:
            break
        e.step()
    else:
        raise AssertionError('match did not finish')
    a.output.write_text(json.dumps({'seed': a.seed, 'fouls': rows}, indent=2) + '\n')


if __name__ == '__main__':
    main()
