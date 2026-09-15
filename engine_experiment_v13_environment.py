from __future__ import annotations

"""v1.3 match environment: weather, pitch, wind and temperature.

The environment is deterministic per fixture seed but generated with an
independent RNG so it does not consume or shift the match RNG sequence. Effects
are intentionally small and causal: surface affects control/carrying, wind
mostly affects aerial/long actions and heat/heavy turf adds fatigue load.
"""

from copy import deepcopy
from dataclasses import replace
import random

from engine import Band, PendingAction, clamp, weighted_choice
from engine_experiment_v13_ratings import MatchEngineV13Ratings


class MatchEngineV13Environment(MatchEngineV13Ratings):
    WEATHER = {"clear", "overcast", "rain", "heavy_rain"}
    PITCH = {"dry", "normal", "slick", "heavy"}

    def __init__(self, *args, environment: dict | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._v13_environment = self._normalise_environment(
            environment if environment is not None else self._generate_environment()
        )

    def _generate_environment(self) -> dict:
        home = self.teams[0].team.name
        away = self.teams[1].team.name
        rng = random.Random(f"v13-environment:{self.seed}:{home}:{away}")
        weather = weighted_choice(
            rng,
            [("clear", 0.53), ("overcast", 0.23), ("rain", 0.19), ("heavy_rain", 0.05)],
        )
        if weather == "clear":
            pitch = weighted_choice(rng, [("normal", 0.68), ("dry", 0.32)])
        elif weather == "overcast":
            pitch = weighted_choice(rng, [("normal", 0.82), ("dry", 0.13), ("slick", 0.05)])
        elif weather == "rain":
            pitch = weighted_choice(rng, [("slick", 0.72), ("heavy", 0.18), ("normal", 0.10)])
        else:
            pitch = weighted_choice(rng, [("heavy", 0.58), ("slick", 0.42)])
        wind = clamp(rng.gauss(0.25, 0.15), 0.02, 0.85)
        temperature = clamp(rng.gauss(22.0, 5.3), 8.0, 36.0)
        return {
            "weather": weather,
            "pitch": pitch,
            "wind": round(wind, 4),
            "temperature_c": round(temperature, 2),
            "source": "seeded_fixture_context",
        }

    @classmethod
    def _normalise_environment(cls, raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise TypeError("environment must be a mapping")
        weather = str(raw.get("weather", "clear")).lower().strip()
        pitch = str(raw.get("pitch", "normal")).lower().strip()
        if weather not in cls.WEATHER:
            raise ValueError(f"Unsupported weather: {weather}")
        if pitch not in cls.PITCH:
            raise ValueError(f"Unsupported pitch condition: {pitch}")
        wind = float(raw.get("wind", 0.20))
        temperature = float(raw.get("temperature_c", 22.0))
        if not 0.0 <= wind <= 1.0:
            raise ValueError("wind must be in 0..1")
        if not -5.0 <= temperature <= 45.0:
            raise ValueError("temperature_c must be in -5..45")
        return {
            "weather": weather,
            "pitch": pitch,
            "wind": round(wind, 4),
            "temperature_c": round(temperature, 2),
            "source": str(raw.get("source", "explicit")),
        }

    def environment_diagnostic(self) -> dict:
        env = dict(self._v13_environment)
        env.update(self._environment_effects())
        return env

    def _environment_effects(self) -> dict:
        env = self._v13_environment
        weather = env["weather"]
        pitch = env["pitch"]
        wind = float(env["wind"])
        temp = float(env["temperature_c"])

        surface_control = {
            "dry": 0.003,
            "normal": 0.0,
            "slick": 0.016,
            "heavy": 0.027,
        }[pitch]
        if weather == "rain":
            surface_control += 0.008
        elif weather == "heavy_rain":
            surface_control += 0.018

        heavy_ground = {"dry": 0.0, "normal": 0.0, "slick": 0.15, "heavy": 1.0}[pitch]
        heat = clamp((temp - 27.0) / 9.0)
        cold = clamp((10.0 - temp) / 10.0)
        return {
            "surface_control_penalty": round(surface_control, 5),
            "long_ball_wind_penalty": round(0.036 * wind, 5),
            "cross_wind_penalty": round(0.029 * wind, 5),
            "long_shot_wind_penalty": round(0.040 * wind, 5),
            "heat_load": round(heat, 5),
            "heavy_ground_load": round(heavy_ground, 5),
            "cold_load": round(cold, 5),
        }

    def _advance_clock(self, seconds: float, possession_team: int):
        super()._advance_clock(seconds, possession_team)
        effects = self._environment_effects()
        extra_per_minute = (
            0.00034 * float(effects["heat_load"])
            + 0.00024 * float(effects["heavy_ground_load"])
            + 0.00006 * float(effects["cold_load"])
        )
        if extra_per_minute <= 0.0:
            return
        extra = float(seconds) / 60.0 * extra_per_minute
        for rt in self.teams:
            for ps in rt.on_field:
                stamina_relief = 0.86 + 0.14 * (100.0 - ps.player.stamina) / 80.0
                ps.energy = clamp(ps.energy - extra * stamina_relief, 0.18, 1.0)

    def _safe_pass(self, team, actor, zone, ctx):
        effects = self._environment_effects()
        tuned = dict(ctx)
        tuned["pressure"] = clamp(
            float(tuned.get("pressure", 0.5))
            + 0.34 * float(effects["surface_control_penalty"])
        )
        return super()._safe_pass(team, actor, zone, tuned)

    def _progressive_action(self, team, actor, zone, kind, ctx):
        effects = self._environment_effects()
        tuned = dict(ctx)
        penalty = 0.50 * float(effects["surface_control_penalty"])
        if kind in {"long_ball", "switch"}:
            penalty += float(effects["long_ball_wind_penalty"])
        tuned["pressure"] = clamp(float(tuned.get("pressure", 0.5)) + penalty)
        if self._v13_environment["pitch"] == "heavy":
            tuned["space"] = clamp(float(tuned.get("space", 0.5)) - 0.012)
        return super()._progressive_action(team, actor, zone, kind, tuned)

    def _carry(self, team, actor, zone, ctx):
        effects = self._environment_effects()
        tuned = dict(ctx)
        surface = float(effects["surface_control_penalty"])
        tuned["pressure"] = clamp(float(tuned.get("pressure", 0.5)) + 0.80 * surface)
        if self._v13_environment["pitch"] in {"slick", "heavy"}:
            tuned["space"] = clamp(float(tuned.get("space", 0.5)) - 0.010 - 0.20 * surface)
        return super()._carry(team, actor, zone, tuned)

    def _create_or_resolve_danger(self, team, actor, zone, kind, ctx):
        effects = self._environment_effects()
        tuned = dict(ctx)
        penalty = 0.0
        if kind == "cross":
            penalty += float(effects["cross_wind_penalty"])
        elif kind in {"dribble", "cutback"}:
            penalty += 0.55 * float(effects["surface_control_penalty"])
        elif kind == "through_ball":
            penalty += 0.25 * float(effects["surface_control_penalty"])
        tuned["pressure"] = clamp(float(tuned.get("pressure", 0.5)) + penalty)
        return super()._create_or_resolve_danger(team, actor, zone, kind, tuned)

    def _resolve_shot(self, p: PendingAction):
        effects = self._environment_effects()
        wind = float(self._v13_environment["wind"])
        distance_factor = {
            Band.BOX: 0.10,
            Band.ATT: 0.70,
            Band.MID: 1.00,
            Band.DEF: 1.00,
        }[p.zone.band]
        weather = self._v13_environment["weather"]
        rain_noise = 0.004 if weather == "rain" else 0.009 if weather == "heavy_rain" else 0.0
        extra_pressure = distance_factor * float(effects["long_shot_wind_penalty"]) + rain_noise
        tuned = replace(p, pressure=clamp(float(p.pressure) + extra_pressure))
        return super()._resolve_shot(tuned)

    def _foul_probability(self, defender, attacker, ctx) -> float:
        base = float(super()._foul_probability(defender, attacker, ctx))
        pitch = self._v13_environment["pitch"]
        weather = self._v13_environment["weather"]
        slip = 0.0
        if pitch == "slick":
            slip += 0.004
        elif pitch == "heavy":
            slip += 0.003
        if weather == "heavy_rain":
            slip += 0.003
        return clamp(base + slip, 0.0, 0.22)

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["environment"] = self.environment_diagnostic()
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        data["v13_environment"] = deepcopy(self._v13_environment)
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_environment")
        obj._v13_environment = cls._normalise_environment(
            raw if isinstance(raw, dict) else {
                "weather": "clear",
                "pitch": "normal",
                "wind": 0.20,
                "temperature_c": 22.0,
                "source": "legacy_restore_default",
            }
        )
        return obj


MatchEngine = MatchEngineV13Environment

__all__ = ["MatchEngineV13Environment", "MatchEngine"]
