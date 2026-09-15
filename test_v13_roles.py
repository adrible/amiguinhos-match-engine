from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_injuries import MatchEngineV13Injuries
from engine_experiment_v13_roles import MatchEngineV13Roles


class DerivedRoleTests(unittest.TestCase):
    def engine(self, seed=8501):
        return MatchEngineV13Roles(
            make_generic_team("Home", 80, "balanced", seed=101),
            make_generic_team("Away", 80, "balanced", seed=202),
            seed=seed,
        )

    @staticmethod
    def player(e, position: str, team=0):
        return next(ps for ps in e.teams[team].on_field if ps.player.position.upper() == position)

    def test_canonical_entrypoint_includes_injuries_and_roles(self):
        self.assertTrue(issubclass(MatchEngineV13Roles, MatchEngineV13Injuries))
        self.assertIs(CanonicalMatchEngine, MatchEngineV13Roles)

    def test_role_diagnostic_is_rng_pure_and_creates_no_player_rating(self):
        e = self.engine()
        p = self.player(e, "CM")
        rng_before = e.rng.getstate()
        first = e.role_diagnostic(p)
        second = e.role_diagnostic(p)
        self.assertEqual(first, second)
        self.assertEqual(e.rng.getstate(), rng_before)
        for name in ("role", "role_rating", "target_forward", "deep_playmaker", "inside_forward"):
            self.assertFalse(hasattr(p.player, name))

    def test_striker_profile_distinguishes_target_from_channel_runner(self):
        e = self.engine(seed=8503)
        p = self.player(e, "ST")
        for attr in ("strength", "heading", "composure", "technique", "passing"):
            setattr(p.player, attr, 95)
        for attr in ("pace", "off_ball", "dribbling", "finishing"):
            setattr(p.player, attr, 48)
        target = e.role_diagnostic(p)
        self.assertEqual(target["primary"], "target_forward")

        for attr in ("strength", "heading", "passing"):
            setattr(p.player, attr, 45)
        for attr in ("pace", "off_ball", "anticipation", "dribbling"):
            setattr(p.player, attr, 95)
        p.player.finishing = 70
        runner = e.role_diagnostic(p)
        self.assertEqual(runner["primary"], "channel_runner")

    def test_winger_profile_distinguishes_touchline_and_inside_forward(self):
        e = self.engine(seed=8505)
        p = self.player(e, "RW")
        p.player.preferred_foot = "R"
        for attr in ("crossing", "pace", "dribbling", "technique", "off_ball"):
            setattr(p.player, attr, 94)
        p.player.finishing = 48
        wide = e.role_diagnostic(p)
        self.assertEqual(wide["primary"], "touchline_winger")

        p.player.preferred_foot = "L"
        p.player.crossing = 50
        for attr in ("finishing", "dribbling", "technique", "off_ball", "pace", "composure"):
            setattr(p.player, attr, 95)
        inside = e.role_diagnostic(p)
        self.assertEqual(inside["primary"], "inside_forward")

    def test_midfielder_profile_distinguishes_playmaker_and_ball_winner(self):
        e = self.engine(seed=8507)
        p = self.player(e, "DM")
        for attr in ("passing", "vision", "technique", "composure", "anticipation"):
            setattr(p.player, attr, 95)
        for attr in ("tackling", "positioning", "strength", "aggression"):
            setattr(p.player, attr, 48)
        playmaker = e.role_diagnostic(p)
        self.assertEqual(playmaker["primary"], "deep_playmaker")

        for attr in ("passing", "vision", "technique"):
            setattr(p.player, attr, 48)
        for attr in ("tackling", "positioning", "anticipation", "strength", "stamina", "aggression"):
            setattr(p.player, attr, 95)
        winner = e.role_diagnostic(p)
        self.assertEqual(winner["primary"], "ball_winner")

    def test_fullback_role_reads_existing_overlap_instruction(self):
        e = self.engine(seed=8509)
        p = self.player(e, "RB")
        for attr in ("pace", "stamina", "crossing", "off_ball", "dribbling", "technique"):
            setattr(p.player, attr, 88)
        e.set_tactics(0, overlap_right=0.05)
        low = e.role_diagnostic(p)["scores"]["overlapping_fullback"]
        e.set_tactics(0, overlap_right=0.95)
        high = e.role_diagnostic(p)["scores"]["overlapping_fullback"]
        self.assertGreater(high, low)

    def test_role_changes_preference_not_execution_attributes(self):
        e = self.engine(seed=8511)
        p = self.player(e, "RW")
        p.player.preferred_foot = "R"
        for attr in ("crossing", "pace", "dribbling", "technique", "off_ball"):
            setattr(p.player, attr, 95)
        p.player.finishing = 45
        zone = Zone(Band.ATT, Lane.RIGHT)
        ctx = {"pressure": 0.40, "space": 0.62, "space_behind": 0.48, "support": 0.58, "defensive_quality": 0.55}
        baseline = dict(MatchEngineV13Injuries._decision_weights(e, p, zone, e.teams[0].team.tactics, ctx))
        role_weights = dict(e._decision_weights(p, zone, e.teams[0].team.tactics, ctx))
        self.assertGreater(role_weights["cross"], baseline["cross"])
        if "shoot" in baseline:
            self.assertLess(role_weights["shoot"], baseline["shoot"])
        self.assertEqual(p.player.crossing, 95)
        self.assertEqual(p.player.pace, 95)

    def test_same_seed_remains_deterministic_with_roles(self):
        a, b = self.engine(seed=8513), self.engine(seed=8513)
        out_a, out_b = [], []
        for _ in range(26):
            ea, eb = a.step(), b.step()
            out_a.append((ea.minute, ea.type.value, ea.text_key, ea.team, ea.data))
            out_b.append((eb.minute, eb.type.value, eb.text_key, eb.team, eb.data))
        self.assertEqual(out_a, out_b)

    def test_save_load_continuation_remains_deterministic(self):
        e = self.engine(seed=8515)
        for _ in range(16):
            e.step()
        clone = MatchEngineV13Roles.from_json(e.export_json())
        out_a, out_b = [], []
        for _ in range(12):
            ea, eb = e.step(), clone.step()
            out_a.append((ea.minute, ea.type.value, ea.text_key, ea.team, ea.data))
            out_b.append((eb.minute, eb.type.value, eb.text_key, eb.team, eb.data))
        self.assertEqual(out_a, out_b)
        self.assertEqual(e.export_state(), clone.export_state())


if __name__ == "__main__":
    unittest.main()
