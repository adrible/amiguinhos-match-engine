"""Paired, outcome-blind benchmark of two runtime checkouts.

Run this script from the candidate checkout. Each worker runs in an isolated
Python process, so module caches cannot accidentally compare a version to itself.
Raw third-party CSVs stay in a local cache; only source hashes and aggregates
are written to the report. All contiguous seeds are retained.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def worker(root, start, count, output, neutral=False, mirror=False):
    sys.path.insert(0, str(Path(root).resolve()))
    import real_match_benchmark_v13 as bench
    if neutral:
        bench.BENCHMARK_VENUE_MODE = "neutral"
    if mirror:
        original = bench.MatchEngine
        def swapped(home, away, **kwargs):
            return original(away, home, **kwargs)
        bench.MatchEngine = swapped
    rows, _ = bench.simulate_engine_population(count, start)
    Path(output).write_text(json.dumps({'start': start, 'rows': rows}), encoding='utf-8')


def neutral_comparison(bench, real, simulated, seasons):
    """Same aggregate scales; neutral comparisons never score home/away slots.

    League aggregates are a broad reference, not a neutral-only dataset.
    This index is not interchangeable with the original home_away index.
    """
    from collections import Counter
    excluded = {'home_goals_per_match', 'away_goals_per_match', 'home_win_rate',
                'away_win_rate', 'result_distribution', 'scoreline_distribution'}
    result = bench.compare(real, simulated, seasons)
    components = [c for c in result['components'] if c['name'] not in excluded]
    def unordered(summary):
        result = Counter()
        for score, fraction in summary['scoreline_distribution'].items():
            result['-'.join(sorted(score.split('-')))] += fraction
        return dict(result)
    distance = bench._js_distance(unordered(real), unordered(simulated))
    components.append({'name': 'unordered_scoreline_distribution', 'kind': 'distribution',
                       'weight': 2., 'distance': distance, 'score': 100 * (1-distance)})
    return {'realism_index': sum(c['score']*c['weight'] for c in components)/sum(c['weight'] for c in components),
            'components': components, 'scope': 'neutral aggregate reference; no directional home/away metrics',
            'largest_gaps': sorted([c for c in components if c['kind']=='scalar'],key=lambda c:c['standardised_gap'],reverse=True)[:8]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--candidate', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--matches', type=int, default=300)
    parser.add_argument('--start-seed', type=int, default=91000)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--neutral', action='store_true')
    parser.add_argument('--mirror', action='store_true')
    parser.add_argument('--worker-root')
    parser.add_argument('--worker-start', type=int)
    parser.add_argument('--worker-count', type=int)
    args = parser.parse_args()
    if args.worker_root:
        worker(args.worker_root, args.worker_start, args.worker_count, args.output, args.neutral, args.mirror)
        return
    if args.matches <= 0 or not args.baseline or not args.cache or not args.output:
        parser.error('positive matches, baseline, cache and output are required')
    import real_match_benchmark_v13 as bench
    if bench.RESERVED_OFFICIAL_FINAL_SEED in range(args.start_seed, args.start_seed + args.matches):
        parser.error('reserved official-final seed is quarantined')
    real_rows, seasons = bench.load_real_collection(bench.SOURCE_FILE, args.cache)
    real = bench.summarise_matches(real_rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    chunks = args.output.parent / 'chunks'
    chunks.mkdir(exist_ok=True)
    jobs = []
    for label, root in [('before', args.baseline), ('after', args.candidate)]:
        for offset in range(0, args.matches, 50):
            count = min(50, args.matches - offset)
            start = args.start_seed + offset
            path = chunks / f'{label}_{start}.json'
            jobs.append((label, root.resolve(), start, count, path))
    def run(job):
        label, root, start, count, path = job
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker-root', str(root),
                        '--worker-start', str(start), '--worker-count', str(count), '--output', str(path)] + (['--neutral'] if args.neutral else []) + (['--mirror'] if args.mirror else []), check=True)
        print(f'{label}: {start}..{start+count-1} complete', flush=True)
        return label, json.loads(path.read_text())
    grouped = {'before': [], 'after': []}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(run, job) for job in jobs]):
            label, result = future.result()
            grouped[label].append(result)
    report = {'seed_range': [args.start_seed, args.start_seed+args.matches-1],
              'mirrored': args.mirror, 'real_match_count': len(real_rows), 'engine_matches_per_version': args.matches,
              'venue_mode': 'neutral' if args.neutral else bench.BENCHMARK_VENUE_MODE, 'real': real,
              'sources': [{'league': d['league'], 'season': d['season'], 'url': d['source'],
                           'matches': d['metrics']['matches']} for d in seasons],
              'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.cache.glob('*.csv'))},
              'scope': 'Core directly mapped match metrics only; xG and timing are excluded.',
              'versions': {}}
    for label, root in [('before', args.baseline), ('after', args.candidate)]:
        rows = [row for chunk in sorted(grouped[label], key=lambda d: d['start']) for row in chunk['rows']]
        if len(rows) != args.matches:
            raise RuntimeError('incomplete seed range')
        summary = bench.summarise_matches(rows)
        head = subprocess.check_output(['git','rev-parse','HEAD'], cwd=root, text=True).strip()
        # Runtime content hashes identify a tested worktree even before its audit commit.
        runtime_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob('*.py')) if not p.name.startswith('test_')}
        report['versions'][label] = {'checkout_head': head, 'runtime_sha256': runtime_hashes,
                                    'summary': summary, 'comparison': (neutral_comparison(bench, real, summary, seasons) if args.neutral else bench.compare(real, summary, seasons))}
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding='utf-8')
    print(json.dumps({label: data['comparison']['realism_index'] for label, data in report['versions'].items()}), flush=True)


if __name__ == '__main__':
    main()
