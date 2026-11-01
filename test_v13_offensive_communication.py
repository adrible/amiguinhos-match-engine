import copy

from engine import Band, Lane, MatchConfig, Zone, make_generic_team
from engine_experiment_v13_offensive_communication import MatchEngineV13OffensiveCommunication


def _engine(seed=1929):
    return MatchEngineV13OffensiveCommunication(
        make_generic_team("Home", 78, seed=81),
        make_generic_team("Away", 78, seed=82),
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=False),
    )


def _player(engine, team, position):
    return next(ps for ps in engine.teams[team].on_field if ps.player.position == position)


def test_offensive_communication_is_rng_pure_and_does_not_mutate_attributes():
    engine = _engine()
    actor = _player(engine, 0, "CM")
    receiver = _player(engine, 0, "ST")
    before_rng = copy.deepcopy(engine.rng.getstate())
    before_actor = copy.deepcopy(actor.player.__dict__)
    before_receiver = copy.deepcopy(receiver.player.__dict__)
    diag = engine.offensive_communication_diagnostic(
        0, actor, receiver, Zone(Band.ATT, Lane.CENTER), action="through_ball", ctx={"pressure": 0.35, "space_behind": 0.65}
    )
    assert engine.rng.getstate() == before_rng
    assert actor.player.__dict__ == before_actor
    assert receiver.player.__dict__ == before_receiver
    assert 0.0 <= diag["quality"] <= 1.0


def test_through_ball_into_space_uses_run_call():
    engine = _engine()
    actor = _player(engine, 0, "AM")
    receiver = _player(engine, 0, "ST")
    diag = engine.offensive_communication_diagnostic(
        0, actor, receiver, Zone(Band.ATT, Lane.CENTER), action="through_ball", ctx={"pressure": 0.30, "space_behind": 0.75}
    )
    assert diag["signal"] == "run_call"


def test_switch_uses_switch_call():
    engine = _engine()
    actor = _player(engine, 0, "CM")
    receiver = _player(engine, 0, "RW")
    diag = engine.offensive_communication_diagnostic(
        0, actor, receiver, Zone(Band.MID, Lane.LEFT), action="switch", ctx={"pressure": 0.40, "space_behind": 0.30}
    )
    assert diag["signal"] == "switch_call"


def test_pair_familiarity_can_make_receiver_option_clearer_without_execution_bonus():
    engine = _engine()
    actor = _player(engine, 0, "CM")
    receiver = _player(engine, 0, "ST")
    zone = Zone(Band.ATT, Lane.CENTER)
    ctx = {"pressure": 0.38, "space_behind": 0.52}
    if hasattr(engine, "set_pair_familiarity"):
        engine.set_pair_familiarity(0, actor.player.name, receiver.player.name, 0.15)
    low = engine.offensive_communication_diagnostic(0, actor, receiver, zone, action="progressive_pass", ctx=ctx)
    if hasattr(engine, "set_pair_familiarity"):
        engine.set_pair_familiarity(0, actor.player.name, receiver.player.name, 0.90)
    high = engine.offensive_communication_diagnostic(0, actor, receiver, zone, action="progressive_pass", ctx=ctx)
    assert high["quality"] >= low["quality"]
    assert "passing_bonus" not in high
    assert "finishing_bonus" not in high


def test_target_weight_effect_is_modest():
    engine = _engine()
    actor = _player(engine, 0, "CM")
    zone = Zone(Band.MID, Lane.CENTER)
    base = list(super(MatchEngineV13OffensiveCommunication, engine)._base_target_weights(0, zone, actor, {"pressure": 0.35, "space_behind": 0.45}))
    adjusted = list(engine._base_target_weights(0, zone, actor, {"pressure": 0.35, "space_behind": 0.45}))
    b = {ps.player.name: weight for ps, weight in base}
    a = {ps.player.name: weight for ps, weight in adjusted}
    for name in set(b) & set(a):
        ratio = a[name] / b[name] if b[name] else 1.0
        assert 0.95 <= ratio <= 1.07
