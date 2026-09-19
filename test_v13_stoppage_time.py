import copy

from engine import Band, Event, EventType, Lane, MatchConfig, PendingAction, Zone, make_generic_team
from engine_experiment_v13_stoppage import MatchEngineV13Stoppage


def _engine(seed=101):
    return MatchEngineV13Stoppage(
        make_generic_team("Home", 78, seed=1),
        make_generic_team("Away", 78, seed=2),
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=False),
    )


def test_stoppage_diagnostic_is_rng_pure():
    engine = _engine()
    before = copy.deepcopy(engine.rng.getstate())
    diagnostic = engine.stoppage_time_diagnostic()
    after = engine.rng.getstate()
    assert diagnostic["current_period"]["marker"] == 45
    assert before == after


def test_dead_time_advances_match_clock_but_not_possession():
    engine = _engine()
    before_clock = engine.state.second
    before_possession = [row.possession_seconds for row in engine.stats]
    before_minutes = engine.teams[0].on_field[0].minutes
    engine._advance_dead_clock(42.0, 28.0, reason="goal_celebration")
    assert engine.state.second == before_clock + 42.0
    assert [row.possession_seconds for row in engine.stats] == before_possession
    assert engine.teams[0].on_field[0].minutes > before_minutes
    diag = engine.stoppage_time_diagnostic()["current_period"]
    assert diag["dead_elapsed_seconds"] == 42.0
    assert diag["recoverable_seconds"] == 28.0


def test_advantage_played_has_no_dead_ball_time():
    engine = _engine()
    event = Event(
        engine.minute,
        0,
        EventType.FOUL,
        1,
        "advantage_played",
        {"advantage": True, "foul_type": "trip"},
    )
    before_clock = engine.state.second
    before_diag = copy.deepcopy(engine.stoppage_time_diagnostic())
    engine._apply_clock_for_event(event, had_pending=False)
    after_diag = engine.stoppage_time_diagnostic()
    assert engine.state.second == before_clock
    assert after_diag["dead_elapsed_by_marker"] == before_diag["dead_elapsed_by_marker"]
    assert after_diag["recoverable_by_marker"] == before_diag["recoverable_by_marker"]
    assert event.data["clock_accounted"] is True
    assert "dead_elapsed_seconds" not in event.data


def _sub_names(engine):
    out_name = next(ps.player.name for ps in engine.teams[0].on_field if ps.player.position != "GK")
    in_name = next(p.name for p in engine.teams[0].bench if p.position != "GK")
    return out_name, in_name


def test_first_half_substitution_uses_conservative_recovery():
    engine = _engine()
    out_name, in_name = _sub_names(engine)
    before = engine.state.second
    event = engine.substitute(0, out_name, in_name)
    assert event.type == EventType.SUBSTITUTION
    assert event.data["dead_elapsed_seconds"] == 30.0
    assert event.data["recoverable_seconds"] == 22.0
    assert engine.state.second == before + 30.0


def test_second_half_substitution_uses_modern_recovery():
    engine = _engine()
    engine.state.period_index = 1
    engine.state.second = 60.0 * 60.0
    out_name, in_name = _sub_names(engine)
    event = engine.substitute(0, out_name, in_name)
    assert event.data["dead_elapsed_seconds"] == 30.0
    assert event.data["recoverable_seconds"] == 27.0


def test_extra_time_recovery_returns_to_conservative_profile():
    engine = _engine()
    engine.state.period_markers = [105, 120]
    engine.state.period_index = 0
    engine.state.second = 96.0 * 60.0
    event = Event(engine.minute, 0, EventType.CARD, 2, "card_shown_contextual", {})
    elapsed, recoverable, _ = engine._dead_time_profile(event)
    assert elapsed == 20.0
    assert recoverable == 12.0


def test_recovery_profiles_never_recover_more_than_elapsed():
    engine = _engine()
    events = [
        Event(engine.minute, 0, EventType.FOUL, 1, "foul_incident", {"card": None}),
        Event(engine.minute, 0, EventType.CARD, 2, "card_shown_contextual", {}),
        Event(engine.minute, 0, EventType.CORNER, 3, "corner_awarded", {}),
        Event(engine.minute, 0, EventType.GOAL, 5, "goal", {}),
    ]
    for period_index in (0, 1):
        engine.state.period_index = period_index
        for event in events:
            elapsed, recoverable, _ = engine._dead_time_profile(event)
            assert 0.0 <= recoverable <= elapsed


def test_added_time_is_announced_from_actual_recoverable_loss():
    engine = _engine()
    engine.state.second = 44.0 * 60.0
    engine._advance_dead_clock(60.0, 60.0, reason="test_delay")
    announcement = engine._check_period_boundary()
    assert announcement is not None
    assert announcement.type == EventType.INFO
    assert announcement.text_key == "stoppage_time_announced"
    assert announcement.data["added_minutes"] == 1
    assert engine.state.period_index == 0

    engine.state.second = 45.75 * 60.0
    assert engine._check_period_boundary() is None
    engine.state.second = 46.0 * 60.0
    end = engine._check_period_boundary()
    assert end is not None
    assert end.type == EventType.PERIOD_END
    assert engine.state.period_index == 1


def test_new_delay_during_added_time_extends_announced_minimum():
    engine = _engine()
    engine.state.second = 44.0 * 60.0
    engine._advance_dead_clock(60.0, 60.0, reason="initial_delay")
    announcement = engine._check_period_boundary()
    assert announcement.data["added_minutes"] == 1

    engine._advance_dead_clock(30.0, 20.0, reason="late_injury")
    engine.state.second = 46.10 * 60.0
    assert engine._check_period_boundary() is None
    engine.state.second = 46.34 * 60.0
    end = engine._check_period_boundary()
    assert end is not None
    assert end.type == EventType.PERIOD_END


def test_pending_live_action_consumes_small_real_time():
    engine = _engine()
    striker = next(ps for ps in engine.teams[0].on_field if ps.player.position == "ST")
    engine.state.possession = 0
    engine.state.zone = Zone(Band.BOX, Lane.CENTER)
    engine.state.pending = PendingAction(
        team=0,
        actor=striker.player.name,
        kind="shoot",
        zone=Zone(Band.BOX, Lane.CENTER),
        danger=0.58,
        pressure=0.35,
        origin="through_ball",
    )
    before = engine.stats[0].possession_seconds
    event = engine.step()
    assert event.data.get("live_action_seconds", 0.0) > 0.0
    assert engine.stats[0].possession_seconds > before


def test_stoppage_state_survives_save_load():
    engine = _engine()
    engine.state.second = 40.0 * 60.0
    engine._advance_dead_clock(82.0, 68.0, reason="injury:moderate")
    payload = engine.export_json()
    restored = MatchEngineV13Stoppage.from_json(payload)
    assert restored.stoppage_time_diagnostic() == engine.stoppage_time_diagnostic()
    assert restored.state.second == engine.state.second


def test_same_seed_remains_deterministic_with_stoppage_layer():
    a = _engine(seed=909)
    b = _engine(seed=909)
    for _ in range(80):
        ea = a.step()
        eb = b.step()
        assert (ea.type, ea.text_key, ea.team, ea.minute, ea.data) == (
            eb.type, eb.text_key, eb.team, eb.minute, eb.data
        )
        if a.state.ended or b.state.ended:
            break
    assert a.snapshot() == b.snapshot()



def test_second_half_boundary_is_anchored_to_public_90_after_first_half_added_time():
    engine = _engine()
    engine.state.second = 48.0 * 60.0
    engine._emit(EventType.PERIOD_END, engine.state.possession, 5, "period_end", marker=45)
    engine.state.period_index = 1

    state = engine._ensure_stoppage_state()
    state["recoverable_by_marker"]["90"] = 244.0

    engine.state.second = 90.0 * 60.0
    assert engine._check_period_boundary() is None

    engine.state.second = 93.0 * 60.0
    announcement = engine._check_period_boundary()
    assert announcement is not None
    assert announcement.type == EventType.INFO
    assert announcement.text_key == "stoppage_time_announced"
    assert announcement.data["marker"] == 90
    assert announcement.data["added_minutes"] == 5


def load_tests(loader, tests, pattern):
    """Expose all new plain-function realism tests to the unittest-only CI."""
    from test_v13_new_stack_unittest import NewRealismStackFunctionTests

    return loader.loadTestsFromTestCase(NewRealismStackFunctionTests)
