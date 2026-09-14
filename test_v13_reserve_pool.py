from __future__ import annotations

import unittest

from team_loader import load_team as load_stable_team
from team_loader_v13 import load_team_v13


class V13ReservePoolTests(unittest.TestCase):
    def test_stable_v12_opponent_without_bench_stays_untouched(self):
        stable = load_stable_team("flamengo_u21")
        self.assertEqual(stable.bench, [])
        self.assertEqual(stable.name, "Flamengo U21")

    def test_v13_uses_real_flamengo_u20_roster_instead_of_synthetic_names(self):
        candidate = load_team_v13("flamengo_u21")
        self.assertEqual(candidate.name, "Flamengo Sub-20")
        self.assertEqual(
            [player.name for player in candidate.starters],
            [
                "Léo Nannetti",
                "Daniel Sales",
                "Weverson",
                "João Victor",
                "Ítalo",
                "Rogério Araújo",
                "Lucas Falcone",
                "Jhefinho Vinicius",
                "Joshua",
                "Sayago",
                "Victor Hugo",
            ],
        )
        self.assertGreaterEqual(len(candidate.bench), 7)
        self.assertTrue(all("Reserva" not in player.name for player in candidate.bench))

    def test_corrected_amiguinhos_bench_is_white_arthur_gonzales(self):
        candidate = load_team_v13("amiguinhos_u21")
        self.assertEqual(
            [player.name for player in candidate.bench],
            ["Rodrigo White", "Arthur Peixoto", "Gabriel Gonzales"],
        )
        starter_names = [player.name for player in candidate.starters]
        self.assertIn("Igor", starter_names)
        self.assertNotIn("Rodrigo White", starter_names)
        self.assertEqual(candidate.tactics.formation, "4-2-3-1")

    def test_amiguinhos_evolved_ratings_survive_roster_reorder(self):
        candidate = load_team_v13("amiguinhos_u21")
        igor = next(player for player in candidate.starters if player.name == "Igor")
        white = next(player for player in candidate.bench if player.name == "Rodrigo White")
        self.assertEqual(igor.overall, 75)
        self.assertEqual(igor.pace, 82)
        self.assertEqual(white.overall, 77)
        self.assertEqual(white.crossing, 84)

    def test_flamengo_u20_pool_is_deterministic(self):
        first = load_team_v13("flamengo_u21")
        second = load_team_v13("flamengo_u21")
        first_rows = [
            (p.name, p.position, p.overall, p.pace, p.passing, p.finishing, p.tackling)
            for p in [*first.starters, *first.bench]
        ]
        second_rows = [
            (p.name, p.position, p.overall, p.pace, p.passing, p.finishing, p.tackling)
            for p in [*second.starters, *second.bench]
        ]
        self.assertEqual(first_rows, second_rows)

    def test_flamengo_is_on_shared_youth_scale_not_old_84_team_scale(self):
        candidate = load_team_v13("flamengo_u21")
        starter_average = sum(p.overall for p in candidate.starters) / len(candidate.starters)
        self.assertGreater(starter_average, 78.0)
        self.assertLess(starter_average, 82.0)
        self.assertEqual(max(p.overall for p in candidate.starters), 82)

    def test_flamengo_bench_contains_real_current_u20_options(self):
        candidate = load_team_v13("flamengo_u21")
        names = {player.name for player in candidate.bench}
        self.assertTrue(
            {
                "Pedro Batista",
                "Gustavo Ramires",
                "Rafael Henrique",
                "Andrew Nathan",
                "Douglas Telles",
                "Juliano",
                "Josmar",
                "Diego Queiroz",
            }.issubset(names)
        )


if __name__ == "__main__":
    unittest.main()
