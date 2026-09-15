from __future__ import annotations

import unittest

from engine import Band, EventType, Lane, PendingAction, Player, Tactics, Team, Zone
from engine_experiment_v13_substitutions import MatchEngineV13Substitutions


def mk_player(name: str, position: str, overall: int = 76, **attrs) -> Player:
    payload = dict(
        name=name,
        position=position,
        overall=overall,
        pace=overall,
        passing=overall,
        vision=overall,
        technique=overall,
        dribbling=overall,
        crossing=overall,
        finishing=overall,
        long_shots=overall,
        heading=overall,
        strength=overall,
        tackling=overall,
        positioning=overall,
        anticipation=overall,
        composure=overall,
        off_ball=overall,
        stamina=overall,
        aggression=60,
        discipline=72,
    )
    payload.update(attrs)
    return Player(**payload)


def make_team(prefix: str) -> Team:
    starters = [
        mk_player(f"{prefix}_GK", "GK", 76),
        mk_player(f"{prefix}_RB", "RB", 75),
        mk_player(f"{prefix}_CB1", "CB", 77),
        mk_player(f"{prefix}_CB2", "CB", 76),
        mk_player(f"{prefix}_LB", "LB", 75),
        mk_player(f"{prefix}_DM", "DM", 76),
        mk_player(f"{prefix}_CM", "CM", 77),
        mk_player(f"{prefix}_AM", "AM", 78),
        mk_player(f"{prefix}_RW", "RW", 77),
        mk_player(f"{prefix}_LW", "LW", 77),
        mk_player(f"{prefix}_ST", "ST", 79),
    ]
    bench = [
        mk_player(f"{prefix}_B_GK", "GK", 74),
        mk_player(f"{prefix}_B_CB", "CB", 76),
        mk_player(f"{prefix}_B_CM", "CM", 76),
        mk_player(f"{prefix}_B_AM", "AM", 77),
        mk_player(f"{prefix}_B_W", "RW", 77),
        mk_player(f"{prefix}_B_ST", "ST", 78),
    ]
    return Team(prefix, starters=starters, bench=bench, tactics=Tactics())


def make_engine(seed: int = 7) -> MatchEngineV13Substitutions:
    return MatchEngineV13Substitutions(make_team("A"), make_team("B"), seed=seed)


def open_stoppage(engine: MatchEngineV13Substitutions, minute: float) -> None:
    engine.state.second = minute * 60.0
    engine.state.restart = "free_kick"
    engine.state.restart_team = 0
    engine.state.restart_zone = Zone(Band.MID, Lane.CENTER)


class AutomaticSubstitutionTests(unittest.TestCase):
    def test_non_emergency_first_half_change_is_forbidden(self):
        engine = make_engine()
        open_stoppage(engine, 35.0)
        cm = engine.teams[0].by_name("A_CM")
        cm.energy = 0.05
        cm.yellow = 1
        self.assertIsNone(engine.auto_substitution_diagnostic())
        self.assertIsNone(engine._maybe_auto_substitution())
        self.assertEqual(engine.teams[0].substitutions, 0)

    def test_first_half_injury_can_force_change(self):
        engine = make_engine()
        open_stoppage(engine, 28.0)
        cm = engine.teams[0].by_name("A_CM")
        cm.injured = True

        event = engine._maybe_auto_substitution()

        self.assertIsNotNone(event)
        self.assertEqual(event.type, EventType.SUBSTITUTION)
        self.assertEqual(event.team, 0)
        self.assertEqual(event.data["reason"], "injury")
        self.assertTrue(event.data["auto"])
        self.assertEqual(engine.teams[0].substitutions, 1)
        self.assertNotIn("A_CM", [ps.player.name for ps in engine.teams[0].on_field])

    def test_pending_live_action_blocks_automatic_change(self):
        engine = make_engine()
        open_stoppage(engine, 70.0)
        cm = engine.teams[0].by_name("A_CM")
        cm.energy = 0.40
        engine.state.pending = PendingAction(
            team=0,
            actor="A_ST",
            kind="shoot",
            zone=Zone(Band.BOX, Lane.CENTER),
            danger=0.7,
            pressure=0.5,
        )
        self.assertIsNone(engine._maybe_auto_substitution())
        self.assertEqual(engine.teams[0].substitutions, 0)

    def test_second_half_fatigue_triggers_change_at_stoppage(self):
        engine = make_engine()
        open_stoppage(engine, 70.0)
        cm = engine.teams[0].by_name("A_CM")
        cm.energy = 0.48

        diagnostic = engine.auto_substitution_diagnostic()
        self.assertIsNotNone(diagnostic)
        self.assertEqual(diagnostic["team"], 0)
        self.assertEqual(diagnostic["out"], "A_CM")
        self.assertEqual(diagnostic["reason"], "fatigue")

        event = engine.step()
        self.assertEqual(event.type, EventType.SUBSTITUTION)
        self.assertEqual(event.data["out"], "A_CM")
        self.assertEqual(event.data["reason"], "fatigue")
        self.assertEqual(engine.state.restart, "free_kick")

    def test_same_team_cannot_chain_normal_changes_at_same_stoppage(self):
        engine = make_engine()
        open_stoppage(engine, 72.0)
        engine.teams[0].by_name("A_CM").energy = 0.42
        first = engine._maybe_auto_substitution()
        self.assertIsNotNone(first)

        engine.teams[0].by_name("A_AM").energy = 0.40
        second = engine._maybe_auto_substitution()
        self.assertIsNone(second)
        self.assertEqual(engine.teams[0].substitutions, 1)

    def test_exact_role_fit_beats_unusable_high_overall_bench_player(self):
        engine = make_engine()
        open_stoppage(engine, 70.0)
        rt = engine.teams[0]
        rt.by_name("A_CM").energy = 0.45
        rt.bench = [
            mk_player("Exact_CM", "CM", 72),
            mk_player("Star_CB", "CB", 95),
        ]

        diagnostic = engine.auto_substitution_diagnostic()
        self.assertIsNotNone(diagnostic)
        self.assertEqual(diagnostic["out"], "A_CM")
        self.assertEqual(diagnostic["in"], "Exact_CM")
        self.assertEqual(diagnostic["role_fit"], 1.0)

    def test_trailing_context_prefers_more_attacking_compatible_option(self):
        engine = make_engine()
        open_stoppage(engine, 75.0)
        engine.stats[1].goals = 1
        rt = engine.teams[0]
        rt.bench = [
            mk_player(
                "Attack_CM", "CM", 77,
                pace=88, passing=87, vision=90, dribbling=88,
                off_ball=88, finishing=82, tackling=55, positioning=60,
            ),
            mk_player(
                "Control_CM", "CM", 77,
                pace=70, passing=75, vision=72, dribbling=68,
                off_ball=68, finishing=58, tackling=88, positioning=88,
            ),
        ]

        diagnostic = engine.auto_substitution_diagnostic()
        self.assertIsNotNone(diagnostic)
        self.assertEqual(diagnostic["reason"], "tactical_chase")
        self.assertEqual(diagnostic["in"], "Attack_CM")
        self.assertGreater(diagnostic["context_gain"], 0.0)

    def test_leading_context_prefers_more_defensive_compatible_option(self):
        engine = make_engine()
        open_stoppage(engine, 76.0)
        engine.stats[0].goals = 1
        rt = engine.teams[0]
        rt.bench = [
            mk_player(
                "Attack_CM", "CM", 77,
                pace=88, passing=88, vision=90, dribbling=88,
                off_ball=88, finishing=84, tackling=54, positioning=58,
                anticipation=66, strength=65, discipline=65,
            ),
            mk_player(
                "Defend_CM", "CM", 77,
                pace=70, passing=73, vision=70, dribbling=66,
                off_ball=65, finishing=55, tackling=90, positioning=90,
                anticipation=89, stamina=86, strength=84, discipline=86,
            ),
        ]

        diagnostic = engine.auto_substitution_diagnostic()
        self.assertIsNotNone(diagnostic)
        self.assertEqual(diagnostic["reason"], "tactical_protect")
        self.assertEqual(diagnostic["in"], "Defend_CM")
        self.assertGreater(diagnostic["context_gain"], 0.0)

    def test_auto_substitution_setting_survives_roundtrip(self):
        engine = make_engine()
        engine.auto_substitutions_enabled = False
        restored = MatchEngineV13Substitutions.from_json(engine.export_json())
        self.assertFalse(restored.auto_substitutions_enabled)
        self.assertEqual(engine.export_state(), restored.export_state())

    def test_same_seed_remains_reproducible_with_auto_substitutions(self):
        first = make_engine(seed=91)
        second = make_engine(seed=91)
        for _ in range(250):
            if first.state.ended or second.state.ended:
                break
            a = first.step()
            b = second.step()
            self.assertEqual(
                (a.type, a.team, a.relevance, a.text_key, a.data),
                (b.type, b.team, b.relevance, b.text_key, b.data),
            )
        self.assertEqual(first.export_state(), second.export_state())


if __name__ == "__main__":
    unittest.main()
