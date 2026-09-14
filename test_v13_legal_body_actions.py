from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13_legal_body import MatchEngineV13LegalBody


class LegalBodyActionTests(unittest.TestCase):
    def engine(self):
        return MatchEngineV13LegalBody(
            make_generic_team('Home', 80, 'balanced', seed=10),
            make_generic_team('Away', 80, 'balanced', seed=20),
            seed=30,
        )

    def actor(self, e):
        return next(ps for ps in e.teams[0].on_field if ps.player.position != 'GK')

    def ctx(self):
        return {'pressure': 0.35, 'space': 0.62, 'support': 0.58, 'space_behind': 0.50}

    def test_all_legal_contact_parts_have_nonzero_probability_for_core_actions(self):
        e = self.engine(); a = self.actor(e); z = Zone(Band.ATT, Lane.CENTER)
        for action in ('safe_pass', 'carry', 'dribble', 'shoot'):
            probs = e.body_part_probabilities(a, action, z, self.ctx(), source='open_play')
            self.assertEqual(set(probs), set(e.CONTACT_PARTS))
            self.assertTrue(all(v > 0 for v in probs.values()))
            self.assertAlmostEqual(sum(probs.values()), 1.0, places=8)

    def test_preferred_foot_is_easier_than_weak_and_exotic_contacts(self):
        e = self.engine(); a = self.actor(e)
        preferred, weak = e._preferred_and_weak_foot(a)
        for action in ('safe_pass', 'carry', 'shoot'):
            pref = e._part_execution_modifier(a, action, preferred)
            weak_mod = e._part_execution_modifier(a, action, weak)
            shoulder = e._part_execution_modifier(a, action, 'shoulder')
            self.assertGreater(pref, weak_mod)
            self.assertGreater(weak_mod, shoulder)

    def test_aerial_ball_makes_head_chest_and_thigh_more_likely(self):
        e = self.engine(); a = self.actor(e); z = Zone(Band.BOX, Lane.CENTER)
        ground = e.body_part_probabilities(a, 'shoot', z, self.ctx(), source='cutback')
        aerial = e.body_part_probabilities(a, 'shoot', z, self.ctx(), source='cross')
        for part in ('head', 'chest', 'thigh'):
            self.assertGreater(aerial[part], ground[part])

    def test_lower_body_injury_shifts_contact_away_from_feet(self):
        e = self.engine(); a = self.actor(e); z = Zone(Band.ATT, Lane.CENTER)
        normal = e.body_part_probabilities(a, 'safe_pass', z, self.ctx(), source='cross')
        a.injured = True
        e._v13_injury_locations = {a.player.name: 'lower_body'}
        hurt = e.body_part_probabilities(a, 'safe_pass', z, self.ctx(), source='cross')
        preferred, _ = e._preferred_and_weak_foot(a)
        self.assertLess(hurt[preferred], normal[preferred])
        self.assertGreater(hurt['head'], normal['head'])

    def test_dummy_is_no_touch_and_available_only_on_a_received_ball(self):
        e = self.engine(); a = self.actor(e); z = Zone(Band.ATT, Lane.CENTER); ctx = self.ctx()
        e._v13_current_reception_source = 'open_play'
        plain = dict(e._decision_weights(a, z, e.teams[0].team.tactics, ctx))
        self.assertNotIn('dummy', plain)
        e._v13_current_reception_source = 'progression'
        received = dict(e._decision_weights(a, z, e.teams[0].team.tactics, ctx))
        self.assertGreater(received.get('dummy', 0.0), 0.0)

    def test_injury_location_and_forced_contact_survive_roundtrip(self):
        e = self.engine(); a = self.actor(e)
        e._v13_injury_locations = {a.player.name: 'lower_body'}
        e._v13_forced_shot_body_part = {'team': 0, 'actor': a.player.name, 'part': 'left_foot', 'modifier': 0.8, 'source': 'open_play'}
        clone = MatchEngineV13LegalBody.from_json(e.export_json())
        self.assertEqual(clone._v13_injury_locations[a.player.name], 'lower_body')
        self.assertEqual(clone._v13_forced_shot_body_part['part'], 'left_foot')


if __name__ == '__main__':
    unittest.main()
