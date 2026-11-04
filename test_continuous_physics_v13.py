import math
import unittest
from dataclasses import asdict
from continuous_physics_v13 import (BallState,MotionState,PhysicalProfile,advance_ball,
    contact_height,flight_to_target,move_player,offside_snapshot,offside_interference,
    resolve_collision,start_jump)

class MotionTests(unittest.TestCase):
    def test_acceleration_braking_and_elite_speed_are_distinct(self):
        p=PhysicalProfile(sprint_speed=10.5);m=MotionState();x,y=5.,34.;before=0.
        for _ in range(65):
            x,y=move_player(x,y,m,p,(104.,34.),.1)
            speed=math.hypot(m.vx,m.vy)
            self.assertLessEqual(speed-before,p.acceleration*.1+1e-8);before=speed
        self.assertGreater(m.peak_speed*3.6,35.)
        self.assertLessEqual(m.peak_speed,10.5)
        prior=math.hypot(m.vx,m.vy);move_player(x,y,m,p,(x,y),.1)
        self.assertGreater(math.hypot(m.vx,m.vy),0.)
        self.assertLess(math.hypot(m.vx,m.vy),prior)

    def test_turns_take_time_and_do_not_teleport_velocity(self):
        p=PhysicalProfile();m=MotionState(vx=8.,heading=0.);x,y=50.,34.
        x,y=move_player(x,y,m,p,(20.,34.),.1)
        self.assertGreater(m.vx,0.)
        self.assertLessEqual(abs(m.heading),p.turn_rate*.1+1e-8)

    def test_fatigue_and_wet_grip_lower_the_same_sprint(self):
        peaks=[]
        for energy,grip in ((1.,1.),(.4,1.),(1.,.8)):
            p=PhysicalProfile();m=MotionState();x,y=3.,34.
            for _ in range(55):x,y=move_player(x,y,m,p,(104.,34.),.1,energy=energy,grip=grip)
            peaks.append(m.peak_speed)
        self.assertGreater(peaks[0],peaks[1]);self.assertGreater(peaks[0],peaks[2])

    def test_jump_height_depends_on_person_and_energy(self):
        maxima=[]
        for height,jump,energy in ((1.7,3.,1.),(1.95,4.,1.),(1.95,4.,.3)):
            p=PhysicalProfile(height=height,jump_speed=jump);m=MotionState();self.assertTrue(start_jump(m,p,energy));self.assertFalse(start_jump(m,p,energy))
            heights=[]
            for _ in range(120):
                move_player(50.,34.,m,p,(50.,34.),.01);heights.append(contact_height(m,p))
            maxima.append(max(heights));self.assertEqual(m.z,0.)
        self.assertGreater(maxima[1],maxima[0]);self.assertGreater(maxima[1],maxima[2])

    def test_contact_conserves_momentum_and_loses_energy(self):
        a=MotionState(vx=4.);b=MotionState(vx=-2.);pa=PhysicalProfile(mass=70.);pb=PhysicalProfile(mass=90.)
        before=70*a.vx+90*b.vx;energy=.5*70*a.vx*a.vx+.5*90*b.vx*b.vx
        aa,bb,hit=resolve_collision((50.,34.),(50.5,34.),a,b,pa,pb,.1)
        self.assertTrue(hit);self.assertAlmostEqual(70*a.vx+90*b.vx,before)
        self.assertLess(.5*70*a.vx*a.vx+.5*90*b.vx*b.vx,energy)
        self.assertGreater(bb[0]-aa[0],.5)

class BallTests(unittest.TestCase):
    def test_drag_changes_horizontal_velocity(self):
        ball=BallState(30.,34.,2.,25.,0.,3.)
        advance_ball(ball,.1)
        self.assertLess(ball.vx,25.);self.assertGreater(ball.z,2.)

    def test_bounce_dissipates_energy_and_never_goes_underground(self):
        ball=BallState(30.,34.,2.,10.,0.,0.);heights=[]
        for _ in range(150):
            advance_ball(ball,.02);heights.append(ball.z);self.assertGreaterEqual(ball.z,0.)
        self.assertGreater(ball.bounces,0);self.assertLessEqual(max(heights),2.)

    def test_grass_friction_stops_a_ground_ball(self):
        b=BallState(20.,34.,0.,2.,0.,0.)
        for _ in range(100):advance_ball(b,.1)
        self.assertEqual(b.vx,0.);self.assertEqual(b.z,0.)

    def test_drag_plan_hits_height_and_receiving_point(self):
        for z in (0.,1.,2.1):
            b,duration=flight_to_target((20.,34.,0.),(45.,42.,z),speed=20.,aerial=z>0)
            left=duration
            while left>1e-9:
                h=min(.025,left);advance_ball(b,h,rolling=0.,restitution=0.);left-=h
            self.assertAlmostEqual(b.x,45.,delta=.08);self.assertAlmostEqual(b.y,42.,delta=.08);self.assertAlmostEqual(b.z,z,delta=.08)

    def test_invalid_physical_inputs_are_rejected(self):
        for value in (-1.,float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):advance_ball(BallState(),value)
        with self.assertRaises(ValueError):PhysicalProfile(height=4.).validate()
        with self.assertRaises(ValueError):BallState(z=-1.).validate()

class OffsideTests(unittest.TestCase):
    def frame(self,runner=92.,ball=80.,defenders=(99.,90.),direction=1,restart=None):
        mirror=lambda x:x if direction==1 else 105.-x
        players=[{'team':0,'player':'runner','x':mirror(runner),'y':34.},*({'team':1,'player':str(i),'x':mirror(x),'y':34.} for i,x in enumerate(defenders))]
        return offside_snapshot(0,{'x':mirror(ball),'y':34.},players,direction=direction,second=12.,restart=restart)

    def test_second_last_opponent_includes_keeper(self):
        self.assertEqual(self.frame()['flagged'],['runner'])
        self.assertEqual(self.frame(defenders=(89.,95.))['second_last_defender_x'],89.)

    def test_level_ball_level_defender_and_own_half_are_onside(self):
        for frame in (self.frame(runner=90.),self.frame(runner=92.,ball=92.),self.frame(runner=50.,defenders=(40.,30.))):self.assertEqual(frame['flagged'],[])

    def test_both_attack_directions_give_same_judgement(self):
        self.assertEqual(self.frame(direction=1)['flagged'],self.frame(direction=-1)['flagged'])

    def test_corner_throw_goal_kick_exempt_only_direct_receipt(self):
        for kind in ('corner','throw_in','goal_kick'):self.assertEqual(self.frame(restart=kind)['flagged'],[])
        self.assertEqual(self.frame(restart='free_kick')['flagged'],['runner'])

    def test_position_alone_is_not_offence(self):
        f=self.frame();self.assertFalse(offside_interference(f,'runner'));self.assertTrue(offside_interference(f,'runner',participates=True))

    def test_deflection_and_save_do_not_reset_but_deliberate_play_does(self):
        f=self.frame();self.assertTrue(offside_interference(f,'runner',participates=True,deliberate_save=True))
        self.assertFalse(offside_interference(f,'runner',participates=True,opponent_deliberate_play=True))
        self.assertTrue(offside_interference(f,'runner',participates=True,opponent_deliberate_play=True,deliberate_save=True))

    def test_saved_release_frame_is_immutable_at_later_positions(self):
        f=self.frame();players=f['players'];players[0]['x']=70.
        self.assertTrue(offside_interference(f,'runner',participates=True))

if __name__=='__main__':unittest.main()
