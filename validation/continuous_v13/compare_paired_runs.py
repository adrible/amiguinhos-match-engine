"""Summarize two complete matched league batches, without choosing outcomes."""
import argparse
import glob
import gzip
import json
import random
from collections import Counter
from pathlib import Path
from statistics import mean


def read_runs(pattern):
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise ValueError(f'no files match {pattern}')
    runs = [json.loads(gzip.open(p, 'rt', encoding='utf-8').read()) if p.endswith('.gz')
            else json.loads(Path(p).read_text()) for p in paths]
    if any(r['failures'] for r in runs):
        raise ValueError('a run contains failures')
    for field in ('engine_code_sha256', 'physics_sha256', 'model_sha256'):
        if len({r[field] for r in runs}) != 1:
            raise ValueError(f'inconsistent {field}')
    games = [g for r in runs for g in r['matches']]
    keys = [(g['fixture'], g['source_match_id'], g['seed']) for g in games]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate fixtures')
    return runs, dict(zip(keys, games))


def game_metrics(g):
    stats, shots = g['stats'], g['shots']
    passes = sum(g['pass_outcomes'].values())
    return {'goals': sum(stats['goals']), 'shots': sum(stats['shots']),
            'on_target': sum(stats['on_target']), 'fouls': sum(stats['fouls']),
            'yellow': sum(stats['yellow']), 'passes': passes,
            'completed_passes': g['pass_outcomes'].get('completed', 0),
            'penalties': sum(s['origin'] == 'penalty' for s in shots),
            'cross_shots': sum(s['origin'] == 'cross' for s in shots),
            'cross_headers': sum(s['origin'] == 'cross' and s['body_part'] == 'head' for s in shots),
            'xg': sum(stats['xg']),
            'home_win': int(stats['goals'][0] > stats['goals'][1]),
            'away_win': int(stats['goals'][0] < stats['goals'][1]),
            'draw_0_0': int(stats['goals'] == [0, 0])}


def summarize(games):
    metrics = [game_metrics(g) for g in games]
    shots = [s for g in games for s in g['shots'] if s['origin'] != 'penalty']
    avg = {k: mean(m[k] for m in metrics) for k in metrics[0]}
    avg['pass_accuracy'] = sum(m['completed_passes'] for m in metrics) / max(1, sum(m['passes'] for m in metrics))
    avg['shot_distance_nonpenalty'] = mean(s['frame']['distance'] for s in shots)
    avg['nonpenalty_xg_per_shot'] = mean(s['xg'] for s in shots)
    avg['nonpenalty_conversion'] = mean(s['goal'] for s in shots)
    return avg


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--before', required=True)
    p.add_argument('--after', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--bootstrap', type=int, default=5000)
    a = p.parse_args()
    rb, before = read_runs(a.before)
    ra, after = read_runs(a.after)
    if before.keys() != after.keys():
        raise ValueError('batches do not contain the same fixtures and seeds')
    keys = sorted(before)
    b, c = [before[k] for k in keys], [after[k] for k in keys]
    rows_b, rows_c = [game_metrics(x) for x in b], [game_metrics(x) for x in c]
    rng = random.Random(20261109)
    intervals = {}
    for metric in ('goals', 'shots', 'on_target', 'fouls', 'yellow', 'passes', 'penalties', 'cross_shots', 'cross_headers', 'xg'):
        delta = [z[metric] - x[metric] for x, z in zip(rows_b, rows_c)]
        draws = sorted(mean(delta[rng.randrange(len(delta))] for _ in delta) for _ in range(a.bootstrap))
        intervals[metric] = {'mean_difference': mean(delta), 'ci95': [draws[int(.025 * (len(draws)-1))], draws[int(.975 * (len(draws)-1))]]}
    out = {'matches_per_version': len(keys), 'matched_fixtures_seeds': keys,
           'before_engine_sha256': rb[0]['engine_code_sha256'], 'after_engine_sha256': ra[0]['engine_code_sha256'],
           'before': summarize(b), 'after': summarize(c), 'paired_bootstrap': intervals,
           'bootstrap_replicates': a.bootstrap, 'parity_before': any(r['parity'] for r in rb),
           'parity_after': any(r['parity'] for r in ra),
           'note': 'Paired exploratory simulations on generic rosters; intervals describe these fixtures, not real-world model validity.'}
    a.output.write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
