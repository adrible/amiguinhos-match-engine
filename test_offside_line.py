from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13_offside import MatchEngineV13Offside


CTX = {
    "pressure": 0.58,
    "space": 0.48,
    "space_behind": 0.42,
    "support": 0.52,
    "wide_space": 0.10,
    "defending_availability": 1.0,
}


def make_engine(seed=123):
    a = make_generic_team("Attack", 79, "balanced", seed=10)
    b = make_generic_team("Defence", 80, "balanced", seed=20)
    return MatchEngineV13Offside(a, b, seed=seed)


def actor_target(e):
    actor = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "CM")
    target = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "ST")
    return actor, target


class OffsideLineTests(unittest.TestCase):
    def test_high_coordinated_line_can_step_up(self):
        e = make_engine()
        actor, target = actor_target(e)
        e.teams[1].team.tactics.defensive_line = 0.95
        e.teams[1].team.tactics.compactness = 0.92
        for ps in e.teams[1].on_field:
            if ps.player.position.upper() in {"CB", "LB", "RB", "DM", "GK"}:
                ps.player.positioning = 91
                ps.player.anticipation = 90
                ps.player.composure = 88
                ps.player.discipline = 88
        d = e.offside_line_diagnostic(
            0, Zone(Band.MID, Lane.CENTER),
            dict(CTX, pressure=0.72, space_behind=0.28),
            actor=actor.player.name, target=target.player.name,
        )
        self.assertEqual(d["response"], "step_up")
        self.assertGreater(d["coordination"], 0.70)
        self.assertGreater(d["offside_probability"], 0.04)
        self.assertGreater(d["onside_exposure"], 0.0)

    def test_low_line_prefers_hold_or_drop_and_has_less_offside(self):
        high = make_engine(seed=22)
        low = make_engine(seed=22)
        ah, th = actor_target(high)
        al, tl = actor_target(low)
        for engine, line in ((high, 0.95), (low, 0.12)):
            engine.teams[1].team.tactics.defensive_line = line
            engine.teams[1].team.tactics.compactness = 0.86
        dh = high.offside_line_diagnostic(
            0, Zone(Band.MID, Lane.CENTER), CTX,
            actor=ah.player.name, target=th.player.name,
        )
        dl = low.offside_line_diagnostic(
            0, Zone(Band.MID, Lane.CENTER), CTX,
            actor=al.player.name, target=tl.player.name,
        )
        self.assertEqual(dh["response"], "step_up")
        self.assertIn(dl["response"], {"hold_line", "drop_and_track"})
        self.assertGreater(dh["offside_probability"], dl["offside_probability"])

    def test_better_runner_timing_reduces_offside_probability(self):
        fast = make_engine(seed=33)
        slow = make_engine(seed=33)
        af, tf = actor_target(fast)
        a_s, ts = actor_target(slow)
        for engine in (fast, slow):
            engine.teams[1].team.tactics.defensive_line = 0.94
            engine.teams[1].team.tactics.compactness = 0.90
        for attr in ("off_ball", "anticipation", "pace", "composure"):
            setattr(tf.player, attr, 96)
            setattr(ts.player, attr, 55)
        df = fast.offside_line_diagnostic(
            0, Zone(Band.MID, Lane.CENTER), CTX,
            actor=af.player.name, target=tf.player.name,
        )
        ds = slow.offside_line_diagnostic(
            0, Zone(Band.MID, Lane.CENTER), CTX,
            actor=a_s.player.name, target=ts.player.name,
        )
        self.assertGreater(df["runner_timing"], ds["runner_timing"])
        self.assertLess(df["offside_probability"], ds["offside_probability"])

    def test_transition_makes_step_less_attractive(self):
        settled = make_engine(seed=44)
        transition = make_engine(seed=44)
        a1, t1 = actor_target(settled)
        a2, t2 = actor_target(transition)
        for engine in (settled, transition):
            engine.teams[1].team.tactics.defensive_line = 0.76
            engine.teams[1].team.tactics.compactness = 0.78
        settled.state.transition_boost = 0.0
        transition.state.transition_boost = 1.0
        ds = settled.offside_line_diagnostic(
            0, Zone(Band.MID, Lane.CENTER), CTX,
            actor=a1.player.name, target=t1.player.name,
        )
        dt = transition.offside_line_diagnostic(
            0, Zone(Band.MID, Lane.CENTER), CTX,
            actor=a2.player.name, target=t2.player.name,
        )
        self.assertGreater(ds["scores"]["step_up"], dt["scores"]["step_up"])
        self.assertLess(ds["scores"]["drop_and_track"], dt["scores"]["drop_and_track"])

    def test_beaten_step_concedes_real_depth(self):
        e = make_engine()
        actor, target = actor_target(e)
        e.teams[1].team.tactics.defensive_line = 0.96
        e.teams[1].team.tactics.compactness = 0.92
        d = e.offside_line_diagnostic(
            0, Zone(Band.MID, Lane.CENTER),
            dict(CTX, pressure=0.70, space_behind=0.30),
            actor=actor.player.name, target=target.player.name,
        )
        self.assertEqual(d["response"], "step_up")
        self.assertTrue(d["onside_context"].get("offside_trap_beaten"))
        self.assertGreater(
            d["onside_context"]["space_behind"],
            d["defensive_context"]["space_behind"],
        )
        self.assertLess(
            d["onside_context"]["pressure"],
            d["defensive_context"]["pressure"],
        )

    def test_line_diagnostic_does_not_modify_player_attributes(self):
        e = make_engine()
        actor, target = actor_target(e)
        defender = next(ps for ps in e.teams[1].on_field if ps.player.position.upper() == "CB")
        before = (
            defender.effective("positioning"), defender.effective("anticipation"),
            defender.effective("composure"), defender.effective("discipline"),
            target.effective("off_ball"), target.effective("pace"),
        )
        _ = e.offside_line_diagnostic(
            0, Zone(Band.MID, Lane.CENTER), CTX,
            actor=actor.player.name, target=target.player.name,
        )
        after = (
            defender.effective("positioning"), defender.effective("anticipation"),
            defender.effective("composure"), defender.effective("discipline"),
            target.effective("off_ball"), target.effective("pace"),
        )
        self.assertEqual(before, after)

    def test_same_seed_reproducible_with_offside_line(self):
        a1 = make_generic_team("A", 78, "balanced", seed=10)
        b1 = make_generic_team("B", 80, "balanced", seed=20)
        a2 = make_generic_team("A", 78, "balanced", seed=10)
        b2 = make_generic_team("B", 80, "balanced", seed=20)
        e1 = MatchEngineV13Offside(a1, b1, seed=999)
        e2 = MatchEngineV13Offside(a2, b2, seed=999)
        for _ in range(240):
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
