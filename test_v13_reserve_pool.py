from __future__ import annotations

import unittest

from team_loader import load_team as load_stable_team
from team_loader_v13 import load_team_v13


class V13ReservePoolTests(unittest.TestCase):
    def test_stable_v12_opponent_without_bench_stays_untouched(self):
        stable = load_stable_team("flamengo_u21")
        self.assertEqual(stable.bench, [])

    def test_v13_supplies_bench_when_source_has_none(self):
        candidate = load_team_v13("flamengo_u21")
        self.assertGreaterEqual(len(candidate.bench), 5)
        self.assertTrue(all("Reserva" in player.name for player in candidate.bench))

    def test_known_amiguinhos_bench_is_not_supplemented_or_replaced(self):
        candidate = load_team_v13("amiguinhos_u21")
        self.assertEqual(
            [player.name for player in candidate.bench],
            ["Arthur Peixoto", "Igor", "Gabriel Gonzales"],
        )

    def test_generated_bench_is_deterministic(self):
        first = load_team_v13("flamengo_u21")
        second = load_team_v13("flamengo_u21")
        first_rows = [
            (p.name, p.position, p.overall, p.pace, p.passing, p.finishing, p.tackling)
            for p in first.bench
        ]
        second_rows = [
            (p.name, p.position, p.overall, p.pace, p.passing, p.finishing, p.tackling)
            for p in second.bench
        ]
        self.assertEqual(first_rows, second_rows)

    def test_generated_bench_is_not_stronger_than_team_by_design(self):
        candidate = load_team_v13("flamengo_u21")
        starter_average = sum(p.overall for p in candidate.starters) / len(candidate.starters)
        bench_average = sum(p.overall for p in candidate.bench) / len(candidate.bench)
        self.assertLess(bench_average, starter_average + 0.5)


if __name__ == "__main__":
    unittest.main()
