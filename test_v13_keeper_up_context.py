from __future__ import annotations
import unittest
from engine import Band, Lane, Zone, PendingAction, make_generic_team
from engine_experiment_v13_spatial import MatchEngineV13Spatial

class KeeperUpContextTests(unittest.TestCase):
    def engine(self):
        return MatchEngineV13Spatial(
            make_generic_team('Home', 78, 'balanced', seed=11),
            make_generic_team('Away', 78, 'balanced', seed=22),
            seed=33,
        )

    def set_score(self, e, home, away):
        e.stats[0].goals = home
        e.stats[1].goals = away

    def test_ten_minutes_losing_is_still_normal(self):
        e = self.engine(); self.set_score(e, 0, 1); e.state.second = 10 * 60
        self.assertEqual(e._keeper_attack_mode(0, Zone(Band.BOX, Lane.CENTER)), 'normal')
        gk = e._goalkeeper(0)
        self.assertFalse(e._contextual_attacking_receiver_eligible(0, Zone(Band.BOX, Lane.CENTER), gk))

    def test_94th_minute_one_goal_down_attacking_corner_enables_keeper_up(self):
        e = self.engine(); self.set_score(e, 0, 1); e.state.second = 94 * 60
        z = Zone(Band.BOX, Lane.CENTER)
        e.state.restart = 'corner'; e.state.restart_team = 0; e.state.restart_zone = z
        self.assertEqual(e._keeper_attack_mode(0, z), 'keeper_up')
        self.assertTrue(e._contextual_attacking_receiver_eligible(0, z, e._goalkeeper(0)))

    def test_94th_minute_one_goal_down_open_play_does_not_send_keeper(self):
        e = self.engine(); self.set_score(e, 0, 1); e.state.second = 94 * 60
        self.assertEqual(e._keeper_attack_mode(0, Zone(Band.BOX, Lane.CENTER)), 'normal')

    def test_two_goals_down_does_not_send_keeper_even_late(self):
        e = self.engine(); self.set_score(e, 0, 2); e.state.second = 94 * 60
        z = Zone(Band.BOX, Lane.CENTER)
        e.state.restart = 'corner'; e.state.restart_team = 0; e.state.restart_zone = z
        self.assertEqual(e._keeper_attack_mode(0, z), 'normal')

    def test_draw_at_94_does_not_send_keeper(self):
        e = self.engine(); self.set_score(e, 1, 1); e.state.second = 94 * 60
        self.assertEqual(e._keeper_attack_mode(0, Zone(Band.BOX, Lane.CENTER)), 'normal')

    def test_late_attacking_corner_activates_exposure(self):
        e = self.engine(); self.set_score(e, 0, 1); e.state.second = 91 * 60
        e.state.restart = 'corner'; e.state.restart_team = 0
        e.state.restart_zone = Zone(Band.BOX, Lane.RIGHT)
        ev = e._resolve_restart()
        self.assertTrue(ev.data.get('keeper_up'))
        self.assertTrue(e._keeper_is_exposed(0))

    def test_exposed_keeper_increases_counter_xg(self):
        e = self.engine(); self.set_score(e, 0, 1); e.state.second = 94 * 60
        p = PendingAction(1, e._choose_actor(1, Zone(Band.ATT, Lane.CENTER)).player.name,
                          'shoot', Zone(Band.ATT, Lane.CENTER), danger=0.55,
                          pressure=0.25, origin='transition')
        shooter = e.teams[1].by_name(p.actor)
        defender = e._choose_actor(0, Zone(Band.DEF, Lane.CENTER))
        keeper = e._goalkeeper(0)
        base = e._calculate_xg(p, shooter, defender, keeper)
        e._activate_keeper_up(0)
        exposed = e._calculate_xg(p, shooter, defender, keeper)
        self.assertGreater(exposed, base + 0.20)

    def test_keeper_exposure_survives_json_roundtrip(self):
        e = self.engine(); self.set_score(e, 0, 1); e.state.second = 94 * 60
        e._activate_keeper_up(0, seconds=40)
        clone = MatchEngineV13Spatial.from_json(e.export_json())
        self.assertTrue(clone._keeper_is_exposed(0))
        self.assertEqual(clone._v13_keeper_up_team, 0)

if __name__ == '__main__':
    unittest.main()
