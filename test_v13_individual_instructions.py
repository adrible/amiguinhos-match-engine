from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_instructions import MatchEngineV13IndividualInstructions
from engine_experiment_v13_rotations import MatchEngineV13Rotations
from team_loader_v13 import load_team_v13


class IndividualInstructionTests(unittest.TestCase):
    def engine(self, seed=9701):
        return MatchEngineV13IndividualInstructions(
            load_team_v13("amiguinhos_u21"),
            make_generic_team("Away", 80, "balanced", seed=606),
            seed=seed,
        )

    @staticmethod
    def weight_map(items):
        return {name: float(weight) for name, weight in items}

    @staticmethod
    def target_weight(items, name):
        return next(float(weight) for ps, weight in items if ps.player.name == name)

    def test_canonical_entrypoint_uses_instruction_layer(self):
        self.assertTrue(issubclass(MatchEngineV13IndividualInstructions, MatchEngineV13Rotations))
        self.assertIs(CanonicalMatchEngine, MatchEngineV13IndividualInstructions)

    def test_conflicting_instructions_are_rejected(self):
        e = self.engine()
        with self.assertRaises(ValueError):
            e.set_player_instruction(
                0, "Mike Junior", stay_back=True, attack_depth=True
            )
        with self.assertRaises(ValueError):
            e.set_player_instruction(
                0, "Remo", move_inside=True, hold_width=True
            )

    def test_setting_instruction_is_rng_pure_and_attribute_pure(self):
        e = self.engine(seed=9703)
        remo = e.teams[0].by_name("Remo").player
        state = e.rng.getstate()
        before = dict(remo.__dict__)
        diag = e.set_player_instruction(0, "Remo", avoid_dribble=True, cross_more=True)
        self.assertEqual(e.rng.getstate(), state)
        self.assertEqual(before, remo.__dict__)
        self.assertTrue(diag["instructions"]["avoid_dribble"])
        self.assertFalse(hasattr(remo, "instruction_rating"))

    def test_avoid_dribble_changes_tendency_not_execution(self):
        e = self.engine(seed=9705)
        mike = e.teams[0].by_name("Mike Junior")
        zone = Zone(Band.MID, Lane.LEFT)
        ctx = {"pressure": 0.45, "space": 0.55, "space_behind": 0.48, "support": 0.58, "transition_threat": 0.4}
        tactics = e.teams[0].team.tactics
        before = self.weight_map(e._decision_weights(mike, zone, tactics, ctx))
        attrs = dict(mike.player.__dict__)
        e.set_player_instruction(0, mike.player.name, avoid_dribble=True)
        after = self.weight_map(e._decision_weights(mike, zone, tactics, ctx))
        self.assertLess(after["carry"], before["carry"])
        self.assertEqual(attrs, mike.player.__dict__)

    def test_more_risk_rebalances_available_actions(self):
        e = self.engine(seed=9707)
        adib = e.teams[0].by_name("Gabriel Adib")
        zone = Zone(Band.MID, Lane.CENTER)
        ctx = {"pressure": 0.40, "space": 0.60, "space_behind": 0.62, "support": 0.58, "transition_threat": 0.42}
        tactics = e.teams[0].team.tactics
        before = self.weight_map(e._decision_weights(adib, zone, tactics, ctx))
        e.set_player_instruction(0, adib.player.name, take_more_risks=True)
        after = self.weight_map(e._decision_weights(adib, zone, tactics, ctx))
        self.assertLess(after["safe_pass"], before["safe_pass"])
        self.assertGreater(after["through_ball"], before["through_ball"])
        self.assertGreater(after["progressive_pass"], before["progressive_pass"])

    def test_attack_depth_makes_player_more_available_high(self):
        e = self.engine(seed=9709)
        zone = Zone(Band.ATT, Lane.CENTER)
        ctx = {"pressure": 0.4, "space": 0.6, "space_behind": 0.72, "support": 0.55}
        before = self.target_weight(
            e._base_target_weights(0, zone, None, ctx), "Pedro Valverde"
        )
        e.set_player_instruction(0, "Pedro Valverde", attack_depth=True)
        after = self.target_weight(
            e._base_target_weights(0, zone, None, ctx), "Pedro Valverde"
        )
        self.assertGreater(after, before)

    def test_width_and_inside_instructions_change_receiver_geometry(self):
        wide = self.engine(seed=9711)
        center = self.engine(seed=9711)
        wide.set_player_instruction(0, "Remo", hold_width=True)
        center.set_player_instruction(0, "Remo", move_inside=True)
        ctx = {"pressure": 0.4, "space": 0.6, "space_behind": 0.5, "support": 0.55}
        wide_weight = self.target_weight(
            wide._base_target_weights(0, Zone(Band.ATT, Lane.RIGHT), None, ctx), "Remo"
        )
        inside_weight = self.target_weight(
            center._base_target_weights(0, Zone(Band.ATT, Lane.CENTER), None, ctx), "Remo"
        )
        self.assertGreater(wide_weight, self.target_weight(
            center._base_target_weights(0, Zone(Band.ATT, Lane.RIGHT), None, ctx), "Remo"
        ))
        self.assertGreater(inside_weight, self.target_weight(
            wide._base_target_weights(0, Zone(Band.ATT, Lane.CENTER), None, ctx), "Remo"
        ))

    def test_press_target_reduces_receiver_availability_without_buff(self):
        e = self.engine(seed=9713)
        target = e.teams[1].on_field[6]
        marker = e.teams[0].by_name("Felipe")
        zone = Zone(Band.MID, Lane.CENTER)
        ctx = {"pressure": 0.45, "space": 0.55, "space_behind": 0.48, "support": 0.55}
        before = self.target_weight(
            e._base_target_weights(1, zone, None, ctx), target.player.name
        )
        marker_attrs = dict(marker.player.__dict__)
        e.set_player_instruction(0, marker.player.name, press_target=target.player.name)
        after = self.target_weight(
            e._base_target_weights(1, zone, None, ctx), target.player.name
        )
        self.assertLess(after, before)
        self.assertEqual(marker_attrs, marker.player.__dict__)

    def test_instructions_survive_roundtrip_and_future_is_identical(self):
        e = self.engine(seed=9715)
        e.set_player_instruction(0, "Mike Junior", avoid_dribble=True, move_inside=True)
        e.set_player_instruction(0, "Felipe", press_target=e.teams[1].on_field[6].player.name)
        clone = MatchEngineV13IndividualInstructions.from_json(e.export_json())
        self.assertEqual(
            e._v13_individual_instructions,
            clone._v13_individual_instructions,
        )
        a, b = e.step(), clone.step()
        self.assertEqual(
            (a.minute, a.team, a.type.value, a.text_key, a.data),
            (b.minute, b.team, b.type.value, b.text_key, b.data),
        )
        self.assertEqual(e.export_state(), clone.export_state())


if __name__ == "__main__":
    unittest.main()
