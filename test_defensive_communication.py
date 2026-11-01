from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13_communication import MatchEngineV13Communication


CTX = {
    "pressure": 0.44,
    "space": 0.56,
    "space_behind": 0.58,
    "support": 0.52,
    "wide_space": 0.10,
    "defending_availability": 1.0,
}


def make_engine(seed=123):
    a = make_generic_team("Attack", 79, "balanced", seed=10)
    b = make_generic_team("Defence", 80, "balanced", seed=20)
    return MatchEngineV13Communication(a, b, seed=seed)


class DefensiveCommunicationTests(unittest.TestCase):
    def test_cover_call_coordinates_existing_second_defender(self):
        e = make_engine()
        e.teams[1].team.tactics.pressing = 0.96
        e.teams[1].team.tactics.compactness = 0.86
        e.teams[1].team.tactics.defensive_line = 0.68
        d = e.communication_diagnostic(
            0,
            Zone(Band.MID, Lane.CENTER),
            dict(CTX, pressure=0.31, space_behind=0.40),
            kind="open_play",
        )
        self.assertTrue(d["coverage_active"])
        self.assertTrue(d["active"])
        self.assertEqual(d["communication_type"], "cover_call")
        self.assertIsNotNone(d["communicator"])
        self.assertIsNotNone(d["receiver"])
        self.assertNotEqual(d["communicator"], d["receiver"])

    def test_cross_zone_handoff_gets_one_handoff_call(self):
        e = make_engine()
        actor = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "CM")
        winger = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "LW")
        winger.player.off_ball = 96
        winger.player.anticipation = 95
        winger.player.pace = 92
        winger.player.technique = 90
        winger.player.composure = 90
        e.teams[1].team.tactics.compactness = 0.82
        e.teams[1].team.tactics.pressing = 0.50
        for ps in e.teams[1].on_field:
            if ps.player.position.upper() == "RB":
                ps.player.positioning = 62
                ps.player.anticipation = 60
                ps.player.pace = 64
                ps.player.tackling = 65
            elif ps.player.position.upper() == "CB":
                ps.player.positioning = 94
                ps.player.anticipation = 94
                ps.player.pace = 86
                ps.player.tackling = 90
                ps.player.composure = 88
                ps.player.discipline = 88
        d = e.communication_diagnostic(
            0,
            Zone(Band.ATT, Lane.LEFT),
            dict(CTX, space_behind=0.70),
            kind="through_ball",
            actor=actor.player.name,
            target=winger.player.name,
        )
        self.assertTrue(d["marking_switched"])
        self.assertTrue(d["active"])
        self.assertEqual(d["communication_type"], "handoff_call")
        self.assertIsNotNone(d["initiator"])
        self.assertIsNotNone(d["receiver"])
        self.assertNotEqual(d["initiator"], d["receiver"])

    def test_no_handoff_or_cover_means_no_free_communication_bonus(self):
        e = make_engine()
        d = e.communication_diagnostic(
            0,
            Zone(Band.BOX, Lane.CENTER),
            dict(CTX, pressure=0.65, space=0.25, space_behind=0.25),
            kind="shoot",
        )
        self.assertFalse(d["coverage_active"])
        self.assertFalse(d["marking_switched"])
        self.assertFalse(d["active"])
        self.assertIsNone(d["communication_type"])
        self.assertTrue(all(abs(v) < 1e-12 for v in d["effects"].values()))

    def test_better_defensive_reading_improves_call_quality(self):
        hi = make_engine(seed=7)
        lo = make_engine(seed=7)
        for engine, value in ((hi, 94), (lo, 56)):
            engine.teams[1].team.tactics.pressing = 0.96
            engine.teams[1].team.tactics.compactness = 0.88
            engine.teams[1].team.tactics.defensive_line = 0.70
            for ps in engine.teams[1].on_field:
                ps.player.positioning = value
                ps.player.anticipation = value
                ps.player.composure = value
                ps.player.discipline = value
                if ps.player.position.upper() == "GK":
                    ps.player.gk_positioning = value
        ctx = dict(CTX, pressure=0.30, space_behind=0.38)
        dh = hi.communication_diagnostic(0, Zone(Band.MID, Lane.CENTER), ctx)
        dl = lo.communication_diagnostic(0, Zone(Band.MID, Lane.CENTER), ctx)
        self.assertTrue(dh["active"])
        self.assertTrue(dl["active"])
        self.assertGreater(dh["quality"], dl["quality"])

    def test_communication_only_modulates_existing_relationship(self):
        e = make_engine()
        e.teams[1].team.tactics.pressing = 0.98
        e.teams[1].team.tactics.compactness = 0.88
        e.teams[1].team.tactics.defensive_line = 0.72
        d = e.communication_diagnostic(
            0,
            Zone(Band.MID, Lane.CENTER),
            dict(CTX, pressure=0.30, space_behind=0.35),
        )
        self.assertTrue(d["active"])
        total = sum(abs(float(v)) for v in d["effects"].values())
        self.assertLess(total, 0.012)

    def test_communication_does_not_modify_player_attributes(self):
        e = make_engine()
        e.teams[1].team.tactics.pressing = 0.96
        e.teams[1].team.tactics.compactness = 0.86
        defender = next(ps for ps in e.teams[1].on_field if ps.player.position.upper() == "CB")
        before = (
            defender.effective("positioning"),
            defender.effective("anticipation"),
            defender.effective("composure"),
            defender.effective("discipline"),
        )
        _ = e.communication_diagnostic(0, Zone(Band.MID, Lane.CENTER), CTX)
        after = (
            defender.effective("positioning"),
            defender.effective("anticipation"),
            defender.effective("composure"),
            defender.effective("discipline"),
        )
        self.assertEqual(before, after)

    def test_same_seed_reproducible_with_communication_layer(self):
        a1 = make_generic_team("A", 78, "balanced", seed=10)
        b1 = make_generic_team("B", 80, "balanced", seed=20)
        a2 = make_generic_team("A", 78, "balanced", seed=10)
        b2 = make_generic_team("B", 80, "balanced", seed=20)
        e1 = MatchEngineV13Communication(a1, b1, seed=999)
        e2 = MatchEngineV13Communication(a2, b2, seed=999)
        for _ in range(220):
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
