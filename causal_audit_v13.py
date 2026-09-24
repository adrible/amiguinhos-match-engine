"""v1.3 causal audit using ordered, unfiltered seed schedules.

Run against separate engine checkouts to compare one mechanism at a time:
    python causal_audit_v13.py /path/to/checkout benchmark 300 report.json

The observer does not alter inputs, RNG or exported engine state. Ledger bins
cover every shot; floor diagnostics cover the core resolver's attempts and
report hypothetical old/new probability mass along the observed trajectory.
These sums are not forecasts of a changed match trajectory. Neither real-world
reference rates nor target scores are read during simulation.
"""
import argparse, json, random, sys
from copy import deepcopy
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

P=argparse.ArgumentParser()
P.add_argument('--start-seed',type=int,default=None); P.add_argument('--verify-observer',action='store_true'); P.add_argument('root'); P.add_argument('population',choices=['benchmark','generic','heavy']); P.add_argument('count',type=int); P.add_argument('output'); P.add_argument('--workers',type=int,default=8)

def run_one(job):
    root,pop,seed,*verify_args=job
    if seed == 1810131239:
        raise ValueError('Reserved official seed cannot be simulated')
    verify = bool(verify_args and verify_args[0])
    sys.path.insert(0,root)
    from engine import make_generic_team, Band, clamp
    from engine_experiment_v13 import MatchEngine
    import real_match_benchmark_v13 as bm
    class AuditEngine(MatchEngine):
        def __init__(self,*a,**kw):
            self.audit_incidents=[]; self.audit_shots=[]
            super().__init__(*a,**kw)
        def _decide_card(self,team,defender,incident,zone,count):
            booked=bool(defender.yellow)
            card,p=super()._decide_card(team,defender,incident,zone,count)
            ep=p.get('effective_yellow',p['yellow']*(self._second_yellow_factor(incident) if booked else 1))
            self.audit_incidents.append(dict(incident,booked=booked,card=card,yellow=p['yellow'],effective_yellow=ep,red=p['direct_red'],zone=zone.band.value))
            return card,p
        def _calculate_xg(self,p,shooter,defender,keeper):
            xg=super()._calculate_xg(p,shooter,defender,keeper)
            pressure=clamp(p.pressure)
            block=clamp(.07+.23*pressure+(defender.effective('positioning')-70)/260-.07*p.danger,.03,.34)
            tech=.40*shooter.effective('finishing')+.25*shooter.effective('technique')+.20*shooter.effective('composure')+.15*shooter.effective('heading' if p.body_part=='head' else 'finishing')
            ot=clamp({Band.BOX:.56,Band.ATT:.31,Band.MID:.18,Band.DEF:.08}[p.zone.band]+(tech-72)/170+.12*p.danger-.20*pressure,.10,.86)
            fin=.45*shooter.effective('finishing')+.30*shooter.effective('composure')+.25*shooter.effective('technique')
            gk=.40*keeper.effective('reflexes')+.35*keeper.effective('gk_positioning')+.25*keeper.effective('one_on_one')
            reach=(1-block)*ot; raw=(xg/max(.08,reach))*(1+(fin-gk)/240)
            self.audit_shots.append(dict(xg=xg,origin=p.origin,body_part=p.body_part,reach=reach,raw=raw,floor_active=raw<.06,old_expected=reach*clamp(raw,.06,.86),no_floor_expected=reach*clamp(raw,0,.86)))
            return xg
    if pop=='benchmark':
        r=random.Random(f'v13-real-population:{seed}')
        hs=bm._weighted_pick(r,bm.STRENGTHS,bm.STRENGTH_WEIGHTS); aw=bm._weighted_pick(r,bm.STRENGTHS,bm.STRENGTH_WEIGHTS)
        ht=bm._weighted_pick(r,bm.STYLES,bm.STYLE_WEIGHTS); at=bm._weighted_pick(r,bm.STYLES,bm.STYLE_WEIGHTS)
        h=make_generic_team(f'Benchmark Home {seed}',hs,ht,seed=900000+seed*2)
        a=make_generic_team(f'Benchmark Away {seed}',aw,at,seed=900001+seed*2)
        kw={'venue_context':{'mode':bm.BENCHMARK_VENUE_MODE,'source':'real_league_benchmark'}}
    else:
        name,hs,aws=('Candidate',1001,2002) if pop=='generic' else ('Realism',71001,72002)
        h=make_generic_team(name+' A',78,'balanced',seed=hs); a=make_generic_team(name+' B',78,'balanced',seed=aws); kw={}
    e=AuditEngine(deepcopy(h),deepcopy(a),seed=seed,**kw)
    for step in range(7000):
        if e.state.ended: break
        e.step()
    else: raise RuntimeError(f'guard {seed}')
    if verify:
        control = MatchEngine(deepcopy(h), deepcopy(a), seed=seed, **kw)
        for _ in range(7000):
            if control.state.ended: break
            control.step()
        else: raise RuntimeError(f'control guard {seed}')
        if control.export_state() != e.export_state():
            raise AssertionError('Observer changed exported engine state')
        if control.rng.getstate() != e.rng.getstate():
            raise AssertionError('Observer changed RNG')
    assert e.shot_ledger_coverage()['complete']
    ledger=e.shot_ledger_diagnostic()
    assert abs(sum(s['xg'] for s in ledger)-sum(s.xg for s in e.stats))<1e-8
    assert len({s['shot_id'] for s in ledger})==len(ledger)
    counts=Counter(); groups=defaultdict(Counter)
    for r in e.audit_incidents:
        sev=r['severity']; b='<0.30' if sev<.3 else '0.30-0.50' if sev<.5 else '0.50-0.66' if sev<.66 else '0.66-0.75' if sev<.75 else '0.75-0.84' if sev<.84 else '>=0.84'
        keys=['severity:'+b,'source:'+('ordinary' if r.get('ordinary_contact') else 'other')]
        if r['booked']: keys+=['booked:'+('spa' if r.get('spa') else 'routine')]
        if r.get('dogso'): keys+=['dogso:'+str(r.get('attempt_to_play_ball'))+':'+r['zone']]
        if r.get('violent'): keys+=['violent']
        for k in keys:
            g=groups[k];g['n']+=1;g[r['card'] or 'none']+=1;g['yellow_sum']+=r['yellow'];g['effective_yellow_sum']+=r['effective_yellow'];g['expected_red']+=r['red'];g['expected_second']+=(1-r['red'])*r['effective_yellow']*r['booked']
    for r in ledger:
        x=r['xg']; b='<0.05' if x<.05 else '.05-.10' if x<.1 else '.10-.20' if x<.2 else '.20-.40' if x<.4 else '.40+'
        g=groups['xg:'+b];g['n']+=1;g['xg']+=x;g['goals']+=r['goal'];g['sot']+=r['on_target']
    for r in e.audit_shots:
        if r['xg']<.05:
            for k in ['low_xg_total','low_xg_origin:'+str(r['origin']),'low_xg_body:'+str(r['body_part'])]:
                g=groups[k];g['n']+=1;g['xg']+=r['xg'];g['floor_active']+=r['floor_active'];g['old_expected']+=r['old_expected'];g['no_floor_expected']+=r['no_floor_expected']
    for event in e.state.event_log:
        if event.type.value=='card': counts['card:'+str(event.data.get('card'))]+=1
    record=bm._engine_match_record(e)
    record['xg']=sum(s.xg for s in e.stats)
    return dict(seed=seed,record=record,groups={k:dict(v) for k,v in groups.items()},counts=dict(counts))

def main():
    args=P.parse_args(); start=args.start_seed if args.start_seed is not None else {'generic':0,'heavy':70000,'benchmark':91000}[args.population]
    assert args.count>0
    if start<=1810131239<start+args.count: raise ValueError('Reserved seed')
    jobs=[(str(Path(args.root).resolve()),args.population,s,args.verify_observer and s==start) for s in range(start,start+args.count)]
    rows=[];groups=defaultdict(Counter);counts=Counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i,row in enumerate(pool.map(run_one,jobs),1):
            rows.append({'seed':row['seed'],**row['record']});counts.update(row['counts'])
            for k,v in row['groups'].items():groups[k].update(v)
            if i%50==0: print(f'{args.population}: {i}/{args.count}',flush=True)
    result=dict(population=args.population,count=args.count,start_seed=start,rows=rows,groups={k:dict(v) for k,v in sorted(groups.items())},counts=dict(counts))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result,indent=2))
    print(args.output,flush=True)
if __name__=='__main__':main()
