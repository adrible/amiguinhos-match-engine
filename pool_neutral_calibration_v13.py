"""Combine both fixture orders; uncertainty resamples fixture pairs together."""
import argparse
import json
from pathlib import Path
import random
import statistics
import real_match_benchmark_v13 as bench
from compare_general_engine_v13 import neutral_comparison


def pool(root, cache):
    reports=[json.loads((root/name/'comparison.json').read_text()) for name in ['holdout','mirrored']]
    if reports[0]['seed_range']!=reports[1]['seed_range'] or reports[0]['mirrored'] or not reports[1]['mirrored']:
        raise ValueError('Expected identical seed ranges in opposite orders')
    if reports[0]['source_sha256']!=reports[1]['source_sha256']:
        raise ValueError('Real source mismatch')
    if any(r['venue_mode']!='neutral' for r in reports):
        raise ValueError('Neutral fixtures required')
    _,seasons=bench.load_real_collection(bench.SOURCE_FILE,cache)
    real=reports[0]['real']; grouped={};versions={}
    for version in ['before','after']:
        grouped[version]=[]
        for name in ['holdout','mirrored']:
            rows=[r for p in sorted((root/name/'chunks').glob(version+'_*.json')) for r in json.loads(p.read_text())['rows']]
            if len(rows)!=reports[0]['engine_matches_per_version']:
                raise ValueError('Incomplete fixture population')
            grouped[version].append(rows)
        summary=bench.summarise_matches(grouped[version][0]+grouped[version][1])
        versions[version]={'summary':summary,'comparison':neutral_comparison(bench,real,summary,seasons)}
    intervals={}
    for metric in ['goals','shots','sot','fouls','yellow','red','draw','zero_zero']:
        def value(row):
            if metric=='draw':return int(row['home_goals']==row['away_goals'])
            if metric=='zero_zero':return int(row['home_goals']==row['away_goals']==0)
            return row['home_'+metric]+row['away_'+metric]
        values=[sum(value(grouped['after'][o][i])-value(grouped['before'][o][i]) for o in (0,1))/2
                for i in range(len(grouped['before'][0]))]
        rng=random.Random(20260920)
        bootstrap=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(5000))
        intervals[metric]={'delta_after_minus_before':statistics.mean(values),'bootstrap_95_percent_interval':[bootstrap[125],bootstrap[4874]]}
    return {'fixture_pairs_per_version':len(grouped['before'][0]),'matches_per_version':2*len(grouped['before'][0]),
            'seed_range':reports[0]['seed_range'],'real':real,'versions':versions,'paired_deltas':intervals,
            'scope':'Both orders pooled; fixture pairs retained together during bootstrap. League reference is not a neutral-only sample.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--cache',type=Path,required=True)
    args=p.parse_args();report=pool(args.root,args.cache)
    (args.root/'pooled.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({v:r['comparison']['realism_index'] for v,r in report['versions'].items()}))
