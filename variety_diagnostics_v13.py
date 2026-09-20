"""Controlled opportunities: technique/target coverage, not match-frequency estimates."""
from collections import Counter
import json
from pathlib import Path
from engine import Band, Lane, Zone, PendingAction, make_generic_team
from engine_experiment_v13 import MatchEngine
from spatial_shot_v13 import shot_geometry


def diagnose(count=3000):
    e=MatchEngine(make_generic_team('A',85,seed=1),make_generic_team('B',85,seed=2),seed=13)
    a=next(p for p in e.teams[0].on_field if p.player.position=='ST')
    a.player.creativity=95
    a.player.technique=92
    a.player.vision=92
    a.player.preferred_foot='R'
    zone=Zone(Band.BOX,Lane.LEFT)
    targets=Counter(); actual=Counter(); shots=Counter(); passes=Counter(); executions=Counter()
    for i in range(count):
        e.state.second=i
        p=PendingAction(0,a.player.name,'shoot',zone,danger=.8,pressure=(.3 if i%2 else .7),
                        origin=['cross','cutback','through_ball','rebound','open_play'][i%5],
                        body_part='head' if i%7==0 else 'right_foot')
        g=shot_geometry(e,p,a,e._goalkeeper(1),e.shot_selection_diagnostic(a,p,e._goalkeeper(1)))
        targets[g['intended_shot_region']]+=1
        actual[g['actual_shot_region']]+=1
        shots[g['shot_type']]+=1
        e._v13_reception_plan={'actor':a.player.name,'zone':zone,'mode':'first_time'}
        d=e.creative_pass_diagnostic(a,zone,'through_ball',{'pressure':.55,'support':.8})
        if d['attempt']:
            passes[d['technique']]+=1
            executions[d['technique']]+=int(d['success'])
    return {'controlled_opportunities':count,'scope':'Synthetic high-skill opportunities; not match rates. Executed technique does not guarantee completed pass.',
            'intended_regions':dict(targets),'actual_regions':dict(actual),
            'shot_types':dict(shots),'pass_attempts':dict(passes),'pass_technique_executed':dict(executions)}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    result=diagnose();args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
