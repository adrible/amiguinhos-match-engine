"""Paired descriptive bootstrap; resamples recorded matches, never engine seeds."""
import json
import random
import statistics
from summarise_audit import HERE, all_data, real, datasets, compare, summarise_matches

b = [r['stats'] for r in all_data['baseline']['records']]
s = [r['stats'] for r in all_data['spatial']['records']]
for row in b+s:
    for side in ('home','away'):
        assert 0<=row[side+'_goals']<=row[side+'_sot']<=row[side+'_shots']
    assert all(v>=0 for v in row.values())
rng = random.Random('index-bootstrap-20261104')
diffs = []
for _ in range(1000):
    idx = rng.choices(range(600), k=600)
    bi = compare(real, summarise_matches([b[i] for i in idx]), datasets)['realism_index']
    si = compare(real, summarise_matches([s[i] for i in idx]), datasets)['realism_index']
    diffs.append(si-bi)
v = sorted(diffs)
out = {'resamples':1000, 'sampling':'paired match indices with replacement; fixed real reference',
       'difference_spatial_minus_baseline_95_percentile':[v[24],v[974]],
       'bootstrap_mean_difference':statistics.mean(diffs), 'differences':diffs,
       'caveat':'Descriptive bootstrap of this synthetic sample and repository index; not universal realism uncertainty.'}
(HERE/'index_bootstrap.json').write_text(json.dumps(out,separators=(',',':')))
print({k:v for k,v in out.items() if k!='differences'})
