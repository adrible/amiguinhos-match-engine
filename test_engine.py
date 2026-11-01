import unittest
from statistics import mean

from engine import (
    MatchEngine, MatchConfig, EventType,
    make_generic_team, simulate_full_match,
)


def make_pair(home_strength=75, away_strength=75,
              home_style="balanced", away_style="balanced",
              seed=1):
    home = make_generic_team("Home", home_strength, home_style, seed=seed)
    away = make_generic_team("Away", away_strength, away_style, seed=seed + 1000)
    return home, away


class MatchEngineTests(unittest.TestCase):
    def test_same_seed_is_reproducible(self):
        h1, a1 = make_pair(seed=11)
        h2, a2 = make_pair(seed=11)
        e1 = simulate_full_match(h1, a1, seed=777)
        e2 = simulate_full_match(h2, a2, seed=777)

        self.assertEqual(e1.score, e2.score)
        self.assertEqual(
            [(ev.type, ev.minute, ev.text_key, ev.data) for ev in e1.state.event_log],
            [(ev.type, ev.minute, ev.text_key, ev.data) for ev in e2.state.event_log],
        )

    def test_statistics_are_coherent(self):
        home, away = make_pair(seed=22)
        e = simulate_full_match(home, away, seed=888)
        for s in e.stats:
            self.assertGreaterEqual(s.shots, s.on_target)
            self.assertGreaterEqual(s.on_target, s.goals)
            self.assertGreaterEqual(s.xg, 0.0)
            self.assertGreaterEqual(s.fouls, s.red)
            self.assertGreaterEqual(s.yellow + s.red, 0)

    def test_advance_stops_on_danger_and_then_resolves_one_beat(self):
        home, away = make_pair(seed=33)
        e = MatchEngine(home, away, seed=999)

        ev = e.advance_until_relevant()
        self.assertGreaterEqual(ev.relevance, 2)
        if e.state.pending or e.state.restart:
            before = len(e.state.event_log)
            e.advance_until_relevant()
            self.assertEqual(len(e.state.event_log), before + 1)

    def test_tactical_change_does_not_reset_match(self):
        home, away = make_pair(seed=44)
        e = MatchEngine(home, away, seed=123)
        e.advance_until_relevant()
        minute = e.minute
        score = e.score
        e.set_tactics(0, pressing=0.82, defensive_line=0.67)
        self.assertEqual(e.score, score)
        self.assertEqual(e.minute, minute)
        self.assertAlmostEqual(e.teams[0].team.tactics.pressing, 0.82)

    def test_stronger_team_has_aggregate_advantage_not_guaranteed_win(self):
        goal_diff = []
        lost_or_drew = 0
        for i in range(120):
            home, away = make_pair(82, 72, seed=100 + i)
            e = simulate_full_match(home, away, seed=2000 + i)
            goal_diff.append(e.score[0] - e.score[1])
            if e.score[0] <= e.score[1]:
                lost_or_drew += 1

        self.assertGreater(mean(goal_diff), 0.25)
        self.assertGreater(lost_or_drew, 0)

    def test_no_fixed_shot_or_goal_quota(self):
        shots = set()
        goals = set()
        for i in range(80):
            home, away = make_pair(seed=400 + i)
            e = simulate_full_match(home, away, seed=5000 + i)
            shots.add(sum(s.shots for s in e.stats))
            goals.add(sum(e.score))
        self.assertGreater(len(shots), 8)
        self.assertGreater(len(goals), 4)


    def test_contextual_attacking_target_selection_prefers_quality_without_quota(self):
        from engine import Band, Lane, Zone

        home, away = make_pair(seed=451)
        e = MatchEngine(home, away, seed=5451)
        high = next(ps for ps in e.teams[0].on_field if ps.player.position == "ST")
        low = next(ps for ps in e.teams[0].on_field if ps.player.position == "AM")
        low.player.position = "ST"

        for attr in ("off_ball", "anticipation", "finishing", "composure", "technique"):
            setattr(high.player, attr, 96)
            setattr(low.player, attr, 44)

        counts = {high.player.name: 0, low.player.name: 0}
        zone = Zone(Band.ATT, Lane.CENTER)
        for _ in range(2400):
            target = e._choose_target(
                0, zone, attacking=True, exclude=None, action="through_ball"
            )
            if target.player.name in counts:
                counts[target.player.name] += 1

        self.assertGreater(counts[high.player.name], counts[low.player.name])
        self.assertGreater(counts[low.player.name], 0)

    def test_contextual_target_quality_changes_with_action(self):
        home, away = make_pair(seed=452)
        e = MatchEngine(home, away, seed=5452)
        aerial = next(ps for ps in e.teams[0].on_field if ps.player.position == "ST")
        runner = next(ps for ps in e.teams[0].on_field if ps.player.position == "AM")

        for ps in (aerial, runner):
            ps.player.position = "ST"
            for attr in ("off_ball", "anticipation", "finishing", "composure", "technique", "heading", "strength"):
                setattr(ps.player, attr, 70)

        aerial.player.heading = 98
        aerial.player.strength = 94
        aerial.player.finishing = 55
        runner.player.heading = 48
        runner.player.strength = 60
        runner.player.finishing = 97
        runner.player.off_ball = 96
        runner.player.composure = 94

        self.assertGreater(
            e._attacking_target_quality(aerial, "cross"),
            e._attacking_target_quality(runner, "cross"),
        )
        self.assertGreater(
            e._attacking_target_quality(runner, "through_ball"),
            e._attacking_target_quality(aerial, "through_ball"),
        )


class StabilityRegressionTests(unittest.TestCase):
    def test_snapshot_is_json_safe_and_full_state_restores_exactly(self):
        import json
        home, away = make_pair(seed=55)
        e1 = MatchEngine(home, away, seed=4321)
        for _ in range(20):
            e1.step()
        json.dumps(e1.snapshot())
        payload = e1.export_json()
        e2 = MatchEngine.from_json(payload)
        seq1, seq2 = [], []
        for _ in range(30):
            a = e1.step()
            b = e2.step()
            seq1.append((a.type, a.minute, a.text_key, a.data))
            seq2.append((b.type, b.minute, b.text_key, b.data))
        self.assertEqual(seq1, seq2)
        self.assertEqual(e1.score, e2.score)

    def test_formation_changes_spatial_context(self):
        h1, a1 = make_pair(seed=66)
        h2, a2 = make_pair(seed=66)
        e1 = MatchEngine(h1, a1, seed=99)
        e2 = MatchEngine(h2, a2, seed=99)
        e1.set_tactics(0, formation="3-4-3")
        e1.set_tactics(1, formation="5-4-1")
        e2.set_tactics(0, formation="4-2-3-1")
        e2.set_tactics(1, formation="4-2-3-1")
        e1.rng.setstate(e2.rng.getstate())
        c1 = e1._spatial_context(0, e1.state.zone)
        e2.rng.setstate(e1.rng.getstate())
        h3, a3 = make_pair(seed=66)
        h4, a4 = make_pair(seed=66)
        x = MatchEngine(h3, a3, seed=123)
        y = MatchEngine(h4, a4, seed=123)
        x.set_tactics(1, formation="5-4-1")
        y.set_tactics(1, formation="3-4-3")
        sx = x.rng.getstate(); sy = y.rng.getstate()
        self.assertEqual(sx, sy)
        from engine import Zone, Band, Lane
        cx = x._spatial_context(0, Zone(Band.ATT, Lane.CENTER))
        y.rng.setstate(sy)
        cy = y._spatial_context(0, Zone(Band.ATT, Lane.CENTER))
        self.assertNotEqual(round(cx["pressure"], 6), round(cy["pressure"], 6))

    def test_numerical_disadvantage_reduces_defensive_pressure(self):
        from engine import Zone, Band, Lane
        home, away = make_pair(seed=77)
        e = MatchEngine(home, away, seed=101)
        zone = Zone(Band.ATT, Lane.CENTER)
        state = e.rng.getstate()
        full = e._spatial_context(0, zone)
        cb = next(ps for ps in e.teams[1].on_field if ps.player.position == "CB")
        e.teams[1].on_field.remove(cb)
        e.rng.setstate(state)
        short = e._spatial_context(0, zone)
        self.assertLess(short["pressure"], full["pressure"])
        self.assertGreater(short["space"], full["space"])

    def test_substitution_is_blocked_during_live_pending_action(self):
        home, away = make_pair(seed=88)
        e = MatchEngine(home, away, seed=202)
        for _ in range(500):
            e.step()
            if e.state.pending:
                break
        self.assertIsNotNone(e.state.pending)
        out_name = e.teams[0].on_field[1].player.name
        in_name = e.teams[0].bench[1].name
        with self.assertRaises(ValueError):
            e.substitute(0, out_name, in_name)

    def test_transition_boost_decays_with_time(self):
        home, away = make_pair(seed=99)
        e = MatchEngine(home, away, seed=303)
        e.state.transition_boost = 0.9
        e._advance_clock(120.0, 0)
        self.assertLess(e.state.transition_boost, 0.08)

    def test_fatigue_is_meaningful_by_full_time(self):
        home, away = make_pair(seed=111)
        e = simulate_full_match(home, away, seed=404)
        energies = [ps.energy for rt in e.teams for ps in rt.on_field]
        self.assertLess(sum(energies) / len(energies), 0.86)
        self.assertLess(min(energies), 0.80)

    def test_zone_mirror_flips_lane(self):
        from engine import Zone, Band, Lane
        self.assertEqual(Zone(Band.ATT, Lane.LEFT).mirror(), Zone(Band.DEF, Lane.RIGHT))
        self.assertEqual(Zone(Band.MID, Lane.RIGHT).mirror(), Zone(Band.MID, Lane.LEFT))

    def test_second_half_kickoff_is_opposite_initial_kickoff(self):
        home, away = make_pair(seed=122)
        e = MatchEngine(home, away, seed=505)
        first = e.state.kickoff_team
        guard = 0
        while guard < 2000:
            ev = e.step()
            guard += 1
            if ev.type == EventType.PERIOD_END and ev.data.get("marker") == 45:
                break
        self.assertLess(guard, 2000)
        self.assertEqual(e.state.possession, 1 - first)

    def test_phase_tracks_match_location(self):
        from engine import Zone, Band, Lane
        home, away = make_pair(seed=133)
        e = MatchEngine(home, away, seed=606)
        e.state.zone = Zone(Band.DEF, Lane.CENTER)
        e._update_phase(e.state.zone)
        self.assertEqual(e.state.phase, "build_up")
        e.state.zone = Zone(Band.ATT, Lane.CENTER)
        e._update_phase(e.state.zone)
        self.assertEqual(e.state.phase, "final_third")
        e.state.transition_boost = 0.5
        e._update_phase(e.state.zone)
        self.assertEqual(e.state.phase, "transition")


if __name__ == "__main__":
    unittest.main()
