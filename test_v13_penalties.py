import copy

from engine import MatchConfig, make_generic_team
from engine_experiment_v13_penalties import MatchEngineV13Penalties


def _engine(seed=2737):
    return MatchEngineV13Penalties(
        make_generic_team("Home", 78, seed=121),
        make_generic_team("Away", 78, seed=122),
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=False, allow_extra_time=True),
    )


def _taker_keeper(engine):
    taker = engine._best_player(0, ("finishing", "composure", "technique"), exclude_positions={"GK"})
    keeper = engine._goalkeeper(1)
    return taker, keeper


def test_penalty_plans_are_rng_pure_and_normalised():
    engine = _engine()
    taker, keeper = _taker_keeper(engine)
    pressure = engine._penalty_pressure(0, taker, shootout=False)
    before = copy.deepcopy(engine.rng.getstate())
    taker_plan = engine.penalty_taker_plan_diagnostic(0, taker, keeper, pressure=pressure)
    keeper_plan = engine.penalty_keeper_plan_diagnostic(1, keeper, 0)
    assert engine.rng.getstate() == before
    assert abs(sum(taker_plan["styles"].values()) - 1.0) < 1e-9
    assert abs(sum(taker_plan["targets"].values()) - 1.0) < 1e-9
    assert abs(sum(keeper_plan["weights"].values()) - 1.0) < 1e-9


def test_keeper_memory_uses_only_previous_kicks():
    engine = _engine()
    _, keeper = _taker_keeper(engine)
    before = engine.penalty_keeper_plan_diagnostic(1, keeper, 0)
    assert before["observed"]["total"] == 0
    for idx in range(4):
        engine._v13_penalty_history.append({
            "attacking_team": 0,
            "defending_team": 1,
            "taker": f"T{idx}",
            "keeper": keeper.player.name,
            "style": "placed",
            "target": "low_left",
            "keeper_approach": "wait",
            "scored": True,
            "shootout": True,
            "minute": 120.0,
        })
    after = engine.penalty_keeper_plan_diagnostic(1, keeper, 0)
    assert after["observed"]["total"] == 4
    assert after["weights"]["guess_left"] > before["weights"]["guess_left"]


def test_live_penalty_uses_richer_metadata_and_no_attribute_mutation():
    engine = _engine(seed=2838)
    taker, keeper = _taker_keeper(engine)
    before_taker = copy.deepcopy(taker.player.__dict__)
    before_keeper = copy.deepcopy(keeper.player.__dict__)
    engine.state.restart = "penalty"
    engine.state.restart_team = 0
    event = engine._resolve_restart()
    assert event.data.get("penalty_style") in engine.PENALTY_STYLES
    assert event.data.get("penalty_target") in engine.PENALTY_TARGETS
    assert event.data.get("keeper_approach") in engine.KEEPER_APPROACHES
    assert len(engine.penalty_history_diagnostic()) == 1
    assert taker.player.__dict__ == before_taker
    assert keeper.player.__dict__ == before_keeper


def test_shootout_resolves_one_kick_per_step_with_decision_metadata():
    engine = _engine(seed=2939)
    engine._start_shootout()
    before_kicks = sum(engine._v13_shootout["kicks"])
    event = engine.step()
    after_kicks = sum(engine._v13_shootout["kicks"])
    assert after_kicks == before_kicks + 1
    assert event.data.get("shootout") is True
    assert event.data.get("penalty_style") in engine.PENALTY_STYLES
    assert event.data.get("penalty_target") in engine.PENALTY_TARGETS
    assert event.data.get("keeper_approach") in engine.KEEPER_APPROACHES


def test_penalty_history_survives_save_load():
    engine = _engine(seed=3040)
    engine.state.restart = "penalty"
    engine.state.restart_team = 0
    engine._resolve_restart()
    restored = MatchEngineV13Penalties.from_json(engine.export_json())
    assert restored.penalty_history_diagnostic() == engine.penalty_history_diagnostic()


def test_same_seed_penalty_duel_is_deterministic():
    a = _engine(seed=3141)
    b = _engine(seed=3141)
    for engine in (a, b):
        engine.state.restart = "penalty"
        engine.state.restart_team = 0
    ea = a._resolve_restart()
    eb = b._resolve_restart()
    assert ea.type == eb.type
    assert ea.text_key == eb.text_key
    assert ea.data == eb.data
    assert a.penalty_history_diagnostic() == b.penalty_history_diagnostic()
