from __future__ import annotations

import json
import unittest

from engine import MatchConfig
from engine_experiment_v13_adaptation import MatchEngineV13Adaptation
from engine_experiment_v13_persistence import (
    MatchEngineV13Persistence,
    STATE_VERSION,
)
from team_loader_v13 import load_team_v13


def make_engine(seed=321, auto_adapt=True):
    home = load_team_v13("amiguinhos_u21")
    away = load_team_v13("flamengo_u21")
    return MatchEngineV13Persistence(
        home,
        away,
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=auto_adapt),
    )


def force_one_adaptation(engine):
    engine.state.second = 70 * 60
    engine.state.period_index = 1
    engine.stats[0].goals = 0
    engine.stats[1].goals = 1
    engine._maybe_auto_adapt()
    if not engine.adaptation_history(0):
        raise AssertionError("expected forced adaptation fixture to create history")


class V13PersistenceTests(unittest.TestCase):
    def test_export_marks_candidate_state_version(self):
        e = make_engine()
        data = e.export_state()
        self.assertEqual(data["version"], STATE_VERSION)
        self.assertIn("engine_version", data)
        self.assertIn("v13", data)
        json.dumps(data, ensure_ascii=False)

    def test_pair_familiarity_and_adaptation_history_restore(self):
        e = make_engine()
        e.set_pair_familiarity(0, "Gabriel Adib", "Mike Junior", 0.87)
        force_one_adaptation(e)
        restored = MatchEngineV13Persistence.from_json(e.export_json())

        self.assertIsInstance(restored, MatchEngineV13Persistence)
        self.assertEqual(
            restored.pair_familiarity(0, "Mike Junior", "Gabriel Adib"),
            0.87,
        )
        self.assertEqual(restored.adaptation_history(), e.adaptation_history())
        self.assertEqual(restored.snapshot(), e.snapshot())

    def test_traits_survive_persistence_layer(self):
        e = make_engine()
        restored = MatchEngineV13Persistence.from_json(e.export_json())
        for name in ("Gabriel Adib", "Mike Junior", "Jorge Henrique", "Remo"):
            before = e.teams[0].by_name(name).player
            after = restored.teams[0].by_name(name).player
            self.assertEqual(after.creativity, before.creativity)
            self.assertEqual(after.boldness, before.boldness)

    def test_restore_preserves_adaptation_cooldown(self):
        e = make_engine()
        force_one_adaptation(e)
        restored = MatchEngineV13Persistence.from_json(e.export_json())
        original_profile = e._adaptation_profile(0)
        restored_profile = restored._adaptation_profile(0)
        self.assertFalse(original_profile["eligible"])
        self.assertFalse(restored_profile["eligible"])
        self.assertEqual(
            original_profile["blocked_reasons"],
            restored_profile["blocked_reasons"],
        )

    def test_restored_match_continues_with_identical_rng_sequence(self):
        e = make_engine(seed=777)
        e.set_pair_familiarity(0, "Gabriel Adib", "Mike Junior", 0.83)
        e.set_pair_familiarity(1, "Matheus Braga", "Lucas Tavares", 0.76)

        for _ in range(120):
            if e.state.ended:
                break
            e.step()
        restored = MatchEngineV13Persistence.from_json(e.export_json())
        self.assertEqual(e.rng.getstate(), restored.rng.getstate())

        for _ in range(160):
            if e.state.ended or restored.state.ended:
                break
            a = e.step()
            b = restored.step()
            self.assertEqual(
                (a.type, a.team, a.relevance, a.text_key, a.data),
                (b.type, b.team, b.relevance, b.text_key, b.data),
            )
            self.assertEqual(e.snapshot(), restored.snapshot())
        self.assertEqual(e.export_state(), restored.export_state())

    def test_pending_danger_restores_exactly(self):
        e = make_engine(seed=456, auto_adapt=False)
        for _ in range(800):
            if e.state.ended:
                self.fail("match ended before a pending danger was found")
            e.step()
            if e.state.pending is not None:
                break
        self.assertIsNotNone(e.state.pending)

        restored = MatchEngineV13Persistence.from_json(e.export_json())
        self.assertEqual(e.snapshot(), restored.snapshot())
        for _ in range(80):
            if e.state.ended or restored.state.ended:
                break
            a = e.step()
            b = restored.step()
            self.assertEqual(
                (a.type, a.team, a.relevance, a.text_key, a.data),
                (b.type, b.team, b.relevance, b.text_key, b.data),
            )
        self.assertEqual(e.export_state(), restored.export_state())

    def test_older_v13_state_without_private_section_still_loads(self):
        home = load_team_v13("amiguinhos_u21")
        away = load_team_v13("flamengo_u21")
        old = MatchEngineV13Adaptation(home, away, seed=44)
        payload = old.export_state()
        self.assertNotIn("v13", payload)

        restored = MatchEngineV13Persistence.from_state_dict(payload)
        self.assertIsInstance(restored, MatchEngineV13Persistence)
        self.assertEqual(restored.adaptation_history(), [])
        self.assertEqual(
            restored.pair_familiarity(0, "Gabriel Adib", "Mike Junior"),
            0.50,
        )


if __name__ == "__main__":
    unittest.main()
