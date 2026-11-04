"""Aggregate fixed paired cohorts, preserving failures and match-level sampling."""
import argparse,gzip,json,math,random,statistics as st,sys
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from real_match_benchmark_v13 import load_real_collection,SOURCE_FILE,summarise_matches,compare
p=argparse.ArgumentParser();p.add_argument('--start-seed',type=int,default=114000);p.add_argument('--count',type=int,default=300);p.add_argument('--chunks',type=int,default=3);p.add_argument('--raw',type=Path,default=Path('/tmp'));p.add_argument('--output',type=Path,default=Path(__file__).parent);a=p.parse_args()
realrows,datasets=load_real_collection(SOURCE_FILE,ROOT/'.cache/real_match_benchmark');real=summarise_matches(realrows)
def read(path):
 if path.exists():return json.loads(path.read_bytes())
 return json.loads(gzip.decompress(path.with_suffix('.json.gz').read_bytes()))
def dist(values):
 if not values:return {'n':0}
 v=sorted(values);return {'n':len(v),'mean':st.mean(v),'median':st.median(v),'p95':v[int(.95*(len(v)-1))],'max':max(v)}
def shot_summary(ss):
 n=len(ss)
 if not n:return {'n':0}
 return {'n':n,'distance':dist([s['distance'] for s in ss]),'inside_box':sum(s['inside_box'] for s in ss)/n,
         'sot':sum(s['on_target'] for s in ss)/n,'goals':sum(s['goal'] for s in ss)/n,'blocked':sum(s['blocked'] for s in ss)/n,
         'mean_xg':st.mean(s['xg'] for s in ss),'body_share':dict(Counter(s['body_part'] for s in ss)),
         'distance_bins':{f'{lo}-{hi}':sum(lo<=s['distance']<hi for s in ss)/n for lo,hi in [(0,6),(6,12),(12,18),(18,24),(24,35),(35,120)]},
         'header_height':dist([s['z'] for s in ss if s['body_part']=='head']),
         'angle_degrees':dist([abs(math.atan2(3.66-(34.-s.get('team_y',s['y'])),max(.1,105.-s['team_x']))-math.atan2(-3.66-(34.-s.get('team_y',s['y'])),max(.1,105.-s['team_x'])))*180/math.pi for s in ss])}
def group_by(ss,key):return {k:shot_summary([s for s in ss if s[key]==k]) for k in sorted({s[key] for s in ss})}
allrows={};allshots={};out={'validation':{'start_seed':a.start_seed,'count':a.count,'chunks':a.chunks},'real':real,'real_datasets':datasets,'cohorts':{}}
for label in ('before','after'):
 chunks=[read(a.raw/f'realism-{label}-{i}.json') for i in range(a.chunks)]
 rows=sorted([m for c in chunks for m in c['matches']],key=lambda x:x['seed'])
 failures=[f for c in chunks for f in c['failures']]
 if failures or [r['seed'] for r in rows]!=list(range(a.start_seed,a.start_seed+a.count)):raise AssertionError((label,failures,'incomplete cohort'))
 if not chunks[0]['parity_checked']:raise AssertionError('Observer parity not checked')
 ss=[s for c in chunks for s in c['shots']];counts=Counter();distances=defaultdict(list)
 for c in chunks:
  for k,v in c['spatial_counts'].items():counts[k]=max(counts[k],v) if k.startswith('max_') else counts[k]+v
  for k,v in c['spatial_distances'].items():distances[k].extend(v)
 summary=summarise_matches([m['stats'] for m in rows]);metrics=summary['metrics']
 # The synthetic cohorts are paired, but reference events are a different population.
 xgbins={}
 for lo,hi in [(0,.05),(.05,.1),(.1,.2),(.2,.4),(.4,1.01)]:
  cell=[s for s in ss if lo<=s['xg']<hi];xgbins[f'{lo}-{hi}']=shot_summary(cell)
 pressure={}
 for lo,hi in [(0,.33),(.33,.66),(.66,1.01)]:pressure[f'{lo}-{hi}']=shot_summary([s for s in ss if lo<=s['pressure']<hi])
 style=defaultdict(list);strength=defaultdict(list)
 for m in rows:
  style[m['population']['home_style']+' / '+m['population']['away_style']].append(m['stats'])
  gap=m['population']['home_strength']-m['population']['away_strength'];strength['home_stronger' if gap>8 else 'away_stronger' if gap< -8 else 'similar'].append(m['stats'])
 core={'commit':chunks[0]['engine_commit'],'runtime_parameters':chunks[0].get('runtime_parameters'),'n':len(rows),'failures':failures,'summary':summary,'comparison':compare(real,summary,datasets),
       'counts':dict(counts),'distances':{k:dist(v) for k,v in distances.items()},'shots':shot_summary(ss),
       'body':group_by(ss,'body_part'),'origin':group_by(ss,'origin'),'xg_bins':xgbins,'pressure_bins':pressure,
       'styles':{k:summarise_matches(v) for k,v in style.items()},'strength':{k:summarise_matches(v) for k,v in strength.items()},
       'extras':{k:st.mean(m['extra'].get(k,0) for m in rows) for k in sorted({k for m in rows for k in m['extra']})}}
 out['cohorts'][label]=core;allrows[label]=rows;allshots[label]=ss
# Match-cluster normal intervals for paired changes; shots within matches are dependent.
def match_values(m):
 s=m['stats'];h,aw=s['home_goals'],s['away_goals'];return {'goals':h+aw,'shots':s['home_shots']+s['away_shots'],'sot':s['home_sot']+s['away_sot'],
 'home_goals':h,'away_goals':aw,'home_win':int(h>aw),'draw':int(h==aw),'btts':int(h>0 and aw>0),'over25':int(h+aw>2)}
paired={}
for key in match_values(allrows['before'][0]):
 v=[match_values(n)[key]-match_values(o)[key] for o,n in zip(allrows['before'],allrows['after'])];mean=st.mean(v);margin=1.96*st.stdev(v)/math.sqrt(len(v))
 paired[key]={'delta':mean,'low95':mean-margin,'high95':mean+margin}
out['paired']=paired
rng=random.Random(202611041);boot=[]
for _ in range(1000):
 indices=rng.choices(range(a.count),k=a.count);scores=[]
 for label in ('before','after'):
  ss=summarise_matches([allrows[label][i]['stats'] for i in indices]);scores.append(compare(real,ss,datasets)['realism_index'])
 boot.append(scores[1]-scores[0])
boot.sort();out['index_delta_bootstrap']={'resamples':1000,'low95':boot[25],'high95':boot[974],'mean':st.mean(boot)}
reference=json.loads((ROOT/'data/spatial_shot_reference_v13.json').read_text());out['shot_reference']=reference
# Retain a data-level view of assists without asserting equality of provider labels.
rawref=json.loads((ROOT/'.cache/statsbomb/shot_rows.json').read_text())
offset=(new_parameters:=out['cohorts']['after'].get('runtime_parameters') or {}).get('CONTEXT_LOGIT_OFFSET') or 0.
held=[r for r in rawref if r['match_id'] in reference['validation_match_ids'] and not r['penalty']]
coef=reference['coefficients']
def adjusted(r):
 features={'intercept':1.,'distance':r['distance'],'angle':r['angle'],'header':r['header'],'pressure':r['pressure'],'cross':r['cross'],'cutback':r['cutback'],'freekick':r['freekick']}
 z=offset+sum(coef[k]*features[k] for k in coef)
 return 1./(1.+math.exp(-z))
out['engine_reference_diagnostic']={'context_logit_offset':offset,'mean_engine_xg_on_16_real_matches':st.mean(adjusted(r) for r in held),'mae_to_statsbomb':st.mean(abs(adjusted(r)-r['xg']) for r in held)}
out['reference_assists']={k:{'n':len(v),'distance':st.mean(s['distance'] for s in v),'xg':st.mean(s['xg'] for s in v)} for k in ('cross','cutback','freekick') if (v:=[s for s in rawref if s[k] and not s['penalty']])}
from scipy.stats import ks_2samp,wasserstein_distance
refd=[s['distance'] for s in rawref if not s['penalty']]
out['distance_effect_sizes']={k:{'ks_statistic':float(ks_2samp(refd,[s['distance'] for s in ss]).statistic),'wasserstein_metres':float(wasserstein_distance(refd,[s['distance'] for s in ss]))} for k,ss in allshots.items()}
a.output.mkdir(parents=True,exist_ok=True);(a.output/'summary.json').write_text(json.dumps(out,indent=2))
# Reproducible shot maps. Each cell is a share of all non-penalty shots.
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,Arc
import numpy as np
fig,axes=plt.subplots(1,3,figsize=(14,4.9),layout='constrained');fig.patch.set_facecolor('#f8fafc')
sets=[('Anterior',[(s['team_x'],s.get('team_y',s['y'])) for s in allshots['before']]),('Calibrado',[(s['team_x'],s.get('team_y',s['y'])) for s in allshots['after']]),('StatsBomb · Copa 2022',[(s['x'],s['y']) for s in rawref if not s['penalty']])]
for ax,(title,points) in zip(axes,sets):
 xy=np.array(points);hist,xx,yy=np.histogram2d(xy[:,0],xy[:,1],bins=(21,14),range=((0,105),(0,68)))
 im=ax.pcolormesh(xx,yy,100*hist.T/len(points),cmap='YlOrRd',vmin=0,vmax=10,rasterized=False)
 ax.add_patch(Rectangle((0,0),105,68,fill=False,color='#334155',lw=1.2));ax.add_patch(Rectangle((88.5,13.84),16.5,40.32,fill=False,color='#334155'))
 ax.add_patch(Rectangle((99.5,24.84),5.5,18.32,fill=False,color='#334155'));ax.plot([52.5,52.5],[0,68],color='#64748b',lw=.7)
 ax.plot([105,105],[30.34,37.66],color='#0f172a',lw=4);ax.set(xlim=(0,106),ylim=(0,68),title=f'{title}\n{len(points):,} chutes',xlabel='x no sentido do ataque (m)');ax.set_aspect('equal');ax.set_yticks([0,34,68]);ax.spines[['top','right','left','bottom']].set_visible(False)
fig.colorbar(im,ax=axes,shrink=.65,label='% dos chutes por célula')
fig.suptitle('Origem das finalizações · sem pênaltis',fontsize=17,fontweight='bold')
fig.text(.01,.015,'Fonte real: StatsBomb Open Data. Coordenadas normalizadas para 105 × 68 m; Copa e ligas têm populações diferentes.',fontsize=9,color='#475569')
fig.savefig(a.output/'shot_origins.svg');fig.savefig(a.output/'shot_origins.png',dpi=160)
print(json.dumps({k:{'index':v['comparison']['realism_index'],**v['summary']['metrics']} for k,v in out['cohorts'].items()},indent=2));print('paired',paired);print('index delta bootstrap',out['index_delta_bootstrap'])
