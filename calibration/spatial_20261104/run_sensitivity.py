"""Deterministic counterfactual shot surfaces; no match outcome targets."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from engine import Band,Lane,Zone,PendingAction,make_generic_team
from engine_experiment_v13 import MatchEngine
from spatial_shot_v13 import shot_geometry

def surface(distance=12.,pressure=.4,quality=80,keeper_quality=80,body='right_foot',lateral=0.):
 e=MatchEngine(make_generic_team('A',80,seed=311),make_generic_team('B',80,seed=322),seed=113001)
 ps=e.teams[0].on_field[-1];k=e._goalkeeper(1);ps.x,ps.y=105.-distance,34.+lateral
 for attr in ('finishing','technique','composure','heading','balance','weak_foot'):
  if hasattr(ps.player,attr):setattr(ps.player,attr,quality)
 for attr in ('reflexes','gk_positioning','handling','one_on_one'):
  setattr(k.player,attr,keeper_quality)
 p=PendingAction(0,ps.player.name,'shoot',Zone(Band.BOX,Lane.CENTER),danger=.6,pressure=pressure,body_part=body)
 totals={'sot':0,'xg':0.,'expected_goals':0.,'spread':0.}
 for i in range(1000):
  e.state.second=i
  g=shot_geometry(e,p,ps,k,e.shot_selection_diagnostic(ps,p,k))
  xg=e._calculate_xg(p,ps,None,k)
  block=min(.34,max(.03,.07+.23*pressure+(80.-70)/260.-.07*p.danger))
  finisher=.45*ps.effective('finishing')+.3*ps.effective('composure')+.25*ps.effective('technique')
  conditional=e._shot_goal_probability(xg,block,g['reference_on_target_probability'],finisher,g['keeper_ability'])
  conditional=min(.98,max(0.,conditional*g['spatial_conversion_multiplier']))
  totals['sot']+=g['spatial_on_target'];totals['xg']+=xg
  totals['expected_goals']+=(1.-block)*g['spatial_on_target']*conditional
  totals['spread']+=g['shot_execution_spread']
 return {k:v/1000 for k,v in totals.items()}
cases={}
for distance in (6,12,18,24,35):cases[f'distance_{distance}']=surface(distance=distance)
for pressure in (0.,.5,1.):cases[f'pressure_{pressure}']=surface(pressure=pressure)
for quality in (45,70,95):cases[f'finisher_{quality}']=surface(quality=quality)
for quality in (45,70,95):cases[f'keeper_{quality}']=surface(keeper_quality=quality)
for y in (0.,10.,20.):cases[f'lateral_{y}']=surface(lateral=y)
for body in ('left_foot','right_foot','head'):cases[f'body_{body}']=surface(body=body)
checks={
 'distance_reduces_xg':cases['distance_6']['xg']>cases['distance_12']['xg']>cases['distance_24']['xg']>cases['distance_35']['xg'],
 'distance_reduces_accuracy':cases['distance_6']['sot']>cases['distance_35']['sot'],
 'pressure_reduces_xg':cases['pressure_0.0']['xg']>cases['pressure_1.0']['xg'],
 'pressure_reduces_accuracy':cases['pressure_0.0']['sot']>cases['pressure_1.0']['sot'],
 'skill_changes_accuracy':cases['finisher_95']['sot']>cases['finisher_45']['sot'],
 'skill_does_not_change_xg':abs(cases['finisher_95']['xg']-cases['finisher_45']['xg'])<1e-10,
 'keeper_reduces_conversion':cases['keeper_95']['expected_goals']<cases['keeper_45']['expected_goals'],
 'keeper_does_not_change_xg':abs(cases['keeper_95']['xg']-cases['keeper_45']['xg'])<1e-10,
 'angle_reduces_xg':cases['lateral_0.0']['xg']>cases['lateral_20.0']['xg']}
result={'scope':'20,000 counterfactual goal-plane executions. Sensitivity, not real-event validation. Expected goals use base block and spatial conversion formulas; they are not complete match outcomes.',
 'seed':113001,'samples_per_case':1000,'cases':cases,'checks':checks}
Path(sys.argv[1]).write_text(json.dumps(result,indent=2))
print(json.dumps(checks,indent=2))
if not all(checks.values()):raise AssertionError('Sensitivity failed')
