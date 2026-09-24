import unittest
from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine


class ContactCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = MatchEngine(make_generic_team('A', 78, seed=1),
                                  make_generic_team('B', 78, seed=2), seed=17)
        self.zone = Zone(Band.MID, Lane.CENTER)
        self.actor = self.engine.teams[0].on_field[5]
        self.defender = self.engine.teams[1].on_field[5]

    def test_space_reduces_low_pressure_contact(self):
        e = self.engine
        tight = e.contact_foul_probability(0, self.actor, self.defender, self.zone,
                                           'safe_pass', {'pressure': .1, 'space': 0})
        open_ = e.contact_foul_probability(0, self.actor, self.defender, self.zone,
                                           'safe_pass', {'pressure': .1, 'space': 1})
        self.assertLess(open_, tight)
        self.assertGreater(open_, 0)

    def test_fully_contested_contact_preserves_duel(self):
        e = self.engine
        probabilities = [e.contact_foul_probability(0, self.actor, self.defender,
                         self.zone, 'carry', {'pressure': 1, 'space': s}) for s in (0, 1)]
        self.assertEqual(*probabilities)

    def test_repeated_warned_fouls_raise_caution_without_red_lottery(self):
        e = self.engine
        incident = dict(type='trip', severity=.35, spa=False, dogso=False,
                        violent=False, ordinary_contact=True, attempt_to_play_ball=True)
        rng = e.rng.getstate()
        first = e._card_probabilities(1, self.defender, incident, self.zone, 1)
        e.rng.setstate(rng)
        repeated = e._card_probabilities(1, self.defender, incident, self.zone, 4)
        e._ref_warned_players.add(e._foul_key(1, self.defender))
        e.rng.setstate(rng)
        warned = e._card_probabilities(1, self.defender, incident, self.zone, 4)
        self.assertLess(first['yellow'], repeated['yellow'])
        self.assertLess(repeated['yellow'], warned['yellow'])
        self.assertEqual(first['direct_red'], warned['direct_red'])
