import copy

from engine import Band, Lane, MatchConfig, PendingAction, Zone, make_generic_team
from engine_experiment_v13_gk_one_v_one import MatchEngineV13GoalkeeperOneVOne


def _engine(seed=2434):
    return MatchEngineV13GoalkeeperOneVOne(
        make_generic_team("Home", 78, seed=111),
        make_generic_team("Away", 78, seed=112),
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=False),
    )


def _pending(engine):
    striker = next(ps for ps in engine.teams[0].on_field if ps.player.position == "ST")
    return PendingAction(
        team=0,
        actor=striker.player.name,
        kind="shoot",
        zone=Zone(Band.BOX, Lane.CENTER),
        danger=0.70,
        pressure=0.30,
        origin="through_ball",
    )


def test_one_v_one_detection_is_contextual():
    engine = _engine()
    p = _pending(engine)
    assert engine._is_keeper_one_v_one(p)
    p.origin = "corner"
    assert not engine._is_keeper_one_v_one(p)


def test_marginal_box_shot_is_not_mislabeled_as_genuine_one_v_one():
    engine = _engine()
    p = _pending(engine)
    p.danger = 0.53
    p.pressure = 0.61
    assert not engine._is_keeper_one_v_one(p)


def test_scramble_origin_requires_clear_isolation():
    engine = _engine()
    p = _pending(engine)
    p.origin = "second_ball"
    p.danger = 0.68
    p.pressure = 0.34
    assert not engine._is_keeper_one_v_one(p)
    p.danger = 0.74
    p.pressure = 0.26
    assert engine._is_keeper_one_v_one(p)


def test_transition_and_carry_use_different_isolation_thresholds():
    engine = _engine()
    p = _pending(engine)
    p.danger = 0.60
    p.pressure = 0.52
    p.origin = "transition"
    assert engine._is_keeper_one_v_one(p)
    p.origin = "carry"
    assert not engine._is_keeper_one_v_one(p)


def test_one_v_one_diagnostics_are_rng_pure_and_normalised():
    engine = _engine()
    p = _pending(engine)
    shooter = engine.teams[0].by_name(p.actor)
    keeper = engine._goalkeeper(1)
    before = copy.deepcopy(engine.rng.getstate())
    atk = engine.attacker_one_v_one_diagnostic(shooter, keeper, p)
    gk = engine.keeper_one_v_one_diagnostic(keeper, shooter, p)
    assert engine.rng.getstate() == before
    assert abs(sum(atk["weights"].values()) - 1.0) < 1e-9
    assert abs(sum(gk["weights"].values()) - 1.0) < 1e-9


def test_rushing_keeper_can_be_attacked_by_chip_without_guaranteed_outcome():
    engine = _engine()
    p = _pending(engine)
    shooter = engine.teams[0].by_name(p.actor)
    keeper = engine._goalkeeper(1)
    interaction = engine._one_v_one_interaction("chip", "rush", shooter, keeper)
    assert interaction["interaction"] == "chip_attacks_rush"
    assert -0.065 <= interaction["danger_delta"] <= 0.075
    assert -0.035 <= interaction["pressure_delta"] <= 0.115
    assert "goal" not in interaction


def test_one_v_one_resolution_adds_decision_metadata_without_attribute_mutation():
    engine = _engine(seed=2535)
    p = _pending(engine)
    shooter = engine.teams[0].by_name(p.actor)
    keeper = engine._goalkeeper(1)
    before_shooter = copy.deepcopy(shooter.player.__dict__)
    before_keeper = copy.deepcopy(keeper.player.__dict__)
    event = engine._resolve_shot(p)
    assert event.data.get("goalkeeper_one_v_one") is True
    assert event.data.get("attacker_1v1_choice") in engine.ATTACKER_CHOICES
    assert event.data.get("keeper_1v1_choice") in engine.KEEPER_CHOICES
    assert event.data.get("one_v_one_base_danger") == 0.7
    assert event.data.get("one_v_one_base_pressure") == 0.3
    assert event.data.get("one_v_one_origin") == "through_ball"
    assert shooter.player.__dict__ == before_shooter
    assert keeper.player.__dict__ == before_keeper


def test_same_seed_one_v_one_choices_are_deterministic():
    a = _engine(seed=2636)
    b = _engine(seed=2636)
    ea = a._resolve_shot(_pending(a))
    eb = b._resolve_shot(_pending(b))
    assert ea.data.get("attacker_1v1_choice") == eb.data.get("attacker_1v1_choice")
    assert ea.data.get("keeper_1v1_choice") == eb.data.get("keeper_1v1_choice")
    assert ea.type == eb.type
    assert ea.text_key == eb.text_key