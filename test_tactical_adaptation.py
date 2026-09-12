from __future__ import annotations

import unittest

from engine import Event, EventType, MatchConfig, make_generic_team
from engine_experiment_v13_adaptation import MatchEngineV13Adaptation


def make_engine(seed=123, enabled=True):
    a = make_generic_team("A", 79, "balanced", seed=10)
    b = make_generic_team("B", 80, "balanced", seed=20)
    cfg = MatchConfig(auto_tactical_adaptation=enabled)
    return MatchEngineV13Adaptation(a, b, seed=seed, config=cfg)


def add_event(e, minute, team, typ, text="probe", **data):
    e.state.event_log.append(
        Event(minute=float(minute), team=team, type=typ, relevance=2, text_key=text, data=data)
    )


class TacticalAdaptationTests(unittest.TestCase):
    def test_diagnostic_is_rng_pure_and_does_not_change_tactics(self):
        e = make_engine(seed=999)
        e.state.second = 70 * 60
        e.stats[0].goals = 0
        e.stats[1].goals = 1
        before_rng = e.rng.getstate()
        before = dict(e.teams[0].team.tactics.__dict__)
        diag = e.tactical_adaptation_diagnostic(0)
        self.assertEqual(before_rng, e.rng.getstate())
        self.assertEqual(before, e.teams[0].team.tactics.__dict__)
        self.assertEqual(diag["response"], "chase_game")
        self.assertTrue(diag["eligible"])

    def test_losing_late_recommends_chase_game_with_real_tradeoff(self):
        e = make_engine()
        e.state.second = 76 * 60
        e.stats[0].goals = 0
        e.stats[1].goals = 2
        diag = e.tactical_adaptation_diagnostic(0)
        self.assertEqual(diag["response"], "chase_game")
        changes = diag["preview"]["changes"]
        self.assertGreater(changes["risk"]["after"], changes["risk"]["before"])
        self.assertGreater(changes["tempo"]["after"], changes["tempo"]["before"])
        self.assertLess(changes["compactness"]["after"], changes["compactness"]["before"])

    def test_leading_late_recommends_protect_lead(self):
        e = make_engine()
        e.state.second = 82 * 60
        e.stats[0].goals = 2
        e.stats[1].goals = 1
        diag = e.tactical_adaptation_diagnostic(0)
        self.assertEqual(diag["response"], "protect_lead")
        self.assertTrue(diag["eligible"])
        changes = diag["preview"]["changes"]
        self.assertLess(changes["risk"]["after"], changes["risk"]["before"])
        self.assertGreater(changes["compactness"]["after"], changes["compactness"]["before"])
        self.assertLess(changes["defensive_line"]["after"], changes["defensive_line"]["before"])

    def test_recent_depth_pressure_can_trigger_protect_depth(self):
        e = make_engine()
        e.state.second = 40 * 60
        for minute in (31, 33, 35, 37, 39):
            add_event(
                e, minute, 1, EventType.DANGER,
                kind="through_ball", zone={"band": "att", "lane": "center"},
            )
        diag = e.tactical_adaptation_diagnostic(0)
        self.assertEqual(diag["response"], "protect_depth")
        self.assertTrue(diag["eligible"])
        changes = diag["preview"]["changes"]
        self.assertLess(changes["defensive_line"]["after"], changes["defensive_line"]["before"])
        self.assertLess(changes["pressing"]["after"], changes["pressing"]["before"])

    def test_recent_wide_pressure_can_trigger_protect_wide(self):
        e = make_engine()
        e.state.second = 42 * 60
        for minute in (33, 35, 37, 39, 41):
            add_event(
                e, minute, 1, EventType.DANGER,
                kind="cross", zone={"band": "att", "lane": "left"},
            )
        diag = e.tactical_adaptation_diagnostic(0)
        self.assertEqual(diag["response"], "protect_wide")
        self.assertTrue(diag["eligible"])
        changes = diag["preview"]["changes"]
        self.assertGreater(changes["width"]["after"], changes["width"]["before"])
        self.assertLess(changes["compactness"]["after"], changes["compactness"]["before"])

    def test_old_events_outside_window_are_ignored(self):
        e = make_engine()
        e.state.second = 50 * 60
        for minute in (10, 12, 14, 16, 18):
            add_event(
                e, minute, 1, EventType.DANGER,
                kind="through_ball", zone={"band": "att", "lane": "center"},
            )
        diag = e.tactical_adaptation_diagnostic(0)
        self.assertEqual(diag["evidence"]["events_in_window"], 0)
        self.assertFalse(diag["eligible"])

    def test_cooldown_prevents_repeated_ratcheting(self):
        e = make_engine()
        e.state.second = 70 * 60
        e.stats[0].goals = 0
        e.stats[1].goals = 1
        first = e._adaptation_profile(0)
        record = e._apply_tactical_adaptation(0, first)
        self.assertIsNotNone(record)
        after_first = dict(e.teams[0].team.tactics.__dict__)
        second = e._adaptation_profile(0)
        self.assertFalse(second["eligible"])
        self.assertIn("cooldown", second["blocked_reasons"])
        self.assertIsNone(e._apply_tactical_adaptation(0, second))
        self.assertEqual(after_first, e.teams[0].team.tactics.__dict__)

    def test_config_disabled_preserves_tactics(self):
        e = make_engine(enabled=False)
        e.state.second = 75 * 60
        e.stats[0].goals = 0
        e.stats[1].goals = 2
        before = [dict(rt.team.tactics.__dict__) for rt in e.teams]
        for _ in range(20):
            if e.state.ended:
                break
            e.step()
        after = [dict(rt.team.tactics.__dict__) for rt in e.teams]
        self.assertEqual(before, after)
        self.assertEqual(e.adaptation_history(), [])

    def test_adaptation_does_not_change_formation_or_player_attributes(self):
        e = make_engine()
        e.state.second = 76 * 60
        e.stats[0].goals = 0
        e.stats[1].goals = 1
        player = e.teams[0].on_field[0]
        formation = e.teams[0].team.tactics.formation
        attrs = (
            player.effective("positioning"), player.effective("anticipation"),
            player.effective("pace"), player.effective("composure"),
        )
        profile = e._adaptation_profile(0)
        e._apply_tactical_adaptation(0, profile)
        self.assertEqual(formation, e.teams[0].team.tactics.formation)
        self.assertEqual(attrs, (
            player.effective("positioning"), player.effective("anticipation"),
            player.effective("pace"), player.effective("composure"),
        ))

    def test_same_seed_reproducible_with_auto_adaptation_enabled(self):
        e1 = make_engine(seed=777, enabled=True)
        e2 = make_engine(seed=777, enabled=True)
        for _ in range(320):
            if e1.state.ended or e2.state.ended:
                break
            x1 = e1.step()
            x2 = e2.step()
            self.assertEqual(
                (x1.type, x1.team, x1.text_key, x1.data),
                (x2.type, x2.team, x2.text_key, x2.data),
            )
            self.assertEqual(
                [rt.team.tactics.__dict__ for rt in e1.teams],
                [rt.team.tactics.__dict__ for rt in e2.teams],
            )
        self.assertEqual(e1.snapshot(), e2.snapshot())
        self.assertEqual(e1.adaptation_history(), e2.adaptation_history())


if __name__ == "__main__":
    unittest.main()
