"""Controlled interventions after an identical 60-minute simulated prefix.

Common random-number seeds reduce starting-state variation; trajectories may
diverge after intervention. Effects are within this model, not causal estimates
of real football. No result is used to tune the frozen continuous engine.
"""
import argparse
import copy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from engine import MatchConfig, make_generic_team
from engine_experiment_v13_continuous import MatchEngine

CASES=('pressing','low_block','numerical_advantage','rain','fresh_substitution','score_state','scheduled_120_minutes')


def fingerprint_attributes(e):
    rows=[]
    for rt in e.teams:
        rows.append([{k:v for k,v in asdict(p.player).items() if k!='name'} for p in rt.on_field])
    return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()


def fixture(seed):
    a=make_generic_team('A',80,seed=140000)
    b=make_generic_team('B',80,seed=140000)
    # A same-attribute, same-role replacement exists before either branch.
    a.bench.append(replace(a.starters[-1],name='A equal-attribute fresh ST'))
    e=MatchEngine(a,b,seed=seed,venue_context='neutral',config=MatchConfig(injuries_enabled=False,direct_red_enabled=False,auto_tactical_adaptation=False),
        environment={'weather':'clear','pitch':'normal','wind':.2,'temperature_c':22.})
    e.auto_substitutions_enabled=False
    for left,right in zip(e.teams[0].on_field,e.teams[1].on_field):
        e.set_player_physical_profile(1,right.player.name,**asdict(e._cs_profiles[e._key(0,left.player.name)]))
    return e


def advance(e,minute=None):
    for _ in range(20000):
        if e.state.ended or (minute is not None and e.minute>=minute and e.state.pending is None and e._cs_transport is None):return e
        e.step()
    raise AssertionError('Match did not terminate')


def measure(e):
    active=[[p for p in rt.on_field if not p.red] for rt in e.teams]
    return {'minute':e.minute,'goals':list(e.score),'shots':[s.shots for s in e.stats],'xg':[s.xg for s in e.stats],
        'energy':[statistics.mean(p.energy for p in rr) for rr in active],
        'active_players':[len(rr) for rr in active],
        'distance':[sum(v.distance for k,v in e._cs_motion.items() if k.startswith(str(t)+'::')) for t in (0,1)],
        'sprint_distance':[sum(v.sprint_distance for k,v in e._cs_motion.items() if k.startswith(str(t)+'::')) for t in (0,1)],
        'passes':len(e._cs_passes),'completed_passes':sum(p['status']=='completed' for p in e._cs_passes),
        'pass_completion':sum(p['status']=='completed' for p in e._cs_passes)/max(1,len(e._cs_passes)),
        'control_seconds':list(e._cs_totals['controlled_seconds']),
        'shot_pressure':statistics.mean(s['frame']['pressure'] for s in e._cs_shots) if e._cs_shots else None,
        'mean_shot_distance':statistics.mean(s['frame']['distance'] for s in e._cs_shots) if e._cs_shots else None}


def intervention(e,case):
    """One prescribed input; all its consequences are left to the engine."""
    if case=='pressing':e.set_tactics(0,pressing=.9);return {'input':'team0.pressing','before':.5,'after':.9}
    if case=='low_block':e.set_tactics(1,defensive_line=.25);return {'input':'team1.defensive_line','before':.5,'after':.25}
    if case=='rain':
        e._v13_environment={**e._v13_environment,'weather':'rain'}
        return {'input':'weather','before':'clear','after':'rain','pitch_unchanged':'normal'}
    if case=='numerical_advantage':
        p=next(p for p in e.teams[1].on_field if p.player.position=='CB' and not p.red)
        p.red=True;e.stats[1].red+=1
        if e._xy_ball.get('owner')=={'team':1,'player':p.player.name}:e._loose('prescribed_dismissal')
        return {'input':'team1.active_player','before':p.player.name,'after':'dismissed_without_foul'}
    if case=='fresh_substitution':
        p=e.teams[0].on_field[-1];incoming='A equal-attribute fresh ST'
        # Profiles and attributes match; freshness, replacement identity and the
        # normal substitution stoppage are the treatment, not better talent.
        assert {k:v for k,v in asdict(p.player).items() if k!='name'}=={k:v for k,v in asdict(next(p for p in e.teams[0].bench if p.name==incoming)).items() if k!='name'}
        profile=copy.deepcopy(e._cs_profiles[e._key(0,p.player.name)])
        before_energy=p.energy;e.substitute(0,p.player.name,incoming)
        e.set_player_physical_profile(0,incoming,**asdict(profile))
        return {'input':'team0.ST replacement','before_energy':before_energy,'after_energy':1.,'attributes_equal':True,'profile_equal':True,'normal_stoppage_seconds':18.}
    if case=='score_state':
        before=list(e.score);e.stats[0].goals+=1
        return {'input':'score differential','before':before,'after':list(e.score),'note':'Prescribed scoreboard, not a simulated goal; compare incremental goals only.'}
    if case=='scheduled_120_minutes':
        e.state.period_markers=[45,90,105,120]
        return {'input':'scheduled duration','before':90,'after':120,'note':'Unconditional duration stress test; not tournament extra-time qualification.'}
    raise ValueError(case)


def window(end,start):
    result={}
    for key in ('goals','shots','xg','distance','sprint_distance','control_seconds'):
        result[key]=[a-b for a,b in zip(end[key],start[key])]
    result['minutes']=end['minute']-start['minute']
    result['energy']=end['energy']
    result['energy_change']=[a-b for a,b in zip(end['energy'],start['energy'])]
    result['passes']=end['passes']-start['passes']
    result['completed_passes']=end['completed_passes']-start['completed_passes']
    result['pass_completion']=result['completed_passes']/max(1,result['passes'])
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--start',type=int,default=0);p.add_argument('--count',type=int,default=8);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    out={'engine_commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
        'scope':'Paired controlled simulation, identical 60-minute prefix, one input per contrast; exploratory model effects, not real-world causal validation.',
        'seeds':list(range(125000+args.start,125000+args.start+args.count)),'pairs':[],'failures':[]}
    begun=time.monotonic()
    for seed in out['seeds']:
        try:
            prefix=advance(fixture(seed),60.)
            assert not prefix.state.ended
            raw=prefix.export_state();fingerprint=fingerprint_attributes(prefix);base_start=measure(prefix)
            baseline=advance(MatchEngine.from_state_dict(raw));baseline_end=measure(baseline)
            baseline_window=window(baseline_end,base_start)
            assert baseline.shot_ledger_coverage()['complete']
            for case in CASES:
                case_raw=raw;case_baseline_end=baseline_end;case_baseline_window=baseline_window;case_start=base_start
                if case=='score_state':
                    score_control=MatchEngine.from_state_dict(raw)
                    score_control.stats[0].goals=score_control.stats[1].goals=0
                    case_raw=score_control.export_state();case_start=measure(score_control)
                    case_baseline_end=measure(advance(score_control));case_baseline_window=window(case_baseline_end,case_start)
                treatment=MatchEngine.from_state_dict(case_raw)
                assert fingerprint_attributes(treatment)==fingerprint
                prescribed=intervention(treatment,case)
                start=measure(treatment)
                # Substitution's normal 18 seconds belong to its observation window.
                if case=='fresh_substitution':start={**case_start,'energy':start['energy']}
                advance(treatment)
                assert treatment.shot_ledger_coverage()['complete']
                end=measure(treatment);win=window(end,start)
                delta={k:[a-b for a,b in zip(win[k],case_baseline_window[k])] for k in ('goals','shots','xg','distance','sprint_distance','energy','control_seconds')}
                delta['pass_completion']=win['pass_completion']-case_baseline_window['pass_completion']
                out['pairs'].append({'seed':seed,'case':case,'prefix_minute':prefix.minute,'attributes_sha256':fingerprint,
                    'intervention':prescribed,'baseline_window':case_baseline_window,'treatment_window':win,'paired_delta':delta,
                    'baseline_end':case_baseline_end,'treatment_end':end})
        except Exception:out['failures'].append({'seed':seed,'traceback':traceback.format_exc()})
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(out,separators=(',',':')))
        print(f'seed={seed}; pairs={len(out["pairs"])}; failures={len(out["failures"])}; seconds={time.monotonic()-begun:.1f}',flush=True)
    if out['failures']:raise SystemExit(1)


if __name__=='__main__':main()
