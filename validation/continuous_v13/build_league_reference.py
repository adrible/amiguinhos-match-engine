"""Full EPL 2015/16, StatsBomb Open Data. Aggregate and compact event evidence.
Attribution: StatsBomb/Hudl https://github.com/statsbomb/open-data
Raw inputs cached, never substituted with missing or sampled fixtures.
"""
import concurrent.futures as cf
import gzip,hashlib,json,math,time,urllib.request
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];CACHE=ROOT/'.cache/statsbomb';OUT=ROOT/'validation/continuous_v13';OUT.mkdir(parents=True,exist_ok=True)
BASE='https://raw.githubusercontent.com/statsbomb/open-data/master/data/'
def fetch(path):
 dest=CACHE/path.replace('/','_')
 if dest.exists():
  try:json.loads(dest.read_bytes())
  except (json.JSONDecodeError,UnicodeDecodeError):dest.unlink()
 if not dest.exists():
  for retry in range(4):
   try:
    payload=urllib.request.urlopen(urllib.request.Request(BASE+path,headers={'User-Agent':'Amiguinhos-Research'}),timeout=90).read()
    json.loads(payload);tmp=dest.with_suffix('.download');tmp.write_bytes(payload);tmp.replace(dest);break
   except Exception:
    if retry==3:raise
    time.sleep(1+retry)
 data=dest.read_bytes();return json.loads(data),hashlib.sha256(data).hexdigest()
matches,_=fetch('matches/2/27.json');assert len(matches)==380
teams={m['home_team']['home_team_name'] for m in matches};assert len(teams)==20
shots=[];passes=[];summaries=[];digests=[]
def extract(match):
 mid=match['match_id'];events,digest=fetch(f'events/{mid}.json');index={e['id']:e for e in events};ss=[];pp=[];prior={};poss={};keeper_missing=0
 for e in events:
  name=e['type']['name'];team=e.get('team',{}).get('name');period=e.get('period',0)
  if period>4:continue
  ts=float(e.get('minute',0))*60+float(e.get('second',0));loc=e.get('location')
  if name=='Pass' and loc:
   p=e['pass'];end=p.get('end_location',loc);row={'match_id':mid,'team':team,'period':period,'second':ts,'x':loc[0]*.875,'y':loc[1]*.85,'end_x':end[0]*.875,'end_y':end[1]*.85,'completed':'outcome' not in p,'pressure':bool(e.get('under_pressure')),'cross':bool(p.get('cross')),'through_ball':bool(p.get('through_ball') or p.get('technique',{}).get('name')=='Through Ball'),'height':p.get('height',{}).get('name'),'type':p.get('type',{}).get('name','Open Play')};row['distance']=math.hypot(row['end_x']-row['x'],row['end_y']-row['y']);pp.append(row)
  if name=='Shot' and loc:
   sh=e['shot'];assist=index.get(sh.get('key_pass_id'),{}).get('pass',{});ff=sh.get('freeze_frame',[])
   keeper=next((f for f in ff if (f.get('keeper') or f.get('position',{}).get('name')=='Goalkeeper') and not f.get('teammate')),None)
   opponents=[f for f in ff if not f.get('teammate') and not (f.get('keeper') or f.get('position',{}).get('name')=='Goalkeeper')]
   x,y=loc[0]*.875,loc[1]*.85;dx,dy=105-x,34-y
   recent=prior.get(team);rebound=bool(recent and recent['type']=='Shot' and recent['possession']==e.get('possession') and ts-recent['second']<=8 and recent['period']==period)
   source='penalty' if sh['type']['name']=='Penalty' else 'corner' if e.get('play_pattern',{}).get('name')=='From Corner' else 'rebound' if rebound else 'cross' if assist.get('cross') else 'through_ball' if (assist.get('through_ball') or assist.get('technique',{}).get('name')=='Through Ball') else 'cutback' if assist.get('cut_back') else 'free_kick' if sh['type']['name']=='Free Kick' else 'open_play'
   outcome=sh['outcome']['name'];body=sh['body_part']['name'];kp={'x':keeper['location'][0]*.875,'y':keeper['location'][1]*.85} if keeper else None
   ss.append({'match_id':mid,'team':team,'period':period,'second':ts,'x':x,'y':y,'distance':math.hypot(dx,dy),'angle':abs(math.atan2(3.66-dy,max(.01,dx))-math.atan2(-3.66-dy,max(.01,dx))),'inside_box':dx<=16.5 and abs(dy)<=20.16,'body':body,'header':body=='Head','pressure':bool(e.get('under_pressure')),'source':source,'cross':bool(assist.get('cross')),'through_ball':source=='through_ball','cutback':bool(assist.get('cut_back')),'freekick':source=='free_kick','penalty':source=='penalty','xg':sh['statsbomb_xg'],'goal':outcome=='Goal','on_target':outcome in {'Goal','Saved','Saved to Post'},'blocked':outcome=='Blocked','keeper':kp,'keeper_depth':105-kp['x'] if kp else None,'keeper_lateral':abs(34-kp['y']) if kp else None,'nearest_defender':min((math.hypot(f['location'][0]*.875-x,f['location'][1]*.85-y) for f in opponents),default=None),'defenders':[[f['location'][0]*.875,f['location'][1]*.85] for f in opponents]})
   keeper_missing+=keeper is None
  if name in {'Shot','Pass','Carry','Miscontrol','Dispossessed'}:prior[team]={'type':name,'possession':e.get('possession'),'period':period,'second':ts}
 return ss,pp,{'match_id':mid,'sha256':digest,'keeper_missing':keeper_missing,'home':match['home_team']['home_team_name'],'away':match['away_team']['away_team_name'],'home_score':match['home_score'],'away_score':match['away_score'],'match_date':match['match_date']}
start=time.monotonic()
with cf.ThreadPoolExecutor(max_workers=8) as pool:
 for i,(ss,pp,m) in enumerate(pool.map(extract,sorted(matches,key=lambda m:(m['match_date'],m['match_id'])))):
  shots+=ss;passes+=pp;summaries.append(m)
  if (i+1)%20==0:print(f'{i+1}/380 complete; shots={len(shots)}; passes={len(passes)}; seconds={time.monotonic()-start:.1f}',flush=True)
assert len(summaries)==380 and len({(m['home'],m['away']) for m in summaries})==380
result={'source':'StatsBomb Open Data, Premier League 2015/16','source_url':'https://github.com/statsbomb/open-data','matches':summaries,'n_matches':380,'n_teams':20,'coordinate_note':'120x80 normalized to 105x68, approximate metres; freeze frames are shot instants, not continuous tracking. No acceleration, jump or ball-flight observations are inferred.','rebound_definition':'previous same-team relevant action is a shot, same possession and period, within eight seconds; explicit inference, not provider label','shots':shots,'passes':passes,'split':{'train_ids':[m['match_id'] for m in summaries[:304]],'validation_ids':[m['match_id'] for m in summaries[304:]],'policy':'chronological 304/76 split, declared before outcomes'}}
raw=json.dumps(result,separators=(',',':')).encode();(CACHE/'epl_2015_16_compact.json.gz').write_bytes(gzip.compress(raw,mtime=0))
def stats(rows):
 n=len(rows);return {'n':n,'distance_mean':sum(r['distance'] for r in rows)/n if n else None,'xg_mean':sum(r['xg'] for r in rows)/n if n else None,'goal_rate':sum(r['goal'] for r in rows)/n if n else None,'sot_rate':sum(r['on_target'] for r in rows)/n if n else None,'pressure_rate':sum(r['pressure'] for r in rows)/n if n else None,'keeper_coverage':sum(r['keeper'] is not None for r in rows)/n if n else None}
summary={k:v for k,v in result.items() if k not in {'shots','passes'}};summary['shots']=stats([s for s in shots if not s['penalty']]);summary['by_source']={k:stats([s for s in shots if s['source']==k]) for k in sorted({s['source'] for s in shots})};summary['passes']={'attempts':len(passes),'complete':sum(p['completed'] for p in passes),'accuracy':sum(p['completed'] for p in passes)/len(passes),'per_match':len(passes)/380};(OUT/'league_reference.json').write_text(json.dumps(summary,indent=2));print('saved complete league',flush=True)
