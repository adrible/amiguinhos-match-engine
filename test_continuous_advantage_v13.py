import copy
import unittest
from unittest.mock import patch

from engine import Band, Lane, PendingAction, Zone, make_generic_team
from engine_experiment_v13_continuous import MatchEngineV13Continuous


class ContinuousFoulAdvantageTests(unittest.TestCase):
    def fixture(self):
        e = MatchEngineV13Continuous(make_generic_team('A', 80, seed=1),
                                     make_generic_team('B', 80, seed=2), seed=127801)
        attacker = e.teams[0].on_field[-1]
        defender = e.teams[1].on_field[-1]
        attacker.x, attacker.y = e._to_world(0, 60., 34.)
        e._control(0, attacker, source='test')
        e.state.pending = PendingAction(0, attacker.player.name, 'shoot',
                                        Zone(Band.MID, Lane.CENTER), .2, .1)
        e._cs_foul_contact = {'team': 1, 'defender': defender.player.name,
                              'attacker': attacker.player.name, 'x': attacker.x,
                              'y': attacker.y, 'second': e._cs_time}
        return e

    def resolve(self, e, advantage):
        with patch.object(e, '_advantage_probability', return_value=float(advantage)), \
             patch.object(e, '_decide_card', return_value=(None, {'yellow': 0., 'direct_red': 0.})), \
             patch.object(e, '_injury_outcome', return_value=None):
            return e._handle_physical_foul()

    def test_advantage_preserves_control_possession_and_pending_action(self):
        e = self.fixture()
        ball, possession, pending = copy.deepcopy((e._xy_ball, e._cs_possession, e.state.pending))
        event = self.resolve(e, True)
        self.assertTrue(event.data['advantage'])
        self.assertEqual(e._xy_ball, ball)
        self.assertEqual(e._cs_possession, possession)
        self.assertEqual(e.state.pending, pending)
        self.assertIsNone(e._cs_restart_point)

    def test_stopped_foul_closes_possession_and_sets_restart(self):
        e = self.fixture()
        point = (e._cs_foul_contact['x'], e._cs_foul_contact['y'])
        event = self.resolve(e, False)
        self.assertFalse(event.data['advantage'])
        self.assertIsNone(e._xy_ball['owner'])
        self.assertIsNone(e._cs_possession)
        self.assertIsNone(e.state.pending)
        self.assertEqual(e._cs_restart_point, point)
        self.assertEqual(e.state.restart, 'free_kick')


if __name__ == '__main__':
    unittest.main()
