"""Chronological fit to provider xG; final 76 league fixtures kept out of fit."""
import gzip,json,math
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
ROOT=Path(__file__).resolve().parents[2];raw=json.loads(gzip.decompress((ROOT/'.cache/statsbomb/epl_2015_16_compact.json.gz').read_bytes()))
features=['intercept','distance','angle','header','pressure','cross','through_ball','rebound','keeper_depth','keeper_lateral','nearest_defender','keeper_missing']
train=[s for s in raw['shots'] if not s['penalty'] and s['match_id'] in raw['split']['train_ids']]
valid=[s for s in raw['shots'] if not s['penalty'] and s['match_id'] in raw['split']['validation_ids']]
imputation={'keeper_depth':float(np.median([s['keeper_depth'] for s in train if s['keeper_depth'] is not None])), 'keeper_lateral':float(np.median([s['keeper_lateral'] for s in train if s['keeper_lateral'] is not None])), 'nearest_defender':float(np.median([s['nearest_defender'] for s in train if s['nearest_defender'] is not None]))}
def vector(s):return [1.,s['distance'],s['angle'],float(s['header']),float(s['pressure']),float(s['cross']),float(s['through_ball']),float(s['source']=='rebound'),s['keeper_depth'] if s['keeper_depth'] is not None else imputation['keeper_depth'],s['keeper_lateral'] if s['keeper_lateral'] is not None else imputation['keeper_lateral'],s['nearest_defender'] if s['nearest_defender'] is not None else imputation['nearest_defender'],float(s['keeper'] is None)]
X=np.array([vector(s) for s in train]);y=np.array([s['xg'] for s in train])
bounds=[(-12,4),(-.5,0),(0,6),(-4,0),(-4,0),(-3,1),(-2,2),(-2,2),(-.1,.3),(-.5,.5),(0,.4),(-2,2)]
def loss(beta):
 z=X@beta;pen=.0001*np.sum(beta[3:]**2)
 grad=X.T@(expit(z)-y)/len(y);grad[3:]+=.0002*beta[3:]
 return float(np.mean(np.logaddexp(0,z)-y*z)+pen),grad
fit=minimize(loss,[-2,-.1,1.5,-1,-.3,0,0,0,.05,0,.02,0],jac=True,bounds=bounds,method='L-BFGS-B',options={'maxiter':5000,'ftol':1e-13,'gtol':1e-8})
if not fit.success:raise RuntimeError(fit.message)
pred=lambda rows:expit(np.array([vector(s) for s in rows])@fit.x)
def scores(rows):
 p=pred(rows);yy=np.array([s['xg'] for s in rows]);return {'n':len(rows),'mae_to_provider':float(np.mean(abs(p-yy))),'provider_mean_xg':float(yy.mean()),'predicted_mean_xg':float(p.mean()),'actual_goals_per_shot':sum(s['goal'] for s in rows)/len(rows),'brier_to_goals':float(np.mean((p-np.array([s['goal'] for s in rows]))**2))}
result={'schema':1,'source':raw['source'],'source_url':raw['source_url'],'features':features,'coefficients':dict(zip(features,map(float,fit.x))),'imputation':imputation,'fit':'regularized soft-label binomial cross entropy to StatsBomb xG; physiological skill excluded','split':raw['split'],'train':scores(train),'validation':scores(valid),'all_league':scores(train+valid),'validation_by_source':{k:scores([s for s in valid if s['source']==k]) for k in sorted({s['source'] for s in valid})},'validation_pressure':{str(p):scores([s for s in valid if s['pressure']==p]) for p in (False,True)},'note':'Independent approximation, not the StatsBomb proprietary model. Freeze frames may omit players; missing measurements are explicitly imputed and counted.'}
(ROOT/'data/continuous_shot_model_v13.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:result[k] for k in ('train','validation','validation_by_source')},indent=2))
