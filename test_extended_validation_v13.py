from __future__ import annotations

import copy
import random
import unittest

from engine import Band, Lane, Zone
from engine_experiment_v13 import MatchEngine
from evaluation_v13 import (
    evaluation_schedule,
    run_adaptation_ab,
    run_broad_evaluation,
    run_knockout_stress,
    tournament_teams,
)
from final_protocol_v13 import OFFICIAL_FINAL_SEED
from team_loader import load_team as load_stable_team
from team_loader_v13 import load_team_v13, load_v13_trait_database


class ExtendedV13ValidationTests(unittest.TestCase):
    def make_engine(self, home="amiguinhos_u21", away="flamengo_u21", seed=123):
        return MatchEngine(load_team_v13(home), load_team_v13(away), seed=seed)

    def test_evaluation_schedule_covers_every_opponent_twice(self):
        teams = tournament_teams()
        opponents = set(teams) - {"amiguinhos_u21"}
        schedule = evaluation_schedule(count_per_orientation=3, base_seed=1000)
        self.assertEqual(len(schedule), 2 * len(opponents))
        for opponent in opponents:
            rows = [row for row in schedule if row["opponent"] == opponent]
            self.assertEqual(len(rows), 2)
            self.assertEqual({(r["home_key"], r["away_key"]) for r in rows}, {
                ("amiguinhos_u21", opponent),
                (opponent, "amiguinhos_u21"),
            })
            self.assertEqual(rows[0]["start_seed"], rows[1]["start_seed"])

    def test_evaluation_schedule_is_deterministic_and_never_uses_official_seed(self):
        first = evaluation_schedule(count_per_orientation=5, base_seed=1000)
        second = evaluation_schedule(count_per_orientation=5, base_seed=1000)
        self.assertEqual(first, second)
        used = {
            seed
            for row in first
            for seed in range(row["start_seed"], row["start_seed"] + row["count"])
        }
        self.assertNotIn(OFFICIAL_FINAL_SEED, used)
        with self.assertRaises(AssertionError):
            evaluation_schedule(count_per_orientation=1, base_seed=OFFICIAL_FINAL_SEED)

    def test_small_broad_evaluation_retains_all_results(self):
        report = run_broad_evaluation(count_per_orientation=1, base_seed=40000)
        expected = 2 * (len(tournament_teams()) - 1)
        self.assertEqual(report["total_matches"], expected)
        results = report["overall_results"]
        self.assertEqual(results["wins"] + results["draws"] + results["losses"], expected)
        self.assertEqual(len(report["by_opponent"]), len(tournament_teams()) - 1)
        self.assertEqual(len(report["rows"]), 2 * (len(tournament_teams()) - 1))

    def test_adaptation_ab_uses_same_unfiltered_seed_range(self):
        report = run_adaptation_ab(count=2, start_seed=45000)
        self.assertEqual(report["count"], 2)
        self.assertEqual(report["start_seed"], 45000)
        self.assertEqual(report["without_adaptation"]["count"], 2)
        self.assertEqual(report["with_adaptation"]["count"], 2)
        self.assertFalse(report["without_adaptation"]["auto_adapt"])
        self.assertTrue(report["with_adaptation"]["auto_adapt"])
        self.assertNotEqual(report["official_seed_quarantined"], 45000)

    def test_knockout_stress_resolves_every_match_without_official_seed(self):
        report = run_knockout_stress(count=3, start_seed=46000, auto_adapt=True)
        self.assertEqual(sum(report["winners"].values()), 3)
        self.assertEqual(sum(report["decided_by"].values()), 3)
        self.assertTrue(report["allow_extra_time"])
        self.assertTrue(report["auto_adapt"])
        self.assertNotEqual(report["official_seed_quarantined"], 46000)

    def test_zero_adversity_makes_determination_behaviorally_neutral(self):
        engine = self.make_engine()
        actor = engine.teams[0].by_name("Gabriel Adib")
        actor.energy = 1.0
        engine.state.second = 0.0
        engine.stats[0].goals = engine.stats[1].goals = 0
        zone = Zone(Band.ATT, Lane.CENTER)
        ctx = {
            "pressure": 0.0,
            "space": 0.55,
            "space_behind": 0.52,
            "support": 0.55,
            "transition_threat": 0.45,
        }
        tactics = engine.teams[0].team.tactics
        actor.player.determination = 100.0
        high = engine._decision_weights(actor, zone, tactics, ctx)
        actor.player.determination = 0.0
        low = engine._decision_weights(actor, zone, tactics, ctx)
        self.assertEqual(high, low)
        self.assertEqual(engine.determination_diagnostic(0, actor, ctx)["adversity"], 0.0)

    def test_determination_drive_is_monotonic_under_fixed_adversity(self):
        engine = self.make_engine()
        actor = engine.teams[0].by_name("Gabriel Adib")
        actor.energy = 0.45
        engine.state.second = 82 * 60
        engine.stats[0].goals = 0
        engine.stats[1].goals = 1
        ctx = {"pressure": 0.75}
        drives = []
        for value in (20.0, 50.0, 80.0, 100.0):
            actor.player.determination = value
            drives.append(engine.determination_diagnostic(0, actor, ctx)["drive"])
        self.assertEqual(drives, sorted(drives))
        self.assertLess(drives[0], 0.0)
        self.assertAlmostEqual(drives[1], 0.0, places=12)
        self.assertGreater(drives[-1], 0.0)

    def test_determination_diagnostic_is_rng_pure_and_attribute_pure(self):
        engine = self.make_engine(seed=987)
        actor = engine.teams[0].by_name("Gabriel Adib")
        engine.state.second = 78 * 60
        actor.energy = 0.51
        before_rng = engine.rng.getstate()
        before_player = copy.deepcopy(actor.player.__dict__)
        before_energy = actor.energy
        _ = engine.determination_diagnostic(0, actor, {"pressure": 0.81})
        self.assertEqual(engine.rng.getstate(), before_rng)
        self.assertEqual(actor.player.__dict__, before_player)
        self.assertEqual(actor.energy, before_energy)

    def test_unconfigured_player_uses_universal_bounded_fallback(self):
        engine = self.make_engine()
        opponent = engine.teams[1].by_name("André Vidal")
        self.assertFalse(hasattr(opponent.player, "determination"))
        value = engine._determination(opponent)
        self.assertGreaterEqual(value, 0.0)
        self.assertLessEqual(value, 1.0)
        self.assertGreater(value, 0.40)

    def test_penalty_determination_effect_is_monotonic_but_small(self):
        engine = self.make_engine()
        taker = engine.teams[0].by_name("Mike Junior")
        keeper = engine._shootout_keeper(1)
        probs = []
        for value in (30.0, 50.0, 95.0):
            taker.player.determination = value
            probs.append(engine._penalty_conversion_probability(taker, keeper))
        self.assertLess(probs[0], probs[1])
        self.assertLess(probs[1], probs[2])
        self.assertLessEqual(probs[2] - probs[0], 0.0121)

    def test_literal_v13_attributes_match_json_exactly_for_entire_roster(self):
        database = load_v13_trait_database()
        player_data = database["teams"]["amiguinhos_u21"]["players"]
        stable = load_stable_team("amiguinhos_u21")
        candidate = load_team_v13("amiguinhos_u21")
        stable_players = {p.name: p for p in [*stable.starters, *stable.bench]}
        candidate_players = {p.name: p for p in [*candidate.starters, *candidate.bench]}
        self.assertEqual(set(stable_players), set(candidate_players))
        self.assertEqual(set(player_data), set(candidate_players))

        changed = 0
        for name, candidate_player in candidate_players.items():
            expected_attributes = player_data[name]["attributes"]
            for attr, expected in expected_attributes.items():
                self.assertEqual(getattr(candidate_player, attr), int(expected), f"{name}:{attr}")
                self.assertLessEqual(getattr(candidate_player, attr), 95)
                if getattr(stable_players[name], attr) != int(expected):
                    changed += 1
        self.assertGreater(changed, 0)

    def test_v13_loader_does_not_treat_literal_values_as_deltas(self):
        database = load_v13_trait_database()
        adib_data = database["teams"]["amiguinhos_u21"]["players"]["Gabriel Adib"]
        stable = load_stable_team("amiguinhos_u21")
        candidate = load_team_v13("amiguinhos_u21")
        stable_adib = {p.name: p for p in [*stable.starters, *stable.bench]}["Gabriel Adib"]
        candidate_adib = {p.name: p for p in [*candidate.starters, *candidate.bench]}["Gabriel Adib"]

        self.assertEqual(candidate_adib.passing, adib_data["attributes"]["passing"])
        self.assertNotEqual(candidate_adib.passing, stable_adib.passing + adib_data["attributes"]["passing"])
        self.assertEqual(candidate_adib.overall, adib_data["attributes"]["overall"])

    def test_every_amiguinhos_player_has_explicit_determination(self):
        team = load_team_v13("amiguinhos_u21")
        players = [*team.starters, *team.bench]
        self.assertTrue(players)
        for player in players:
            self.assertTrue(hasattr(player, "determination"), player.name)
            self.assertGreaterEqual(player.determination, 0.0)
            self.assertLessEqual(player.determination, 100.0)

    def test_all_roster_determination_values_survive_roundtrip(self):
        engine = self.make_engine(seed=55)
        restored = MatchEngine.from_json(engine.export_json())
        original = {ps.player.name: getattr(ps.player, "determination", None) for ps in engine.teams[0].on_field}
        replay = {ps.player.name: getattr(ps.player, "determination", None) for ps in restored.teams[0].on_field}
        self.assertEqual(replay, original)

    def test_short_multimatch_invariant_stress_across_strengths(self):
        opponents = ("ajax_u21", "psg_u21", "flamengo_u21", "real_madrid_u21")
        for opponent in opponents:
            for seed in range(600, 604):
                engine = self.make_engine(away=opponent, seed=seed)
                guard = 0
                while not engine.state.ended and guard < 5000:
                    engine.step()
                    guard += 1
                self.assertLess(guard, 5000)
                self.assertEqual(engine.score, (engine.stats[0].goals, engine.stats[1].goals))
                for stats in engine.stats:
                    self.assertGreaterEqual(stats.shots, stats.on_target)
                    self.assertGreaterEqual(stats.on_target, stats.goals)
                    self.assertGreaterEqual(stats.xg, 0.0)
                minutes = [event.minute for event in engine.state.event_log]
                self.assertEqual(minutes, sorted(minutes))
                for runtime in engine.teams:
                    for player_state in runtime.on_field:
                        self.assertGreaterEqual(player_state.energy, 0.18)
                        self.assertLessEqual(player_state.energy, 1.0)


if __name__ == "__main__":
    unittest.main()
