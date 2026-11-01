from __future__ import annotations

import unittest

from engine import Event, EventType, MatchConfig, make_generic_team
from engine_experiment_v13_adaptation_stability import MatchEngineV13AdaptationStability


def make_engine(seed=123):
    a = make_generic_team("A", 79, "balanced", seed=10)
    b = make_generic_team("B", 80, "balanced", seed=20)
    return MatchEngineV13AdaptationStability(
        a, b, seed=seed, config=MatchConfig(auto_tactical_adaptation=True)
    )


def add_event(e, minute, team, kind):
    e.state.event_log.append(
        Event(
            minute=float(minute),
            team=team,
            type=EventType.DANGER,
            relevance=3,
            text_key="danger_created",
            data={"kind": kind, "zone": {"band": "att", "lane": "left"}},
        )
    )


class TacticalAdaptationStabilityTests(unittest.TestCase):
    def test_sparse_pattern_is_not_enough_for_structural_change(self):
        e = make_engine()
        e.state.second = 40 * 60
        add_event(e, 36, 1, "through_ball")
        add_event(e, 38, 1, "through_ball")
        profile = e._adaptation_profile(0)
        self.assertFalse(profile["eligible"])
        self.assertIsNone(profile["response"])
        self.assertIn("insufficient_persistent_evidence", profile["blocked_reasons"])

    def test_persistent_depth_pattern_still_triggers_response(self):
        e = make_engine()
        e.state.second = 42 * 60
        for minute in (33, 35, 37, 39, 41):
            add_event(e, minute, 1, "through_ball")
        profile = e._adaptation_profile(0)
        self.assertEqual(profile["response"], "protect_depth")
        self.assertTrue(profile["eligible"])
        self.assertTrue(profile["stability_gate"]["pattern_must_span_window"])

    def test_clustered_depth_burst_does_not_count_as_sustained_pattern(self):
        e = make_engine()
        e.state.second = 42 * 60
        for minute in (38.0, 38.5, 39.0, 40.0, 41.0):
            add_event(e, minute, 1, "through_ball")
        profile = e._adaptation_profile(0)
        self.assertFalse(profile["eligible"])
        self.assertIsNone(profile["response"])
        self.assertIn(
            "pattern_not_temporally_persistent", profile["blocked_reasons"]
        )

    def test_same_response_is_not_reapplied_or_relabelled_after_use(self):
        e = make_engine()
        e._v13_adaptation_history = [
            {
                "minute": 35.0,
                "team": 0,
                "response": "protect_depth",
                "response_score": 0.70,
            }
        ]
        e.state.second = 70 * 60
        for minute in (61, 63, 65, 67, 69):
            add_event(e, minute, 1, "through_ball")
        profile = e._adaptation_profile(0)
        self.assertIsNone(profile["response"])
        self.assertFalse(profile["eligible"])
        self.assertIn(
            "dominant_response_already_applied", profile["blocked_reasons"]
        )
        self.assertTrue(
            profile["stability_gate"][
                "handled_dominant_need_blocks_structural_fallthrough"
            ]
        )

    def test_late_score_need_can_override_handled_structural_problem(self):
        e = make_engine()
        e._v13_adaptation_history = [
            {"minute": 50.0, "team": 0, "response": "protect_depth"}
        ]
        e.state.second = 82 * 60
        e.stats[0].goals = 0
        e.stats[1].goals = 2
        for minute in (73, 75, 77, 79, 81):
            add_event(e, minute, 1, "through_ball")
        profile = e._adaptation_profile(0)
        self.assertEqual(profile["response"], "chase_game")
        self.assertTrue(profile["eligible"])

    def test_global_cooldown_is_longer_than_original_reaction_cycle(self):
        e = make_engine()
        e.state.second = 70 * 60
        e.stats[0].goals = 0
        e.stats[1].goals = 1
        first = e._adaptation_profile(0)
        self.assertTrue(first["eligible"])
        e._apply_tactical_adaptation(0, first)

        e.state.second = 82 * 60
        second = e._adaptation_profile(0)
        self.assertFalse(second["eligible"])
        self.assertIn("cooldown", second["blocked_reasons"])

    def test_team_cannot_reconfigure_more_than_three_times(self):
        e = make_engine()
        e._v13_adaptation_history = [
            {"minute": 25.0, "team": 0, "response": "protect_depth"},
            {"minute": 45.0, "team": 0, "response": "protect_wide"},
            {"minute": 65.0, "team": 0, "response": "regain_control"},
        ]
        e.state.second = 88 * 60
        e.stats[0].goals = 0
        e.stats[1].goals = 1
        profile = e._adaptation_profile(0)
        self.assertFalse(profile["eligible"])
        self.assertIn("team_adaptation_limit", profile["blocked_reasons"])

    def test_late_score_context_remains_available_without_pattern_events(self):
        e = make_engine()
        e.state.second = 78 * 60
        e.stats[0].goals = 0
        e.stats[1].goals = 2
        profile = e._adaptation_profile(0)
        self.assertEqual(profile["response"], "chase_game")
        self.assertTrue(profile["eligible"])

    def test_same_score_response_is_not_ratcheted_repeatedly(self):
        e = make_engine()
        e._v13_adaptation_history = [
            {"minute": 64.0, "team": 0, "response": "chase_game"}
        ]
        e.state.second = 89 * 60
        e.stats[0].goals = 0
        e.stats[1].goals = 2
        profile = e._adaptation_profile(0)
        self.assertFalse(profile["eligible"])
        self.assertIsNone(profile["response"])
        self.assertIn(
            "dominant_response_already_applied", profile["blocked_reasons"]
        )

    def test_same_seed_stays_reproducible_with_hysteresis(self):
        e1 = make_engine(seed=777)
        e2 = make_engine(seed=777)
        for _ in range(320):
            if e1.state.ended or e2.state.ended:
                break
            a = e1.step()
            b = e2.step()
            self.assertEqual(
                (a.type, a.team, a.relevance, a.text_key, a.data),
                (b.type, b.team, b.relevance, b.text_key, b.data),
            )
            self.assertEqual(e1.adaptation_history(), e2.adaptation_history())
        self.assertEqual(e1.snapshot(), e2.snapshot())


if __name__ == "__main__":
    unittest.main()
