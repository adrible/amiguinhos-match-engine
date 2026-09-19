from __future__ import annotations

import unittest

from engine import Band, Lane, PendingAction, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine
from engine_experiment_v13_rebounds import MatchEngineV13Rebounds


class ReboundContinuityTests(unittest.TestCase):
    def engine(self, seed=8301):
        return MatchEngine(
            make_generic_team("Home", 80, "balanced", seed=101),
            make_generic_team("Away", 80, "balanced", seed=202),
            seed=seed,
        )

    def context(self, e, lane=Lane.CENTER, danger=0.55, pressure=0.50, depth=0):
        shooter = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "ST")
        p = PendingAction(
            team=0,
            actor=shooter.player.name,
            kind="shoot",
            zone=Zone(Band.BOX, lane),
            danger=danger,
            pressure=pressure,
            defender=next(ps.player.name for ps in e.teams[1].on_field if ps.player.position.upper() == "CB"),
            origin="open_play",
            rebound_depth=depth,
        )
        return shooter, p

    def test_canonical_engine_contains_rebound_layer(self):
        self.assertTrue(issubclass(MatchEngine, MatchEngineV13Rebounds))

    def test_rebound_geometry_stays_connected_to_shot_lane(self):
        e = self.engine(seed=8303)
        shooter, p = self.context(e, lane=Lane.LEFT)
        for blocked, post in ((True, False), (False, True), (False, False)):
            zone = e._rebound_ball_zone(p, blocked=blocked, post=post)
            self.assertEqual(zone.band, Band.BOX)
            self.assertIn(zone.lane, {Lane.LEFT, Lane.CENTER})

    def test_save_spill_allows_keeper_recovery_but_block_does_not(self):
        e = self.engine(seed=8305)
        shooter, p = self.context(e)
        keeper = e._goalkeeper(1)
        for attr in ("handling", "reflexes", "gk_positioning"):
            setattr(keeper.player, attr, 45)
        low = e.rebound_contest_diagnostic(0, p, shooter, 0.22)
        for attr in ("handling", "reflexes", "gk_positioning"):
            setattr(keeper.player, attr, 95)
        high = e.rebound_contest_diagnostic(0, p, shooter, 0.22)
        blocked = e.rebound_contest_diagnostic(0, p, shooter, 0.22, blocked=True)
        self.assertGreater(high["keeper_recovery_probability"], low["keeper_recovery_probability"])
        self.assertEqual(blocked["keeper_recovery_probability"], 0.0)

    def test_reaction_quality_changes_second_ball_edge(self):
        e = self.engine(seed=8307)
        shooter, p = self.context(e)
        attackers = [ps for ps in e.teams[0].on_field if ps.player.name != shooter.player.name and ps.player.position.upper() != "GK"]
        for ps in attackers:
            for attr in ("anticipation", "off_ball", "pace", "positioning", "composure"):
                setattr(ps.player, attr, 48)
        low = e.rebound_contest_diagnostic(0, p, shooter, 0.24, blocked=True)
        for ps in attackers:
            for attr in ("anticipation", "off_ball", "pace", "positioning", "composure"):
                setattr(ps.player, attr, 94)
        high = e.rebound_contest_diagnostic(0, p, shooter, 0.24, blocked=True)
        self.assertGreater(high["attack_score"], low["attack_score"])
        self.assertGreater(high["attacker_win_probability"], low["attacker_win_probability"])

    def test_rebound_resolution_consumes_real_time(self):
        e = self.engine(seed=8309)
        shooter, p = self.context(e)
        before = e.state.second
        event = e._create_rebound(0, p, shooter, 0.25, blocked=True)
        self.assertGreater(e.state.second, before)
        self.assertTrue(event.data.get("second_ball_read"))
        self.assertIn(
            event.text_key,
            {"rebound_attacker_wins", "rebound_defender_controls", "rebound_defender_clears"},
        )

    def test_attacker_win_creates_only_one_live_pending_action(self):
        found = False
        for seed in range(8311, 8341):
            e = self.engine(seed=seed)
            shooter, p = self.context(e)
            for ps in e.teams[0].on_field:
                if ps.player.name != shooter.player.name and ps.player.position.upper() != "GK":
                    ps.player.anticipation = 95
                    ps.player.off_ball = 95
            event = e._create_rebound(0, p, shooter, 0.35, post=True)
            if event.text_key == "rebound_attacker_wins":
                found = True
                self.assertIsNotNone(e.state.pending)
                self.assertEqual(e.state.pending.origin, "rebound")
                self.assertEqual(e.state.pending.rebound_depth, 1)
                break
        self.assertTrue(found)

    def test_same_seed_same_rebound_contest(self):
        a, b = self.engine(seed=8343), self.engine(seed=8343)
        sa, pa = self.context(a, lane=Lane.RIGHT)
        sb, pb = self.context(b, lane=Lane.RIGHT)
        ea = a._create_rebound(0, pa, sa, 0.28, blocked=False, post=False)
        eb = b._create_rebound(0, pb, sb, 0.28, blocked=False, post=False)
        self.assertEqual((ea.minute, ea.team, ea.type, ea.text_key, ea.data), (eb.minute, eb.team, eb.type, eb.text_key, eb.data))
        self.assertEqual(a.export_state(), b.export_state())

    def test_save_load_before_rebound_preserves_continuation(self):
        a = self.engine(seed=8345)
        sa, pa = self.context(a)
        b = MatchEngine.from_json(a.export_json())
        sb = b.teams[0].by_name(sa.player.name)
        pb = PendingAction(
            team=pa.team,
            actor=pa.actor,
            kind=pa.kind,
            zone=pa.zone,
            danger=pa.danger,
            pressure=pa.pressure,
            defender=pa.defender,
            origin=pa.origin,
            rebound_depth=pa.rebound_depth,
        )
        ea = a._create_rebound(0, pa, sa, 0.20, blocked=True)
        eb = b._create_rebound(0, pb, sb, 0.20, blocked=True)
        self.assertEqual((ea.minute, ea.team, ea.type, ea.text_key, ea.data), (eb.minute, eb.team, eb.type, eb.text_key, eb.data))
        self.assertEqual(a.export_state(), b.export_state())


if __name__ == "__main__":
    unittest.main()
