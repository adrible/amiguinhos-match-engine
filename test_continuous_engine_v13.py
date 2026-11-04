import copy,json,math,unittest
from engine import Band,EventType,Lane,MatchConfig,PendingAction,Zone,make_generic_team
from engine_experiment_v13_continuous import MatchEngineV13Continuous as Continuous
from engine_experiment_v13 import get_engine_class,MatchEngine
from runner_v13 import MatchSessionV13


def fixture(seed=121001):
    return Continuous(make_generic_team('A',80,seed=1),make_generic_team('B',80,seed=2),seed=seed,
        environment={'weather':'clear','pitch':'normal','wind':.2,'temperature_c':22.})

def isolated_pass(e,x=30.,end=42.,aerial=False):
    team=0;actor=e.teams[team].on_field[-1];target=e.teams[team].on_field[-2]
    rows=[]
    for ti,rt in enumerate(e.teams):
        for i,ps in enumerate(rt.on_field):
            xx,yy=(4.+i*3.,5.) if ti==0 else (95.-i*2.,63.)
            if ps is actor:xx,yy=x,34.
            if ps is target:xx,yy=end,34.
            rows.append({'team':ti,'player':ps.player.name,'x':xx,'y':yy,'vx':0.,'vy':0.})
    e.set_tracking_frame(rows,ball={'x':x,'y':34.,'z':0.})
    e._control(team,actor,source='test');e._cs_auto_targets=None
    return actor,target

class ContinuousStateTests(unittest.TestCase):
    def test_opt_in_mode_has_real_runner_and_preserves_default(self):
        self.assertIs(get_engine_class(),MatchEngine);self.assertIs(get_engine_class('continuous'),Continuous)
        session=MatchSessionV13.from_fixture(seed=121000,engine_mode='continuous')
        self.assertIsInstance(session.engine,Continuous);self.assertTrue(session.pristine)
        self.assertEqual(session.snapshot()['engine_mode'],'continuous')
        with self.assertRaises(ValueError):get_engine_class('invalid')

    def test_initial_kickoff_is_an_actual_recorded_pass(self):
        e=fixture();e.step();self.assertEqual(len(e._cs_passes),1)
        self.assertEqual(len([r for r in e._cs_events if r['kind']=='pass_release']),1)

    def test_fixed_tick_is_invariant_under_observation_partition(self):
        e=fixture();other=Continuous.from_json(e.export_json())
        e.advance_physics(2.)
        for _ in range(20):other.advance_physics(.1)
        self.assertEqual(e.export_state(),other.export_state())

    def test_subtick_residual_and_velocity_survive_save_load(self):
        e=fixture();e.advance_physics(.037);r=Continuous.from_json(e.export_json())
        e.advance_physics(2.163);r.advance_physics(2.163)
        self.assertEqual(e.export_state(),r.export_state())

    def test_saved_session_restores_the_same_engine_mode(self):
        e=fixture();e.step();s=MatchSessionV13(e);r=MatchSessionV13.from_json(s.export_json())
        self.assertIsInstance(r.engine,Continuous);self.assertEqual(e.export_state(),r.engine.export_state())

    def test_pass_can_be_saved_midflight_and_resumed_exactly(self):
        e=fixture();a,b=isolated_pass(e,end=55.)
        e.release_pass(0,a.player.name,b.player.name);e.advance_physics(.3)
        self.assertIsNotNone(e._cs_transport)
        r=Continuous.from_json(e.export_json());self.assertEqual(e.export_state(),r.export_state())
        for _ in range(15):e.advance_physics(.2);r.advance_physics(.2)
        self.assertEqual(e.export_state(),r.export_state())

    def test_physical_profile_and_explicit_velocity_are_atomic(self):
        e=fixture();ps=e.teams[0].on_field[-1];before=e.export_state()
        with self.assertRaises(ValueError):e.set_player_physical_profile(0,ps.player.name,height=5.)
        self.assertEqual(before,e.export_state())
        with self.assertRaises(ValueError):e.set_tracking_frame([{'team':0,'player':ps.player.name,'x':20.,'y':34.,'vx':float('nan'),'vy':0.}],require_all=False)
        self.assertEqual(before,e.export_state())
        e.set_player_physical_profile(0,ps.player.name,height=1.97,mass=90.)
        e.set_tracking_frame([{'team':0,'player':ps.player.name,'x':20.,'y':34.,'vx':3.,'vy':4.}],require_all=False)
        row=next(p for p in e.pitch_snapshot()['players'] if p['team']==0 and p['player']==ps.player.name)
        self.assertEqual(row['speed_mps'],5.);self.assertEqual(row['physical_profile_source'],'explicit')

    def test_external_ball_velocity_is_read_and_evolves(self):
        e=fixture();e.set_tracking_frame([],ball={'x':50.,'y':34.,'z':2.,'vx':20.,'vy':0.,'vz':2.},require_all=False)
        e.advance_physics(.2);self.assertGreater(e._xy_ball['x'],50.);self.assertLess(e._cs_ball.vx,20.)

    def test_invalid_restored_clocks_and_physical_values_are_rejected(self):
        e=fixture();raw=e.export_state()
        bad=copy.deepcopy(raw);bad['v13_continuous']['remainder']=.2
        with self.assertRaises(ValueError):Continuous.from_state_dict(bad)
        bad=copy.deepcopy(raw);key=next(iter(bad['v13_continuous']['motion']));bad['v13_continuous']['motion'][key]['vx']=float('nan')
        with self.assertRaises(ValueError):Continuous.from_state_dict(bad)

class PassAndContactTests(unittest.TestCase):
    def test_every_release_has_one_terminal_outcome(self):
        e=fixture();a,b=isolated_pass(e);e.release_pass(0,a.player.name,b.player.name)
        for _ in range(30):
            e.advance_physics(.1)
            if e._cs_transport is None:break
        row=e._cs_passes[-1];self.assertNotEqual(row['status'],'in_flight')
        events=[r for r in e._cs_events if r.get('pass_id')==row['id'] and r['kind'].startswith('pass_')]
        self.assertEqual(len([r for r in events if r['kind']=='pass_release']),1)
        self.assertEqual(len([r for r in events if r['kind']!='pass_release']),1)

    def test_observation_does_not_consume_rng_or_change_state(self):
        e=fixture();e.step();before=e.export_state()
        frame=e.pitch_snapshot();diag=e.tracking_diagnostic();events=e.tracking_events()
        frame['players'][0]['vx']=99.;diag['totals']['collisions']=999;events[0]['kind']='changed'
        self.assertEqual(before,e.export_state())

    def test_replacing_an_observed_flight_closes_its_ledger(self):
        e=fixture();a,b=isolated_pass(e,end=55.);e.release_pass(0,a.player.name,b.player.name)
        e.set_tracking_frame([],ball={'x':50.,'y':30.,'z':0.},require_all=False)
        self.assertEqual(e._cs_passes[-1]['status'],'cancelled');self.assertIsNone(e._cs_transport)

    def test_no_remote_receiver_can_fire_an_assisted_shot(self):
        e=fixture();actor=e.teams[0].on_field[-1];e._xy_ball['owner']=None
        before=sum(s.shots for s in e.stats)
        e._resolve_shot(PendingAction(0,actor.player.name,'shoot',Zone(Band.BOX,Lane.CENTER),.8,.1,origin='through_ball'))
        self.assertEqual(sum(s.shots for s in e.stats),before)
        self.assertTrue(any(r['kind']=='shot_not_released' for r in e._cs_events))

    def test_shot_utility_is_not_a_distance_quota(self):
        e=fixture();a,b=isolated_pass(e,x=50.,end=60.)
        p=PendingAction(0,a.player.name,'shoot',Zone(Band.MID,Lane.CENTER),.5,.2)
        keeper=e._goalkeeper(1);keeper.x,keeper.y=104.,34.;normal=e._calculate_xg(p,a,None,keeper)
        keeper.x,keeper.y=60.,55.;exposed=e._calculate_xg(p,a,None,keeper)
        self.assertGreater(exposed,normal)
        self.assertGreater(e.action_values(0,a)['shot'],0.)

    def test_synthetic_heights_and_jumps_differ_per_player(self):
        e=fixture();a,b=e.teams[0].on_field[-2:]
        e.set_player_physical_profile(0,a.player.name,height=1.7,jump_speed=2.8)
        e.set_player_physical_profile(0,b.player.name,height=1.95,jump_speed=3.8)
        self.assertTrue(e.jump_player(0,a.player.name));self.assertTrue(e.jump_player(0,b.player.name))
        e.advance_physics(.3)
        self.assertNotEqual(e._cs_motion[e._key(0,a.player.name)].z,e._cs_motion[e._key(0,b.player.name)].z)

    def test_opponent_goal_kick_exclusion_is_geometric(self):
        e=fixture();op=e.teams[1].on_field[-1];op.x,op.y=7.,34.
        e._restart_exclusion(0,'goal_kick',(5.5,34.));self.assertGreaterEqual(op.x,16.5)

    def test_same_team_possession_continues_through_a_pass(self):
        e=fixture();a,b=isolated_pass(e);start=copy.deepcopy(e._cs_possession)
        e.release_pass(0,a.player.name,b.player.name)
        self.assertEqual(e._cs_possession,start)

    def test_substitution_has_fresh_velocity_and_fresh_energy(self):
        e=fixture();team=0;out=e.teams[team].on_field[-1];incoming=e.teams[team].bench[0]
        e._cs_motion[e._key(team,out.player.name)].vx=8.;out.energy=.4
        e.substitute(team,out.player.name,incoming.name);fresh=e.teams[team].by_name(incoming.name)
        self.assertEqual(fresh.energy,1.);self.assertLessEqual(e._cs_motion[e._key(team,incoming.name)].peak_speed,10.5)
        self.assertNotEqual(e._cs_motion[e._key(team,incoming.name)].distance,e._cs_motion[e._key(team,out.player.name)].distance)

class EngineOffsideTests(unittest.TestCase):
    def test_hand_point_cannot_create_offside(self):
        e=fixture();actor=e.teams[0].on_field[-1];a,b=isolated_pass(e,x=50.,end=60.)
        e.teams[1].on_field[0].x=100.;e.teams[1].on_field[1].x=90.
        for p in e.teams[1].on_field[2:]:p.x=80.
        actor.x=89.
        frame=e.freeze_offside(0,body_points=[{'team':0,'player':actor.player.name,'part':'foot','x':89.},{'team':0,'player':actor.player.name,'part':'hand','x':100.}])
        self.assertNotIn(actor.player.name,frame['flagged'])

    def test_deliberate_save_preserves_frame_deliberate_play_resets(self):
        e=fixture();e.freeze_offside(0);e.note_deliberate_opponent_play(1,save=True)
        self.assertIsNotNone(e._cs_offside);e.note_deliberate_opponent_play(1);self.assertIsNone(e._cs_offside)

    def test_four_periods_and_manual_extra_time_change_ends(self):
        e=fixture();e.state.period_markers=[45,90,105,120]
        directions=[]
        for i in range(4):e.state.period_index=i;directions.append(e.attack_direction(0))
        self.assertEqual(directions,[1,-1,1,-1])

class ShotContactOrderingTests(unittest.TestCase):
    def test_earlier_body_block_precedes_goal_crossing_and_roster_order(self):
        from continuous_physics_v13 import BallState
        e=fixture();a,b=e.teams[1].on_field[-2:]
        a.x,a.y=104.,34.;b.x,b.y=103.,34.
        e._cs_ball=BallState(x=106.,y=34.,z=1.,vx=30.)
        e._cs_shot_live={'team':0,'on_frame':True,'start_second':0.,'reaction':0.,'result':None}
        e._shot_contact((102.,34.,1.),[(1,p,e._key(1,p.player.name)) for p in (a,b)])
        self.assertEqual(e._cs_shot_live['result'],'block')
        self.assertEqual(e._cs_shot_live['blocker'],b.player.name)
        self.assertLess(e._cs_ball.x,103.)
        self.assertNotIn('crossing',e._cs_shot_live)

    def test_nearest_defender_feature_excludes_keeper_as_in_training_data(self):
        e=fixture();shooter=e.teams[0].on_field[-1];shooter.x,shooter.y=95.,34.
        keeper=e._goalkeeper(1);keeper.x,keeper.y=95.1,34.
        for p in e.teams[1].on_field:
            if p is not keeper:p.x,p.y=90.,34.
        self.assertAlmostEqual(e._shot_frame(0,shooter)['nearest_defender'],5.)

    def test_ball_above_individual_body_is_not_blocked(self):
        from continuous_physics_v13 import BallState
        e=fixture();p=e.teams[1].on_field[-1];p.x,p.y=103.,34.
        e._cs_ball=BallState(x=104.,y=34.,z=3.,vx=30.)
        e._cs_shot_live={'team':0,'on_frame':False,'start_second':0.,'reaction':0.,'result':None}
        e._shot_contact((102.,34.,3.),[(1,p,e._key(1,p.player.name))])
        self.assertIsNone(e._cs_shot_live['result'])

if __name__=='__main__':unittest.main()
