"""StatsBomb Open Data, World Cup 2022: geometry reference and held-out xG fit.
Data source: https://github.com/statsbomb/open-data (now hudl/open-data).
Only aggregates/model coefficients are published; raw events remain in cache.
"""
import concurrent.futures as cf
import hashlib,json,math
from pathlib import Path
import urllib.request
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

ROOT=Path(__file__).resolve().parents[2]; CACHE=ROOT/'.cache/statsbomb'; CACHE.mkdir(parents=True,exist_ok=True)
BASE='https://raw.githubusercontent.com/statsbomb/open-data/master/data/'
def fetch(path):
 p=CACHE/path.replace('/','_')
 if not p.exists():
  req=urllib.request.Request(BASE+path,headers={'User-Agent':'Amiguinhos-football-research'})
  p.write_bytes(urllib.request.urlopen(req,timeout=60).read())
 return json.loads(p.read_bytes()),hashlib.sha256(p.read_bytes()).hexdigest()
matches,_=fetch('matches/43/106.json');ids=sorted(m['match_id'] for m in matches)
def read(mid):
 events,digest=fetch(f'events/{mid}.json');byid={e['id']:e for e in events};rows=[]
 for e in events:
  if e['type']['name']!='Shot' or e.get('period',0)==5:continue
  shot=e['shot']; loc=e['location'];x,y=loc[0]*105/120,loc[1]*68/80
  dx,dy=105-x,34-y;distance=math.hypot(dx,dy)
  angle=abs(math.atan2(3.66-dy,max(.1,dx))-math.atan2(-3.66-dy,max(.1,dx)))
  assist=byid.get(shot.get('key_pass_id'),{}).get('pass',{})
  kind=shot['type']['name'];body=shot['body_part']['name'];outcome=shot['outcome']['name']
  row={'match_id':mid,'x':x,'y':y,'distance':distance,'angle':angle,'header':body=='Head',
       'pressure':bool(e.get('under_pressure')),'cross':bool(assist.get('cross')),
       'cutback':bool(assist.get('cut_back')),'freekick':kind=='Free Kick','penalty':kind=='Penalty',
       'xg':shot['statsbomb_xg'],'goal':outcome=='Goal','on_target':outcome in ('Goal','Saved','Saved to Post'),
       'inside_box':dx<=16.5 and abs(dy)<=20.16,'kind':kind,'body':body,
       'end_z':shot.get('end_location',[0,0,0])[2] if len(shot.get('end_location',[]))>=3 else None}
  rows.append(row)
 return rows,{'match_id':mid,'sha256':digest}
rows=[];hashes=[]
with cf.ThreadPoolExecutor(max_workers=8) as pool:
 for rr,hh in pool.map(read,ids):rows.extend(rr);hashes.append(hh)
hold=set(ids[::4]);train=[r for r in rows if r['match_id'] not in hold and not r['penalty']];valid=[r for r in rows if r['match_id'] in hold and not r['penalty']]
features=['intercept','distance','angle','header','pressure','cross','cutback','freekick']
def vector(r):return [1.,r['distance'],r['angle'],float(r['header']),float(r['pressure']),float(r['cross']),float(r['cutback']),float(r['freekick'])]
X=np.array([vector(r) for r in train]);y=np.array([r['xg'] for r in train])
# Soft-label binomial cross entropy fits mean chance probability without
# overweighting the logarithms of very small probabilities.
bounds=[(-20,10),(-2,0),(0,10),(-5,0),(-5,0),(-5,0),(0,5),(-5,0)]
def objective(coef):
 z=X@coef
 return float(np.mean(np.logaddexp(0,z)-y*z)), X.T@(expit(z)-y)/len(y)
fit=minimize(objective,[-2,-.09,2,-1,-.2,-.1,0,0],jac=True,bounds=bounds,method='L-BFGS-B',options={'maxiter':5000,'ftol':1e-13,'gtol':1e-9})
if not fit.success:raise RuntimeError(fit.message)
coef=fit.x
pred=lambda rr:expit(np.array([vector(r) for r in rr])@coef)
def stats(rr):
 a=np.array([r['distance'] for r in rr]);return {'shots':len(rr),'distance_mean':float(a.mean()),'distance_median':float(np.median(a)),
 'inside_box_share':sum(r['inside_box'] for r in rr)/len(rr),'header_share':sum(r['header'] for r in rr)/len(rr),
 'goals_per_shot':sum(r['goal'] for r in rr)/len(rr),'on_target_rate':sum(r['on_target'] for r in rr)/len(rr),'mean_xg':float(np.mean([r['xg'] for r in rr])),
 'distance_bins':{f'{lo}-{hi}':sum(lo<=r['distance']<hi for r in rr)/len(rr) for lo,hi in [(0,6),(6,12),(12,18),(18,24),(24,35),(35,120)]}}
result={'source':'StatsBomb Open Data — FIFA World Cup 2022','source_url':'https://github.com/statsbomb/open-data','matches':len(ids),
 'coordinate_note':'StatsBomb 120x80 normalized to the engine 105x68 frame; approximate normalized metres, not measured stadium dimensions.',
 'split':'Every fourth sorted match ID held out before fitting; no shootouts; penalties excluded from geometry fit.',
 'train_match_ids':[m for m in ids if m not in hold],'validation_match_ids':sorted(hold),
 'fit_objective':'soft-label binomial cross entropy against StatsBomb xG, with sign constraints',
 'features':features,'coefficients':dict(zip(features,map(float,coef))),
 'train':stats(train),'validation':stats(valid),'all_nonpenalty':stats(train+valid),
 'validation_xg_mae':float(np.mean(abs(pred(valid)-[r['xg'] for r in valid]))),
 'validation_predicted_mean_xg':float(pred(valid).mean()),'digests':hashes,
 'by_body':{body:stats([r for r in rows if not r['penalty'] and r['body']==body]) for body in ('Head','Right Foot','Left Foot')}}
(ROOT/'data/spatial_shot_reference_v13.json').write_text(json.dumps(result,indent=2))
(CACHE/'shot_rows.json').write_text(json.dumps(rows))
print(json.dumps({k:v for k,v in result.items() if k not in ('digests','train_match_ids','validation_match_ids')},indent=2))
