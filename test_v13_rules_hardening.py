from __future__ import annotations

from engine import Band, Lane, PendingAction, Zone, make_generic_team
from engine_experiment_v13_finishing import MatchEngineV13AdvancedFinishing
from engine_experiment_v13_rules_hardening import MatchEngineV13RulesHardening
from diagnostics_v13 import _bin_for_xg


def _engine(seed: int = 1307):
    return MatchEngineV13RulesHardening(
        make_generic_team("Home", 80, "balanced", seed=101),
        make_generic_team("Away", 80, "balanced", seed=202),
        seed=seed,
    )


def _line_share(engine, team: int, zone: Zone, positions: set[str]) -> float:
    shares = engine.defender_engagement_diagnostic(team, zone)
    return sum(
        share
        for ps in engine.teams[team].on_field
        for name, share in shares.items()
        if ps.player.name == name and ps.player.position.upper() in positions
    )


def test_high_press_engagement_uses_first_line_not_holding_midfield_only():
    engine = _engine()
    zone = Zone(Band.DEF, Lane.CENTER)
    front = _line_share(engine, 1, zone, {"ST", "LW", "RW", "AM"})
    holding = _line_share(engine, 1, zone, {"DM", "CB"})
    assert front > holding


def test_box_engagement_favors_real_defensive_line():
    engine = _engine()
    zone = Zone(Band.BOX, Lane.CENTER)
    back = _line_share(engine, 1, zone, {"CB", "LB", "RB", "DM"})
    front = _line_share(engine, 1, zone, {"ST", "LW", "RW", "AM"})
    assert back > front


def test_attack_left_maps_to_defending_right_side():
    engine = _engine()
    zone = Zone(Band.ATT, Lane.LEFT)
    shares = engine.defender_engagement_diagnostic(1, zone)
    rb = next(ps for ps in engine.teams[1].on_field if ps.player.position.upper() == "RB")
    lb = next(ps for ps in engine.teams[1].on_field if ps.player.position.upper() == "LB")
    assert shares[rb.player.name] > shares[lb.player.name]


def test_defender_engagement_diagnostic_is_rng_pure():
    engine = _engine()
    state = engine.rng.getstate()
    engine.defender_engagement_diagnostic(1, Zone(Band.MID, Lane.CENTER))
    assert engine.rng.getstate() == state


def test_finishing_selection_does_not_feed_player_skill_back_into_xg_danger():
    engine = MatchEngineV13AdvancedFinishing(
        make_generic_team("Home", 80, "balanced", seed=303),
        make_generic_team("Away", 80, "balanced", seed=404),
        seed=1411,
    )
    shooter = next(
        ps for ps in engine.teams[0].on_field
        if ps.player.position.upper() in {"ST", "AM", "LW", "RW"}
    )
    defender = next(
        ps for ps in engine.teams[1].on_field
        if ps.player.position.upper() in {"CB", "LB", "RB", "DM"}
    )
    pending = PendingAction(
        team=0,
        actor=shooter.player.name,
        kind="shoot",
        zone=Zone(Band.BOX, Lane.CENTER),
        danger=0.66,
        pressure=0.38,
        defender=defender.player.name,
        origin="through_ball",
        body_part="foot",
    )
    original_danger = pending.danger
    engine._resolve_shot(pending)
    assert pending.danger == original_danger


def test_raw_xg_describes_situation_not_finisher_or_keeper_attributes():
    engine = _engine(seed=1423)
    shooter = next(ps for ps in engine.teams[0].on_field if ps.player.position.upper() == "ST")
    defender = next(ps for ps in engine.teams[1].on_field if ps.player.position.upper() == "CB")
    keeper = engine._goalkeeper(1)
    pending = PendingAction(
        0,
        shooter.player.name,
        "shoot",
        Zone(Band.BOX, Lane.CENTER),
        danger=0.70,
        pressure=0.31,
        defender=defender.player.name,
        origin="cutback",
    )
    baseline = engine._calculate_xg(pending, shooter, defender, keeper)
    for attr in ("finishing", "technique", "composure", "long_shots"):
        setattr(shooter.player, attr, 95)
    for attr in ("reflexes", "gk_positioning", "one_on_one"):
        setattr(keeper.player, attr, 45)
    changed = engine._calculate_xg(pending, shooter, defender, keeper)
    assert baseline == changed


def test_xg_diagnostic_uses_requested_chance_quality_bins():
    assert _bin_for_xg(0.049) == "0.00-0.05"
    assert _bin_for_xg(0.050) == "0.05-0.10"
    assert _bin_for_xg(0.100) == "0.10-0.20"
    assert _bin_for_xg(0.200) == "0.20-0.40"
    assert _bin_for_xg(0.400) == "0.40+"


def test_canonical_shot_ledger_covers_stats_and_exact_xg():
    engine = _engine(seed=0)
    guard = 0
    while sum(st.shots for st in engine.stats) < 6 and not engine.state.ended and guard < 2500:
        engine.step()
        guard += 1
    assert guard < 2500
    coverage = engine.shot_ledger_coverage()
    rows = engine.shot_ledger_diagnostic()
    assert coverage["complete"]
    assert len(rows) == sum(st.shots for st in engine.stats)
    assert len({row["shot_id"] for row in rows}) == len(rows)
    assert abs(sum(float(row["xg"]) for row in rows) - sum(st.xg for st in engine.stats)) < 1e-8


def test_shot_ledger_roundtrip_preserves_existing_attempts_and_future_coverage():
    engine = _engine(seed=2026)
    guard = 0
    while sum(st.shots for st in engine.stats) < 3 and not engine.state.ended and guard < 2500:
        engine.step()
        guard += 1
    restored = MatchEngineV13RulesHardening.from_json(engine.export_json())
    assert restored.shot_ledger_diagnostic() == engine.shot_ledger_diagnostic()
    assert restored.shot_ledger_coverage() == engine.shot_ledger_coverage()
    for _ in range(80):
        if engine.state.ended or restored.state.ended:
            break
        a = engine.step()
        b = restored.step()
        assert (a.type, a.team, a.text_key, a.data) == (b.type, b.team, b.text_key, b.data)
    assert restored.shot_ledger_coverage()["complete"]
    assert restored.shot_ledger_diagnostic() == engine.shot_ledger_diagnostic()
