from __future__ import annotations

"""Structural hardening for the current v1.3 candidate.

This top adapter fixes three mechanics exposed by live/diagnostic matches:
- historical competition substitution limits come from fixture metadata;
- tactical-foul responsibility is probabilistic instead of always selecting the
  single highest-scoring player;
- normal automatic substitutions require a positive footballing benefit after
  accounting for freshness and the relevant match context.

No rule reads a desired score, benchmark target, team strength or future event.
"""

from dataclasses import replace

from engine import Lane, MatchConfig, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_venue import MatchEngineV13VenueContext


VERSION = "1.3-candidate-rules-hardening"
HISTORICAL_2014_KEYS = {"brazil_2014", "germany_2014"}


class MatchEngineV13RulesHardening(MatchEngineV13VenueContext):
    """Competition-law, foul-attribution and substitution-benefit guardrails."""

    def __init__(self, home, away, seed=None, config=None, **kwargs):
        effective_config = replace(config) if config is not None else MatchConfig()
        home_key = getattr(home, "historical_key", None)
        away_key = getattr(away, "historical_key", None)
        if home_key in HISTORICAL_2014_KEYS and away_key in HISTORICAL_2014_KEYS:
            # 2014 World Cup law: three substitutions; there was no fourth
            # extra-time substitute in that competition era.
            effective_config = replace(
                effective_config,
                max_substitutions=3,
                allow_extra_time_substitution=False,
            )
        super().__init__(home, away, seed=seed, config=effective_config, **kwargs)

    def _tactical_foul_candidate(self, defending_team: int, zone: Zone) -> PlayerState:
        """Choose a plausible fouler without deterministically reusing one player.

        Positioning still matters strongly, but nearby teammates share the
        responsibility. Prior foul involvement and an existing caution make a
        player less likely to volunteer for the next cynical intervention.
        """
        candidates = [
            ps
            for ps in self.teams[int(defending_team)].on_field
            if not ps.red and ps.player.position.upper() != "GK"
        ]
        if not candidates:
            return self._goalkeeper(defending_team)

        def tactical_count(name: str) -> int:
            count = 0
            for event in self.state.event_log:
                if event.text_key == "tactical_foul_stops_transition" and event.data.get("fouler") == name:
                    count += 1
            return count

        weighted = []
        for ps in candidates:
            pos = ps.player.position.upper()
            positional = {
                "DM": 1.35,
                "CM": 1.18,
                "CB": 1.08,
                "LB": 0.94,
                "RB": 0.94,
                "AM": 0.62,
                "LW": 0.46,
                "RW": 0.46,
                "ST": 0.30,
            }.get(pos, 0.45)
            if zone.lane == Lane.LEFT and pos in {"LB", "CB", "DM", "CM"}:
                positional *= 1.18
            elif zone.lane == Lane.RIGHT and pos in {"RB", "CB", "DM", "CM"}:
                positional *= 1.18

            positioning = clamp(ps.effective("positioning") / 100.0)
            tackling = clamp(ps.effective("tackling") / 100.0)
            pace = clamp(ps.effective("pace") / 100.0)
            composure = clamp(ps.effective("composure") / 100.0)
            involvement = (
                tactical_count(ps.player.name)
                + int(getattr(self, "_ref_player_fouls", {}).get(self._foul_key(defending_team, ps), 0))
            )
            management = 1.0 / (1.0 + 0.34 * involvement)
            if ps.yellow:
                management *= 0.48
            ability = 0.31 * positioning + 0.27 * tackling + 0.23 * pace + 0.19 * composure
            weight = max(0.01, positional * (0.45 + ability) * management)
            weighted.append((ps, weight))

        return weighted_choice(self._v13_tactical_foul_rng, weighted)

    def _replacement_profile(self, team, outgoing, incoming, reason):
        profile = super()._replacement_profile(team, outgoing, incoming, reason)
        if profile is None:
            return None

        reason = str(reason)
        fresh_gain = float(profile.get("fresh_gain", 0.0))
        context_gain = float(profile.get("context_gain", 0.0))
        net_benefit = 0.56 * fresh_gain + 0.44 * context_gain
        profile["net_benefit"] = net_benefit

        # Medical necessity and deliberate shootout preparation have benefits
        # not represented by the ordinary freshness/context indices.
        if reason in {"injury", "injury_management", "shootout_preparation"}:
            return profile

        if reason in {"tactical_chase", "tactical_protect"}:
            if net_benefit < 0.010:
                return None
        elif reason in {"fatigue", "freshness"}:
            if fresh_gain < -0.020 or net_benefit < 0.0:
                return None
        elif reason == "card_risk":
            # Removing a vulnerable booked player has a real benefit outside the
            # technical indices, but not enough to justify a major downgrade.
            if fresh_gain < -0.040 or net_benefit < -0.010:
                return None
        elif net_benefit < 0.0:
            return None
        return profile

    def auto_substitution_diagnostic(self):
        candidate = self._best_auto_substitution()
        if candidate is None:
            return None
        outgoing = candidate["outgoing"]
        incoming = candidate["incoming"]
        data = {
            "team": int(candidate["team"]),
            "out": outgoing.player.name,
            "in": incoming.name,
            "reason": candidate["reason"],
            "out_energy": float(outgoing.energy),
            "role_fit": float(candidate["role_fit"]),
            "fresh_gain": float(candidate["fresh_gain"]),
            "context_gain": float(candidate["context_gain"]),
            "net_benefit": float(candidate.get("net_benefit", 0.0)),
            "candidate_score": float(candidate["candidate_score"]),
        }
        for key in (
            "position_familiarity",
            "assigned_position",
            "natural_position",
            "penalty_gain",
            "incoming_penalty_quality",
            "outgoing_penalty_quality",
        ):
            if key in candidate:
                value = candidate[key]
                data[key] = float(value) if isinstance(value, (int, float)) else value
        return data


MatchEngine = MatchEngineV13RulesHardening

__all__ = ["MatchEngineV13RulesHardening", "MatchEngine", "VERSION"]
