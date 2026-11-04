import copy
import math
import unittest

from engine import Band, Lane, Zone, PendingAction, Event, EventType, make_generic_team
from engine_experiment_v13 import MatchEngine
from engine_experiment_v13_coordinates import PitchPlayerState
from runner_v13 import MatchSessionV13


class CoordinatesTests(unittest.TestCase):
    def fixture(self, seed=123):
        return MatchEngine(make_generic_team("A", 80, seed=11),
                           make_generic_team("B", 80, seed=22), seed=seed)

    def test_all_starters_have_distinct_physical_points_and_opposite_directions(self):
        e = self.fixture()
        frame = e.pitch_snapshot()
        self.assertEqual(len(frame["players"]), 22)
        self.assertEqual(frame["attack_directions"], [1, -1])
        self.assertEqual(len({(p["x"], p["y"]) for p in frame["players"]}), 22)
        for p in frame["players"]:
            self.assertTrue(0 <= p["x"] <= 105 and 0 <= p["y"] <= 68)
            self.assertLessEqual(p["x"], 52.5) if p["team"] == 0 else self.assertGreaterEqual(p["x"], 52.5)
        self.assertIsInstance(e.teams[0].on_field[0], PitchPlayerState)

    def test_inspection_is_detached_rng_pure_and_state_pure(self):
        e = self.fixture()
        before = e.export_state()
        frame = e.pitch_snapshot()
        frame["players"][0]["x"] = 105.
        frame["ball"]["x"] = 1.
        for _ in range(3):
            e.spatial_reading(0)
            e.pitch_snapshot()
        self.assertEqual(e.export_state(), before)

    def test_external_frame_is_atomic_and_rejects_bad_points(self):
        e = self.fixture()
        frame = e.pitch_snapshot()
        for value in (float("nan"), float("inf"), -1., 106., True):
            bad = copy.deepcopy(frame["players"])
            bad[-1]["x"] = value
            before = e.export_state()
            with self.assertRaises(ValueError):
                e.set_tracking_frame(bad)
            self.assertEqual(before, e.export_state())
        with self.assertRaises(ValueError):
            e.set_tracking_frame(frame["players"][:-1])
        with self.assertRaises(ValueError):
            e.set_tracking_frame(frame["players"] + [frame["players"][0]])

    def test_external_frame_is_actually_read_by_pressure_and_pass_lanes(self):
        e = self.fixture()
        actor = e.teams[0].on_field[-1]
        target = e.teams[0].on_field[-2]
        e.set_player_coordinates(0, actor.player.name, 50., 34.)
        e.set_player_coordinates(0, target.player.name, 70., 34.)
        for opponent in e.teams[1].on_field:
            e.set_player_coordinates(1, opponent.player.name, 100., 67.)
        far = e.spatial_reading(0, actor.player.name)
        blocker = e.teams[1].on_field[2]
        e.set_player_coordinates(1, blocker.player.name, 51., 34.)
        close = e.spatial_reading(0, actor.player.name)
        self.assertGreater(close["local_pressure"], far["local_pressure"])
        corridor = next(p for p in close["passes"] if p["player"] == target.player.name)
        self.assertAlmostEqual(corridor["opponent_clearance"], 0.)
        self.assertAlmostEqual(corridor["distance"], 20.)

    def test_geometry_changes_engine_context_not_only_telemetry(self):
        e = self.fixture()
        state = e.rng.getstate()
        e.set_tracking_frame(e.pitch_snapshot()["players"], ball={"x": 52.5, "y": 34.})
        for opponent in e.teams[1].on_field:
            e.set_player_coordinates(1, opponent.player.name, 100., 67.)
        far = e._spatial_context(0, Zone(Band.MID, Lane.CENTER))
        e.rng.setstate(state)
        for opponent in e.teams[1].on_field:
            e.set_player_coordinates(1, opponent.player.name, 53., 34.)
        near = e._spatial_context(0, Zone(Band.MID, Lane.CENTER))
        self.assertGreater(near["pressure"], far["pressure"])
        self.assertLess(near["space"], far["space"])

    def test_previously_accepted_home_context_is_not_scaled_down(self):
        neutral = self.fixture()
        home = MatchEngine(make_generic_team("A", 80, seed=11),
                           make_generic_team("B", 80, seed=22), seed=123,
                           venue_context="home_away")
        zone = Zone(Band.MID, Lane.CENTER)
        n, h = neutral._spatial_context(0, zone), home._spatial_context(0, zone)
        venue = home._venue_effects(0)
        for key in ("pressure", "support", "space"):
            self.assertAlmostEqual(h[key] - n[key], venue[key + "_shift"], places=6)

    def test_nearby_defender_receives_more_engagement_weight(self):
        e = self.fixture()
        ps = e.teams[1].on_field[2]
        zone = Zone(Band.MID, Lane.CENTER)
        e.set_player_coordinates(1, ps.player.name, 100., 67.)
        far = e._defender_engagement_weight(ps, zone)
        e.set_player_coordinates(1, ps.player.name, 52.5, 34.)
        self.assertGreater(e._defender_engagement_weight(ps, zone), far)

    def test_movement_is_persistent_speed_limited_and_rng_free(self):
        e = self.fixture()
        before = e.pitch_snapshot()
        rng = e.rng.getstate()
        e._move_players(.1)
        after = e.pitch_snapshot()
        moved = False
        for p, q in zip(before["players"], after["players"]):
            distance = math.hypot(p["x"] - q["x"], p["y"] - q["y"])
            self.assertLessEqual(distance, .85 + 1e-9)
            moved |= distance > 0
        self.assertTrue(moved)
        self.assertEqual(e.rng.getstate(), rng)

    def test_formation_and_tactics_change_movement_destinations(self):
        e = self.fixture()
        before = e._formation_anchors(0)
        e.set_tactics(0, formation="4-3-3", width=1.)
        self.assertNotEqual(before, e._formation_anchors(0))
        e._move_players(5.)
        self.assertTrue(all(0 <= p.x <= 105 and 0 <= p.y <= 68 for p in e.teams[0].on_field))

    def test_save_restore_keeps_coordinates_ball_rng_and_future_events_exact(self):
        e = self.fixture()
        for _ in range(40):
            e.step()
        r = MatchEngine.from_json(e.export_json())
        self.assertEqual(e.export_state(), r.export_state())
        for _ in range(60):
            if e.state.ended:
                break
            self.assertEqual(e.step(), r.step())
            self.assertEqual(e.pitch_snapshot(), r.pitch_snapshot())
        self.assertEqual(e.export_state(), r.export_state())

    def test_legacy_state_gets_deterministic_coordinates_without_rng_draws(self):
        e = self.fixture()
        for _ in range(10):
            e.step()
        state = e.export_state()
        del state["v13_coordinates"]
        for team in state["teams"]:
            for p in team["on_field"]:
                p.pop("x")
                p.pop("y")
        a, b = MatchEngine.from_state_dict(state), MatchEngine.from_state_dict(state)
        self.assertEqual(a.rng.getstate(), e.rng.getstate())
        self.assertEqual(a.pitch_snapshot(), b.pitch_snapshot())
        self.assertEqual(a.step(), b.step())

    def test_halftime_switches_ends_and_final_whistle_does_not_switch_again(self):
        e = self.fixture()
        e.state.period_index = 1
        e._reset_kickoff_coordinates()
        self.assertEqual(e.pitch_snapshot()["attack_directions"], [-1, 1])
        self.assertGreater(e.teams[0].on_field[0].x, 90.)
        e.state.period_index = 2
        self.assertEqual(e.pitch_snapshot()["attack_directions"], [-1, 1])

    def test_substitution_preserves_departing_players_point_and_removes_him(self):
        e = self.fixture()
        outgoing = e.teams[0].on_field[-1]
        incoming = e.teams[0].bench[0]
        point = e.player_coordinates(0, outgoing.player.name)
        e.launch_ball(point["x"], point["y"], aerial=True,
                      receiver={"team": 0, "player": outgoing.player.name})
        e.substitute(0, outgoing.player.name, incoming.name)
        self.assertEqual(e.player_coordinates(0, incoming.name), point)
        with self.assertRaises(KeyError):
            e.player_coordinates(0, outgoing.player.name)
        self.assertEqual(len(e.pitch_snapshot()["players"]), 22)
        self.assertIsNone(e.pitch_snapshot()["ball_flight"]["receiver"])
        restored = MatchEngine.from_json(e.export_json())
        self.assertEqual(e.export_state(), restored.export_state())

    def test_dismissed_players_are_absent_from_tracking_and_local_reading(self):
        e = self.fixture()
        outgoing = e.teams[1].on_field.pop()
        outgoing.red = True
        self.assertEqual(len(e.pitch_snapshot()["players"]), 21)
        self.assertNotIn(outgoing.player.name,
                         [p["player"] for p in e.spatial_reading(1)["passes"]])

    def test_emergency_goalkeeper_does_not_leave_an_active_player_without_coordinates(self):
        e = self.fixture()
        e.teams[0].on_field[0].player.position = "CB"
        anchors = e._formation_anchors(0)
        self.assertEqual(len(anchors), 11)
        self.assertEqual(anchors[e._goalkeeper(0).player.name], (5.5, 34.))
        e._move_players(.1)
        self.assertEqual(len(e.pitch_snapshot()["players"]), 22)

    def test_live_packet_contains_all_players_in_same_coordinate_frame(self):
        e = self.fixture()
        session = MatchSessionV13(e)
        packet = session.press_p_packet()
        self.assertEqual(packet["pitch"], e.pitch_snapshot())
        self.assertEqual(len(packet["pitch"]["players"]), 22)

    def test_ball_has_physical_height_and_tracking_rejects_invalid_z_atomically(self):
        e = self.fixture()
        self.assertEqual(e.pitch_snapshot()["ball"]["z"], 0.)
        for z in (-1., float("nan"), float("inf"), True):
            before = e.export_state()
            with self.assertRaises(ValueError):
                e.set_tracking_frame([], require_all=False, ball={"x": 50., "y": 34., "z": z})
            self.assertEqual(e.export_state(), before)
        e.set_tracking_frame([], require_all=False, ball={"x": 50., "y": 34., "z": 2.})
        self.assertEqual(e.spatial_reading(0)["ball_height"], 2.)
        ctx = e._spatial_context(0, Zone(Band.MID, Lane.CENTER))
        self.assertEqual(ctx["ball_height_metres"], 2.)
        self.assertTrue(ctx["aerial_ball"])

    def test_aerial_ball_obeys_gravity_and_lands_at_declared_endpoint(self):
        e = self.fixture()
        e.set_tracking_frame([], require_all=False, ball={"x": 20., "y": 34., "z": 0.})
        flight = e.launch_ball(60., 34., speed=20., aerial=True, kind="cross")
        before = e.export_state()
        middle = e.ball_position_at(e.state.second + 1.)
        self.assertAlmostEqual(middle["x"], 40.)
        self.assertAlmostEqual(middle["z"], 4.905)
        self.assertEqual(e.export_state(), before)
        e._advance_clock(flight["duration"] / 2, e.state.possession)
        self.assertAlmostEqual(e.pitch_snapshot()["ball"]["z"], 4.905)
        e._advance_clock(flight["duration"] / 2, e.state.possession)
        self.assertEqual(e.ball_position_at(), {"x": 60., "y": 34., "z": 0.})
        self.assertIsNone(e.pitch_snapshot()["ball_flight"])

    def test_ground_pass_stays_on_ground_and_airborne_save_restores_exactly(self):
        e = self.fixture()
        e.launch_ball(70., 34., speed=15.)
        self.assertEqual(e.ball_position_at(e.state.second + .5)["z"], 0.)
        e.launch_ball(80., 50., z=1.6, speed=18., aerial=True)
        e._advance_clock(.2, e.state.possession)
        restored = MatchEngine.from_json(e.export_json())
        for _ in range(4):
            e._advance_clock(.3, e.state.possession)
            restored._advance_clock(.3, restored.state.possession)
            self.assertEqual(e.export_state(), restored.export_state())

    def test_ball_can_cross_touchline_while_player_coordinates_stay_bounded(self):
        e = self.fixture()
        e.set_tracking_frame([], require_all=False, ball={"x": 106., "y": -1., "z": .4})
        restored = MatchEngine.from_json(e.export_json())
        self.assertEqual(e.pitch_snapshot(), restored.pitch_snapshot())
        with self.assertRaises(ValueError):
            e.set_player_coordinates(0, e.teams[0].on_field[0].player.name, 106., 34.)

    def test_saved_invalid_flight_is_rejected(self):
        e = self.fixture()
        e.launch_ball(80., 34., aerial=True)
        state = e.export_state()
        state["v13_coordinates"]["flight"]["duration"] = -1.
        with self.assertRaises(ValueError):
            MatchEngine.from_state_dict(state)

    def test_unowned_airborne_tracking_point_falls_instead_of_hovering(self):
        e = self.fixture()
        e.set_tracking_frame([], require_all=False, ball={"x": 50., "y": 34., "z": 2.})
        e._advance_clock(.2, e.state.possession)
        self.assertAlmostEqual(e.pitch_snapshot()["ball"]["z"], 2. - .5 * 9.81 * .2 ** 2)
        e._advance_clock(1., e.state.possession)
        self.assertEqual(e.pitch_snapshot()["ball"]["z"], 0.)

    def test_pending_cross_launches_an_aerial_trajectory(self):
        e = self.fixture()
        actor, target = e.teams[0].on_field[-2:]
        e.state.pending = PendingAction(0, target.player.name, "shoot",
                                       Zone(Band.BOX, Lane.CENTER), danger=.6, pressure=.3, body_part="head", origin="cross")
        e._emit(EventType.DANGER, 0, 3, "cross_delivered",
                actor=actor.player.name, target=target.player.name, kind="cross")
        flight = e.pitch_snapshot()["ball_flight"]
        self.assertIsNotNone(flight)
        self.assertTrue(flight["aerial"])
        self.assertEqual(flight["target"]["z"], 1.6)

    def test_shot_goal_plane_height_maps_to_world_xyz_for_both_teams(self):
        from unittest.mock import patch
        from engine_experiment_v13_rules_hardening import MatchEngineV13RulesHardening
        for team in (0, 1):
            e = self.fixture()
            actor = e.teams[team].on_field[-1]
            pending = PendingAction(team, actor.player.name, "shoot", Zone(Band.BOX, Lane.CENTER), danger=.6, pressure=.3)
            event = Event(1., team, EventType.MISS, 3, "shot_missed",
                          {"actual_goal_position": {"x": -2., "z": 1.8}})
            with patch.object(MatchEngineV13RulesHardening, "_resolve_shot", return_value=event):
                result = e._resolve_shot(pending)
            self.assertEqual(result.data["shot_ball_coordinates"],
                             {"x": 105. if team == 0 else 0.,
                              "y": 32. if team == 0 else 36., "z": 1.8})

    def test_ball_height_changes_receiving_weights_through_heading(self):
        e = self.fixture()
        actor = e.teams[0].on_field[-1]
        high, low = e.teams[0].on_field[-3:-1]
        high.player.heading, low.player.heading = 98, 40
        zone = Zone(Band.ATT, Lane.CENTER)
        ground = {ps.player.name: w for ps, w in e._base_target_weights(0, zone, actor)}
        e.set_tracking_frame([], require_all=False, ball={"x": 50., "y": 34., "z": 2.})
        aerial = {ps.player.name: w for ps, w in e._base_target_weights(0, zone, actor)}
        self.assertGreater(aerial[high.player.name] / ground[high.player.name],
                           aerial[low.player.name] / ground[low.player.name])
