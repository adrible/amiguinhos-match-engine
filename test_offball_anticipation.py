from __future__ import annotations

import unittest

from engine import Band, Lane, Player, Tactics, Team, Zone, make_generic_team
from engine_experiment_v13_offball import MatchEngineV13OffBall


CTX = {
    "pressure": 0.48,
    "space": 0.52,
    "space_behind": 0.76,
    "support": 0.48,
}


def build_team(runner_ant=90, runner_off=94, runner_pace=94, left_overlap=0.70, right_overlap=0.25):
    creator = Player(
        name="Creator", position="CM", overall=79,
        passing=82, vision=86, technique=84, composure=82,
        anticipation=80, off_ball=76, pace=73,
    )
    creator.creativity = 90
    creator.boldness = 72

    runner = Player(
        name="Runner", position="RW", overall=80,
        pace=runner_pace, off_ball=runner_off, anticipation=runner_ant,
        technique=79, finishing=76, composure=78,
    )
    st = Player(
        name="Striker", position="ST", overall=81,
        pace=80, off_ball=87, anticipation=85, finishing=89,
        heading=86, strength=84, composure=84,
    )
    am = Player(
        name="Ten", position="AM", overall=80,
        pace=77, off_ball=82, anticipation=82, finishing=78,
        technique=85, vision=86, composure=83,
    )
    lb = Player(
        name="Left Back", position="LB", overall=77,
        pace=84, off_ball=79, anticipation=78, crossing=84, stamina=88,
    )
    rb = Player(
        name="Right Back", position="RB", overall=77,
        pace=84, off_ball=79, anticipation=78, crossing=84, stamina=88,
    )
    others = [
        Player(name="GK", position="GK"),
        Player(name="CB1", position="CB"),
        Player(name="CB2", position="CB"),
        Player(name="DM", position="DM"),
        Player(name="CM2", position="CM"),
    ]
    team = Team(
        "Movers",
        starters=[others[0], rb, others[1], others[2], lb, others[3], creator, others[4], am, runner, st],
        tactics=Tactics(overlap_left=left_overlap, overlap_right=right_overlap, risk=0.55, mentality=0.10),
    )
    opp = make_generic_team("Opp", 79, "balanced", seed=22)
    e = MatchEngineV13OffBall(team, opp, seed=1234)
    return e, e.teams[0].by_name("Creator")


class OffBallAnticipationTests(unittest.TestCase):
    zone = Zone(Band.ATT, Lane.CENTER)

    def row(self, engine, actor, name, zone=None, ctx=None):
        rows = engine.movement_diagnostic(0, actor, zone or self.zone, ctx or CTX)
        return next(r for r in rows if r["player"] == name)

    def test_fast_intelligent_winger_projects_a_forward_run(self):
        e, actor = build_team()
        r = self.row(e, actor, "Runner")
        self.assertIn(r["intent"], {"blind_side_run", "diagonal_run", "run_in_behind", "box_attack"})
        self.assertEqual(r["projected_band"], Band.BOX.value)
        self.assertGreater(r["depth_gain"], 0.55)

    def test_anticipation_improves_run_quality_and_timing(self):
        hi, a_hi = build_team(runner_ant=94, runner_off=94, runner_pace=92)
        lo, a_lo = build_team(runner_ant=58, runner_off=62, runner_pace=92)
        rh = self.row(hi, a_hi, "Runner")
        rl = self.row(lo, a_lo, "Runner")
        self.assertGreater(rh["score"], rl["score"])
        self.assertGreater(rh["projected_quality"], rl["projected_quality"])
        self.assertLess(rh["projection_seconds"], rl["projection_seconds"])

    def test_offball_movement_does_not_change_execution_attributes(self):
        e, actor = build_team()
        runner = e.teams[0].by_name("Runner")
        before = (runner.effective("pace"), runner.effective("technique"), runner.effective("finishing"))
        _ = self.row(e, actor, "Runner")
        after = (runner.effective("pace"), runner.effective("technique"), runner.effective("finishing"))
        self.assertEqual(before, after)

    def test_deep_zone_does_not_teleport_runner_to_box(self):
        e, actor = build_team()
        r = self.row(e, actor, "Runner", zone=Zone(Band.DEF, Lane.CENTER))
        self.assertNotEqual(r["projected_band"], Band.BOX.value)
        self.assertIn(r["intent"], {"support", "check_short", "release_forward"})

    def test_fullback_overlap_is_side_specific(self):
        e, actor = build_team(left_overlap=0.90, right_overlap=0.10)
        left = self.row(e, actor, "Left Back", zone=Zone(Band.MID, Lane.LEFT))
        right = self.row(e, actor, "Right Back", zone=Zone(Band.MID, Lane.RIGHT))
        self.assertGreater(left["score"], right["score"])

    def test_creativity_does_not_create_the_run(self):
        low, a_low = build_team()
        high, a_high = build_team()
        a_low.player.creativity = 35
        a_high.player.creativity = 95
        rl = self.row(low, a_low, "Runner")
        rh = self.row(high, a_high, "Runner")
        # The teammate's run exists independently of whether the passer sees it.
        self.assertEqual(rl["intent"], rh["intent"])
        self.assertAlmostEqual(rl["score"], rh["score"], places=12)
        self.assertAlmostEqual(rl["projected_quality"], rh["projected_quality"], places=12)

    def test_creativity_changes_perception_of_same_movement(self):
        low, a_low = build_team()
        high, a_high = build_team()
        a_low.player.creativity = 42
        a_high.player.creativity = 94
        dl = low.hidden_option_diagnostic(0, a_low, self.zone, CTX)
        dh = high.hidden_option_diagnostic(0, a_high, self.zone, CTX)
        self.assertIsNotNone(dl)
        self.assertIsNotNone(dh)
        self.assertEqual(dl["target_name"], dh["target_name"])
        self.assertEqual(dl["movement"]["intent"], dh["movement"]["intent"])
        self.assertGreater(dh["perception_probability"], dl["perception_probability"])

    def test_only_one_active_movement_per_player(self):
        e, actor = build_team()
        rows = e.movement_diagnostic(0, actor, self.zone, CTX)
        names = [r["player"] for r in rows]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(isinstance(r["intent"], str) for r in rows))

    def test_same_seed_remains_reproducible_with_movement_layer(self):
        e1, _ = build_team()
        e2, _ = build_team()
        for _ in range(180):
            if e1.state.ended or e2.state.ended:
                break
            x1 = e1.step()
            x2 = e2.step()
            self.assertEqual((x1.type, x1.team, x1.text_key, x1.data), (x2.type, x2.team, x2.text_key, x2.data))
        self.assertEqual(e1.snapshot(), e2.snapshot())


if __name__ == "__main__":
    unittest.main()
