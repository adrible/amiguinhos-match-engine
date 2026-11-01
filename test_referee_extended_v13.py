from __future__ import annotations

import unittest

from engine import Band, Event, EventType, Lane, PendingAction, Zone
from engine_experiment_v13 import MatchEngine
from team_loader_v13 import load_team_v13


class RefereeExtendedV13Tests(unittest.TestCase):
    def make_engine(self, seed=123):
        return MatchEngine(
            load_team_v13("amiguinhos_u21"),
            load_team_v13("flamengo_u21"),
            seed=seed,
        )

    @staticmethod
    def dribble_pending(team=0, actor="Pedro Valverde"):
        return PendingAction(
            team=team,
            actor=actor,
            kind="dribble",
            zone=Zone(Band.BOX, Lane.CENTER),
            danger=0.70,
            pressure=0.62,
            defender="João Victor" if team == 0 else "Igor",
            origin="dribble",
        )

    @staticmethod
    def shot_pending(team=0):
        return PendingAction(
            team=team,
            actor="Gabriel Félix" if team == 0 else "Victor Hugo",
            kind="shoot",
            zone=Zone(Band.BOX, Lane.CENTER),
            danger=0.72,
            pressure=0.58,
            defender="João Victor" if team == 0 else "Igor",
            origin="cross",
        )

    def test_behavioral_second_caution_is_always_harder_than_first(self):
        e = self.make_engine()
        for reason in ("dissent", "confrontation", "simulation", "retaliation"):
            factor = e._second_behavior_yellow_factor(reason)
            self.assertGreater(factor, 0.0)
            self.assertLess(factor, 1.0)

    def test_confrontation_second_yellow_can_be_managed_or_given(self):
        managed = 0
        dismissed = 0
        for seed in range(100, 140):
            e = self.make_engine(seed)
            player = e.teams[0].by_name("Felipe")
            player.yellow = 1
            applied = e._apply_reaction_sanctions(
                [{"team": 0, "player": player, "reason": "confrontation", "card": "yellow"}]
            )
            if player.red:
                dismissed += 1
                self.assertEqual(applied[0]["card"], "second_yellow_red")
            else:
                managed += 1
                self.assertEqual(applied, [])
        self.assertGreater(managed, 0)
        self.assertGreater(dismissed, 0)

    def test_unpunished_handball_contact_does_not_mutate_play(self):
        e = self.make_engine(seed=201)
        p = self.shot_pending()
        e.state.pending = p
        e.state.transition_boost = 0.37
        e.state.phase = "normal"
        defender = e.teams[1].by_name("João Victor")
        before_fouls = e.stats[1].fouls
        incident = e._build_handball_incident(
            p,
            defender,
            forced={
                "arm_position": "extended",
                "movement_to_ball": False,
                "offence": True,
                "certainty": 0.82,
                "spa": False,
                "dogso": False,
            },
        )
        ev = e._commit_handball(
            p,
            defender,
            incident,
            force_referee_call=False,
            force_var_intervention=False,
        )
        self.assertIsNone(ev)
        self.assertIs(e.state.pending, p)
        self.assertEqual(e.state.transition_boost, 0.37)
        self.assertEqual(e.state.phase, "normal")
        self.assertEqual(e.stats[1].fouls, before_fouls)

    def test_called_box_handball_awards_penalty_and_counts_foul(self):
        e = self.make_engine(seed=202)
        p = self.shot_pending()
        e.state.pending = p
        defender = e.teams[1].by_name("João Victor")
        before = e.stats[1].fouls
        incident = e._build_handball_incident(
            p,
            defender,
            forced={
                "arm_position": "extended",
                "movement_to_ball": False,
                "offence": True,
                "certainty": 0.88,
                "spa": False,
                "dogso": False,
            },
        )
        ev = e._commit_handball(p, defender, incident, force_referee_call=True)
        self.assertEqual(ev.type, EventType.PENALTY)
        self.assertEqual(ev.text_key, "penalty_for_handball")
        self.assertEqual(e.state.restart, "penalty")
        self.assertEqual(e.state.restart_team, 0)
        self.assertEqual(e.stats[1].fouls, before + 1)

    def test_var_can_award_missed_clear_handball_penalty(self):
        e = self.make_engine(seed=203)
        p = self.shot_pending()
        e.state.pending = p
        defender = e.teams[1].by_name("João Victor")
        incident = e._build_handball_incident(
            p,
            defender,
            forced={
                "arm_position": "above_shoulder",
                "movement_to_ball": False,
                "offence": True,
                "certainty": 0.94,
                "spa": False,
                "dogso": False,
            },
        )
        first = e._commit_handball(
            p,
            defender,
            incident,
            force_referee_call=False,
            force_var_intervention=True,
        )
        self.assertEqual(first.text_key, "var_check_missed_handball")
        self.assertIsNone(e.state.restart)
        review = e.step()
        self.assertEqual(review.text_key, "var_awards_penalty_handball")
        self.assertEqual(e.state.restart, "penalty")
        self.assertEqual(e.stats[1].fouls, 1)

    def test_detected_simulation_is_cautionable_and_turns_restart_over(self):
        e = self.make_engine(seed=204)
        p = self.dribble_pending()
        e.state.pending = p
        actor = e.teams[0].by_name("Pedro Valverde")
        ev = e._commit_simulation(p, actor, force_detected=True)
        self.assertEqual(ev.text_key, "simulation_detected")
        self.assertEqual(actor.yellow, 1)
        self.assertEqual(e.state.restart, "free_kick")
        self.assertEqual(e.state.restart_team, 1)

    def test_var_can_overturn_penalty_won_by_simulation(self):
        e = self.make_engine(seed=205)
        p = self.dribble_pending()
        e.state.pending = p
        actor = e.teams[0].by_name("Pedro Valverde")
        first = e._commit_simulation(
            p,
            actor,
            force_detected=False,
            force_fooled=True,
            force_var_overturn=True,
        )
        self.assertEqual(first.type, EventType.PENALTY)
        self.assertTrue(first.data["var_review_pending"])
        self.assertIsNone(e.state.restart)
        review = e.step()
        self.assertEqual(review.text_key, "var_overturns_penalty_simulation")
        self.assertEqual(e.state.restart, "free_kick")
        self.assertEqual(e.state.restart_team, 1)
        self.assertEqual(actor.yellow, 1)

    def test_concussion_protocol_forces_stoppage_instead_of_advantage(self):
        e = self.make_engine(seed=206)
        attacker = e.teams[0].by_name("Pedro Valverde")
        p = e._advantage_probability(
            0,
            attacker,
            Zone(Band.ATT, Lane.CENTER),
            {"type": "elbow_or_forearm", "severity": 0.75},
            None,
            {"grade": "head_check", "concussion_protocol": True},
        )
        self.assertEqual(p, 0.0)

    def test_match_heat_rises_after_confrontation_and_decays_with_time(self):
        e = self.make_engine(seed=207)
        start = e._match_heat
        ev = Event(
            minute=10.0,
            team=0,
            type=EventType.INFO,
            relevance=3,
            text_key="mass_confrontation",
            data={"reaction": "confront"},
        )
        e._update_match_heat(ev)
        hot = e._match_heat
        self.assertGreater(hot, start)
        e.state.second += 10 * 60
        e._decay_match_heat()
        self.assertLess(e._match_heat, hot)

    def test_extended_referee_state_and_pending_var_survive_roundtrip(self):
        e = self.make_engine(seed=208)
        p = self.dribble_pending()
        e.state.pending = p
        actor = e.teams[0].by_name("Pedro Valverde")
        _ = e._commit_simulation(
            p,
            actor,
            force_detected=False,
            force_fooled=True,
            force_var_overturn=True,
        )
        payload = e.export_json()
        restored = MatchEngine.from_json(payload)
        self.assertEqual(restored.referee_diagnostic(), e.referee_diagnostic())
        a = e.step()
        b = restored.step()
        self.assertEqual((a.type, a.team, a.text_key, a.data), (b.type, b.team, b.text_key, b.data))
        self.assertEqual(restored.snapshot(), e.snapshot())


if __name__ == "__main__":
    unittest.main()
