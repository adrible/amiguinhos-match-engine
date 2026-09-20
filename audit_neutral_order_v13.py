"""Paired diagnostic of listing order; bootstrap fixture pairs, not individual games."""
import argparse
import json
from pathlib import Path
import random
import statistics


def analyse(normal, mirrored, version):
    def rows(folder):
        found = {}
        for path in sorted((folder / 'chunks').glob(version + '_*.json')):
            chunk = json.loads(path.read_text())
            found.update({chunk['start'] + i: row for i, row in enumerate(chunk['rows'])})
        return found
    a, b = rows(normal), rows(mirrored)
    seeds = sorted(set(a) & set(b))
    if not seeds:
        raise ValueError('No matched fixture seeds')
    # Each fixture occurs in both orders. Averaging slot differences cancels
    # the fixture's underlying strength imbalance in expectation, not pathwise.
    values = [(a[s]['home_goals'] - a[s]['away_goals'] +
               b[s]['home_goals'] - b[s]['away_goals']) / 2 for s in seeds]
    rng = random.Random(20260920)
    boot = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(5000))
    metrics = {}
    for label, source in [('normal', a), ('mirrored', b)]:
        r = [source[s] for s in seeds]
        metrics[label] = {
            'goals_per_match': statistics.mean(x['home_goals'] + x['away_goals'] for x in r),
            'zero_zero_rate': sum(x['home_goals'] == x['away_goals'] == 0 for x in r) / len(r),
            'draw_rate': sum(x['home_goals'] == x['away_goals'] for x in r) / len(r),
        }
    return {'fixture_pairs': len(seeds), 'seed_range': [seeds[0], seeds[-1]],
            'slot_goal_difference': statistics.mean(values),
            'paired_bootstrap_95_percent_interval': [boot[125], boot[4874]],
            'matched_metrics': metrics,
            'interpretation': 'An interval including zero is inconclusive, not proof of symmetry. Labels are internal slots, not venue advantage.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--normal', type=Path, required=True)
    p.add_argument('--mirrored', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    report = {v: analyse(args.normal, args.mirrored, v) for v in ('before', 'after')}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
