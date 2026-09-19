import copy

from engine import Band, Lane, MatchConfig, Zone, make_generic_team
from engine_experiment_v13_micro_adjustments import MatchEngineV13MicroAdjustments


def _engine(seed=1323):
    return MatchEngineV13MicroAdjustments(
        make_generic_team("Home", 78, seed=51),
        make_generic_team("Away", 78, seed=52),
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=False),
    )


def _player(engine, team, position):
    return next(ps for ps in engine.teams[team].on_field if ps.player.position == position)


def _hot_winger(engine):
    winger = _player(engine, 0, "RW")
    engine.state.second = 32.0 * 60.0
    rows = engine._ensure_mismatch_state()
    for idx in range(4):
        rows.append({
            "team": 0,
            "player": winger.player.name,
            "pattern": "carry_dribble",
            "action": "dribble",
            "lane": "right",
            "band": "final_third",
            "success": 1.0,
            "defender": "Away CB3",
            "second": engine.state.second - (4 - idx) * 70.0,
        })
    return winger


def test_hot_player_can_trigger_feed_micro_adjustment():
    engine = _engine()
    winger = _hot_winger(engine)
    choice = engine._select_micro_adjustment(0)
    assert choice is not None
    assert choice["mode"] == "feed_hot_player"
    assert choice["player"] == winger.player.name


def test_late_lead_can_make_fullback_hold_without_formation_change():
    engine = _engine()
    formation = engine.teams[0].team.tactics.formation
    engine.state.second = 82.0 * 60.0
    engine.stats[0].goals = 2
    engine.stats[1].goals = 1
    choice = engine._select_micro_adjustment(0)
    assert choice is not None
    assert choice["mode"] == "hold_fullback"
    assert engine.teams[0].team.tactics.formation == formation


def test_late_chasing_team_can_add_runner():
    engine = _engine()
    engine.state.second = 82.0 * 60.0
    engine.stats[0].goals = 0
    engine.stats[1].goals = 1
    choice = engine._select_micro_adjustment(0)
    assert choice is not None
    assert choice["mode"] == "extra_runner"


def test_no_micro_adjustment_is_forced_early():
    engine = _engine()
    engine.state.second = 10.0 * 60.0
    assert engine._select_micro_adjustment(0) is None


def test_defensive_micro_adjustment_has_explicit_tradeoff():
    engine = _engine()
    engine.state.second = 50.0 * 60.0
    row = engine._ensure_micro_state()["0"]
    row.update({
        "mode": "screen_center",
        "player": _player(engine, 0, "DM").player.name,
        "started_second": engine.state.second,
        "expires_second": engine.state.second + 600.0,
        "last_change_second": engine.state.second,
        "evidence": {"pattern": "vertical_progression"},
    })
    # Team 0 is defending because team 1 attacks.
    base = dict(super(MatchEngineV13MicroAdjustments, engine)._spatial_context(1, Zone(Band.ATT, Lane.CENTER)))
    adjusted = engine._spatial_context(1, Zone(Band.ATT, Lane.CENTER))
    assert adjusted["pressure"] >= base["pressure"]
    assert adjusted["space"] <= base["space"]
    assert adjusted["wide_space"] >= base.get("wide_space", 0.0)


def test_micro_adjustment_expires_and_does_not_mutate_attributes():
    engine = _engine()
    player = _player(engine, 0, "RB")
    before_attrs = copy.deepcopy(player.player.__dict__)
    row = engine._ensure_micro_state()["0"]
    row.update({
        "mode": "hold_fullback",
        "player": player.player.name,
        "started_second": 20.0 * 60.0,
        "expires_second": 31.0 * 60.0,
        "last_change_second": 20.0 * 60.0,
        "evidence": {},
    })
    engine.state.second = 32.0 * 60.0
    assert engine._active_micro(0) is None
    assert player.player.__dict__ == before_attrs


def test_micro_adjustment_state_survives_save_load():
    engine = _engine(seed=1424)
    player = _player(engine, 0, "CM")
    engine.state.second = 70.0 * 60.0
    row = engine._ensure_micro_state()["0"]
    row.update({
        "mode": "extra_runner",
        "player": player.player.name,
        "started_second": engine.state.second,
        "expires_second": engine.state.second + 500.0,
        "last_change_second": engine.state.second,
        "evidence": {"score_diff": -1},
    })
    restored = MatchEngineV13MicroAdjustments.from_json(engine.export_json())
    assert restored.micro_adjustment_diagnostic() == engine.micro_adjustment_diagnostic()
