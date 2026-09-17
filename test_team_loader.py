import unittest

from team_loader import list_teams, load_team


class TeamLoaderTests(unittest.TestCase):
    def test_database_contains_all_16_tournament_teams(self):
        self.assertEqual(len(list_teams()), 16)

    def test_load_amiguinhos_explicit_roster(self):
        team = load_team("amiguinhos_u21")
        self.assertEqual(team.name, "🦆 Amiguinhos U21")
        self.assertEqual(len(team.starters), 11)
        self.assertEqual(len(team.bench), 3)

        # Pre-final ratings: the XI must average 81.6 when rounded to one decimal.
        self.assertEqual(round(sum(p.overall for p in team.starters) / 11, 1), 81.6)

        adib = next(p for p in team.starters if p.name == "Gabriel Adib")
        self.assertEqual(adib.overall, 85)
        self.assertEqual(adib.vision, 90)

        remo = next(p for p in team.starters if p.name == "Remo")
        self.assertEqual(remo.overall, 84)
        self.assertEqual(remo.preferred_foot, "L")

        # Defensive hierarchy before the final: Igor partners Leo at CB;
        # Joao starts at LB for the more defensive setup; White is his
        # more attacking option from the bench.
        starter_names = {p.name for p in team.starters}
        bench_names = {p.name for p in team.bench}
        self.assertIn("Léo", starter_names)
        self.assertIn("Igor", starter_names)
        self.assertIn("João Peixoto", starter_names)
        self.assertNotIn("Rodrigo White", starter_names)
        self.assertIn("Rodrigo White", bench_names)

        igor = next(p for p in team.starters if p.name == "Igor")
        joao = next(p for p in team.starters if p.name == "João Peixoto")
        white = next(p for p in team.bench if p.name == "Rodrigo White")
        self.assertEqual(igor.position, "CB")
        self.assertEqual(igor.overall, 81)
        self.assertEqual(joao.position, "LB")
        self.assertEqual(joao.overall, 80)
        self.assertEqual(white.position, "LB")
        self.assertEqual(white.overall, 81)
        self.assertGreater(white.crossing, joao.crossing)
        self.assertGreater(white.dribbling, joao.dribbling)
        self.assertGreater(joao.strength, white.strength)
        self.assertGreater(joao.tackling, white.tackling)

    def test_load_flamengo_explicit_roster(self):
        team = load_team("flamengo_u21")
        self.assertEqual(len(team.starters), 11)
        lins = next(p for p in team.starters if p.name == "Pedro Lins")
        self.assertEqual(lins.overall, 85)

    def test_load_generic_team_from_same_json(self):
        team = load_team("inter_u21")
        self.assertEqual(team.name, "Inter U21")
        self.assertEqual(len(team.starters), 11)
        self.assertGreaterEqual(len(team.bench), 1)

    def test_unknown_team_raises(self):
        with self.assertRaises(KeyError):
            load_team("nao_existe")


if __name__ == "__main__":
    unittest.main()
