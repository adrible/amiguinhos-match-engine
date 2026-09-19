from __future__ import annotations

import unittest

from engine import Band, Lane, Player, PlayerState, Tactics, Team, Zone, make_generic_team
from engine_experiment_v13_spatial import MatchEngineV13Spatial


BASE_CTX = {
    "pressure": 0.42,
    "space": 0.58,
    "space_behind": 0.48,
    "support": 0.55,
}


def player_state(**kw):
    defaults = dict(
        name="Test",
        position="AM",
        overall=78,
        pace=78,
        passing=80,
        vision=82,
        technique=82,
        dribbling=80,
        crossing=75,
        finishing=78,
        long_shots=80,
        composure=80,
        anticipation=80,
        off_ball=80,
        preferred_foot="R",
    )
    defaults.update(kw)
    return PlayerState(Player(**defaults))


def make_creator_engine(creativity=88, boldness=60, risky=True):
    creator = Player(
        name="Creator", position="CM", overall=78,
        passing=76 if risky else 84,
        vision=80 if risky else 86,
        technique=78 if risky else 85,
        composure=78 if risky else 82,
        dribbling=75, pace=72, off_ball=74,
        anticipation=76 if risky else 80,
        finishing=68, long_shots=72,
    )
    creator.creativity = creativity
    creator.boldness = boldness

    st = Player(
        name="Obvious ST", position="ST", overall=80, pace=79,
        technique=80, finishing=88, off_ball=86,
        anticipation=84, composure=84,
    )
    am = Player(
        name="Obvious AM", position="AM", overall=79, pace=76,
        technique=83, finishing=76, off_ball=80,
        anticipation=80, composure=81,
    )
    runner = Player(
        name="Blind Runner", position="RW", overall=80,
        pace=94, technique=79, finishing=75,
        off_ball=94, anticipation=90, composure=76,
    )
    support = [
        Player(name="GK", position="GK"),
        Player(name="RB", position="RB"),
        Player(name="CB1", position="CB"),
        Player(name="CB2", position="CB"),
        Player(name="LB", position="LB"),
        Player(name="DM", position="DM"),
        Player(name="CM2", position="CM"),
    ]
    team = Team(
        "Creative Team",
        starters=[
            support[0], support[1], support[2], support[3], support[4],
            support[5], creator, support[6], am, runner, st
        ],
        tactics=Tactics(risk=0.58, mentality=0.18),
    )
    opp = make_generic_team("Opp", 78, "balanced", seed=99)
    engine = MatchEngineV13Spatial(team, opp, seed=555)
    actor = engine.teams[0].by_name("Creator")
    return engine, actor


class SpatialDecisionTests(unittest.TestCase):
    def setUp(self):
        a = make_generic_team("A", 75, "balanced", seed=1)
        b = make_generic_team("B", 75, "balanced", seed=2)
        self.engine = MatchEngineV13Spatial(a, b, seed=123)
        self.tactics = Tactics()

    def probs(self, actor, band, lane=Lane.CENTER, ctx=None):
        return self.engine.decision_probabilities(
            actor,
            Zone(band, lane),
            self.tactics,
            dict(BASE_CTX if ctx is None else ctx),
        )

    def test_same_player_shoots_far_more_in_opponent_box_than_deep(self):
        actor = player_state(finishing=84, long_shots=84)
        deep = self.probs(actor, Band.DEF)
        box = self.probs(actor, Band.BOX)
        self.assertNotIn("shoot", deep)
        self.assertGreater(box["shoot"], 0.50)

    def test_central_box_favors_shot_more_than_wide_box(self):
        actor = player_state(finishing=82)
        center = self.probs(actor, Band.BOX, Lane.CENTER)
        wide = self.probs(actor, Band.BOX, Lane.LEFT)
        self.assertGreater(center["shoot"], wide["shoot"])
        self.assertGreater(wide["cutback"], center["cutback"])

    def test_heavy_pressure_deep_increases_direct_escape(self):
        actor = player_state(composure=72, passing=76)
        calm = self.probs(actor, Band.DEF, ctx={**BASE_CTX, "pressure": 0.18})
        pressed = self.probs(actor, Band.DEF, ctx={**BASE_CTX, "pressure": 0.90})
        self.assertGreater(pressed["long_ball"], calm["long_ball"])
        self.assertLess(pressed["carry"], calm["carry"])

    def test_inverted_winger_gets_more_wide_shooting_weight(self):
        right_foot = player_state(preferred_foot="R", long_shots=84)
        left_foot = player_state(preferred_foot="L", long_shots=84)
        inv = self.probs(right_foot, Band.ATT, Lane.LEFT)
        natural = self.probs(left_foot, Band.ATT, Lane.LEFT)
        self.assertGreater(inv["shoot"], natural["shoot"])

    def test_finisher_and_creator_behave_differently_in_box(self):
        finisher = player_state(finishing=92, vision=70, passing=72, dribbling=72)
        creator = player_state(finishing=68, vision=92, passing=90, dribbling=84)
        pf = self.probs(finisher, Band.BOX, Lane.CENTER)
        pc = self.probs(creator, Band.BOX, Lane.CENTER)
        self.assertGreater(pf["shoot"], pc["shoot"])
        self.assertGreater(pc["cutback"], pf["cutback"])

    def test_decision_profile_is_normalized(self):
        actor = player_state()
        for band in Band:
            p = self.probs(actor, band)
            self.assertAlmostEqual(sum(p.values()), 1.0, places=9)
            self.assertTrue(all(v >= 0 for v in p.values()))

    def test_same_seed_still_reproducible(self):
        a1 = make_generic_team("A", 75, "balanced", seed=10)
        b1 = make_generic_team("B", 77, "balanced", seed=20)
        a2 = make_generic_team("A", 75, "balanced", seed=10)
        b2 = make_generic_team("B", 77, "balanced", seed=20)
        e1 = MatchEngineV13Spatial(a1, b1, seed=999)
        e2 = MatchEngineV13Spatial(a2, b2, seed=999)
        for _ in range(150):
            if e1.state.ended or e2.state.ended:
                break
            x1 = e1.step()
            x2 = e2.step()
            self.assertEqual(
                (x1.type, x1.team, x1.text_key, x1.data),
                (x2.type, x2.team, x2.text_key, x2.data),
            )
        self.assertEqual(e1.snapshot(), e2.snapshot())


class CreativityAndBoldnessTests(unittest.TestCase):
    zone = Zone(Band.ATT, Lane.CENTER)
    ctx = {
        "pressure": 0.60,
        "space": 0.40,
        "space_behind": 0.80,
        "support": 0.45,
    }

    def test_creativity_changes_perception_not_action_menu(self):
        low, a_low = make_creator_engine(creativity=42, boldness=60)
        high, a_high = make_creator_engine(creativity=92, boldness=60)
        p_low = low.decision_probabilities(a_low, self.zone, low.teams[0].team.tactics, self.ctx)
        p_high = high.decision_probabilities(a_high, self.zone, high.teams[0].team.tactics, self.ctx)
        self.assertEqual(p_low, p_high)

        d_low = low.hidden_option_diagnostic(0, a_low, self.zone, self.ctx)
        d_high = high.hidden_option_diagnostic(0, a_high, self.zone, self.ctx)
        self.assertEqual(d_low["target_name"], "Blind Runner")
        self.assertEqual(d_high["target_name"], "Blind Runner")
        self.assertGreater(d_high["perception_probability"], d_low["perception_probability"])

    def test_boldness_does_not_change_what_is_perceived(self):
        safe, a_safe = make_creator_engine(creativity=88, boldness=35)
        bold, a_bold = make_creator_engine(creativity=88, boldness=90)
        d_safe = safe.hidden_option_diagnostic(0, a_safe, self.zone, self.ctx)
        d_bold = bold.hidden_option_diagnostic(0, a_bold, self.zone, self.ctx)
        self.assertAlmostEqual(
            d_safe["perception_probability"],
            d_bold["perception_probability"],
            places=12,
        )
        self.assertGreater(
            d_bold["acceptance_probability_if_perceived"],
            d_safe["acceptance_probability_if_perceived"],
        )

    def test_tactical_risk_changes_acceptance_not_perception(self):
        low_risk, a_low = make_creator_engine(creativity=88, boldness=60)
        high_risk, a_high = make_creator_engine(creativity=88, boldness=60)
        low_risk.teams[0].team.tactics.risk = 0.20
        high_risk.teams[0].team.tactics.risk = 0.90
        d_low = low_risk.hidden_option_diagnostic(0, a_low, self.zone, self.ctx)
        d_high = high_risk.hidden_option_diagnostic(0, a_high, self.zone, self.ctx)
        self.assertAlmostEqual(
            d_low["perception_probability"],
            d_high["perception_probability"],
            places=12,
        )
        self.assertGreater(
            d_high["acceptance_probability_if_perceived"],
            d_low["acceptance_probability_if_perceived"],
        )

    def test_adib_style_boldness_accepts_more_high_risk_high_reward(self):
        conservative, a_cons = make_creator_engine(creativity=88, boldness=50)
        aggressive, a_aggr = make_creator_engine(creativity=88, boldness=86)
        r_cons = conservative.risk_reward_diagnostic(0, a_cons, self.zone, self.ctx)
        r_aggr = aggressive.risk_reward_diagnostic(0, a_aggr, self.zone, self.ctx)

        self.assertTrue(r_cons["qualifies"])
        self.assertTrue(r_aggr["qualifies"])
        self.assertGreater(r_cons["expected_deficit"], 0.0)
        self.assertGreater(r_aggr["acceptance_probability"], r_cons["acceptance_probability"])
        self.assertGreater(r_aggr["risk_appetite"], r_cons["risk_appetite"])

    def test_high_boldness_still_rejects_a_bad_hidden_option(self):
        engine, actor = make_creator_engine(creativity=95, boldness=100)
        runner = engine.teams[0].by_name("Blind Runner")
        runner.player.pace = 58
        runner.player.off_ball = 58
        runner.player.anticipation = 56
        runner.player.technique = 62
        runner.player.finishing = 60
        runner.player.composure = 62

        hidden = engine.hidden_option_diagnostic(0, actor, self.zone, self.ctx)
        self.assertFalse(hidden["qualifies"])
        self.assertEqual(hidden["effective_hidden_choice_probability"], 0.0)

    def test_losing_late_increases_risk_tolerance_and_lead_reduces_it(self):
        draw, a_draw = make_creator_engine(creativity=88, boldness=60)
        losing, a_losing = make_creator_engine(creativity=88, boldness=60)
        winning, a_winning = make_creator_engine(creativity=88, boldness=60)
        for engine in (draw, losing, winning):
            engine.state.second = 85 * 60

        losing.stats[1].goals = 1
        winning.stats[0].goals = 1

        r_draw = draw.risk_reward_diagnostic(0, a_draw, self.zone, self.ctx)
        r_losing = losing.risk_reward_diagnostic(0, a_losing, self.zone, self.ctx)
        r_winning = winning.risk_reward_diagnostic(0, a_winning, self.zone, self.ctx)

        self.assertGreater(r_losing["risk_appetite"], r_draw["risk_appetite"])
        self.assertLess(r_winning["risk_appetite"], r_draw["risk_appetite"])
        self.assertGreater(r_losing["acceptance_probability"], r_draw["acceptance_probability"])
        self.assertLess(r_winning["acceptance_probability"], r_draw["acceptance_probability"])

    def test_creativity_and_boldness_do_not_change_execution_attributes(self):
        engine, actor = make_creator_engine(creativity=95, boldness=95)
        before = (
            actor.effective("passing"),
            actor.effective("technique"),
            actor.effective("vision"),
        )
        actor.player.creativity = 20
        actor.player.boldness = 20
        after = (
            actor.effective("passing"),
            actor.effective("technique"),
            actor.effective("vision"),
        )
        self.assertEqual(before, after)

    def test_v13_traits_survive_json_roundtrip(self):
        engine, actor = make_creator_engine(creativity=88, boldness=86)
        payload = engine.export_json()
        restored = MatchEngineV13Spatial.from_json(payload)
        restored_actor = restored.teams[0].by_name("Creator")
        self.assertEqual(restored_actor.player.creativity, 88)
        self.assertEqual(restored_actor.player.boldness, 86)
        self.assertEqual(restored.snapshot(), engine.snapshot())

    def test_accepted_hidden_option_binds_action_and_receiver(self):
        engine, actor = make_creator_engine(creativity=95, boldness=95)
        info = engine._hidden_opportunity(0, actor, self.zone, self.ctx)
        self.assertIsNotNone(info)
        self.assertTrue(info["qualifies"])
        self.assertEqual(info["target_name"], "Blind Runner")

        # Force perception + sane acceptance to isolate the coupling contract.
        engine._creative_scope = lambda *args, **kwargs: 1.0
        original_profile = engine._risk_reward_profile
        engine._risk_reward_profile = lambda *args, **kwargs: {"acceptance_probability": 1.0}
        original_random = engine.rng.random
        engine.rng.random = lambda: 0.0
        try:
            decision = engine._choose_decision(
                actor, self.zone, engine.teams[0].team.tactics, self.ctx
            )
            self.assertEqual(decision, "through_ball")
            self.assertEqual(engine._v13_forced_target["target"], "Blind Runner")

            target = engine._choose_target(
                0, self.zone, attacking=True, exclude=actor.player.name
            )
            self.assertEqual(target.player.name, "Blind Runner")
            self.assertIsNone(engine._v13_forced_target)
        finally:
            engine.rng.random = original_random
            engine._risk_reward_profile = original_profile

    def test_safe_pass_never_uses_creative_forced_target(self):
        engine, actor = make_creator_engine(creativity=100, boldness=100)
        engine._v13_forced_target = {
            "team": 0, "actor": actor.player.name,
            "target": "Blind Runner", "action": "through_ball",
        }
        # Defensive/safe target selection delegates to the stable behavior and
        # cannot consume a creative attacking target by accident.
        target = engine._choose_target(
            0, self.zone, attacking=False, exclude=actor.player.name
        )
        self.assertNotEqual(target.player.name, actor.player.name)
        self.assertIsNotNone(engine._v13_forced_target)


if __name__ == "__main__":
    unittest.main()
