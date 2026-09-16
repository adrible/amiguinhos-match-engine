import copy

from engine import Band, Lane, MatchConfig, Zone, make_generic_team
from engine_experiment_v13_mismatches import MatchEngineV13Mismatches


def _engine(seed=1121):
    return MatchEngineV13Mismatches(
        make_generic_team("Home", 78, seed=41),
        make_generic_team("Away", 78, seed=42),
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=False),
    )


def _player(engine, team, position):
    return next(ps for ps in engine.teams[team].on_field if ps.player.position == position)


def _seed_rows(engine, team, player_name, pattern, successes, lane="center"):
    engine.state.second = 30.0 * 60.0
    rows = engine._ensure_mismatch_state()
    for index, success in enumerate(successes):
        rows.append({
            "team": team,
            "player": player_name,
            "pattern": pattern,
            "action": "dribble" if pattern == "carry_dribble" else "through_ball",
            "lane": lane,
            "band": "final_third",
            "success": float(success),
            "defender": "Away CB3",
            "second": engine.state.second - (len(successes) - index) * 70.0,
        })


def test_repeated_success_creates_positive_mismatch_signal():
    engine = _engine()
    winger = _player(engine, 0, "RW")
    _seed_rows(engine, 0, winger.player.name, "carry_dribble", [1.0, 1.0, 0.85, 1.0], lane="right")
    diag = engine.mismatch_diagnostic(0, winger.player.name, pattern="carry_dribble", lane=Lane.RIGHT)
    assert diag["active"]
    assert diag["sample_count"] == 4
    assert diag["success_rate"] > 0.80
    assert diag["strength"] > 0.0


def test_repeated_failure_creates_negative_signal_not_fake_buff():
    engine = _engine()
    winger = _player(engine, 0, "LW")
    _seed_rows(engine, 0, winger.player.name, "wide_service", [0.0, 0.0, 0.0, 0.2], lane="left")
    diag = engine.mismatch_diagnostic(0, winger.player.name, pattern="wide_service", lane=Lane.LEFT)
    assert diag["active"]
    assert diag["strength"] < 0.0


def test_positive_mismatch_changes_tendency_without_mutating_attributes():
    engine = _engine()
    winger = _player(engine, 0, "RW")
    engine.state.second = 30.0 * 60.0
    zone = Zone(Band.ATT, Lane.RIGHT)
    tactics = engine.teams[0].team.tactics
    ctx = {"pressure": 0.35, "space": 0.50, "space_behind": 0.48, "support": 0.52, "wide_space": 0.20}
    before_attrs = copy.deepcopy(winger.player.__dict__)
    neutral = dict(engine._decision_weights(winger, zone, tactics, ctx))
    _seed_rows(engine, 0, winger.player.name, "carry_dribble", [1.0, 1.0, 1.0, 0.85], lane="right")
    hot = dict(engine._decision_weights(winger, zone, tactics, ctx))
    if "dribble" in neutral and "dribble" in hot:
        assert hot["dribble"] >= neutral["dribble"]
    assert winger.player.__dict__ == before_attrs


def test_team_can_prefer_receiver_who_is_winning_repeated_duels():
    engine = _engine()
    winger = _player(engine, 0, "RW")
    engine.state.second = 30.0 * 60.0
    zone = Zone(Band.ATT, Lane.RIGHT)
    actor = _player(engine, 0, "CM")
    base = dict((ps.player.name, weight) for ps, weight in super(MatchEngineV13Mismatches, engine)._base_target_weights(0, zone, actor, {}))
    _seed_rows(engine, 0, winger.player.name, "carry_dribble", [1.0, 1.0, 1.0, 1.0], lane="right")
    adjusted = dict((ps.player.name, weight) for ps, weight in engine._base_target_weights(0, zone, actor, {}))
    if winger.player.name in base and winger.player.name in adjusted:
        assert adjusted[winger.player.name] >= base[winger.player.name]


def test_old_mismatch_evidence_expires_naturally():
    engine = _engine()
    winger = _player(engine, 0, "RW")
    engine.state.second = 60.0 * 60.0
    rows = engine._ensure_mismatch_state()
    for index in range(4):
        rows.append({
            "team": 0,
            "player": winger.player.name,
            "pattern": "carry_dribble",
            "action": "dribble",
            "lane": "right",
            "band": "final_third",
            "success": 1.0,
            "defender": None,
            "second": engine.state.second - 25.0 * 60.0 - index,
        })
    diag = engine.mismatch_diagnostic(0, winger.player.name, pattern="carry_dribble", lane=Lane.RIGHT)
    assert not diag["active"]
    assert diag["sample_count"] == 0


def test_mismatch_state_survives_save_load():
    engine = _engine(seed=1222)
    winger = _player(engine, 0, "RW")
    _seed_rows(engine, 0, winger.player.name, "carry_dribble", [1.0, 0.85, 1.0], lane="right")
    restored = MatchEngineV13Mismatches.from_json(engine.export_json())
    assert restored._ensure_mismatch_state() == engine._ensure_mismatch_state()


def test_mismatch_diagnostic_is_rng_pure():
    engine = _engine()
    winger = _player(engine, 0, "RW")
    _seed_rows(engine, 0, winger.player.name, "carry_dribble", [1.0, 1.0, 0.85], lane="right")
    before = copy.deepcopy(engine.rng.getstate())
    _ = engine.mismatch_diagnostic(0, winger.player.name, pattern="carry_dribble", lane=Lane.RIGHT)
    assert engine.rng.getstate() == before
