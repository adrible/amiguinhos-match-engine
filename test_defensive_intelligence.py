from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13_defense import MatchEngineV13Defense


CTX = {
    "pressure": 0.45,
    "space": 0.55,
    "space_behind": 0.75,
    "support": 0.50,
    "wide_space": 0.10,
}


def engine_with_defense(strength=79, seed=123):
    a = make_generic_team("Attack", 79, "balanced", seed=10)
    b = make_generic_team("Defence", strength, "balanced", seed=20)
    return MatchEngineV13Defense(a, b, seed=seed)


def tune_defenders(engine, *, positioning, anticipation, tackling, pace, composure=78, discipline=78):
    for ps in engine.teams[1].on_field:
        if ps.player.position.upper() in {"CB", "LB", "RB", "DM", "CM"}:
            ps.player.positioning = positioning
            ps.player.anticipation = anticipation
            ps.player.tackling = tackling
            ps.player.pace = pace
            ps.player.composure = composure
            ps.player.discipline = discipline


class DefensiveIntelligenceTests(unittest.TestCase):
    def test_through_ball_prioritises_runner_or_depth(self):
        e = engine_with_defense()
        z = Zone(Band.ATT, Lane.CENTER)
        d = e.defensive_diagnostic(0, z, CTX, kind="through_ball", target="Runner")
        self.assertIn(d["intent"], {"track_runner", "cover_depth"})
        self.assertLess(d["adjusted"]["space_behind"], d["base"]["space_behind"])
        self.assertGreater(d["adjusted"]["runner_control"], 0.0)

    def test_dribble_prompts_containment_and_reduces_space(self):
        e = engine_with_defense()
        z = Zone(Band.ATT, Lane.LEFT)
        d = e.defensive_diagnostic(0, z, CTX, kind="dribble")
        self.assertEqual(d["intent"], "contain")
        self.assertLess(d["adjusted"]["space"], d["base"]["space"])
        self.assertGreater(d["adjusted"]["dribble_control"], 0.0)

    def test_wide_cross_prompts_cross_blocking(self):
        e = engine_with_defense()
        z = Zone(Band.ATT, Lane.LEFT)
        d = e.defensive_diagnostic(0, z, CTX, kind="cross")
        self.assertEqual(d["intent"], "block_cross")
        self.assertGreater(d["adjusted"]["cross_control"], 0.0)
        self.assertGreater(d["adjusted"]["pressure"], d["base"]["pressure"])

    def test_box_shot_increases_immediate_pressure(self):
        e = engine_with_defense()
        z = Zone(Band.BOX, Lane.CENTER)
        d = e.defensive_diagnostic(0, z, CTX, kind="shoot")
        self.assertIn(d["intent"], {"block_shot", "protect_box"})
        self.assertGreater(d["adjusted"]["pressure"], d["base"]["pressure"])
        self.assertGreater(d["adjusted"]["box_protection"], 0.0)

    def test_high_press_has_a_depth_tradeoff(self):
        e = engine_with_defense()
        e.teams[1].team.tactics.pressing = 0.95
        e.teams[1].team.tactics.defensive_line = 0.35
        e.teams[1].team.tactics.compactness = 0.45
        z = Zone(Band.MID, Lane.CENTER)
        ctx = dict(CTX, pressure=0.35, space=0.60, space_behind=0.25)
        d = e.defensive_diagnostic(0, z, ctx)
        self.assertEqual(d["intent"], "press_ball")
        self.assertGreater(d["adjusted"]["pressure"], d["base"]["pressure"])
        self.assertGreater(d["adjusted"]["space_behind"], d["base"]["space_behind"])

    def test_better_defensive_intelligence_controls_depth_more(self):
        hi = engine_with_defense(seed=1)
        lo = engine_with_defense(seed=1)
        tune_defenders(hi, positioning=92, anticipation=94, tackling=86, pace=88, composure=86, discipline=86)
        tune_defenders(lo, positioning=60, anticipation=58, tackling=62, pace=68, composure=65, discipline=64)
        z = Zone(Band.ATT, Lane.CENTER)
        dh = hi.defensive_diagnostic(0, z, CTX, kind="through_ball", target="Runner")
        dl = lo.defensive_diagnostic(0, z, CTX, kind="through_ball", target="Runner")
        self.assertGreater(dh["quality"], dl["quality"])
        self.assertLess(dh["adjusted"]["space_behind"], dl["adjusted"]["space_behind"])
        self.assertGreater(dh["adjusted"]["runner_control"], dl["adjusted"]["runner_control"])

    def test_one_primary_defensive_intention_only(self):
        e = engine_with_defense()
        z = Zone(Band.ATT, Lane.CENTER)
        d = e.defensive_diagnostic(0, z, CTX, kind="through_ball", target="Runner")
        self.assertIsInstance(d["intent"], str)
        self.assertNotIsInstance(d["intent"], (list, tuple, set))
        # The response may have several physical consequences, but only one
        # decision/intention is active at a time.
        self.assertIn(d["intent"], {
            "press_ball", "delay", "block_lane", "track_runner", "cover_depth",
            "contain", "block_cross", "protect_box", "block_shot", "close_cutback",
        })

    def test_defensive_intelligence_does_not_modify_attacker_attributes(self):
        e = engine_with_defense()
        attacker = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() != "GK")
        before = (
            attacker.effective("pace"), attacker.effective("passing"),
            attacker.effective("dribbling"), attacker.effective("finishing"),
        )
        _ = e.defensive_diagnostic(0, Zone(Band.ATT, Lane.CENTER), CTX, kind="through_ball")
        after = (
            attacker.effective("pace"), attacker.effective("passing"),
            attacker.effective("dribbling"), attacker.effective("finishing"),
        )
        self.assertEqual(before, after)

    def test_same_seed_remains_reproducible_with_defensive_layer(self):
        a1 = make_generic_team("A", 78, "balanced", seed=10)
        b1 = make_generic_team("B", 80, "balanced", seed=20)
        a2 = make_generic_team("A", 78, "balanced", seed=10)
        b2 = make_generic_team("B", 80, "balanced", seed=20)
        e1 = MatchEngineV13Defense(a1, b1, seed=999)
        e2 = MatchEngineV13Defense(a2, b2, seed=999)
        for _ in range(220):
            if e1.state.ended or e2.state.ended:
                break
            x1 = e1.step()
            x2 = e2.step()
            self.assertEqual((x1.type, x1.team, x1.text_key, x1.data), (x2.type, x2.team, x2.text_key, x2.data))
        self.assertEqual(e1.snapshot(), e2.snapshot())


if __name__ == "__main__":
    unittest.main()
