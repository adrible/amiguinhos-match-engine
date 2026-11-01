from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13_injuries import MatchEngineV13Injuries


class InjuryManagementTests(unittest.TestCase):
    def engine(self, seed=8401):
        return MatchEngineV13Injuries(
            make_generic_team("Home", 80, "balanced", seed=101),
            make_generic_team("Away", 80, "balanced", seed=202),
            seed=seed,
        )

    def player(self, e, team=0):
        return next(ps for ps in e.teams[team].on_field if ps.player.position.upper() in {"ST", "AM", "LW", "RW", "CM"})

    def test_body_area_maps_to_functional_region(self):
        e = self.engine()
        p = self.player(e)
        state = e._register_injury_state(0, p, {"grade": "minor", "body_area": "ankle_knee_or_lower_leg", "impact": 0.58, "forced_off": False})
        self.assertEqual(state["region"], "lower_body")
        self.assertEqual(e._v13_injury_locations[p.player.name], "lower_body")
        self.assertTrue(state["can_continue"])

    def test_minor_lower_body_issue_hurts_foot_contact_more_than_heading(self):
        e = self.engine(seed=8403)
        p = self.player(e)
        e._register_injury_state(0, p, {"grade": "minor", "body_area": "lower_leg", "impact": 0.70, "forced_off": False})
        foot = e._injury_part_modifier(p, "right_foot")
        head = e._injury_part_modifier(p, "head")
        self.assertLess(foot, head)
        self.assertLess(foot, 1.0)
        self.assertGreater(head, 0.97)

    def test_temporary_limitation_recovers_with_match_time_without_rng(self):
        e = self.engine(seed=8405)
        p = self.player(e)
        e.state.second = 20.0 * 60.0
        state = e._register_injury_state(0, p, {"grade": "minor", "body_area": "soft_tissue", "impact": 0.55, "forced_off": False})
        rng_before = e.rng.getstate()
        early = e.current_injury_status(0, p.player.name)
        e.state.second += 0.60 * float(state["recovery_minutes"]) * 60.0
        later = e.current_injury_status(0, p.player.name)
        self.assertEqual(e.rng.getstate(), rng_before)
        self.assertGreater(early["current_limitation"], later["current_limitation"])
        e.state.second += float(state["recovery_minutes"]) * 60.0
        recovered = e.current_injury_status(0, p.player.name)
        self.assertTrue(recovered["recovered"])
        self.assertEqual(recovered["current_limitation"], 0.0)

    def test_moderate_and_suspected_concussion_are_forced_off_profiles(self):
        e = self.engine(seed=8407)
        p = self.player(e)
        moderate = e._register_injury_state(0, p, {"grade": "moderate", "body_area": "lower_leg", "impact": 0.74, "forced_off": True})
        self.assertTrue(moderate["forced_off"])
        self.assertFalse(moderate["can_continue"])
        self.assertIsNone(moderate["recovery_minutes"])
        concussion = e._register_injury_state(0, p, {"grade": "moderate", "body_area": "head_or_face", "impact": 0.72, "forced_off": True, "concussion_protocol": True, "suspected_concussion": True})
        self.assertTrue(concussion["forced_off"])
        self.assertEqual(concussion["medical_action"], "concussion_substitution")

    def test_minor_injury_changes_willingness_not_player_attributes(self):
        e = self.engine(seed=8409)
        p = self.player(e)
        zone = Zone(Band.ATT, Lane.CENTER)
        ctx = {"pressure": 0.42, "space": 0.60, "space_behind": 0.50, "support": 0.58, "defensive_quality": 0.55}
        base = dict(e._decision_weights(p, zone, e.teams[0].team.tactics, ctx))
        e._register_injury_state(0, p, {"grade": "minor", "body_area": "lower_leg", "impact": 0.68, "forced_off": False})
        affected = dict(e._decision_weights(p, zone, e.teams[0].team.tactics, ctx))
        if "dribble" in base:
            self.assertLess(affected["dribble"], base["dribble"])
        if "shoot" in base:
            self.assertLess(affected["shoot"], base["shoot"])
        if "safe_pass" in base:
            self.assertGreater(affected["safe_pass"], base["safe_pass"])
        for name in ("injury_resistance", "pain", "recovery", "fitness_medical"):
            self.assertFalse(hasattr(p.player, name))

    def test_injury_state_survives_roundtrip_with_same_current_limitation(self):
        e = self.engine(seed=8411)
        p = self.player(e)
        e.state.second = 35.0 * 60.0
        e._register_injury_state(0, p, {"grade": "minor", "body_area": "upper_body", "impact": 0.62, "forced_off": False})
        e.state.second += 7.5 * 60.0
        before = e.current_injury_status(0, p.player.name)
        clone = MatchEngineV13Injuries.from_json(e.export_json())
        after = clone.current_injury_status(0, p.player.name)
        self.assertEqual(before, after)
        self.assertEqual(e.rng.getstate(), clone.rng.getstate())

    def test_injury_outcome_enriches_existing_referee_result(self):
        e = self.engine(seed=8413)
        attacker = self.player(e, 0)
        defender = next(ps for ps in e.teams[1].on_field if ps.player.position.upper() in {"CB", "DM", "LB", "RB"})
        found = None
        incident = {"type": "reckless_tackle", "severity": 0.92, "spa": False, "dogso": False, "attempt_to_play_ball": True, "violent": False}
        for _ in range(250):
            result = e._injury_outcome(defender, attacker, incident)
            if result is not None:
                found = result
                break
        self.assertIsNotNone(found)
        self.assertIn("injury_region", found)
        self.assertIn("functional_limitation", found)
        self.assertIn("medical_action", found)


if __name__ == "__main__":
    unittest.main()
