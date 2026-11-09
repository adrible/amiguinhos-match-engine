"""Complete 20-team home/away schedule with generic, not historical, rosters.
Output summarizes every pass plus all shot frames; full ledgers stay executable
through the deterministic engine and selected saved fixture evidence.
"""
import argparse,collections,hashlib,json,math,statistics,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from engine import make_generic_team
from engine_experiment_v13_continuous import MatchEngine
p=argparse.ArgumentParser();p.add_argument('--start',type=int,default=0);p.add_argument('--count',type=int,default=380);p.add_argument('--output',type=Path,required=True);p.add_argument('--parity',action='store_true');p.add_argument('--seed-base',type=int,default=124000);a=p.parse_args()
ref=json.loads((ROOT/'validation/continuous_v13/league_reference.json').read_text());schedule=sorted(ref['matches'],key=lambda m:(m['match_date'],m['match_id']));names=sorted({m['home'] for m in schedule});indices={name:i for i,name in enumerate(names)}
def fixture(i):
 m=schedule[i];home=make_generic_team('Generic '+m['home'],80,seed=130000+indices[m['home']]);away=make_generic_team('Generic '+m['away'],80,seed=130000+indices[m['away']])
 return MatchEngine(home,away,seed=a.seed_base+i,venue_context='home_away',environment={'weather':'clear','pitch':'normal','wind':.2,'temperature_c':22.})
def complete(e):
 for _ in range(20000):
  if e.state.ended:break
  e.step()
 else:raise AssertionError('Match guard reached')
 assert e.shot_ledger_coverage()['complete']
 assert len({r['shot_id'] for r in e.shot_ledger_diagnostic()})==sum(s.shots for s in e.stats)
 assert abs(sum(r['xg'] for r in e.shot_ledger_diagnostic())-sum(s.xg for s in e.stats))<1e-7
 assert all(p['status']!='in_flight' for p in e._cs_passes)
 assert abs(sum(e._cs_totals['controlled_seconds'])+e._cs_totals['loose_seconds']-e._cs_totals['in_play_seconds'])<1e-5
 for ps in (p for rt in e.teams for p in rt.on_field):assert all(math.isfinite(v) for v in (ps.x,ps.y,ps.energy)) and 0<=ps.x<=105 and 0<=ps.y<=68
 return e
result={'engine_commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
 'engine_code_sha256':hashlib.sha256((ROOT/'engine_experiment_v13_continuous.py').read_bytes()).hexdigest(),'physics_sha256':hashlib.sha256((ROOT/'continuous_physics_v13.py').read_bytes()).hexdigest(),
 'model_sha256':hashlib.sha256((ROOT/'data/continuous_shot_model_v13.json').read_bytes()).hexdigest(),
 'scope':'380-fixture full home/away schedule; 20 generic strength-80 rosters. Distribution comparison, not prediction of historical player/match outcomes.',
 'start':a.start,'count':a.count,'seeds':list(range(a.seed_base+a.start,a.seed_base+a.start+a.count)),'matches':[],'failures':[],'parity':False}
start=time.monotonic()
for i in range(a.start,a.start+a.count):
 try:
  e=complete(fixture(i))
  if a.parity and i==a.start:
   other=fixture(i)
   for _ in range(20000):
    if other.state.ended:break
    other.pitch_snapshot();other.tracking_diagnostic();other.step()
   assert e.export_state()==other.export_state();result['parity']=True
  stats={key:[getattr(s,key) for s in e.stats] for key in ('goals','shots','on_target','xg','fouls','corners','yellow','red','offsides','substitutions') if hasattr(e.stats[0],key)}
  bykind={}
  for kind in sorted({r['kind'] for r in e._cs_passes}):
   rr=[r for r in e._cs_passes if r['kind']==kind];bykind[kind]={'n':len(rr),'complete':sum(r['status']=='completed' for r in rr),'distance':statistics.mean(r['distance'] for r in rr)}
  result['matches'].append({'fixture':i,'source_match_id':schedule[i]['match_id'],'seed':a.seed_base+i,'stats':stats,'minute':e.minute,
   'pass_outcomes':dict(collections.Counter(r['status'] for r in e._cs_passes)),'passes_by_kind':bykind,
   'totals':e._cs_totals,'players':{k:vars(m) for k,m in e._cs_motion.items()},'shots':e._cs_shots,
   'possession_segments':e._cs_possessions,'event_counts':dict(collections.Counter(r['kind'] for r in e._cs_events))})
 except Exception:result['failures'].append({'fixture':i,'traceback':traceback.format_exc()})
 if (i-a.start+1)%5==0:print(f'{i-a.start+1}/{a.count}; failures={len(result["failures"])}; seconds={time.monotonic()-start:.1f}',flush=True)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,separators=(',',':')));print('saved',a.output,'failures',len(result['failures']),flush=True)
