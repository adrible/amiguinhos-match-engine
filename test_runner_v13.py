from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from engine import Event, EventType
from engine_experiment_v13 import MatchEngine
from final_protocol_v13 import OFFICIAL_FINAL_SEED
from narration_packet_v13 import (
    _sanitize_data,
    build_narration_packet,
    continuity_snapshot,
    event_fact,
)
from runner_v13 import MatchSessionV13, event_view
from team_loader_v13 import load_team_v13


class LiveRunnerTests(unittest.TestCase):
    def test_new_session_is_pristine_and_does_not_presimulate(self):
        session = MatchSessionV13.from_fixture(seed=17)
        self.assertTrue(session.pristine)
        self.assertEqual(session.engine.minute, 0.0)
        self.assertEqual(session.engine.state.event_log, [])
        self.assertIsNone(session.engine.state.pending)
        self.assertIsNone(session.engine.state.restart)
        self.assertEqual(sum(st.shots for st in session.engine.stats), 0)
        self.assertEqual(sum(st.goals for st in session.engine.stats), 0)

    def test_default_runner_venue_is_neutral(self):
        session = MatchSessionV13.from_fixture(seed=171)
        venue = session.snapshot()["venue"]
        self.assertEqual(venue["mode"], "neutral")
        self.assertAlmostEqual(venue["home_effects"]["pressure_shift"], 0.0, places=6)
        self.assertAlmostEqual(venue["away_effects"]["pressure_shift"], 0.0, places=6)

    def test_runner_can_request_explicit_home_away_context(self):
        session = MatchSessionV13.from_fixture(seed=172, venue_mode="home_away")
        venue = session.snapshot()["venue"]
        self.assertEqual(venue["mode"], "home_away")
        self.assertLess(venue["home_effects"]["pressure_shift"], 0.0)
        self.assertGreater(venue["away_effects"]["pressure_shift"], 0.0)
        self.assertTrue(session.pristine)

    def test_snapshot_does_not_advance_live_match(self):
        session = MatchSessionV13.from_fixture(seed=18)
        before_rng = session.engine.rng.getstate()
        before = session.engine.export_state()
        _ = session.snapshot()
        self.assertEqual(before_rng, session.engine.rng.getstate())
        self.assertEqual(before, session.engine.export_state())
        self.assertTrue(session.pristine)

    def test_first_p_advances_only_when_requested(self):
        session = MatchSessionV13.from_fixture(seed=19)
        self.assertTrue(session.pristine)
        event = session.press_p()
        self.assertGreater(session.engine.state.second, 0.0)
        self.assertGreater(len(session.engine.state.event_log), 0)
        self.assertFalse(session.pristine)
        self.assertIsNotNone(event)

    def test_p_matches_direct_live_engine_for_same_seed(self):
        seed = 23
        session = MatchSessionV13.from_fixture(seed=seed)
        direct = MatchEngine(
            load_team_v13("amiguinhos_u21"),
            load_team_v13("flamengo_u21"),
            seed=seed,
        )
        for _ in range(12):
            if session.engine.state.ended or direct.state.ended:
                break
            a = session.press_p()
            b = direct.advance_until_relevant()
            self.assertEqual(
                (a.type, a.team, a.relevance, a.text_key, a.data),
                (b.type, b.team, b.relevance, b.text_key, b.data),
            )
            self.assertEqual(session.engine.export_state(), direct.export_state())

    def test_relevance_override_is_one_press_only(self):
        session = MatchSessionV13.from_fixture(seed=24)
        event = session.press_p(min_relevance=4)
        self.assertTrue(
            event.relevance >= 4
            or event.type in {EventType.PERIOD_END, EventType.MATCH_END}
        )
        self.assertEqual(session.engine.config.relevant_threshold, 2)

    def test_save_load_then_p_matches_uninterrupted_session(self):
        original = MatchSessionV13.from_fixture(seed=29, auto_adapt=True)
        for _ in range(8):
            if original.engine.state.ended:
                break
            original.press_p()

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "match.json"
            original.save(path)
            restored = MatchSessionV13.load(path)
            self.assertEqual(original.engine.export_state(), restored.engine.export_state())

            for _ in range(10):
                if original.engine.state.ended or restored.engine.state.ended:
                    break
                a = original.press_p()
                b = restored.press_p()
                self.assertEqual(
                    (a.type, a.team, a.relevance, a.text_key, a.data),
                    (b.type, b.team, b.relevance, b.text_key, b.data),
                )
                self.assertEqual(
                    original.engine.export_state(), restored.engine.export_state()
                )

    def test_export_import_in_memory_preserves_candidate_class(self):
        session = MatchSessionV13.from_fixture(seed=31)
        session.press_p()
        restored = MatchSessionV13.from_json(session.export_json())
        self.assertIsInstance(restored.engine, MatchEngine)
        self.assertEqual(session.engine.export_state(), restored.engine.export_state())

    def test_event_view_is_presentation_only(self):
        session = MatchSessionV13.from_fixture(seed=37)
        event = session.press_p()
        before_rng = session.engine.rng.getstate()
        before = session.engine.export_state()
        view = event_view(event, session)
        self.assertEqual(view["text_key"], event.text_key)
        self.assertEqual(view["score"]["home_goals"], session.engine.stats[0].goals)
        self.assertEqual(before_rng, session.engine.rng.getstate())
        self.assertEqual(before, session.engine.export_state())

    def test_normal_runner_rejects_reserved_official_final_seed(self):
        with self.assertRaisesRegex(RuntimeError, "official final seed is reserved"):
            MatchSessionV13.from_fixture(seed=OFFICIAL_FINAL_SEED)

    def test_nonofficial_knockout_session_can_enable_extra_time(self):
        session = MatchSessionV13.from_fixture(seed=41, allow_extra_time=True)
        self.assertTrue(session.engine.config.allow_extra_time)
        self.assertFalse(session.engine.config.auto_tactical_adaptation)
        self.assertTrue(session.pristine)

    # ---------------- narration packet regressions ----------------

    def test_restored_narrator_clock_is_anchored_to_live_engine_clock(self):
        session = MatchSessionV13.from_fixture(seed=43)
        for _ in range(6):
            if session.engine.state.ended:
                break
            session.press_p()
        restored = MatchSessionV13.from_json(session.export_json())
        self.assertGreater(restored.engine.state.second, 0.0)
        self.assertAlmostEqual(
            restored.narrator_state.last_display_second,
            restored.engine.state.second,
            places=6,
        )
        self.assertEqual(
            restored.narrator_state.consumed_log_index,
            len(restored.engine.state.event_log),
        )

    def test_narration_sanitization_is_recursive(self):
        raw = {
            "actor": "Oscar",
            "danger": 0.91,
            "nested": {
                "xg": 0.42,
                "target": "Fred",
                "probability": 0.73,
            },
            "sequence": [
                {"kind": "shoot", "execution": 0.81},
                {"kind": "pass", "receiver": "Hulk", "chance_quality": 0.55},
            ],
        }
        clean = _sanitize_data(raw)
        self.assertEqual(clean["actor"], "Oscar")
        self.assertNotIn("danger", clean)
        self.assertEqual(clean["nested"], {"target": "Fred"})
        self.assertEqual(clean["sequence"][0], {"kind": "shoot"})
        self.assertEqual(
            clean["sequence"][1],
            {"kind": "pass", "receiver": "Hulk"},
        )

    def test_foul_fact_never_preannounces_card(self):
        session = MatchSessionV13.from_fixture(seed=44)
        event = Event(
            12.5,
            0,
            EventType.FOUL,
            2,
            "advantage_played",
            {
                "attacker": "Remo",
                "defender": "Opponent",
                "advantage": True,
                "card": "yellow",
                "danger": 0.77,
            },
        )
        fact = event_fact(event, session)
        self.assertTrue(fact["facts"]["advantage"])
        self.assertNotIn("card", fact["facts"])
        self.assertNotIn("danger", fact["facts"])

    def test_duplicate_public_card_is_suppressed(self):
        session = MatchSessionV13.from_fixture(seed=45)
        state = session.narrator_state

        first = Event(
            10.0,
            0,
            EventType.CARD,
            2,
            "card_shown_contextual",
            {"player": "Jorge", "card": "yellow"},
        )
        before = continuity_snapshot(session.engine)
        session.engine.state.event_log.append(first)
        first_packet = build_narration_packet(session, first, state, before)
        self.assertTrue(first_packet["narrate"])

        duplicate = Event(
            10.5,
            0,
            EventType.CARD,
            2,
            "deferred_card_after_advantage",
            {"player": "Jorge", "card": "yellow"},
        )
        before = continuity_snapshot(session.engine)
        session.engine.state.event_log.append(duplicate)
        duplicate_packet = build_narration_packet(session, duplicate, state, before)
        self.assertFalse(duplicate_packet["narrate"])
        self.assertEqual(duplicate_packet["skip_reason"], "card_already_narrated")

    def test_pending_continuity_does_not_expose_danger(self):
        session = MatchSessionV13.from_fixture(seed=46)
        # Find a live pending action naturally; do not alter physics to create it.
        for _ in range(40):
            if session.engine.state.ended or session.engine.state.pending is not None:
                break
            session.engine.step()
        snapshot = continuity_snapshot(session.engine)
        pending = snapshot["pending"]
        if pending is not None:
            self.assertNotIn("danger", pending)
            self.assertFalse(any("probability" in key.lower() for key in pending))


if __name__ == "__main__":
    unittest.main()
