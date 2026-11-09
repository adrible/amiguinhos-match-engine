"""Measure paired pass-kind distributions from the retained league batches."""
import argparse
import json
import random
from pathlib import Path
from statistics import mean
from compare_paired_runs import read_runs


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--before', required=True)
    p.add_argument('--after', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    _, before = read_runs(a.before)
    _, after = read_runs(a.after)
    if before.keys() != after.keys():
        raise ValueError('fixtures and seeds must match')
    keys = sorted(before)
    rng = random.Random(20261110)
    result = {}
    for kind in ('long_ball', 'cross', 'safe_pass', 'progressive_pass', 'through_ball', 'cutback'):
        rows = []
        for source in (before, after):
            counts = [source[k]['passes_by_kind'].get(kind, {}).get('n', 0) for k in keys]
            completed = sum(source[k]['passes_by_kind'].get(kind, {}).get('complete', 0) for k in keys)
            rows.append({'counts': counts, 'per_match': mean(counts),
                         'completed': completed, 'attempts': sum(counts),
                         'accuracy': completed / sum(counts) if sum(counts) else None})
        delta = [y-x for x, y in zip(rows[0]['counts'], rows[1]['counts'])]
        sample = sorted(mean(delta[rng.randrange(len(delta))] for _ in delta) for _ in range(5000))
        for row in rows:
            del row['counts']
        result[kind] = {'before': rows[0], 'after': rows[1], 'difference': mean(delta),
                        'paired_bootstrap_ci95': [sample[124], sample[4874]]}
    out = {'matches_per_version': len(keys), 'bootstrap_replicates': 5000, 'pass_types': result,
           'note': 'Counts use simulator labels, which need not match StatsBomb pass categories.'}
    a.output.write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
