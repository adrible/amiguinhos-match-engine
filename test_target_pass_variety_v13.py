import unittest
from engine import Band, Lane, Zone, PendingAction, make_generic_team
from engine_experiment_v13 import MatchEngine
from spatial_shot_v13 import shot_geometry


class TargetPassVarietyTests(unittest.TestCase):
    def setUp(self):
        self.e = MatchEngine(make_generic_team('A',80,seed=1),make_generic_team('B',80,seed=2),seed=9)
        self.a = next(p for p in self.e.teams[0].on_field if p.player.position == 'ST')
        self.p = PendingAction(0,self.a.player.name,'shoot',Zone(Band.BOX,Lane.CENTER),danger=.6,pressure=.3)

    def test_both_corners_and_high_middle_are_intended_not_only_execution_errors(self):
        found = set()
        for i in range(1200):
            self.e.state.second = i
            g = shot_geometry(self.e,self.p,self.a,self.e._goalkeeper(1),
                              {'shot_type':'placed','execution_quality':.7})
            found.add(g['intended_shot_region'])
            pos = g['intended_goal_position']
            if g['intended_shot_region'].endswith('_left'):
                self.assertLess(pos['x'],0)
            elif g['intended_shot_region'].endswith('_right'):
                self.assertGreater(pos['x'],0)
        self.assertTrue({'high_center','high_left','high_right','low_left','low_right',
                         'mid_left','mid_right','mid_center'} <= found)

    def test_first_touch_tricks_require_matching_first_time_reception(self):
        self.a.player.creativity = 95
        ctx = {'pressure':.55,'support':.8}
        def styles():
            result = set()
            for i in range(1500):
                self.e.state.second = i
                d = self.e.creative_pass_diagnostic(self.a,self.p.zone,'through_ball',ctx)
                if d['attempt']: result.add(d['technique'])
            return result
        self.assertFalse({'first_time','backheel_return'} & styles())
        self.e._v13_reception_plan = {'actor':self.a.player.name,'zone':self.p.zone,'mode':'controlled'}
        self.assertFalse({'first_time','backheel_return'} & styles())
        self.e._v13_reception_plan['mode'] = 'first_time'
        self.assertTrue({'first_time','backheel_return'} <= styles())
        self.e._v13_reception_plan['actor'] = 'another player'
        self.assertFalse({'first_time','backheel_return'} & styles())

    def test_rabona_is_rarer_than_outside_foot_and_requires_awkward_side(self):
        self.a.player.preferred_foot='R'
        self.a.player.creativity=95
        counts={'rabona':0,'outside_foot':0}
        for i in range(2000):
            self.e.state.second=i
            for lane in [Lane.LEFT,Lane.RIGHT]:
                d=self.e.creative_pass_diagnostic(self.a,Zone(Band.ATT,lane),'cross',{'pressure':.5,'support':.7})
                if d['attempt'] and d['technique'] in counts:
                    if lane==Lane.RIGHT:self.fail('Awkward-foot technique on natural side')
                    counts[d['technique']]+=1
        self.assertGreater(counts['rabona'],0)
        self.assertGreater(counts['outside_foot'],counts['rabona']*3)
