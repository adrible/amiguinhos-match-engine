from __future__ import annotations

"""Persistent venue context for the v1.3 candidate.

Venue is modelled as match context, never as a hidden technical-rating bonus.
The layer affects only perceived local pressure/support/space and a very small
away travel load. Referee/card probabilities are deliberately untouched so the
disciplinary calibration remains venue-neutral.

For designated home/away fixtures, the visitor can also experience a causal
environment strain derived from unfamiliarity, crowd hostility and travel. That
strain is applied to the attacking phase through perceived pressure/support/space
rather than through player attributes, and naturally collapses toward zero for
neutral or shared-stadium fixtures.
"""

from copy import deepcopy

from engine import Band, clamp
from engine_experiment_v13_discipline_realism import MatchEngineV13DisciplineRealism

VERSION = "1.3-candidate-venue-context"


class MatchEngineV13VenueContext(MatchEngineV13DisciplineRealism):
    MODES = {"neutral", "home_away", "shared_stadium"}
    DEFAULTS = {
        "neutral": {
            "home_familiarity": 0.50,
            "away_familiarity": 0.50,
            "crowd_home_share": 0.50,
            "away_travel_load": 0.00,
        },
        "home_away": {
            "home_familiarity": 0.82,
            "away_familiarity": 0.44,
            "crowd_home_share": 0.74,
            "away_travel_load": 0.32,
        },
        "shared_stadium": {
            "home_familiarity": 0.72,
            "away_familiarity": 0.70,
            "crowd_home_share": 0.53,
            "away_travel_load": 0.04,
        },
    }

    def __init__(self, *args, venue_context: dict | str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._v13_venue_context = self._normalise_venue_context(venue_context)

    @classmethod
    def _normalise_venue_context(cls, raw: dict | str | None) -> dict:
        if raw is None:
            raw = {"mode": "neutral", "source": "default_neutral"}
        elif isinstance(raw, str):
            raw = {"mode": raw, "source": "explicit_mode"}
        elif not isinstance(raw, dict):
            raise TypeError("venue_context must be a mapping, mode string, or None")
        else:
            raw = dict(raw)

        mode = str(raw.get("mode", "neutral")).strip().lower()
        if mode not in cls.MODES:
            raise ValueError(f"Unsupported venue mode: {mode}")
        defaults = cls.DEFAULTS[mode]

        out = {
            "mode": mode,
            "home_familiarity": clamp(float(raw.get("home_familiarity", defaults["home_familiarity"]))),
            "away_familiarity": clamp(float(raw.get("away_familiarity", defaults["away_familiarity"]))),
            "crowd_home_share": clamp(float(raw.get("crowd_home_share", defaults["crowd_home_share"]))),
            "away_travel_load": clamp(float(raw.get("away_travel_load", defaults["away_travel_load"]))),
            "source": str(raw.get("source", "explicit")),
        }
        return out

    def _away_environment_strain(self) -> float:
        """Return a causal 0..1 visitor-environment load.

        This is deliberately derived only from fixture context. It is not a
        benchmark target and does not inspect score, team identity or ratings.
        Shared-stadium fixtures retain only the small residual implied by their
        crowd/travel context, while neutral fixtures resolve exactly to zero.
        """
        venue = self._v13_venue_context
        if venue["mode"] == "neutral":
            return 0.0
        unfamiliarity = max(0.0, 0.50 - float(venue["away_familiarity"]))
        crowd_hostility = max(0.0, float(venue["crowd_home_share"]) - 0.50)
        travel = max(0.0, float(venue["away_travel_load"]))
        return clamp(
            0.55 * unfamiliarity
            + 0.85 * crowd_hostility
            + 0.45 * travel
        )

    def _away_phase_effects(self, band: Band) -> dict:
        """Extra visitor context in possession, strongest near the home goal."""
        strain = self._away_environment_strain()
        band_scale = {
            Band.DEF: 0.35,
            Band.MID: 0.70,
            Band.ATT: 1.05,
            Band.BOX: 1.20,
        }[band]
        return {
            "pressure_shift": 0.095 * strain * band_scale,
            "support_shift": -0.050 * strain * band_scale,
            "space_shift": -0.020 * strain * band_scale,
        }

    def _venue_effects(self, team: int) -> dict:
        team = int(team)
        if team not in (0, 1):
            raise ValueError("team must be 0 or 1")
        venue = self._v13_venue_context
        familiarity = float(venue["home_familiarity"] if team == 0 else venue["away_familiarity"])
        crowd_edge = float(venue["crowd_home_share"]) - 0.50
        if team == 1:
            crowd_edge *= -1.0
        travel = float(venue["away_travel_load"]) if team == 1 else 0.0

        # Small contextual shifts only. They influence the situation perceived
        # by the decision model, never a player's underlying execution skill.
        pressure_shift = (
            -0.020 * (familiarity - 0.50)
            -0.018 * crowd_edge
            +0.014 * travel
        )
        support_shift = (
            +0.018 * (familiarity - 0.50)
            +0.014 * crowd_edge
            -0.008 * travel
        )
        space_shift = (
            +0.007 * (familiarity - 0.50)
            +0.004 * crowd_edge
            -0.003 * travel
        )

        # The visitor's baseline environment load belongs here rather than in
        # player ratings. Home output is intentionally untouched because the
        # venue asymmetry should primarily emerge from the visitor coping with
        # an unfamiliar/hostile setting, not from a generic home skill boost.
        environment_strain = self._away_environment_strain() if team == 1 else 0.0
        if environment_strain > 0.0:
            pressure_shift += 0.065 * environment_strain
            support_shift -= 0.040 * environment_strain
            space_shift -= 0.016 * environment_strain

        return {
            "team": team,
            "familiarity": round(familiarity, 5),
            "crowd_edge": round(crowd_edge, 5),
            "travel_load": round(travel, 5),
            "environment_strain": round(environment_strain, 6),
            "pressure_shift": round(pressure_shift, 6),
            "support_shift": round(support_shift, 6),
            "space_shift": round(space_shift, 6),
        }

    def venue_diagnostic(self) -> dict:
        return {
            **deepcopy(self._v13_venue_context),
            "away_environment_strain": round(self._away_environment_strain(), 6),
            "home_effects": self._venue_effects(0),
            "away_effects": self._venue_effects(1),
            "referee_bias": 0.0,
        }

    def _spatial_context(self, team, zone):
        context = dict(super()._spatial_context(team, zone))
        team_index = int(team)
        effects = dict(self._venue_effects(team_index))
        if team_index == 1:
            phase = self._away_phase_effects(zone.band)
            effects["pressure_shift"] += phase["pressure_shift"]
            effects["support_shift"] += phase["support_shift"]
            effects["space_shift"] += phase["space_shift"]

        pressure_shift = float(effects["pressure_shift"])
        support_shift = float(effects["support_shift"])
        space_shift = float(effects["space_shift"])
        context["pressure"] = clamp(float(context.get("pressure", 0.5)) + pressure_shift)
        context["support"] = clamp(float(context.get("support", 0.5)) + support_shift)
        context["space"] = clamp(float(context.get("space", 0.5)) + space_shift)
        context["venue_mode"] = self._v13_venue_context["mode"]
        context["venue_pressure_shift"] = round(pressure_shift, 6)
        context["venue_support_shift"] = round(support_shift, 6)
        context["venue_space_shift"] = round(space_shift, 6)
        context["venue_environment_strain"] = effects["environment_strain"]
        return context

    def _advance_clock(self, seconds: float, possession_team: int):
        super()._advance_clock(seconds, possession_team)
        travel = float(self._v13_venue_context.get("away_travel_load", 0.0))
        if travel <= 0.0:
            return
        # Travel load is deliberately tiny: context should matter over a full
        # match, not behave like an attribute penalty from kick-off.
        extra = max(0.0, float(seconds)) / 60.0 * 0.00018 * travel
        if extra <= 0.0:
            return
        for ps in self.teams[1].on_field:
            stamina_relief = 0.92 + 0.08 * (100.0 - ps.player.stamina) / 80.0
            ps.energy = clamp(ps.energy - extra * stamina_relief, 0.18, 1.0)

    def snapshot(self) -> dict:
        data = super().snapshot()
        data["venue"] = self.venue_diagnostic()
        return data

    def export_state(self) -> dict:
        data = super().export_state()
        data["v13_venue_context"] = deepcopy(self._v13_venue_context)
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_venue_context")
        obj._v13_venue_context = cls._normalise_venue_context(
            raw if isinstance(raw, dict) else {"mode": "neutral", "source": "legacy_restore_default"}
        )
        return obj


MatchEngine = MatchEngineV13VenueContext

__all__ = ["MatchEngineV13VenueContext", "MatchEngine", "VERSION"]
