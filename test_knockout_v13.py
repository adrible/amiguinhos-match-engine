from __future__ import annotations

import unittest

from engine import EventType, MatchConfig, make_generic_team
from engine_experiment_v13_knockout import MatchEngineV13Knockout


class KnockoutContinuationTests(unittest.TestCase):
    def _engine(self, seed: int = 77) -> MatchEngineV13Knockout:
        return MatchEngineV13Knockout(
            make_generic_team("Home", 78, "balanced", seed=11),
            make_generic_team("Away", 78, "balanced", seed=22),
            seed=seed,
            config=MatchConfig(allow_extra_time=True),
        )

    def _force_regulation_tie_boundary(self, engine: MatchEngineV13Knockout) -> None:
        engine.stats[0].goals = 1
        engine.stats[1].goals = 1
        engine.state.second = 90.0 * 60.0
        engine.state.period_markers = [45, 90]
        engine.state.period_index = 1
        engine.state.pending = None
        engine.state.restart = None

    def _force_extra_time_tie_boundary(self, engine: MatchEngineV13Knockout) -> None:
        engine.stats[0].goals = 1
        engine.stats[1].goals = 1
        engine.state.second = 120.0 * 60.0
        engine.state.period_markers = [105, 120]
        engine.state.period_index = 1
        engine.state.pending = None
        engine.state.restart = None

    def test_tied_regulation_enters_real_extra_time(self):
        engine = self._engine()
        self._force_regulation_tie_boundary(engine)
        event = engine.step()
        self.assertEqual(event.type, EventType.PERIOD_END)
        self.assertEqual(event.text_key, "regulation_end_tied")
        self.assertFalse(engine.state.ended)
        self.assertEqual(engine.state.period_markers, [105, 120])
        self.assertEqual(engine.state.period_index, 0)
        self.assertEqual(engine.state.phase, "build_up")
        self.assertIn(engine.state.extra_time_kickoff_team, (0, 1))

    def test_extra_time_half_continues_at_105(self):
        engine = self._engine()
        self._force_regulation_tie_boundary(engine)
        engine.step()
        engine.state.second = 105.0 * 60.0
        event = engine.step()
        self.assertEqual(event.type, EventType.PERIOD_END)
        self.assertFalse(engine.state.ended)
        self.assertEqual(engine.state.period_index, 1)

    def test_tied_extra_time_enters_live_shootout(self):
        engine = self._engine()
        self._force_extra_time_tie_boundary(engine)
        event = engine.step()
        self.assertEqual(event.type, EventType.PERIOD_END)
        self.assertEqual(event.text_key, "extra_time_end_tied")
        self.assertFalse(engine.state.ended)
        self.assertEqual(engine.state.phase, "penalty_shootout")
        self.assertTrue(engine._v13_shootout["active"])
        self.assertEqual(engine._v13_shootout["kicks"], [0, 0])

    def test_each_public_step_resolves_only_one_shootout_kick(self):
        engine = self._engine()
        self._force_extra_time_tie_boundary(engine)
        engine.step()
        first = engine.step()
        self.assertEqual(first.type, EventType.PENALTY)
        self.assertTrue(first.data["shootout"])
        self.assertEqual(sum(engine._v13_shootout["kicks"]), 1)
        second = engine.step()
        self.assertEqual(second.type, EventType.PENALTY)
        self.assertEqual(sum(engine._v13_shootout["kicks"]), 2)

    def test_shootout_eventually_resolves_then_emits_match_end(self):
        engine = self._engine(seed=88)
        self._force_extra_time_tie_boundary(engine)
        engine.step()
        guard = 0
        decisive = None
        while not engine._v13_shootout["complete"] and guard < 30:
            decisive = engine.step()
            guard += 1
        self.assertLess(guard, 30)
        self.assertIsNotNone(decisive)
        self.assertEqual(decisive.type, EventType.PENALTY)
        self.assertTrue(decisive.data["decisive"])
        self.assertFalse(engine.state.ended)

        end = engine.step()
        self.assertEqual(end.type, EventType.MATCH_END)
        self.assertEqual(end.text_key, "match_end_shootout")
        self.assertTrue(engine.state.ended)
        self.assertIn(end.data["winner"], (0, 1))
        self.assertNotEqual(end.data["shootout_score"][0], end.data["shootout_score"][1])

    def test_same_seed_reproduces_same_shootout(self):
        first = self._engine(seed=91)
        second = self._engine(seed=91)
        for engine in (first, second):
            self._force_extra_time_tie_boundary(engine)
            engine.step()

        a = []
        b = []
        for _ in range(20):
            ev_a = first.step()
            ev_b = second.step()
            a.append((ev_a.type.value, ev_a.text_key, ev_a.data))
            b.append((ev_b.type.value, ev_b.text_key, ev_b.data))
            if ev_a.type == EventType.MATCH_END:
                break
        self.assertEqual(a, b)

    def test_mid_shootout_persistence_preserves_exact_future(self):
        engine = self._engine(seed=123)
        self._force_extra_time_tie_boundary(engine)
        engine.step()
        engine.step()
        restored = MatchEngineV13Knockout.from_json(engine.export_json())

        original_events = []
        restored_events = []
        for _ in range(8):
            ev_a = engine.step()
            ev_b = restored.step()
            original_events.append((ev_a.type.value, ev_a.text_key, ev_a.data))
            restored_events.append((ev_b.type.value, ev_b.text_key, ev_b.data))
            if ev_a.type == EventType.MATCH_END:
                break
        self.assertEqual(original_events, restored_events)


if __name__ == "__main__":
    unittest.main()
