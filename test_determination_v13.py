from __future__ import annotations

import unittest

from engine import Band, Lane, Zone
from engine_experiment_v13 import MatchEngine
from team_loader import load_team as load_stable_team
from team_loader_v13 import load_team_v13


class DeterminationV13Tests(unittest.TestCase):
    def make_engine(self, seed=123):
        return MatchEngine(
            load_team_v13("amiguinhos_u21"),
            load_team_v13("flamengo_u21"),
            seed=seed,
        )

    def test_stable_v12_roster_is_not_boosted_or_given_determination(self):
        stable = load_stable_team("amiguinhos_u21")
        players = {p.name: p for p in [*stable.starters, *stable.bench]}
        adib = players["Gabriel Adib"]
        self.assertEqual(adib.overall, 79)
        self.assertEqual(adib.passing, 85)
        self.assertEqual(adib.aggression, 80)
        self.assertEqual(adib.discipline, 74)
        self.assertFalse(hasattr(adib, "determination"))

    def test_v13_amiguinhos_receive_explicit_boost_without_personality_rewrite(self):
        candidate = load_team_v13("amiguinhos_u21")
        players = {p.name: p for p in [*candidate.starters, *candidate.bench]}
        adib = players["Gabriel Adib"]
        felipe = players["Felipe"]
        self.assertEqual(adib.overall, 81)
        self.assertEqual(adib.passing, 88)
        self.assertEqual(adib.vision, 89)
        self.assertEqual(adib.aggression, 80)
        self.assertEqual(adib.discipline, 74)
        self.assertEqual(adib.determination, 93.0)
        self.assertEqual(felipe.determination, 94.0)
        self.assertEqual(felipe.aggression, 90)
        self.assertEqual(felipe.discipline, 52)

    def test_unconfigured_opponent_does_not_receive_amiguinhos_boost(self):
        stable = load_stable_team("flamengo_u21")
        candidate = load_team_v13("flamengo_u21")
        stable_players = {p.name: p for p in stable.starters}
        candidate_players = {p.name: p for p in candidate.starters}
        for name in stable_players:
            self.assertEqual(candidate_players[name].overall, stable_players[name].overall)
            self.assertEqual(candidate_players[name].passing, stable_players[name].passing)
            self.assertFalse(hasattr(candidate_players[name], "determination"))

    def test_determination_changes_willingness_only_under_adversity(self):
        e = self.make_engine()
        actor = e.teams[0].by_name("Gabriel Adib")
        zone = Zone(Band.ATT, Lane.CENTER)
        tactics = e.teams[0].team.tactics
        ctx = {
            "pressure": 0.72,
            "space": 0.43,
            "space_behind": 0.55,
            "support": 0.50,
            "transition_threat": 0.48,
        }
        e.state.second = 80 * 60
        e.stats[0].goals = 0
        e.stats[1].goals = 1
        actor.energy = 0.48

        original_passing = actor.effective("passing")
        actor.player.determination = 95.0
        high = dict(e._decision_weights(actor, zone, tactics, ctx))
        actor.player.determination = 40.0
        low = dict(e._decision_weights(actor, zone, tactics, ctx))

        proactive = {"progressive_pass", "carry", "through_ball", "dribble", "shoot"}
        self.assertGreater(sum(high.get(k, 0.0) for k in proactive), sum(low.get(k, 0.0) for k in proactive))
        self.assertLess(high["safe_pass"], low["safe_pass"])
        self.assertEqual(actor.effective("passing"), original_passing)

    def test_high_determination_reduces_fatigue_driven_defensive_error_risk(self):
        e = self.make_engine()
        defender = e.teams[0].by_name("Jorge Henrique")
        defender.energy = 0.42
        e.state.second = 82 * 60
        e.stats[0].goals = 0
        e.stats[1].goals = 1
        zone = Zone(Band.ATT, Lane.CENTER)
        ctx = {
            "pressure": 0.64,
            "space": 0.58,
            "space_behind": 0.60,
            "support": 0.58,
            "defending_availability": 0.82,
        }
        plan = {"defender": defender, "intent": "contain", "quality": 0.70}

        defender.player.determination = 95.0
        high = e._defensive_error_profile(1, zone, ctx, plan, kind="dribble", target=None)
        defender.player.determination = 40.0
        low = e._defensive_error_profile(1, zone, ctx, plan, kind="dribble", target=None)

        self.assertLess(high["risk"], low["risk"])
        self.assertGreater(high["determination_resilience"], low["determination_resilience"])

    def test_determination_and_boost_survive_candidate_roundtrip(self):
        e = self.make_engine(seed=77)
        restored = MatchEngine.from_json(e.export_json())
        original = e.teams[0].by_name("Gabriel Adib").player
        replay = restored.teams[0].by_name("Gabriel Adib").player
        self.assertEqual(replay.determination, original.determination)
        self.assertEqual(replay.passing, original.passing)
        self.assertEqual(replay.overall, original.overall)

    def test_same_seed_remains_reproducible(self):
        e1 = self.make_engine(seed=811)
        e2 = self.make_engine(seed=811)
        for _ in range(200):
            if e1.state.ended or e2.state.ended:
                break
            a = e1.step()
            b = e2.step()
            self.assertEqual((a.type, a.team, a.text_key, a.data), (b.type, b.team, b.text_key, b.data))
        self.assertEqual(e1.snapshot(), e2.snapshot())


if __name__ == "__main__":
    unittest.main()
