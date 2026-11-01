import copy

from engine import Band, Lane, MatchConfig, Zone, make_generic_team
from engine_experiment_v13_numerical_advantage import MatchEngineV13NumericalAdvantage


def _engine(seed=2030):
    return MatchEngineV13NumericalAdvantage(
        make_generic_team("Home", 78, seed=91),
        make_generic_team("Away", 78, seed=92),
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=False),
    )


def _dismiss_non_gk(engine, team, position="CM"):
    ps = next(ps for ps in engine.teams[team].on_field if ps.player.position == position)
    ps.red = True
    engine.teams[team].on_field.remove(ps)
    engine.stats[team].red += 1
    return ps


def test_equal_numbers_have_no_numerical_exploitation():
    engine = _engine()
    diag = engine.numerical_exploitation_diagnostic(0)
    assert diag["advantage"] == 0
    assert diag["attacking_players"] == diag["defending_players"]


def test_11v10_identifies_weakened_line():
    engine = _engine()
    _dismiss_non_gk(engine, 1, "CM")
    diag = engine.numerical_exploitation_diagnostic(0)
    assert diag["advantage"] == 1
    assert diag["weak_line"] == "mid"
    assert diag["line_ratios"]["mid"] < 1.0


def test_compact_ten_man_block_concedes_more_wide_space_not_free_central_space():
    engine = _engine()
    _dismiss_non_gk(engine, 1, "CM")
    engine.teams[1].team.tactics.compactness = 0.85
    wide_zone = Zone(Band.ATT, Lane.RIGHT)
    center_zone = Zone(Band.ATT, Lane.CENTER)
    wide_base = dict(super(MatchEngineV13NumericalAdvantage, engine)._spatial_context(0, wide_zone))
    wide = engine._spatial_context(0, wide_zone)
    center_base = dict(super(MatchEngineV13NumericalAdvantage, engine)._spatial_context(0, center_zone))
    center = engine._spatial_context(0, center_zone)
    assert wide["wide_space"] >= wide_base["wide_space"]
    assert wide["space"] >= wide_base["space"]
    assert center["space"] <= center_base["space"] + 0.02


def test_advantage_changes_choices_not_player_attributes():
    engine = _engine()
    _dismiss_non_gk(engine, 1, "CM")
    actor = next(ps for ps in engine.teams[0].on_field if ps.player.position == "CM")
    before = copy.deepcopy(actor.player.__dict__)
    zone = Zone(Band.MID, Lane.CENTER)
    tactics = engine.teams[0].team.tactics
    ctx = {"pressure": 0.35, "space": 0.52, "space_behind": 0.45, "support": 0.52, "wide_space": 0.22}
    _ = engine._decision_weights(actor, zone, tactics, ctx)
    assert actor.player.__dict__ == before


def test_numerical_diagnostic_is_rng_pure():
    engine = _engine()
    _dismiss_non_gk(engine, 1, "DM")
    before = copy.deepcopy(engine.rng.getstate())
    _ = engine.numerical_exploitation_diagnostic(0)
    assert engine.rng.getstate() == before
