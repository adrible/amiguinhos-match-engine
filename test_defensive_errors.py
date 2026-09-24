from __future__ import annotations

import unittest

from engine import Band, Event, EventType, Lane, Zone, make_generic_team
from engine_experiment_v13_errors import MatchEngineV13Errors


BASE_CTX = {
    "pressure": 0.48,
    "space": 0.52,
    "space_behind": 0.45,
    "support": 0.50,
    "wide_space": 0.10,
    "defending_availability": 1.0,
}


def make_engine(seed=123):
    a = make_generic_team("Attack", 79, "balanced", seed=10)
    b = make_generic_team("Defence", 80, "balanced", seed=20)
    return MatchEngineV13Errors(a, b, seed=seed)


def actor_name(e):
    return next(ps.player.name for ps in e.teams[0].on_field if ps.player.position.upper() == "LW")


def target_name(e):
    return next(ps.player.name for ps in e.teams[0].on_field if ps.player.position.upper() == "ST")


def simple_plan(e, *, communication_quality=1.0, overload=False, switched=False):
    defender = next(ps for ps in e.teams[1].on_field if ps.player.position.upper() == "CB")
    return {
        "intent": "contain",
        "defender": defender,
        "defender_name": defender.player.name,
        "quality": 0.72,
        "effects": {
            "pressure_delta": 0.02,
            "space_delta": -0.03,
            "depth_delta": 0.0,
            "wide_space_delta": 0.0,
            "pass_lane_control": 0.04,
            "runner_control": 0.05,
            "dribble_control": 0.05,
            "cross_control": 0.03,
            "box_protection": 0.03,
        },
        "marking": {
            "switched": switched,
            "handoff_quality": 0.45 if switched else 1.0,
        },
        "coverage": {"active": False},
        "communication": {
            "active": communication_quality < 1.0,
            "quality": communication_quality,
        },
        "overload": {
            "active": overload,
            "attackers_count": 3 if overload else 1,
            "defenders_count": 2 if overload else 1,
        },
    }


class DefensiveErrorTests(unittest.TestCase):
    def test_high_stress_low_quality_defence_has_more_error_risk(self):
        calm = make_engine(seed=8)
        stressed = make_engine(seed=8)

        for engine, value, energy in ((calm, 94, 1.0), (stressed, 56, 0.48)):
            for ps in engine.teams[1].on_field:
                for attr in ("positioning", "anticipation", "composure", "discipline", "tackling", "pace"):
                    setattr(ps.player, attr, value)
                ps.energy = energy

        calm.state.transition_boost = 0.0
        stressed.state.transition_boost = 1.0
        dc = calm.defensive_error_diagnostic(
            0,
            Zone(Band.ATT, Lane.LEFT),
            dict(BASE_CTX, space=0.28, space_behind=0.24, support=0.30),
            kind="dribble",
            actor=actor_name(calm),
        )
        ds = stressed.defensive_error_diagnostic(
            0,
            Zone(Band.ATT, Lane.LEFT),
            dict(BASE_CTX, space=0.82, space_behind=0.78, support=0.86),
            kind="dribble",
            actor=actor_name(stressed),
        )
        self.assertGreater(ds["risk"], dc["risk"])
        self.assertGreater(ds["fatigue"], dc["fatigue"])

    def test_fatigue_raises_risk_for_same_defender_profile(self):
        fresh = make_engine(seed=12)
        tired = make_engine(seed=12)
        for ef, et in zip(fresh.teams[1].on_field, tired.teams[1].on_field):
            et.player.__dict__.update(ef.player.__dict__)
            ef.energy = 1.0
            et.energy = 0.42

        df = fresh.defensive_error_diagnostic(
            0, Zone(Band.MID, Lane.CENTER), BASE_CTX,
            kind="progressive_pass", actor=actor_name(fresh), target=target_name(fresh),
        )
        dt = tired.defensive_error_diagnostic(
            0, Zone(Band.MID, Lane.CENTER), BASE_CTX,
            kind="progressive_pass", actor=actor_name(tired), target=target_name(tired),
        )
        self.assertGreater(dt["risk"], df["risk"])

    def test_good_communication_reduces_coordination_error_risk(self):
        e = make_engine()
        defender = next(ps for ps in e.teams[1].on_field if ps.player.position.upper() == "CB")
        defender.energy = 0.82
        low_plan = simple_plan(e, communication_quality=0.30, switched=True)
        high_plan = simple_plan(e, communication_quality=0.92, switched=True)
        # Keep handoff stress identical so the comparison isolates the call.
        high_plan["marking"]["handoff_quality"] = low_plan["marking"]["handoff_quality"]
        low = e._defensive_error_profile(
            0, Zone(Band.ATT, Lane.CENTER), BASE_CTX, low_plan,
            kind="through_ball", target=target_name(e),
        )
        high = e._defensive_error_profile(
            0, Zone(Band.ATT, Lane.CENTER), BASE_CTX, high_plan,
            kind="through_ball", target=target_name(e),
        )
        self.assertGreater(low["communication_stress"], high["communication_stress"])
        self.assertGreater(low["risk"], high["risk"])

    def test_local_overload_increases_execution_burden(self):
        e = make_engine()
        normal = simple_plan(e, overload=False)
        overloaded = simple_plan(e, overload=True)
        p1 = e._defensive_error_profile(
            0, Zone(Band.ATT, Lane.LEFT), BASE_CTX, normal,
            kind="dribble", target=None,
        )
        p2 = e._defensive_error_profile(
            0, Zone(Band.ATT, Lane.LEFT), BASE_CTX, overloaded,
            kind="dribble", target=None,
        )
        self.assertEqual(p1["overload_severity"], 0.0)
        self.assertGreater(p2["overload_severity"], 0.0)
        self.assertGreater(p2["risk"], p1["risk"])

    def test_realised_error_changes_duel_state_not_score(self):
        e = make_engine()
        base = {
            "pressure": 0.60,
            "space": 0.35,
            "space_behind": 0.30,
            "pass_lane_control": 0.08,
            "runner_control": 0.08,
            "dribble_control": 0.08,
            "cross_control": 0.07,
            "box_protection": 0.07,
        }
        score_before = e.score
        stats_before = (e.stats[0].goals, e.stats[1].goals)
        for error_type in (
            "bad_handoff", "lost_runner", "overcommit",
            "wrong_lane_read", "late_block", "poor_body_position",
        ):
            profile = {
                "error_type": error_type,
                "severity": 0.8,
                "risk": 0.08,
                "defender": "D",
            }
            adjusted = e._apply_defensive_error(base, profile)
            helps_attack = (
                adjusted.get("pressure", base["pressure"]) < base["pressure"]
                or adjusted.get("space", base["space"]) > base["space"]
                or adjusted.get("space_behind", base["space_behind"]) > base["space_behind"]
                or adjusted.get("pass_lane_control", base["pass_lane_control"]) < base["pass_lane_control"]
                or adjusted.get("runner_control", base["runner_control"]) < base["runner_control"]
                or adjusted.get("dribble_control", base["dribble_control"]) < base["dribble_control"]
                or adjusted.get("box_protection", base["box_protection"]) < base["box_protection"]
            )
            self.assertTrue(helps_attack, error_type)
        self.assertEqual(e.score, score_before)
        self.assertEqual((e.stats[0].goals, e.stats[1].goals), stats_before)

    def test_diagnostic_is_rng_pure(self):
        e = make_engine(seed=44)
        before = e.rng.getstate()
        _ = e.defensive_error_diagnostic(
            0, Zone(Band.ATT, Lane.LEFT), BASE_CTX,
            kind="through_ball", actor=actor_name(e), target=target_name(e),
        )
        after = e.rng.getstate()
        self.assertEqual(before, after)

    def test_error_diagnostic_does_not_modify_player_attributes(self):
        e = make_engine()
        defender = next(ps for ps in e.teams[1].on_field if ps.player.position.upper() == "CB")
        before = (
            defender.effective("positioning"), defender.effective("anticipation"),
            defender.effective("composure"), defender.effective("discipline"),
            defender.effective("tackling"), defender.energy,
        )
        _ = e.defensive_error_diagnostic(
            0, Zone(Band.BOX, Lane.CENTER), BASE_CTX,
            kind="shoot", actor=actor_name(e), target=target_name(e),
        )
        after = (
            defender.effective("positioning"), defender.effective("anticipation"),
            defender.effective("composure"), defender.effective("discipline"),
            defender.effective("tackling"), defender.energy,
        )
        self.assertEqual(before, after)

    def test_one_live_window_can_realise_at_most_one_error(self):
        e = make_engine(seed=5)
        profile_a = {
            "risk": 1.0, "error_type": "overcommit", "severity": 0.8,
            "defender": "D1",
        }
        profile_b = {
            "risk": 1.0, "error_type": "lost_runner", "severity": 0.8,
            "defender": "D2",
        }

        seen = []
        def run():
            seen.append(e._realise_defensive_error(profile_a))
            seen.append(e._realise_defensive_error(profile_b))
            return Event(1.0, 0, EventType.DANGER, 2, "test", {})

        event = e._with_error_window(run)
        self.assertEqual(seen, [True, False])
        self.assertEqual(event.data["defensive_error"]["type"], "overcommit")
        self.assertEqual(event.data["defensive_error"]["defender"], "D1")

    def test_same_seed_reproducible_with_contextual_errors(self):
        a1 = make_generic_team("A", 78, "balanced", seed=10)
        b1 = make_generic_team("B", 80, "balanced", seed=20)
        a2 = make_generic_team("A", 78, "balanced", seed=10)
        b2 = make_generic_team("B", 80, "balanced", seed=20)
        e1 = MatchEngineV13Errors(a1, b1, seed=999)
        e2 = MatchEngineV13Errors(a2, b2, seed=999)
        for _ in range(260):
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
