"""Projectile consistency grid; this is not a real-tracking benchmark."""
import json
import math
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine import make_generic_team
from engine_experiment_v13 import MatchEngine

rng = random.Random(20261104)
checks = restores = 0
max_error = 0.
for i in range(240):
    e = MatchEngine(make_generic_team('Physics A',80,seed=1),
                    make_generic_team('Physics B',80,seed=2), seed=123)
    start = {'x':rng.uniform(5,35),'y':rng.uniform(5,63),'z':0.}
    e.set_tracking_frame([],require_all=False,ball=start)
    endx, endy = rng.uniform(45,100), rng.uniform(5,63)
    aerial = i%2==0
    endz = rng.choice([0.,.3,1.6,2.44]) if aerial else 0.
    flight = e.launch_ball(endx,endy,z=endz,speed=rng.uniform(10,35),aerial=aerial)
    T, t0 = flight['duration'], flight['start_second']
    h = T/4
    samples = [e.ball_position_at(t0+j*h) for j in range(5)]
    checks += 1
    assert all(math.isfinite(v) for p in samples for v in p.values())
    assert all(p['z']>=0 for p in samples)
    assert abs(samples[-1]['x']-endx)<1e-8 and abs(samples[-1]['y']-endy)<1e-8 and abs(samples[-1]['z']-endz)<1e-8
    acceleration = (samples[3]['z']-2*samples[2]['z']+samples[1]['z'])/(h*h)
    error = abs(acceleration-(-9.81 if aerial else 0.))
    max_error = max(max_error,error)
    assert error<1e-7
    if i%12==0:
        e._advance_clock(T*.35,e.state.possession)
        restored=MatchEngine.from_json(e.export_json())
        e._advance_clock(T*.2,e.state.possession)
        restored._advance_clock(T*.2,restored.state.possession)
        assert e.export_state()==restored.export_state()
        restores += 1
result = {'cases':checks,'gravity_or_ground_acceleration_failures':0,
          'max_acceleration_error_m_s2':max_error,'midflight_restore_cases':restores,
          'note':'Vacuum projectile mechanics and persistence only; not validation against real ball tracking.'}
Path(__file__).with_name('physics_controls.json').write_text(json.dumps(result,indent=2))
print(result)
