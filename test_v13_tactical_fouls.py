import copy

from engine import Band, Event, EventType, Lane, MatchConfig, PendingAction, Zone, make_generic_team
from engine_experiment_v13_tactical_fouls import MatchEngineV13TacticalFouls


class _AlwaysZeroRng:
    def random(self):
        return 0.0


def _engine(seed=818):
    return MatchEngineV13TacticalFouls(
        make_generic_team("Home", 78, seed=31),
        make_generic_team("Away", 78, seed=32),
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=False),
    )


def test_booked_defender_manages_foul_risk_more_carefully():
    engine = _engine()
    defender = next(ps for ps in engine.teams[0].on_field if ps.player.position == "CB")
    attacker = next(ps for ps in engine.teams[1].on_field if ps.player.position == "ST")
    ctx = {"pressure": 0.65}
    defender.yellow = 0
    clean = engine._foul_probability(defender, attacker, ctx)
    defender.yellow = 1
    booked = engine._foul_probability(defender, attacker, ctx)
    assert booked < clean
    assert booked > 0.0


def test_dangerous_transition_can_be_consciously_stopped():
    engine = _engine()
    engine.state.second = 86.0 * 60.0
    engine.stats[0].goals = 1
    engine.stats[1].goals = 0
    engine.state.zone = Zone(Band.ATT, Lane.RIGHT)
    receiver = next(ps for ps in engine.teams[1].on_field if ps.player.position == "ST")
    engine.state.pending = PendingAction(
        team=1,
        actor=receiver.player.name,
        kind="shoot",
        zone=engine.state.zone,
        danger=0.72,
        pressure=0.28,
        origin="transition",
    )
    event = Event(
        engine.minute,
        1,
        EventType.DANGER,
        2,
        "dangerous_turnover",
        {"transition": 0.88, "receiver": receiver.player.name},
    )
    engine._v13_tactical_foul_rng = _AlwaysZeroRng()
    result = engine._convert_transition_to_tactical_foul(event, 0)
    assert result.type == EventType.FOUL
    assert result.text_key == "tactical_foul_stops_transition"
    assert engine.state.pending is None
    assert engine.state.restart == "free_kick"
    assert engine.state.restart_team == 1
    assert engine.stats[0].fouls == 1


def test_tactical_foul_is_not_created_for_weak_transition():
    engine = _engine()
    engine.state.zone = Zone(Band.MID, Lane.CENTER)
    receiver = next(ps for ps in engine.teams[1].on_field if ps.player.position == "ST")
    engine.state.pending = PendingAction(
        team=1,
        actor=receiver.player.name,
        kind="through_ball",
        zone=engine.state.zone,
        danger=0.35,
        pressure=0.40,
        origin="transition",
    )
    event = Event(engine.minute, 1, EventType.DANGER, 2, "dangerous_turnover", {"transition": 0.40})
    engine._v13_tactical_foul_rng = _AlwaysZeroRng()
    result = engine._convert_transition_to_tactical_foul(event, 0)
    assert result.type == EventType.DANGER
    assert engine.state.pending is not None
    assert engine.stats[0].fouls == 0


def test_same_infringement_is_less_likely_to_be_second_yellow_but_possible():
    engine = _engine()
    fouler = next(ps for ps in engine.teams[0].on_field if ps.player.position == "DM")
    fouler.yellow = 1
    engine._v13_tactical_foul_rng = _AlwaysZeroRng()
    card = engine._tactical_foul_card(
        0,
        fouler,
        transition=0.80,
        zone=Zone(Band.ATT, Lane.RIGHT),
    )
    assert card == "second_yellow_red"
    assert fouler.red
    assert card != "direct_red"


def test_tactical_foul_diagnostic_is_main_rng_pure_and_attributes_unchanged():
    engine = _engine()
    before_rng = copy.deepcopy(engine.rng.getstate())
    before_attrs = [copy.deepcopy(ps.player.__dict__) for ps in engine.teams[0].on_field]
    _ = engine.tactical_foul_diagnostic(0)
    assert engine.rng.getstate() == before_rng
    assert [ps.player.__dict__ for ps in engine.teams[0].on_field] == before_attrs


def test_tactical_foul_state_and_rng_survive_save_load():
    engine = _engine(seed=919)
    state = engine._ensure_tactical_fouls()
    state["attempts"][0] = 3
    state["committed"][0] = 1
    _ = engine._v13_tactical_foul_rng.random()
    restored = MatchEngineV13TacticalFouls.from_json(engine.export_json())
    assert restored.tactical_foul_diagnostic() == engine.tactical_foul_diagnostic()
    assert restored._v13_tactical_foul_rng.getstate() == engine._v13_tactical_foul_rng.getstate()


def test_same_seed_remains_deterministic_with_tactical_fouls():
    a = _engine(seed=1020)
    b = _engine(seed=1020)
    for _ in range(120):
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
