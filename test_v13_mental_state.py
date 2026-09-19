import copy

from engine import Band, Event, EventType, MatchConfig, Zone, make_generic_team
from engine_experiment_v13_mental_state import MatchEngineV13MentalState


def _engine(seed=515):
    return MatchEngineV13MentalState(
        make_generic_team("Home", 78, seed=21),
        make_generic_team("Away", 78, seed=22),
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=False),
    )


def _name(engine, team, position):
    return next(ps.player.name for ps in engine.teams[team].on_field if ps.player.position == position)


def test_mental_diagnostic_is_rng_pure_and_neutral_initially():
    engine = _engine()
    before = copy.deepcopy(engine.rng.getstate())
    rows = engine.mental_state_diagnostic(0)
    assert engine.rng.getstate() == before
    assert rows
    assert all(abs(row["confidence"]) < 1e-12 for row in rows.values())
    assert all(abs(row["pressure"]) < 1e-12 for row in rows.values())


def test_goal_increases_scorer_confidence_without_mutating_attributes():
    engine = _engine()
    scorer = _name(engine, 0, "ST")
    player = engine.teams[0].by_name(scorer).player
    before_attrs = copy.deepcopy(player.__dict__)
    event = Event(20.0, 0, EventType.GOAL, 5, "goal", {"scorer": scorer})
    engine._update_mental_from_event(event)
    row = engine.mental_state_diagnostic(0)[scorer]
    assert row["confidence"] > 0.10
    assert player.__dict__ == before_attrs


def test_big_chance_miss_reduces_confidence_and_adds_pressure():
    engine = _engine()
    shooter = _name(engine, 0, "ST")
    event = Event(
        35.0,
        0,
        EventType.MISS,
        4,
        "shot_missed",
        {"shooter": shooter, "big_chance": True},
    )
    engine._update_mental_from_event(event)
    row = engine.mental_state_diagnostic(0)[shooter]
    assert row["confidence"] < -0.05
    assert row["pressure"] > 0.0


def test_keeper_save_builds_keeper_confidence_and_affects_shooter_only_modestly():
    engine = _engine()
    shooter = _name(engine, 0, "ST")
    keeper = _name(engine, 1, "GK")
    event = Event(
        50.0,
        0,
        EventType.SAVE,
        4,
        "shot_saved",
        {"shooter": shooter, "keeper": keeper, "big_chance": True},
    )
    engine._update_mental_from_event(event)
    assert engine.mental_state_diagnostic(1)[keeper]["confidence"] > 0.04
    assert engine.mental_state_diagnostic(0)[shooter]["confidence"] < 0.0


def test_mental_state_decays_toward_neutral():
    engine = _engine()
    striker = _name(engine, 0, "ST")
    engine._mental_adjust(0, striker, confidence=0.30, pressure=0.60)
    before = engine.mental_state_diagnostic(0)[striker]
    engine._decay_mental_state(20.0 * 60.0)
    after = engine.mental_state_diagnostic(0)[striker]
    assert 0.0 < after["confidence"] < before["confidence"]
    assert 0.0 < after["pressure"] < before["pressure"]


def test_confidence_changes_decision_weights_not_execution_attributes():
    engine = _engine()
    striker_state = engine.teams[0].by_name(_name(engine, 0, "ST"))
    zone = Zone(Band.ATT, engine.state.zone.lane)
    tactics = engine.teams[0].team.tactics
    ctx = {"pressure": 0.35, "space": 0.50, "space_behind": 0.45, "support": 0.50, "wide_space": 0.0}

    before_attrs = copy.deepcopy(striker_state.player.__dict__)
    neutral = dict(engine._decision_weights(striker_state, zone, tactics, ctx))
    engine._mental_adjust(0, striker_state.player.name, confidence=0.40)
    confident = dict(engine._decision_weights(striker_state, zone, tactics, ctx))
    assert confident.get("shoot", 0.0) >= neutral.get("shoot", 0.0)
    assert striker_state.player.__dict__ == before_attrs


def test_mental_state_survives_save_load():
    engine = _engine(seed=616)
    striker = _name(engine, 0, "ST")
    engine._mental_adjust(0, striker, confidence=0.21, pressure=0.17)
    restored = MatchEngineV13MentalState.from_json(engine.export_json())
    assert restored.mental_state_diagnostic() == engine.mental_state_diagnostic()


def test_same_seed_remains_deterministic_with_mental_state():
    a = _engine(seed=717)
    b = _engine(seed=717)
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
