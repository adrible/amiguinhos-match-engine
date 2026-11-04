import copy
import math
import unittest

from engine import Band, Lane, Zone, PendingAction, EventType, make_generic_team
from engine_experiment_v13 import MatchEngine
from spatial_shot_v13 import shot_geometry


class CoordinatePlayTests(unittest.TestCase):
    def fixture(self, seed=1117):
        return MatchEngine(make_generic_team('A',80,seed=11), make_generic_team('B',80,seed=22),seed=seed)

    def pending(self, e, **kw):
        ps=e.teams[0].on_field[-1]
        return PendingAction(0,ps.player.name,'shoot',Zone(Band.BOX,Lane.CENTER),danger=.6,pressure=.4,**kw)

    def test_xg_uses_distance_angle_and_pressure(self):
        e=self.fixture();p=self.pending(e);ps=e.teams[0].by_name(p.actor)
        def xg(x,y,pressure=.4,part='right_foot'):
            ps.x,ps.y=x,y;p.pressure=pressure;p.body_part=part
            return e._calculate_xg(p,ps,None,None)
        self.assertGreater(xg(94,34),xg(80,34))
        self.assertGreater(xg(94,34),xg(94,10))
        self.assertGreater(xg(94,34,0),xg(94,34,1))
        self.assertGreater(xg(94,34),xg(94,34,part='head'))
        for x in range(1,105):
            self.assertTrue(0 < xg(x,34) < 1)

    def test_xg_does_not_use_finishing_or_keeper_quality(self):
        e=self.fixture();p=self.pending(e);ps=e.teams[0].by_name(p.actor);ps.x,ps.y=94,34
        before=e._calculate_xg(p,ps,None,None)
        ps.player.finishing=1;ps.player.composure=1
        self.assertEqual(before,e._calculate_xg(p,ps,None,e._goalkeeper(1)))

    def test_rotation_preserves_distance_angle_and_xg(self):
        e=self.fixture();p=self.pending(e);ps=e.teams[0].by_name(p.actor);ps.x,ps.y=93,22
        a=e.shot_geometry_context(p,ps);p.team=1;ps.x,ps.y=12,46
        self.assertEqual(a,e.shot_geometry_context(p,ps))

    def test_shot_zone_and_distance_are_measured_not_requested(self):
        e=self.fixture();p=self.pending(e);ps=e.teams[0].by_name(p.actor);ps.x,ps.y=70,34
        event=e._resolve_shot(p)
        self.assertEqual(p.zone.band,Band.ATT)
        self.assertAlmostEqual(event.data['shot_geometry_context']['distance'],35)
        self.assertEqual(event.data['shot_origin_coordinates']['x'],70)
        self.assertEqual(event.data['shot_origin_coordinates']['z'],0)

    def test_ground_ball_cannot_produce_header_without_delivery(self):
        e=self.fixture();p=self.pending(e,body_part='head');ps=e.teams[0].by_name(p.actor);ps.x,ps.y=94,34
        event=e._resolve_shot(p)
        self.assertNotEqual(event.data['body_part'],'head')
        self.assertEqual(event.data['shot_origin_coordinates']['z'],0)

    def test_header_has_a_flight_source_contact_height_and_elapsed_time(self):
        e=self.fixture();p=self.pending(e,body_part='head',origin='cross');ps=e.teams[0].by_name(p.actor);ps.x,ps.y=94,34
        e._delivery={'team':0,'x':84.,'y':8.,'kind':'cross','second':e.state.second}
        second=e.state.second;event=e._resolve_shot(p)
        self.assertEqual(event.data['body_part'],'head')
        self.assertEqual(event.data['shot_origin_coordinates'],{'x':94,'y':34,'z':1.6})
        self.assertGreaterEqual(e.state.second-second,math.hypot(10,26)/18)
        self.assertEqual(event.data['delivery_origin_coordinates']['y'],8)

    def test_wrong_team_or_stale_delivery_cannot_produce_header(self):
        for team,age in ((1,0),(0,101)):
            e=self.fixture();e.state.second=200;p=self.pending(e,body_part='head',origin='cross')
            e._delivery={'team':team,'x':84.,'y':8.,'kind':'cross','second':200-age}
            self.assertNotEqual(e._resolve_shot(p).data['body_part'],'head')

    def test_movement_intent_cannot_exceed_elapsed_pace_allowance(self):
        e=self.fixture();ps=e.teams[0].on_field[-1];ps.x,ps.y=10,34
        e._movement_plan=(0,ps.player.name,Zone(Band.BOX,Lane.CENTER))
        start=(ps.x,ps.y);e._move_players(.2)
        self.assertLessEqual(math.hypot(ps.x-start[0],ps.y-start[1]),1.61)
        self.assertLess(ps.x,88.5)

    def test_delivery_and_pending_resume_exactly(self):
        e=self.fixture();p=self.pending(e,body_part='head',origin='cross');e.state.pending=p
        e._delivery={'team':0,'x':84.,'y':8.,'kind':'cross','second':e.state.second}
        restored=MatchEngine.from_state_dict(copy.deepcopy(e.export_state()))
        self.assertEqual(e.export_state(),restored.export_state())
        for _ in range(20):
            e.step();restored.step()
            self.assertEqual(e.export_state(),restored.export_state())

    def test_creator_field_preserves_cross_provenance(self):
        e=self.fixture();p=self.pending(e,body_part='head',origin='cross');e.state.pending=p
        creator=e.teams[0].on_field[-2]
        e._emit(EventType.DANGER,0,3,'danger_created',creator=creator.player.name,receiver=p.actor,kind='cross')
        self.assertEqual(e._delivery['creator'],creator.player.name)
        self.assertIsNotNone(e._xyz_flight)

    def test_external_tracking_can_supply_a_real_aerial_contact(self):
        e=self.fixture();p=self.pending(e,body_part='head');ps=e.teams[0].by_name(p.actor)
        e.set_tracking_frame([{'team':0,'player':p.actor,'x':94.,'y':34.}],
                             ball={'x':94.,'y':34.,'z':1.8},require_all=False)
        event=e._resolve_shot(p)
        self.assertEqual(event.data['body_part'],'head')
        self.assertEqual(event.data['shot_origin_coordinates']['z'],1.8)
        self.assertEqual(event.data['delivery_origin_coordinates']['source'],'external_frame')

    def test_goal_plane_dispersion_reads_measured_distance(self):
        e=self.fixture();p=self.pending(e);ps=e.teams[0].by_name(p.actor);ps.x,ps.y=75.,34.
        keeper=e._goalkeeper(1);selection=e.shot_selection_diagnostic(ps,p,keeper)
        self.assertEqual(shot_geometry(e,p,ps,keeper,selection)['shot_distance_m'],30.)

    def test_rebound_reach_weights_decay_with_distance(self):
        e=self.fixture();shooter=e.teams[0].on_field[-1]
        near,far=e.teams[0].on_field[-2:-4:-1]
        near.x,near.y=94.,34.;far.x,far.y=15.,34.;e._rebound_point=(94.,34.)
        rows={p.player.name:w for p,w in e._rebound_attacker_rows(0,shooter,Zone(Band.BOX,Lane.CENTER))}
        self.assertGreater(rows[near.player.name],rows[far.player.name]*100)

    def test_saved_delivery_rejects_invalid_geometry_and_future_time(self):
        e=self.fixture();raw=e.export_state()
        for point,second in ((float('nan'),0),(84.,1)):
            broken=copy.deepcopy(raw)
            broken['v13_coordinate_play']={'delivery':{'team':0,'x':point,'y':8.,'kind':'cross','second':second}}
            with self.assertRaises(ValueError):MatchEngine.from_state_dict(broken)

    def test_returned_frame_keeps_owned_ball_at_its_current_player(self):
        e=self.fixture();ps=e.teams[0].on_field[-1]
        from unittest.mock import patch
        from engine import Event, EventType
        from engine_experiment_v13_coordinates import MatchEngineV13Coordinates
        def lower_step():
            e._xy_ball={'x':10.,'y':10.,'z':0.,'owner':{'team':0,'player':ps.player.name}}
            ps.x,ps.y=94.,34.
            return Event(e.minute,0,EventType.INFO,0,'test',{})
        with patch.object(MatchEngineV13Coordinates,'step',side_effect=lower_step):
            event=e.step()
        self.assertEqual((e._xy_ball['x'],e._xy_ball['y']),(94.,34.))
        self.assertEqual(event.data['ball_coordinates'],e._xy_ball)


if __name__=='__main__':unittest.main()
