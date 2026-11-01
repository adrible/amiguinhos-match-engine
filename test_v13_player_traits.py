from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from engine_experiment_v13_adaptation import MatchEngineV13Adaptation
from team_loader import load_team as load_stable_team
from team_loader_v13 import load_team_v13


class V13PlayerTraitTests(unittest.TestCase):
    def test_stable_loader_remains_unaware_of_candidate_traits(self):
        team = load_stable_team("amiguinhos_u21")
        names = {p.name: p for p in [*team.starters, *team.bench]}
        for name in ("Gabriel Adib", "Mike Junior", "Jorge Henrique", "Remo"):
            self.assertFalse(hasattr(names[name], "creativity"))
            self.assertFalse(hasattr(names[name], "boldness"))

    def test_v13_loader_attaches_only_explicitly_calibrated_traits(self):
        team = load_team_v13("amiguinhos_u21")
        names = {p.name: p for p in [*team.starters, *team.bench]}
        expected = {
            "Gabriel Adib": (92.0, 86.0),
            "Mike Junior": (89.0, 64.0),
            "Jorge Henrique": (78.0, 61.0),
            "Remo": (72.0, 82.0),
        }
        for name, (creativity, boldness) in expected.items():
            self.assertEqual(getattr(names[name], "creativity"), creativity)
            self.assertEqual(getattr(names[name], "boldness"), boldness)

        # Untuned players deliberately keep engine fallback behaviour.
        self.assertFalse(hasattr(names["Gabriel Félix"], "creativity"))
        self.assertFalse(hasattr(names["Gabriel Félix"], "boldness"))

    def test_calibration_encodes_behavior_not_a_single_overall_order(self):
        team = load_team_v13("amiguinhos_u21")
        names = {p.name: p for p in team.starters}
        self.assertGreater(names["Gabriel Adib"].creativity, names["Jorge Henrique"].creativity)
        self.assertGreater(names["Mike Junior"].creativity, names["Remo"].creativity)
        self.assertGreater(names["Remo"].boldness, names["Mike Junior"].boldness)
        self.assertGreater(names["Gabriel Adib"].boldness, names["Jorge Henrique"].boldness)

    def test_engine_reads_explicit_traits_without_execution_bonus(self):
        home = load_team_v13("amiguinhos_u21")
        away = load_team_v13("flamengo_u21")
        engine = MatchEngineV13Adaptation(home, away, seed=7)
        adib = engine.teams[0].by_name("Gabriel Adib")
        mike = engine.teams[0].by_name("Mike Junior")
        remo = engine.teams[0].by_name("Remo")

        passing_before = (
            adib.effective("passing"), mike.effective("passing"), remo.effective("passing")
        )
        self.assertAlmostEqual(engine._creativity(adib), 0.92, places=6)
        self.assertAlmostEqual(engine._boldness(adib), 0.86, places=6)
        self.assertAlmostEqual(engine._boldness(remo), 0.82, places=6)
        self.assertEqual(
            passing_before,
            (adib.effective("passing"), mike.effective("passing"), remo.effective("passing")),
        )

    def test_untuned_player_keeps_existing_fallback(self):
        home = load_team_v13("amiguinhos_u21")
        away = load_team_v13("flamengo_u21")
        engine = MatchEngineV13Adaptation(home, away, seed=8)
        felix = engine.teams[0].by_name("Gabriel Félix")
        expected_creativity = (
            0.48 * felix.effective("vision") / 100.0
            + 0.32 * felix.effective("technique") / 100.0
            + 0.20 * felix.effective("composure") / 100.0
        )
        self.assertAlmostEqual(engine._creativity(felix), expected_creativity, places=6)
        self.assertEqual(engine._boldness(felix), 0.50)

    def test_invalid_trait_range_is_rejected(self):
        raw = {
            "teams": {
                "amiguinhos_u21": {
                    "players": {"Gabriel Adib": {"creativity": 120, "boldness": 80}}
                }
            }
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "traits.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_team_v13("amiguinhos_u21", traits_path=path)

    def test_v13_traits_survive_candidate_state_roundtrip(self):
        home = load_team_v13("amiguinhos_u21")
        away = load_team_v13("flamengo_u21")
        engine = MatchEngineV13Adaptation(home, away, seed=9)
        restored = MatchEngineV13Adaptation.from_json(engine.export_json())
        for name in ("Gabriel Adib", "Mike Junior", "Jorge Henrique", "Remo"):
            original = engine.teams[0].by_name(name).player
            replay = restored.teams[0].by_name(name).player
            self.assertEqual(replay.creativity, original.creativity)
            self.assertEqual(replay.boldness, original.boldness)


if __name__ == "__main__":
    unittest.main()
