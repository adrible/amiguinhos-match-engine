"""Replay every available shot frame from a complete league, no sampled fixtures."""
import gzip,json,math,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from continuous_shot_model_v13 import MODEL,chance
raw=json.loads(gzip.decompress((ROOT/'.cache/statsbomb/epl_2015_16_compact.json.gz').read_bytes()))
rows=[]
for s in raw['shots']:
 if s['penalty']:continue
 frame={k:s[k] for k in ('distance','angle','pressure','keeper','keeper_depth','keeper_lateral','nearest_defender')}
 # Runtime helper receives cross and through-ball separately from play pattern.
 row={**s,'prediction':chance(frame,header=s['header'],source=s['source'],cross=s['cross'],through_ball=s['through_ball'])}
 rows.append(row)
def summarize(rr):
 n=len(rr)
 if not n:return {'n':0}
 return {'n':n,'distance_mean':statistics.mean(r['distance'] for r in rr),'angle_mean_degrees':statistics.mean(r['angle']*180/math.pi for r in rr),
 'provider_mean_xg':statistics.mean(r['xg'] for r in rr),'engine_mean_xg':statistics.mean(r['prediction'] for r in rr),
 'mae_to_provider':statistics.mean(abs(r['prediction']-r['xg']) for r in rr),'actual_goals_per_shot':statistics.mean(r['goal'] for r in rr),
 'keeper_position_observed':sum(r['keeper'] is not None for r in rr),'pressure_observed_rate':statistics.mean(r['pressure'] for r in rr)}
valid=set(raw['split']['validation_ids'])
result={'source':raw['source'],'matches':380,'n_teams':20,'data_missing_matches':0,'coordinate_note':raw['coordinate_note'],'rebound_definition':raw['rebound_definition'],
 'all':summarize(rows),'heldout_76_matches':summarize([r for r in rows if r['match_id'] in valid]),
 'sources':{k:{'all':summarize([r for r in rows if r['source']==k]),'heldout':summarize([r for r in rows if r['source']==k and r['match_id'] in valid])} for k in sorted({r['source'] for r in rows})},
 'pressure':{str(flag):summarize([r for r in rows if r['pressure']==flag]) for flag in (False,True)},
 'keeper_depth':{f'{lo}-{hi}':summarize([r for r in rows if r['keeper_depth'] is not None and lo<=r['keeper_depth']<hi]) for lo,hi in [(0,2),(2,5),(5,120)]},
 'limitations':['Freeze frames are shot instants; they cannot validate continuous acceleration, jump timing or ball drag against real tracking.','The model approximates provider xG, not deterministic scoring.','Rebounds are inferred from sequence/possession and eight-second timing; source categories are not interchangeable without this definition.']}
(ROOT/'validation/continuous_v13/real_league_replay.json').write_text(json.dumps(result,indent=2));print(json.dumps(result['heldout_76_matches'],indent=2))
