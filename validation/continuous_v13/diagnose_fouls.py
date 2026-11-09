"""Record spatial foul decisions in synthetic matches without changing them."""
import argparse
import json
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
    args = p.parse_args()
    e = MatchEngine(make_generic_team('A', 80, seed=151001),
                    make_generic_team('B', 80, seed=151002), seed=args.seed,
                    venue_context='home_away',
                    environment={'weather': 'clear', 'pitch': 'normal', 'wind': .2, 'temperature_c': 22.})
    original = e._commit_foul
    records = []

    def record(defending_team, defender, attacker, zone, **kwargs):
        x, y = e._to_team(1 - defending_team, attacker.x, attacker.y)
        pressure = e._physical_pressure(1 - defending_team, attacker.x, attacker.y)
        result = original(defending_team, defender, attacker, zone, **kwargs)
        records.append({'minute': e.minute, 'attack_x': x, 'attack_y': y,
                        'box': zone.band.value == 'box', 'pressure': pressure,
                        'advantage': result.data.get('advantage'), 'event': str(result.type.value),
                        'foul_type': result.data.get('foul_type')})
        return result

    e._commit_foul = record
    for _ in range(20000):
        if e.state.ended:
            break
        e.step()
    else:
        raise AssertionError('match did not finish')
    args.output.write_text(json.dumps({'seed': args.seed, 'records': records,
                                     'shots': sum(s.shots for s in e.stats),
                                     'goals': sum(e.score),
                                     'ledger_complete': e.shot_ledger_coverage()['complete']}, indent=2))


if __name__ == '__main__':
    main()
