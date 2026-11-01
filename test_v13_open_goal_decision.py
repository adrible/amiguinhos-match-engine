from __future__ import annotations
import unittest
from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13_spatial import MatchEngineV13Spatial

class OpenGoalDecisionTests(unittest.TestCase):
    def engine(self):
        return MatchEngineV13Spatial(make_generic_team('Home',80,'balanced',seed=11),make_generic_team('Away',80,'balanced',seed=22),seed=33)
    def actor(self,e):
        return next(ps for ps in e.teams[0].on_field if ps.player.position.upper() in {'AM','CM','ST','LW','RW'})
    def test_no_exposed_keeper_means_no_open_goal_signal(self):
        e=self.engine(); a=self.actor(e)
        self.assertFalse(e._open_goal_direct_shot_profile(0,a,Zone(Band.ATT,Lane.CENTER),{'pressure':0.2,'space':0.8})['eligible'])
    def test_open_goal_is_strongly_perceived_and_shot_dominates_when_seen(self):
        e=self.engine(); a=self.actor(e); e._activate_keeper_up(1)
        p=e._open_goal_direct_shot_profile(0,a,Zone(Band.ATT,Lane.CENTER),{'pressure':0.15,'space':0.85})
        self.assertGreater(p['perception_probability'],0.75); self.assertGreater(p['attempt_probability_if_perceived'],0.80)
    def test_pressure_reduces_open_goal_response(self):
        e=self.engine(); a=self.actor(e); e._activate_keeper_up(1)
        lo=e._open_goal_direct_shot_profile(0,a,Zone(Band.MID,Lane.CENTER),{'pressure':0.05,'space':0.9})
        hi=e._open_goal_direct_shot_profile(0,a,Zone(Band.MID,Lane.CENTER),{'pressure':0.95,'space':0.2})
        self.assertGreater(lo['perception_probability'],hi['perception_probability']); self.assertGreater(lo['attempt_probability_if_perceived'],hi['attempt_probability_if_perceived'])
    def test_defensive_third_does_not_force_full_pitch_shot(self):
        e=self.engine(); a=self.actor(e); e._activate_keeper_up(1)
        self.assertFalse(e._open_goal_direct_shot_profile(0,a,Zone(Band.DEF,Lane.CENTER),{'pressure':0,'space':1})['eligible'])
    def test_marker_survives_roundtrip(self):
        e=self.engine(); a=self.actor(e); e._activate_keeper_up(1)
        e._v13_open_goal_shot={'team':0,'actor':a.player.name,'perception_probability':0.9,'attempt_probability_if_perceived':0.9}
        c=MatchEngineV13Spatial.from_json(e.export_json()); self.assertEqual(c._v13_open_goal_shot['actor'],a.player.name)
if __name__=='__main__': unittest.main()
