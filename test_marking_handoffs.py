from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13_marking import MatchEngineV13Marking

CTX = {
    "pressure": 0.46,
    "space": 0.54,
    "space_behind": 0.70,
    "support": 0.52,
    "wide_space": 0.10,
}


def make_engine(seed=123):
    a = make_generic_team("Attack", 79, "balanced", seed=10)
    b = make_generic_team("Defence", 80, "balanced", seed=20)
    return MatchEngineV13Marking(a, b, seed=seed)


class MarkingHandoffTests(unittest.TestCase):
    def test_compact_box_defence_prefers_zonal_structure(self):
        e = make_engine()
        e.teams[1].team.tactics.compactness = 0.92
        e.teams[1].team.tactics.pressing = 0.30
        d = e.marking_diagnostic(0, Zone(Band.BOX, Lane.CENTER), CTX, kind="cross")
        self.assertEqual(d["mode"], "zonal")
        self.assertGreater(d["effects"]["pass_lane_control"], 0.0)

    def test_targeted_depth_threat_moves_toward_man_or_hybrid(self):
        e = make_engine()
        actor = next(ps.player.name for ps in e.teams[0].on_field if ps.player.position.upper() == "CM")
        target = next(ps.player.name for ps in e.teams[0].on_field if ps.player.position.upper() == "ST")
        d = e.marking_diagnostic(
            0, Zone(Band.ATT, Lane.CENTER), CTX,
            kind="through_ball", actor=actor, target=target,
        )
        self.assertIn(d["mode"], {"man", "hybrid"})
        self.assertGreater(d["effects"]["runner_control"], 0.0)

    def test_cross_zone_run_can_trigger_a_handoff(self):
        e = make_engine()
        # Force a left winger to prefer a diagonal central run so the natural
        # wide marker has a reason to hand him to a central defender.
        actor = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "CM")
        winger = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "LW")
        winger.player.off_ball = 96
        winger.player.anticipation = 95
        winger.player.pace = 92
        winger.player.technique = 90
        winger.player.composure = 90
        e.teams[1].team.tactics.compactness = 0.82
        e.teams[1].team.tactics.pressing = 0.50
        # Make the natural wide marker weaker and the projected-zone defenders
        # excellent, so this synthetic case must produce a genuine hand-off.
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
        d = e.marking_diagnostic(
            0, Zone(Band.ATT, Lane.LEFT), CTX,
            kind="through_ball", actor=actor.player.name, target=winger.player.name,
        )
        self.assertNotEqual(d["current_zone"], d["projected_zone"])
        self.assertTrue(d["switched"])
        self.assertNotEqual(d["initial_marker"], d["marker"])
        self.assertGreaterEqual(d["handoff_quality"], 0.46)

    def test_man_marking_is_stickier_than_zonal_marking(self):
        e = make_engine()
        # Compare pure scheme thresholds directly through deterministic style
        # environments: high compactness/low press => zonal; high press/line => man.
        actor = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "CM")
        winger = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "LW")
        winger.player.off_ball = 95
        winger.player.anticipation = 94
        winger.player.pace = 91

        e.teams[1].team.tactics.compactness = 0.99
        e.teams[1].team.tactics.pressing = 0.05
        e.teams[1].team.tactics.defensive_line = 0.20
        zonal_ctx = dict(CTX, space_behind=0.30)
        zonal = e.marking_diagnostic(
            0, Zone(Band.ATT, Lane.LEFT), zonal_ctx,
            kind="open_play", actor=actor.player.name, target=winger.player.name,
        )

        e.teams[1].team.tactics.compactness = 0.35
        e.teams[1].team.tactics.pressing = 0.95
        e.teams[1].team.tactics.defensive_line = 0.90
        man = e.marking_diagnostic(
            0, Zone(Band.ATT, Lane.LEFT), CTX,
            kind="through_ball", actor=actor.player.name, target=winger.player.name,
        )
        self.assertEqual(zonal["mode"], "zonal")
        self.assertEqual(man["mode"], "man")
        # This asserts the intended behavioural distinction without requiring a
        # particular roster to force opposite switch outcomes.
        self.assertGreater(man["effects"]["runner_control"], zonal["effects"]["runner_control"])

    def test_multi_threat_assignment_never_reuses_same_defender(self):
        e = make_engine()
        actor = next(ps.player.name for ps in e.teams[0].on_field if ps.player.position.upper() == "CM")
        rows = e.marking_assignments_diagnostic(
            0, actor, Zone(Band.ATT, Lane.CENTER), CTX, max_threats=4
        )
        markers = [row["marker"] for row in rows]
        self.assertEqual(len(markers), len(set(markers)))

    def test_marking_does_not_change_player_attributes(self):
        e = make_engine()
        actor = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "CM")
        target = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "ST")
        before = (target.effective("pace"), target.effective("off_ball"), target.effective("finishing"))
        _ = e.marking_diagnostic(
            0, Zone(Band.ATT, Lane.CENTER), CTX,
            kind="through_ball", actor=actor.player.name, target=target.player.name,
        )
        after = (target.effective("pace"), target.effective("off_ball"), target.effective("finishing"))
        self.assertEqual(before, after)

    def test_same_seed_reproducible_with_marking_layer(self):
        a1 = make_generic_team("A", 78, "balanced", seed=10)
        b1 = make_generic_team("B", 80, "balanced", seed=20)
        a2 = make_generic_team("A", 78, "balanced", seed=10)
        b2 = make_generic_team("B", 80, "balanced", seed=20)
        e1 = MatchEngineV13Marking(a1, b1, seed=999)
        e2 = MatchEngineV13Marking(a2, b2, seed=999)
        for _ in range(220):
            if e1.state.ended or e2.state.ended:
                break
            x1 = e1.step()
            x2 = e2.step()
            self.assertEqual((x1.type, x1.team, x1.text_key, x1.data), (x2.type, x2.team, x2.text_key, x2.data))
        self.assertEqual(e1.snapshot(), e2.snapshot())


if __name__ == "__main__":
    unittest.main()
