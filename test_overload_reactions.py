from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13_overload import MatchEngineV13Overload


CTX = {
    "pressure": 0.46,
    "space": 0.54,
    "space_behind": 0.48,
    "support": 0.70,
    "wide_space": 0.16,
    "defending_availability": 1.0,
}


def make_engine(seed=123):
    a = make_generic_team("Attack", 79, "balanced", seed=10)
    b = make_generic_team("Defence", 80, "balanced", seed=20)
    return MatchEngineV13Overload(a, b, seed=seed)


def wide_actor(e):
    return next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "LW")


def same_side_fullback(e):
    return next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "LB")


def primary_plan(e, zone):
    defending = e.teams[1].on_field
    primary = next(ps for ps in defending if ps.player.position.upper() == "RB")
    effects = {
        "pressure_delta": 0.025,
        "space_delta": -0.018,
        "depth_delta": 0.010,
        "wide_space_delta": 0.0,
        "pass_lane_control": 0.032,
        "runner_control": 0.030,
        "dribble_control": 0.025,
        "cross_control": 0.018,
        "box_protection": 0.010,
    }
    return {
        "intent": "contain",
        "kind": "dribble",
        "defender": primary,
        "defender_name": primary.player.name,
        "quality": 0.74,
        "effects": effects,
        "marking": {
            "mode": "hybrid",
            "marker_name": primary.player.name,
            "target": None,
            "switched": False,
        },
        "coverage": {"active": False, "defender_name": None},
    }


class OverloadReactionTests(unittest.TestCase):
    def test_same_side_overlap_creates_real_2v1_against_one_committed_defender(self):
        e = make_engine()
        actor = wide_actor(e)
        fullback = same_side_fullback(e)
        e.teams[0].team.tactics.overlap_left = 1.0

        # Make the overlap an obvious local threat and deliberately remove the
        # quality of every unrelated movement. This isolates a true 2v1 without
        # weakening the engine's normal ability to recognise a legitimate third
        # attacker in ordinary play.
        for ps in e.teams[0].on_field:
            if ps.player.name == actor.player.name:
                continue
            if ps.player.name == fullback.player.name:
                ps.player.off_ball = 96
                ps.player.anticipation = 95
                ps.player.pace = 94
                ps.player.stamina = 93
                ps.player.crossing = 91
                ps.player.technique = 88
                ps.player.composure = 88
            else:
                for attr in (
                    "off_ball", "anticipation", "pace", "technique", "vision",
                    "composure", "finishing", "heading", "strength", "stamina",
                    "crossing", "long_shots", "dribbling",
                ):
                    if hasattr(ps.player, attr):
                        setattr(ps.player, attr, 25)

        zone = Zone(Band.ATT, Lane.LEFT)
        plan = primary_plan(e, zone)
        overload = e._overload_plan(
            0, zone, dict(CTX, pressure=0.35), plan,
            actor_name=actor.player.name,
        )
        self.assertTrue(overload["active"])
        self.assertEqual(overload["attackers_count"], 2)
        self.assertEqual(overload["defenders_count"], 1)
        self.assertEqual(overload["label"], "2v1")
        self.assertIn(fullback.player.name, overload["attacking_names"])

    def test_two_local_supports_can_create_3v1_or_3v2(self):
        e = make_engine(seed=20)
        actor = wide_actor(e)
        lb = same_side_fullback(e)
        cm = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "CM")
        e.teams[0].team.tactics.overlap_left = 1.0

        for ps in (lb, cm):
            ps.player.off_ball = 96
            ps.player.anticipation = 95
            ps.player.pace = 92
            ps.player.technique = 92
            ps.player.composure = 90
        lb.player.stamina = 94
        lb.player.crossing = 92
        cm.player.vision = 94

        zone = Zone(Band.ATT, Lane.LEFT)
        plan = primary_plan(e, zone)
        # Commit one additional real defender to model the common 3v2 case.
        second = next(ps for ps in e.teams[1].on_field if ps.player.position.upper() == "CB")
        plan["coverage"] = {"active": True, "defender_name": second.player.name}
        overload = e._overload_plan(0, zone, CTX, plan, actor_name=actor.player.name)

        self.assertTrue(overload["active"])
        self.assertEqual(overload["attackers_count"], 3)
        self.assertEqual(overload["defenders_count"], 2)
        self.assertEqual(overload["label"], "3v2")
        self.assertEqual(len(set(overload["defending_names"])), 2)

    def test_communication_actor_is_not_counted_as_extra_defender(self):
        e = make_engine()
        zone = Zone(Band.ATT, Lane.LEFT)
        plan = primary_plan(e, zone)
        primary = plan["defender_name"]
        cb = next(ps for ps in e.teams[1].on_field if ps.player.position.upper() == "CB")
        plan["communication"] = {
            "active": True,
            "communicator_name": cb.player.name,
            "receiver_name": primary,
        }
        names = e._committed_defender_names(plan)
        self.assertEqual(names, [primary])

    def test_pull_helper_uses_uncommitted_real_defender(self):
        e = make_engine()
        zone = Zone(Band.ATT, Lane.LEFT)
        plan = primary_plan(e, zone)
        committed = set(e._committed_defender_names(plan))
        helper, score = e._best_overload_helper(1, zone, plan, exclude_names=committed)
        self.assertIsNotNone(helper)
        self.assertNotIn(helper.player.name, committed)
        self.assertIn(helper, e.teams[1].on_field)
        self.assertGreater(score, 0.0)

    def test_overload_redistribution_always_has_a_defensive_tradeoff(self):
        base = primary_plan(make_engine(), Zone(Band.ATT, Lane.LEFT))["effects"]
        for response in ("split_difference", "pull_helper", "delay_and_screen"):
            overload = {
                "active": True,
                "attackers_count": 3,
                "defenders_count": 2,
                "response": response,
                "primary_quality": 0.82,
                "zone_lane": Lane.LEFT.value,
            }
            adjusted = MatchEngineV13Overload._redistribute_overload_effects(base, overload)
            # At least one spatial/pressure dimension must become worse for the
            # defence. Numerical inferiority may be managed, never erased free.
            worse = (
                adjusted["pressure_delta"] < base["pressure_delta"]
                or adjusted["space_delta"] > base["space_delta"]
                or adjusted["depth_delta"] > base["depth_delta"]
                or adjusted["wide_space_delta"] > base["wide_space_delta"]
            )
            self.assertTrue(worse, response)

    def test_numerical_scarcity_weakens_simultaneous_controls_before_reallocation(self):
        e = make_engine()
        base = primary_plan(e, Zone(Band.ATT, Lane.LEFT))["effects"]
        two_v_one = {
            "active": True,
            "attackers_count": 2,
            "defenders_count": 1,
            "response": "delay_and_screen",
            "primary_quality": 0.70,
            "zone_lane": Lane.LEFT.value,
        }
        adjusted = e._redistribute_overload_effects(base, two_v_one)
        original_multi = base["dribble_control"] + base["cross_control"] + base["box_protection"]
        new_multi = adjusted["dribble_control"] + adjusted["cross_control"] + adjusted["box_protection"]
        self.assertLess(new_multi, original_multi)

    def test_overload_diagnostic_does_not_modify_player_attributes(self):
        e = make_engine()
        actor = wide_actor(e)
        e.teams[0].team.tactics.overlap_left = 1.0
        defender = next(ps for ps in e.teams[1].on_field if ps.player.position.upper() == "RB")
        before = (
            defender.effective("positioning"), defender.effective("anticipation"),
            defender.effective("tackling"), defender.effective("composure"),
            actor.effective("off_ball"), actor.effective("pace"),
        )
        _ = e.overload_diagnostic(
            0, actor.player.name, Zone(Band.ATT, Lane.LEFT), CTX, kind="dribble"
        )
        after = (
            defender.effective("positioning"), defender.effective("anticipation"),
            defender.effective("tackling"), defender.effective("composure"),
            actor.effective("off_ball"), actor.effective("pace"),
        )
        self.assertEqual(before, after)

    def test_same_seed_reproducible_with_overload_layer(self):
        a1 = make_generic_team("A", 78, "balanced", seed=10)
        b1 = make_generic_team("B", 80, "balanced", seed=20)
        a2 = make_generic_team("A", 78, "balanced", seed=10)
        b2 = make_generic_team("B", 80, "balanced", seed=20)
        e1 = MatchEngineV13Overload(a1, b1, seed=999)
        e2 = MatchEngineV13Overload(a2, b2, seed=999)
        for _ in range(250):
            if e1.state.ended or e2.state.ended:
                break
            x1 = e1.step()
            x2 = e2.step()
            self.assertEqual(
                (x1.type, x1.team, x1.text_key, x1.data),
                (x2.type, x2.team, x2.text_key, x2.data),
            )
        self.assertEqual(e1.snapshot(), e2.snapshot())


if __name__ == "__main__":
    unittest.main()
