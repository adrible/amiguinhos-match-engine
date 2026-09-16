import copy

from engine import Band, Lane, MatchConfig, Zone, make_generic_team
from engine_experiment_v13_second_balls import MatchEngineV13SecondBalls


class _AlwaysZeroRng:
    def random(self):
        return 0.0


def _engine(seed=1525):
    return MatchEngineV13SecondBalls(
        make_generic_team("Home", 78, seed=61),
        make_generic_team("Away", 78, seed=62),
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=False),
    )


def test_second_ball_diagnostic_is_rng_pure():
    engine = _engine()
    before = copy.deepcopy(engine.rng.getstate())
    diag = engine.second_ball_diagnostic(0, Zone(Band.ATT, Lane.CENTER))
    assert engine.rng.getstate() == before
    assert 0.20 <= diag["attacker_win_probability"] <= 0.78
    assert diag["attacker"]
    assert diag["defender"]


def test_cross_clearance_can_stay_live_as_second_ball():
    engine = _engine()
    engine.rng = _AlwaysZeroRng()
    actor = next(ps for ps in engine.teams[0].on_field if ps.player.position == "RW")
    zone = Zone(Band.ATT, Lane.RIGHT)
    engine.state.possession = 0
    engine.state.zone = zone
    ctx = {"support": 0.65, "pressure": 0.35}
    event = engine._turnover(0, actor, zone, "cross_cleared", ctx, severity=0.4)
    assert event.type.value == "rebound"
    assert event.data.get("second_ball_live") is True
    assert event.data.get("source_reason") == "cross_cleared"


def test_second_ball_contest_never_mutates_player_attributes():
    engine = _engine()
    before = [copy.deepcopy(ps.player.__dict__) for rt in engine.teams for ps in rt.on_field]
    _ = engine.second_ball_diagnostic(0, Zone(Band.MID, Lane.CENTER))
    after = [ps.player.__dict__ for rt in engine.teams for ps in rt.on_field]
    assert after == before


def test_attack_recovery_and_defensive_control_are_both_structurally_possible():
    engine = _engine()
    actor = next(ps for ps in engine.teams[0].on_field if ps.player.position == "CM")
    zone = Zone(Band.MID, Lane.CENTER)
    diag = engine.second_ball_diagnostic(0, zone)
    assert 0.0 < diag["attacker_win_probability"] < 1.0
    assert engine._SECOND_BALL_REASONS["long_ball_failed"] > 0.0
    assert actor.player.name


def test_second_ball_layer_does_not_replace_shot_rebound_contract():
    engine = _engine()
    assert hasattr(engine, "rebound_contest_diagnostic")
    assert hasattr(engine, "_create_rebound")
    assert "cross_cleared" in engine._SECOND_BALL_REASONS
