import copy

from engine import Band, Event, EventType, Lane, MatchConfig, Zone, make_generic_team
from engine_experiment_v13_clock_behaviour import MatchEngineV13ClockBehaviour


class _AlwaysZeroRng:
    def random(self):
        return 0.0


def _engine(seed=303):
    return MatchEngineV13ClockBehaviour(
        make_generic_team("Home", 78, seed=11),
        make_generic_team("Away", 78, seed=12),
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=False),
    )


def test_clock_behaviour_diagnostic_is_main_rng_pure():
    engine = _engine()
    before = copy.deepcopy(engine.rng.getstate())
    _ = engine.clock_behaviour_diagnostic(0)
    assert engine.rng.getstate() == before


def test_no_time_waste_pressure_early_or_when_not_protecting_result():
    engine = _engine()
    engine.state.second = 60.0 * 60.0
    assert engine._restart_waste_probability(0, "goal_kick") == 0.0

    engine.state.second = 86.0 * 60.0
    engine.stats[0].goals = 0
    engine.stats[1].goals = 1
    assert engine._restart_waste_probability(0, "goal_kick") == 0.0
    assert engine.clock_behaviour_diagnostic(0)["restart_urgency"] > 0.0


def test_leading_team_can_delay_restart_but_restart_stays_pending():
    engine = _engine()
    engine.state.second = 88.0 * 60.0
    engine.stats[0].goals = 1
    engine.stats[1].goals = 0
    engine.state.restart = "goal_kick"
    engine.state.restart_team = 0
    engine.state.restart_zone = Zone(Band.DEF, Lane.CENTER)
    engine._v13_clock_rng = _AlwaysZeroRng()

    before = engine.state.second
    event = engine._maybe_time_waste_restart()
    assert event is not None
    assert event.text_key == "deliberate_time_wasting"
    assert engine.state.second > before
    assert engine.state.restart == "goal_kick"
    assert event.data["recoverable_seconds"] > 0.0


def test_same_restart_cannot_trigger_delay_twice_in_a_row():
    engine = _engine()
    engine.state.second = 88.0 * 60.0
    engine.stats[0].goals = 2
    engine.stats[1].goals = 1
    engine.state.restart = "goal_kick"
    engine.state.restart_team = 0
    engine.state.restart_zone = Zone(Band.DEF, Lane.CENTER)
    engine._v13_clock_rng = _AlwaysZeroRng()

    first = engine._maybe_time_waste_restart()
    assert first is not None
    second = engine._maybe_time_waste_restart()
    assert second is None


def test_keeper_holds_longer_when_protecting_than_when_chasing():
    protecting = _engine(seed=401)
    protecting.state.second = 86.0 * 60.0
    protecting.stats[0].goals = 1
    protecting.stats[1].goals = 0
    # Team 0 is the keeper team because team 1 took the shot.
    save = Event(86.0, 1, EventType.SAVE, 3, "shot_saved", {})
    p_elapsed, _, p_team = protecting._keeper_hold_profile(save)
    assert p_team == 0

    chasing = _engine(seed=401)
    chasing.state.second = 86.0 * 60.0
    chasing.stats[0].goals = 0
    chasing.stats[1].goals = 1
    c_elapsed, _, c_team = chasing._keeper_hold_profile(save)
    assert c_team == 0
    assert p_elapsed > c_elapsed


def test_time_wasting_second_caution_is_possible_but_not_direct_red():
    engine = _engine()
    engine.state.second = 89.0 * 60.0
    player = engine._goalkeeper(0)
    player.yellow = 1
    engine._v13_clock_rng = _AlwaysZeroRng()
    card = engine._time_wasting_card(0, player, 1.0)
    assert card == "second_yellow_red"
    assert player.red
    assert card != "direct_red"


def test_clock_behaviour_state_and_rng_survive_save_load():
    engine = _engine(seed=777)
    engine.state.second = 88.0 * 60.0
    engine.stats[0].goals = 1
    engine.stats[1].goals = 0
    engine.state.restart = "goal_kick"
    engine.state.restart_team = 0
    # Consume one dedicated decision without touching the main RNG contract.
    _ = engine._v13_clock_rng.random()
    engine._ensure_clock_behaviour()["waste_attempts"][0] = 2

    payload = engine.export_json()
    restored = MatchEngineV13ClockBehaviour.from_json(payload)
    assert restored._ensure_clock_behaviour() == engine._ensure_clock_behaviour()
    assert restored._v13_clock_rng.getstate() == engine._v13_clock_rng.getstate()


def test_same_seed_clock_behaviour_remains_deterministic():
    a = _engine(seed=999)
    b = _engine(seed=999)
    for _ in range(100):
        ea = a.step()
        eb = b.step()
        assert (ea.type, ea.text_key, ea.team, ea.minute, ea.data) == (
            eb.type,
            eb.text_key,
            eb.team,
            eb.minute,
            eb.data,
        )
        if a.state.ended or b.state.ended:
            break
    assert a.snapshot() == b.snapshot()
