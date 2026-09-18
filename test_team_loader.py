import unittest

from team_loader import list_teams, load_team


TOURNAMENT_TEAMS = {
    "amiguinhos_u21",
    "flamengo_u21",
    "ajax_u21",
    "psg_u21",
    "real_madrid_u21",
    "dortmund_u21",
    "barcelona_u21",
    "benfica_u21",
    "river_plate_u21",
    "porto_u21",
    "palmeiras_u21",
    "boca_juniors_u21",
    "liverpool_u21",
    "inter_u21",
    "man_city_u21",
    "bayern_u21",
}


class TeamLoaderTests(unittest.TestCase):
    def test_database_contains_all_16_tournament_teams(self):
        teams = set(list_teams())
        self.assertTrue(TOURNAMENT_TEAMS.issubset(teams))

    def test_database_allows_extra_fixture_teams(self):
        teams = set(list_teams())
        self.assertIn("brazil_2002", teams)
        self.assertIn("danganlock", teams)

    def test_load_amiguinhos_explicit_roster(self):
        team = load_team("amiguinhos_u21")
        self.assertEqual(team.name, "🦆 Amiguinhos U21")
        self.assertEqual(len(team.starters), 11)
        self.assertEqual(len(team.bench), 3)
        self.assertEqual(round(sum(p.overall for p in team.starters) / 11, 1), 81.6)

        adib = next(p for p in team.starters if p.name == "Gabriel Adib")
        self.assertEqual(adib.overall, 85)
        self.assertEqual(adib.vision, 90)
        self.assertEqual(adib.passing, 89)

        remo = next(p for p in team.starters if p.name == "Remo")
        self.assertEqual(remo.overall, 84)
        self.assertEqual(remo.preferred_foot, "L")

        starters = {p.name for p in team.starters}
        bench = {p.name for p in team.bench}
        self.assertIn("Igor", starters)
        self.assertIn("João Peixoto", starters)
        self.assertIn("Rodrigo White", bench)

    def test_load_flamengo_base_roster(self):
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
