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
        adib = next(p for p in team.starters if p.name == "Gabriel Adib")
        self.assertEqual(adib.overall, 79)
        self.assertEqual(adib.vision, 86)
        remo = next(p for p in team.starters if p.name == "Remo")
        self.assertEqual(remo.preferred_foot, "L")

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
