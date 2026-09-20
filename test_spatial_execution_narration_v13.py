import copy
import unittest
from unittest.mock import patch
from engine import Band, Lane, Zone, PendingAction, Event, EventType, make_generic_team
from engine_experiment_v13 import MatchEngine
from runner_v13 import MatchSessionV13
from spatial_shot_v13 import shot_geometry, keeper_response


def fixture(seed=33):
    return MatchEngine(make_generic_team('Home', 80, 'balanced', seed=11),
                       make_generic_team('Away', 80, 'balanced', seed=22), seed=seed)


class SpatialExecutionTests(unittest.TestCase):
    def setup_shot(self):
        e = fixture()
        a = next(p for p in e.teams[0].on_field if p.player.position == 'ST')
        p = PendingAction(0, a.player.name, 'shoot', Zone(Band.BOX, Lane.CENTER), danger=.6, pressure=.3)
        return e, a, p, e._goalkeeper(1)

    def test_intention_is_separate_and_reproducible(self):
        e, a, p, k = self.setup_shot()
        d = e.shot_selection_diagnostic(a, p, k)
        g = shot_geometry(e, p, a, k, d)
        self.assertNotEqual(g['intended_goal_position'], g['actual_goal_position'])
        self.assertEqual(g, shot_geometry(e, p, a, k, d))
        self.assertGreater(g['shot_speed_mps'], 0)

    def test_selected_target_is_the_physical_intention(self):
        e, a, p, k = self.setup_shot()
        for second in range(80):
            e.state.second = second
            selection = e.shot_selection_diagnostic(a, p, k)
            g = shot_geometry(e, p, a, k, selection)
            self.assertEqual(g['shot_target'], selection['target_zone'])

    def test_handling_contributes_to_spatial_save_response(self):
        e, a, p, k = self.setup_shot()
        original = k.player.handling
        try:
            k.player.handling = 40
            weak = keeper_response(k, 0, .55, 0, 12, 18, 'placed')
            k.player.handling = 95
            strong = keeper_response(k, 0, .55, 0, 12, 18, 'placed')
        finally:
            k.player.handling = original
        self.assertLess(strong['spatial_conversion_multiplier'], weak['spatial_conversion_multiplier'])
        self.assertGreater(strong['keeper_attribute_weights']['handling'], 0)

    def test_corner_harder_to_save_and_near_post_position_exposes_far_side(self):
        e, a, p, k = self.setup_shot()
        center = keeper_response(k, 0, .8, 0, 12, 24, 'placed')
        corner = keeper_response(k, 3.3, 2.2, 0, 12, 24, 'placed')
        far = keeper_response(k, -3, 1, 1.5, 12, 24, 'placed')
        near = keeper_response(k, 3, 1, 1.5, 12, 24, 'placed')
        self.assertGreater(corner['spatial_conversion_multiplier'], center['spatial_conversion_multiplier'])
        self.assertGreater(far['spatial_conversion_multiplier'], near['spatial_conversion_multiplier'])

    def test_physical_off_target_never_scores_and_does_not_change_xg(self):
        e, a, p, k = self.setup_shot()
        state = e.export_json()
        from spatial_shot_v13 import shot_geometry as real_geometry
        def forced(on):
            def build(*args):
                d = real_geometry(*args)
                d.update(spatial_on_target=on, spatial_hits_frame=False, keeper_exposed=True,
                         actual_goal_position={'x': 0 if on else 8, 'z': 1})
                return d
            return build
        outcomes = []
        for on in [False, True]:
            clone = MatchEngine.from_json(state)
            with patch('spatial_shot_v13.shot_geometry', side_effect=forced(on)), patch.object(clone.rng, 'random', return_value=.99):
                ev = clone._resolve_shot(copy.deepcopy(p))
            outcomes.append((clone.stats[0].xg, clone.stats[0].goals, ev))
        self.assertEqual(outcomes[0][0], outcomes[1][0])
        self.assertEqual(outcomes[0][1], 0)
        self.assertEqual(outcomes[1][1], 1)

    def test_high_corner_is_harder_to_execute_than_center(self):
        e, a, p, k = self.setup_shot()
        counts = {"central": [0, 0], "high_far_corner": [0, 0]}
        for i in range(2000):
            e.state.second = i
            g = shot_geometry(e, p, a, k, e.shot_selection_diagnostic(a, p, k))
            if g["shot_target"] in counts:
                row = counts[g["shot_target"]]
                row[0] += g["spatial_on_target"]
                row[1] += 1
        center, high = counts["central"], counts["high_far_corner"]
        self.assertGreater(center[0] / center[1], high[0] / high[1] + .15)

    def test_targets_and_execution_vary_without_low_corner_lock(self):
        e, a, p, k = self.setup_shot()
        targets = set()
        for i in range(100):
            e.state.second = i
            g = shot_geometry(e, p, a, k, e.shot_selection_diagnostic(a, p, k))
            targets.add(g['shot_target'])
        self.assertGreaterEqual(len(targets), 6)

    def test_creativity_changes_attempts_and_every_special_pass_has_purpose(self):
        e, a, p, k = self.setup_shot()
        counts = []
        for creativity in [30, 95]:
            a.player.creativity = creativity
            count = 0
            for i in range(400):
                e.state.second = i
                d = e.creative_pass_diagnostic(a, p.zone, 'through_ball', {'pressure': .5, 'support': .7})
                if d['attempt']:
                    count += 1
                    self.assertTrue(d['purpose'])
                    self.assertGreater(d['difficulty'], 0)
            counts.append(count)
        self.assertGreater(counts[1], counts[0] * 2)

    def test_keeper_return_is_visible_and_persisted(self):
        e = fixture()
        e._activate_keeper_up(0, 5)
        e.state.second = 6
        event = e._emit(EventType.INFO, 1, 1, 'safe_pass')
        self.assertEqual(event.data['keeper_returned_team'], 0)
        self.assertFalse(e._keeper_is_exposed(0))


class BatchTests(unittest.TestCase):
    def test_packet_grouping_preserves_raw_engine_physics(self):
        session = MatchSessionV13(fixture(58))
        raw = fixture(58)
        session.press_p_batch(30)
        while len(raw.state.event_log) < len(session.engine.state.event_log):
            raw.step()
        self.assertEqual(raw.export_json(), session.export_json())

    def test_real_halftime_does_not_start_second_half(self):
        session = MatchSessionV13(fixture())
        session.engine.state.second = 45 * 60
        packets = session.press_p_batch(10)
        self.assertEqual(packets[-1]["main_event"]["type"], "period_end")
        self.assertEqual(session.engine.state.restart, "kickoff")

    def test_five_and_ten_match_individual_presses(self):
        for count in [5, 10]:
            a, b = MatchSessionV13(fixture()), MatchSessionV13(fixture())
            self.assertEqual(a.press_p_batch(count), [b.press_p_packet() for _ in range(count)])
            self.assertEqual(a.export_json(), b.export_json())

    def test_boundary_stops_without_consuming_kickoff(self):
        s = MatchSessionV13(fixture())
        packets = [{'main_event': {'type': 'goal'}}, {'main_event': {'type': 'period_end'}}]
        with patch.object(s, 'press_p_packet', side_effect=packets) as press:
            self.assertEqual(len(s.press_p_batch(10)), 2)
            self.assertEqual(press.call_count, 2)

    def test_finished_batch_empty_and_invalid_counts_rejected(self):
        s = MatchSessionV13(fixture())
        s.engine.state.ended = True
        self.assertEqual(s.press_p_batch(5), [])
        for count in [0, -1, 101, True, 1.5]:
            with self.assertRaises(ValueError):
                s.press_p_batch(count)

    def test_foul_aftermath_is_one_packet(self):
        s = MatchSessionV13(fixture())
        e = s.engine
        def advance(**kwargs):
            ev = e._emit(EventType.FOUL, 0, 2, 'foul', fouled='A', defender='B')
            e._queue_event(EventType.INFO, 0, 2, 'player_reaction_to_foul', fouled='A', defender='B')
            e._queue_event(EventType.CARD, 1, 2, 'card_shown_contextual', player='B', card='yellow')
            return ev
        with patch.object(e, 'advance_until_relevant', side_effect=advance):
            packet = s.press_p_packet()
        self.assertEqual(len(packet['bridge_events']), 2)
        self.assertEqual(e._referee_event_queue, [])

    def test_pending_resolution_preserved_even_if_clearance_is_low_relevance(self):
        s = MatchSessionV13(fixture())
        e = s.engine
        actor = next(p for p in e.teams[0].on_field if p.player.position != 'GK')
        e.state.pending = PendingAction(0, actor.player.name, 'cross', Zone(Band.ATT, Lane.LEFT), danger=.4, pressure=.6)
        event = e._resolve_pending()
        self.assertEqual(event.data['resolved_pending_action']['kind'], 'cross')
        self.assertGreaterEqual(event.relevance, 2)

if __name__ == '__main__':
    unittest.main()
