from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13_chemistry import MatchEngineV13Chemistry


CTX = {
    "pressure": 0.46,
    "space": 0.54,
    "space_behind": 0.48,
    "support": 0.58,
    "wide_space": 0.12,
    "defending_availability": 1.0,
}


def make_engine(seed=123):
    a = make_generic_team("Attack", 79, "balanced", seed=10)
    b = make_generic_team("Defence", 80, "balanced", seed=20)
    return MatchEngineV13Chemistry(a, b, seed=seed)


def defender(e, position):
    return next(
        ps for ps in e.teams[1].on_field
        if ps.player.position.upper() == position
    )


class SharedUnderstandingTests(unittest.TestCase):
    def test_familiarity_is_symmetric_and_defaults_neutral(self):
        e = make_engine()
        cb = defender(e, "CB")
        rb = defender(e, "RB")
        self.assertEqual(e.pair_familiarity(1, cb.player.name, rb.player.name), 0.50)
        e.set_pair_familiarity(1, cb.player.name, rb.player.name, 0.91)
        self.assertEqual(e.pair_familiarity(1, rb.player.name, cb.player.name), 0.91)

    def test_high_familiarity_improves_same_handoff_pair(self):
        low = make_engine()
        high = make_engine()
        low_cb, low_rb = defender(low, "CB"), defender(low, "RB")
        high_cb, high_rb = defender(high, "CB"), defender(high, "RB")
        low.set_pair_familiarity(1, low_cb.player.name, low_rb.player.name, 0.05)
        high.set_pair_familiarity(1, high_cb.player.name, high_rb.player.name, 0.95)
        q_low = low._handoff_quality(low_cb, low_rb, 0.35)
        q_high = high._handoff_quality(high_cb, high_rb, 0.35)
        self.assertGreater(q_high, q_low)
        self.assertLessEqual(q_high - q_low, 0.10)

    def test_communication_quality_uses_pair_familiarity_not_team_buff(self):
        low = make_engine()
        high = make_engine()
        zone = Zone(Band.ATT, Lane.LEFT)
        low_cb, low_rb = defender(low, "CB"), defender(low, "RB")
        high_cb, high_rb = defender(high, "CB"), defender(high, "RB")
        low.set_pair_familiarity(1, low_cb.player.name, low_rb.player.name, 0.05)
        high.set_pair_familiarity(1, high_cb.player.name, high_rb.player.name, 0.95)
        plan = {"marking": {"hiddenness": 0.20}}
        q_low = low._communication_quality(
            0, zone, CTX, plan, "handoff_call", low_cb, low_rb
        )
        q_high = high._communication_quality(
            0, zone, CTX, plan, "handoff_call", high_cb, high_rb
        )
        self.assertGreater(q_high, q_low)
        other = next(
            ps for ps in low.teams[1].on_field
            if ps.player.name not in {low_cb.player.name, low_rb.player.name}
            and ps.player.position.upper() != "GK"
        )
        self.assertEqual(
            low.pair_familiarity(1, low_cb.player.name, other.player.name), 0.50
        )

    def test_cover_activation_changes_only_for_concrete_cover_pair(self):
        low = make_engine()
        high = make_engine()
        zone = Zone(Band.ATT, Lane.LEFT)
        low_primary = defender(low, "RB")
        high_primary = defender(high, "RB")

        def plan(primary):
            return {
                "intent": "contain",
                "kind": "dribble",
                "defender": primary,
                "defender_name": primary.player.name,
                "quality": 0.72,
                "marking": {
                    "mode": "hybrid", "marker_name": primary.player.name,
                    "target": None, "switched": False,
                },
            }

        probe = low._coverage_plan(0, zone, CTX, plan(low_primary), kind="dribble")
        self.assertIsNotNone(probe.get("defender"))
        cover_name = probe["defender"].player.name
        low.set_pair_familiarity(1, low_primary.player.name, cover_name, 0.05)
        high.set_pair_familiarity(1, high_primary.player.name, cover_name, 0.95)
        low_cov = low._coverage_plan(0, zone, CTX, plan(low_primary), kind="dribble")
        high_cov = high._coverage_plan(0, zone, CTX, plan(high_primary), kind="dribble")
        self.assertEqual(low_cov["defender_name"], high_cov["defender_name"])
        self.assertGreater(high_cov["activation"], low_cov["activation"])

    def test_line_coordination_uses_caller_member_familiarity(self):
        low = make_engine()
        high = make_engine()
        zone = Zone(Band.ATT, Lane.CENTER)
        probe = low._line_coordination(1, zone, CTX)
        caller = probe["caller"]
        members = [name for name in probe["members"] if name != caller]
        self.assertTrue(members)
        for name in members:
            low.set_pair_familiarity(1, caller, name, 0.05)
            high.set_pair_familiarity(1, caller, name, 0.95)
        low_line = low._line_coordination(1, zone, CTX)
        high_line = high._line_coordination(1, zone, CTX)
        self.assertGreater(high_line["shared_understanding"], low_line["shared_understanding"])
        self.assertGreater(high_line["coordination"], low_line["coordination"])
        self.assertLessEqual(
            high_line["coordination"] - low_line["coordination"], 0.10
        )

    def test_overload_helper_familiarity_changes_pull_response_score(self):
        low = make_engine()
        high = make_engine()
        zone = Zone(Band.ATT, Lane.LEFT)
        low_primary = defender(low, "RB")
        high_primary = defender(high, "RB")
        low_helper = defender(low, "CB")
        high_helper = defender(high, "CB")
        base_low = {
            "defender": low_primary,
            "defender_name": low_primary.player.name,
            "quality": 0.72,
            "marking": {"mode": "hybrid"},
        }
        base_high = {
            "defender": high_primary,
            "defender_name": high_primary.player.name,
            "quality": 0.72,
            "marking": {"mode": "hybrid"},
        }
        low.set_pair_familiarity(1, low_primary.player.name, low_helper.player.name, 0.05)
        high.set_pair_familiarity(1, high_primary.player.name, high_helper.player.name, 0.95)
        _, low_scores = low._overload_response(
            0, zone, CTX, base_low, 3, 2, low_helper, 0.75
        )
        _, high_scores = high._overload_response(
            0, zone, CTX, base_high, 3, 2, high_helper, 0.75
        )
        self.assertGreater(high_scores["pull_helper"], low_scores["pull_helper"])
        self.assertEqual(high_scores["split_difference"], low_scores["split_difference"])
        self.assertEqual(high_scores["delay_and_screen"], low_scores["delay_and_screen"])

    def test_no_concrete_relationship_means_no_active_chemistry(self):
        e = make_engine()
        plan = {
            "marking": {"switched": False},
            "coverage": {"active": False},
            "overload": {"active": False},
            "communication": {"active": False},
        }
        self.assertIsNone(e._active_relationship(0, plan))

    def test_chemistry_diagnostic_is_rng_pure_and_does_not_change_attributes(self):
        e = make_engine(seed=999)
        cb = defender(e, "CB")
        rb = defender(e, "RB")
        before_rng = e.rng.getstate()
        before = (
            cb.effective("positioning"), cb.effective("anticipation"),
            rb.effective("positioning"), rb.effective("anticipation"),
        )
        e.set_pair_familiarity(1, cb.player.name, rb.player.name, 0.88)
        diag = e.shared_understanding_diagnostic(
            1, cb.player.name, rb.player.name, relation="handoff"
        )
        after = (
            cb.effective("positioning"), cb.effective("anticipation"),
            rb.effective("positioning"), rb.effective("anticipation"),
        )
        self.assertEqual(before_rng, e.rng.getstate())
        self.assertEqual(before, after)
        self.assertGreater(diag["score"], 0.50)

    def test_same_seed_reproducible_with_same_pair_familiarity(self):
        e1 = make_engine(seed=777)
        e2 = make_engine(seed=777)
        pairs = []
        defenders1 = [
            ps for ps in e1.teams[1].on_field
            if ps.player.position.upper() in {"CB", "LB", "RB", "DM"}
        ]
        for first, second in zip(defenders1, defenders1[1:]):
            pairs.append((first.player.name, second.player.name))
        for first, second in pairs:
            e1.set_pair_familiarity(1, first, second, 0.82)
            e2.set_pair_familiarity(1, first, second, 0.82)

        for _ in range(250):
            if e1.state.ended or e2.state.ended:
                break
            x1 = e1.step()
            x2 = e2.step()
            self.assertEqual(
                (x1.type, x1.team, x1.text_key, x1.data),
                (x2.type, x2.team, x2.text_key, x2.data),
            )
        self.assertEqual(e1.snapshot(), e2.snapshot())


if __name__ == "__main__":
    unittest.main()
