import copy

from engine import Band, Lane, MatchConfig, Zone, make_generic_team
from engine_experiment_v13_set_piece_defense import MatchEngineV13SetPieceDefense


def _engine(seed=1626):
    return MatchEngineV13SetPieceDefense(
        make_generic_team("Home", 78, seed=71),
        make_generic_team("Away", 78, seed=72),
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=False),
    )


def test_defensive_corner_plan_is_rng_pure_and_assigns_roles():
    engine = _engine()
    target = next(ps for ps in engine.teams[0].on_field if ps.player.position == "ST")
    before = copy.deepcopy(engine.rng.getstate())
    plan = engine.defensive_corner_plan_diagnostic(1, target=target, pattern="central_delivery", corner_lane=Lane.LEFT)
    assert engine.rng.getstate() == before
    assert plan["scheme"] in engine.DEFENSIVE_CORNER_SCHEMES
    assert plan["marker"]
    assert plan["near_post_guard"]
    assert plan["edge_guard"]
    assert abs(sum(plan["weights"].values()) - 1.0) < 1e-9


def test_corner_marker_is_selected_from_actual_defenders_without_rating_mutation():
    engine = _engine()
    target = next(ps for ps in engine.teams[0].on_field if ps.player.position == "ST")
    before = [copy.deepcopy(ps.player.__dict__) for ps in engine.teams[1].on_field]
    engine._v13_corner_defense_context = engine.defensive_corner_plan_diagnostic(1, target=target, pattern="far_post", corner_lane=Lane.RIGHT)
    marker = engine._corner_defender(1)
    assert marker.player.name == engine._v13_corner_defense_context["marker"]
    assert [ps.player.__dict__ for ps in engine.teams[1].on_field] == before


def test_late_chasing_team_keeps_stronger_counter_outlet_commitment():
    protecting = _engine(seed=1727)
    protecting.state.second = 85.0 * 60.0
    protecting.stats[1].goals = 1
    protecting.stats[0].goals = 0
    target = next(ps for ps in protecting.teams[0].on_field if ps.player.position == "ST")
    protect_plan = protecting.defensive_corner_plan_diagnostic(1, target=target, pattern="central_delivery", corner_lane=Lane.LEFT)

    chasing = _engine(seed=1727)
    chasing.state.second = 85.0 * 60.0
    chasing.stats[1].goals = 0
    chasing.stats[0].goals = 1
    target2 = next(ps for ps in chasing.teams[0].on_field if ps.player.position == "ST")
    chase_plan = chasing.defensive_corner_plan_diagnostic(1, target=target2, pattern="central_delivery", corner_lane=Lane.LEFT)
    assert chase_plan["counter_outlet_commitment"] > protect_plan["counter_outlet_commitment"]


def test_corner_resolution_exposes_defensive_assignments_when_delivery_is_used():
    engine = _engine(seed=1828)
    engine.state.restart = "corner"
    engine.state.restart_team = 0
    engine.state.restart_zone = Zone(Band.ATT, Lane.LEFT)
    # Multiple seeds/patterns are legitimate; whenever a delivery target exists,
    # defensive assignments must travel with the event.
    event = engine._resolve_contextual_corner(0, Zone(Band.ATT, Lane.LEFT))
    if "target" in event.data:
        assert event.data.get("defensive_corner_scheme") in engine.DEFENSIVE_CORNER_SCHEMES
        assert event.data.get("defensive_marker")


def test_defensive_plan_has_counter_outlet_tradeoff_not_execution_bonus():
    engine = _engine()
    target = next(ps for ps in engine.teams[0].on_field if ps.player.position == "ST")
    plan = engine.defensive_corner_plan_diagnostic(1, target=target, pattern="near_post", corner_lane=Lane.LEFT)
    assert 0.0 <= plan["counter_outlet_commitment"] <= 1.0
    assert plan["counter_outlet"] is not None
    assert "finishing_bonus" not in plan
    assert "heading_bonus" not in plan
