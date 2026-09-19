from __future__ import annotations

import unittest

from engine import Event, EventType, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_awards import MatchEngineV13Awards
from engine_experiment_v13_leadership import MatchEngineV13Leadership
from engine_experiment_v13_set_piece_routines import MatchEngineV13SetPieceRoutines
from team_loader_v13 import load_team_v13


class LeadershipAndAwardsTests(unittest.TestCase):
    def engine(self, seed=10501):
        return MatchEngineV13Awards(
            load_team_v13("amiguinhos_u21"),
            make_generic_team("Away", 80, "balanced", seed=909),
            seed=seed,
        )

    def test_canonical_entrypoint_contains_leadership_and_awards(self):
        self.assertTrue(issubclass(MatchEngineV13Leadership, MatchEngineV13SetPieceRoutines))
        self.assertTrue(issubclass(MatchEngineV13Awards, MatchEngineV13Leadership))
        self.assertTrue(issubclass(CanonicalMatchEngine, MatchEngineV13Awards))

    def test_captain_is_derived_and_does_not_add_player_attribute(self):
        e = self.engine(10503)
        state = e.rng.getstate()
        before = {ps.player.name: dict(ps.player.__dict__) for ps in e.teams[0].on_field}
        diag = e.captain_diagnostic(0)
        self.assertTrue(diag["active"])
        self.assertGreater(diag["derived_leadership"], 0.0)
        self.assertEqual(state, e.rng.getstate())
        self.assertEqual(before, {ps.player.name: dict(ps.player.__dict__) for ps in e.teams[0].on_field})
        self.assertFalse(any(hasattr(ps.player, "leadership") for ps in e.teams[0].on_field))

    def test_captaincy_transfers_when_captain_leaves_field(self):
        e = self.engine(10505)
        old = e.captain_diagnostic(0)["captain"]
        ps = e.teams[0].by_name(old)
        e.teams[0].on_field.remove(ps)
        transfer = e._refresh_captain(0, reason="test")
        self.assertIsNotNone(transfer)
        self.assertEqual(transfer["from"], old)
        self.assertNotEqual(transfer["to"], old)
        self.assertTrue(e.captain_diagnostic(0)["active"])

    def test_leadership_stabilises_tendency_only_under_adversity(self):
        e = self.engine(10507)
        e.state.second = 86.0 * 60.0
        e.stats[0].goals, e.stats[1].goals = 0, 1
        diag = e.captain_context_diagnostic(0)
        self.assertGreater(diag["adversity"], 0.0)
        self.assertGreater(diag["stabilisation"], 0.0)

    def test_captain_state_survives_roundtrip(self):
        e = self.engine(10509)
        old = e.captain_diagnostic(0)["captain"]
        ps = e.teams[0].by_name(old)
        e.teams[0].on_field.remove(ps)
        e._refresh_captain(0, reason="test")
        clone = MatchEngineV13Awards.from_json(e.export_json())
        self.assertEqual(e._v13_captains, clone._v13_captains)
        self.assertEqual(e._v13_captain_history, clone._v13_captain_history)

    def test_no_event_log_has_no_artificial_man_of_match(self):
        e = self.engine(10511)
        awards = e.match_awards_diagnostic()
        self.assertIsNone(awards["man_of_the_match"])
        self.assertEqual(awards["basis"], "event_derived_match_rating")

    def test_goal_event_can_make_real_man_of_match(self):
        e = self.engine(10513)
        e.state.event_log.append(Event(42.0, 0, EventType.GOAL, 5, "goal", {"scorer": "Gabriel Félix", "xg": 0.22}))
        e.state.event_log.append(Event(30.0, 1, EventType.INFO, 0, "safe_pass", {"actor": e.teams[1].on_field[5].player.name}))
        awards = e.match_awards_diagnostic()
        self.assertEqual(awards["man_of_the_match"]["player"], "Gabriel Félix")
        self.assertTrue(awards["provisional"])

    def test_award_does_not_use_overall_as_tiebreak(self):
        e = self.engine(10515)
        low = min(e.teams[0].on_field, key=lambda ps: ps.player.overall)
        high = max(e.teams[0].on_field, key=lambda ps: ps.player.overall)
        e.state.event_log.append(Event(20.0, 0, EventType.INFO, 0, "safe_pass", {"actor": low.player.name}))
        e.state.event_log.append(Event(21.0, 0, EventType.INFO, 0, "safe_pass", {"actor": high.player.name}))
        lr = e.player_match_rating(0, low.player.name)
        hr = e.player_match_rating(0, high.player.name)
        self.assertEqual(lr["rating"], hr["rating"])
        self.assertEqual(lr["raw_impact"], hr["raw_impact"])

    def test_same_seed_remains_deterministic(self):
        a, b = self.engine(10517), self.engine(10517)
        for _ in range(30):
            ea, eb = a.step(), b.step()
            self.assertEqual((ea.minute, ea.team, ea.type.value, ea.text_key, ea.data), (eb.minute, eb.team, eb.type.value, eb.text_key, eb.data))
        self.assertEqual(a.export_state(), b.export_state())


if __name__ == "__main__":
    unittest.main()
