import copy

from engine import MatchConfig, make_generic_team
from engine_experiment_v13_load_injuries import MatchEngineV13LoadInjuries


class _AlwaysZeroRng:
    def random(self):
        return 0.0

    def getstate(self):
        return ("always-zero",)

    def setstate(self, state):
        pass


def _engine(seed=2131, environment=None):
    return MatchEngineV13LoadInjuries(
        make_generic_team("Home", 78, seed=101),
        make_generic_team("Away", 78, seed=102),
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=False),
        environment=environment,
    )


def test_running_clock_accumulates_load_without_mutating_attributes():
    engine = _engine()
    player = next(ps for ps in engine.teams[0].on_field if ps.player.position == "CM")
    before_attrs = copy.deepcopy(player.player.__dict__)
    before = engine.load_injury_diagnostic(0)[player.player.name]["load"]
    engine._advance_clock(300.0, 0)
    after = engine.load_injury_diagnostic(0)[player.player.name]["load"]
    assert after > before
    assert player.player.__dict__ == before_attrs


def test_heat_and_heavy_pitch_increase_load_multiplier():
    normal = _engine(seed=2232, environment={"weather": "clear", "pitch": "normal", "wind": 0.2, "temperature_c": 22})
    harsh = _engine(seed=2232, environment={"weather": "heavy_rain", "pitch": "heavy", "wind": 0.2, "temperature_c": 34})
    assert harsh._load_environment_multiplier() > normal._load_environment_multiplier()


def test_load_injury_risk_requires_meaningful_accumulated_load():
    engine = _engine()
    player = next(ps for ps in engine.teams[0].on_field if ps.player.position == "CM")
    assert engine._load_injury_risk(0, player) == 0.0
    row = engine._v13_load_state[engine._load_key(0, player.player.name)]
    row["load"] = 70.0
    player.energy = 0.42
    assert engine._load_injury_risk(0, player) > 0.0


def test_forced_load_injury_reuses_existing_medical_state():
    engine = _engine()
    engine.state.second = 80.0 * 60.0
    engine._v13_next_load_check_second = engine.state.second
    player = next(ps for ps in engine.teams[0].on_field if ps.player.position == "CM")
    row = engine._v13_load_state[engine._load_key(0, player.player.name)]
    row["load"] = 92.0
    player.energy = 0.30
    # Make team 1 candidates ineligible so the deterministic forced draw resolves team 0 first.
    for ps in engine.teams[1].on_field:
        engine._v13_load_state[engine._load_key(1, ps.player.name)]["occurred"] = True
    engine._v13_load_injury_rng = _AlwaysZeroRng()
    event = engine._maybe_load_injury()
    assert event is not None
    assert event.text_key == "muscular_load_injury"
    assert event.data["load_related"] is True
    assert engine.current_injury_status(0, event.data["player"]) is not None


def test_dead_ball_gives_only_small_relief():
    engine = _engine()
    player = next(ps for ps in engine.teams[0].on_field if ps.player.position == "CM")
    row = engine._v13_load_state[engine._load_key(0, player.player.name)]
    row["load"] = 50.0
    engine._advance_dead_clock(60.0, 30.0, reason="injury_treatment")
    assert 49.0 < row["load"] < 50.0


def test_load_state_and_rng_survive_save_load():
    engine = _engine(seed=2333)
    engine._advance_clock(900.0, 0)
    _ = engine._v13_load_injury_rng.random()
    restored = MatchEngineV13LoadInjuries.from_json(engine.export_json())
    assert restored.load_injury_diagnostic() == engine.load_injury_diagnostic()
    assert restored._v13_next_load_check_second == engine._v13_next_load_check_second
    assert restored._v13_load_injury_rng.getstate() == engine._v13_load_injury_rng.getstate()
