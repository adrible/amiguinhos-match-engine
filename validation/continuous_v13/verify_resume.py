"""Replay independent full matches after a mid-match JSON save/load.

This check uses only the explicitly supplied synthetic seeds and generic teams.
It compares the entire final state, including RNG and the possession/shot ledgers.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from engine import make_generic_team
from engine_experiment_v13_continuous import MatchEngine


def advance(e, minute=None, observe=False):
    for _ in range(20000):
        if e.state.ended or (minute is not None and e.minute >= minute):
            return
        if observe:
            e.pitch_snapshot()
            e.tracking_diagnostic()
        e.step()
    raise AssertionError('match did not terminate')


def json_state(e):
    # Historical event metadata may contain tuples which JSON restores as lists.
    # Compare the persisted representation, while still comparing every value.
    return json.loads(e.export_json())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--minute', type=float, default=45.)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    e = MatchEngine(make_generic_team('A', 80, seed=151001),
                    make_generic_team('B', 80, seed=151002), seed=args.seed,
                    venue_context='home_away',
                    environment={'weather': 'clear', 'pitch': 'normal', 'wind': .2, 'temperature_c': 22.})
    advance(e, args.minute)
    assert not e.state.ended
    saved_minute = e.minute
    saved = e.export_json()
    restored = MatchEngine.from_json(saved)
    assert json_state(e) == json_state(restored), 'restored state differs before resumption'
    advance(e)
    advance(restored, observe=True)
    final, other = json_state(e), json_state(restored)
    assert final == other, 'restored or observed continuation differs'
    assert e.shot_ledger_coverage()['complete']
    data = {'seed': args.seed, 'save_minute': saved_minute,
            'finished_minute': e.minute, 'score': e.score,
            'shots': sum(s.shots for s in e.stats),
            'save_sha256': hashlib.sha256(saved.encode()).hexdigest(),
            'observer_enabled_on_restored_run': True, 'equal_final_state': True}
    args.output.write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps(data))


if __name__ == '__main__':
    main()
