import sys,json,time,collections,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from engine import make_generic_team
from engine_experiment_v13_continuous import MatchEngine
out=[];start=time.monotonic()
for seed in range(int(sys.argv[1]),int(sys.argv[1])+int(sys.argv[2])):
 e=MatchEngine(make_generic_team('A',80,seed=1),make_generic_team('B',80,seed=2),seed=seed,venue_context='home_away',environment={'weather':'clear','pitch':'normal','wind':.2,'temperature_c':22})
 for i in range(20000):
  if e.state.ended:break
  e.step()
 if not e.state.ended:raise AssertionError('guard')
 assert e.shot_ledger_coverage()['complete']
 row={'seed':seed,'score':e.score,'minute':e.minute,'shots':sum(s.shots for s in e.stats),'sot':sum(s.on_target for s in e.stats),'fouls':sum(s.fouls for s in e.stats),'corners':sum(s.corners for s in e.stats),'passes':dict(collections.Counter(p['status'] for p in e._cs_passes)),'total_passes':len(e._cs_passes),'shot_distance':statistics.mean(s['frame']['distance'] for s in e._cs_shots) if e._cs_shots else None,'sources':dict(collections.Counter(s['origin'] for s in e._cs_shots)),'totals':e._cs_totals}
 out.append(row);print(json.dumps(row),flush=True)
Path(sys.argv[3]).write_text(json.dumps(out,indent=2));print('seconds',time.monotonic()-start,flush=True)
