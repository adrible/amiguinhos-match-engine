from __future__ import annotations

"""Structural hardening for the active v1.3 engine line.

This top adapter fixes mechanics exposed by live/diagnostic matches:
- historical competition substitution limits come from fixture metadata;
- defensive engagement is spatially role-aware in every pitch band;
- tactical-foul responsibility is probabilistic instead of always selecting the
  single highest-scoring player;
- normal automatic substitutions require a positive footballing benefit;
- every resolved shot is captured once in a canonical, RNG-free xG ledger.

No rule reads a desired score, benchmark target, team identity or future event.
"""

from copy import deepcopy
from dataclasses import replace

from engine import Band, Lane, MatchConfig, PlayerState, Zone, clamp, weighted_choice
from engine_experiment_v13_venue import MatchEngineV13VenueContext


VERSION = "1.3-candidate-rules-hardening"
HISTORICAL_2014_KEYS = {"brazil_2014", "germany_2014"}


class MatchEngineV13RulesHardening(MatchEngineV13VenueContext):
    """Competition-law, spatial engagement, shot, foul and substitution guardrails."""

    def _resolve_pending(self):
        from dataclasses import asdict
        pending = self.state.pending
        action = asdict(pending) if pending is not None else None
        event = super()._resolve_pending()
        if action is not None:
            event.data["resolved_pending_action"] = action
            event.relevance = max(2, event.relevance)
        return event

    def __init__(self, home, away, seed=None, config=None, **kwargs):
        # Shot telemetry is engine state, not reconstructed later from public
        # narration/events. It consumes no RNG and cannot affect outcomes.
        self._v13_shot_ledger: list[dict] = []
        self._v13_shot_seq = 0
        self._v13_shot_baseline = [0, 0]

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

    def step(self):
        """Advance one engine beat and account for every shot exactly once.

        The engine contract resolves at most one shot attempt in a public step.
        Comparing canonical statistics before/after the beat catches every shot
        route (open play, corner, rebound, free kick, penalty, specialised v1.3
        layers) without depending on which public event happened to represent it.
        """
        before = [
            {
                "shots": int(st.shots),
                "xg": float(st.xg),
                "on_target": int(st.on_target),
                "goals": int(st.goals),
                "blocked": int(st.blocked),
            }
            for st in self.stats
        ]
        event = super().step()

        for team, st in enumerate(self.stats):
            shot_delta = int(st.shots) - before[team]["shots"]
            if shot_delta < 0:
                raise RuntimeError("Shot statistics regressed during a v1.3 step.")
            if shot_delta > 1:
                raise RuntimeError(
                    "A single v1.3 public step resolved more than one shot; "
                    "split the sequence before recording the shot ledger."
                )
            if shot_delta == 0:
                continue

            self._v13_shot_seq += 1
            data = event.data if event is not None and isinstance(event.data, dict) else {}
            xg_delta = max(0.0, float(st.xg) - before[team]["xg"])
            on_target_delta = int(st.on_target) - before[team]["on_target"]
            goal_delta = int(st.goals) - before[team]["goals"]
            blocked_delta = int(st.blocked) - before[team]["blocked"]
            actor = (
                data.get("shooter")
                or data.get("scorer")
                or data.get("taker")
                or data.get("player")
            )
            origin = data.get("origin")
            if not origin and str(getattr(event, "text_key", "")).startswith("penalty_"):
                origin = "penalty"

            self._v13_shot_ledger.append(
                {
                    "shot_id": f"S{self._v13_shot_seq:06d}",
                    "team": int(team),
                    "minute": round(float(getattr(event, "minute", self.minute)), 6),
                    "actor": None if actor is None else str(actor),
                    "origin": None if origin is None else str(origin),
                    "xg": xg_delta,
                    "on_target": bool(on_target_delta > 0),
                    "goal": bool(goal_delta > 0),
                    "blocked": bool(blocked_delta > 0),
                    "outcome": getattr(getattr(event, "type", None), "value", None),
                    "event_key": getattr(event, "text_key", None),
                    "shot_target": data.get("shot_target"),
                    "intended_goal_position": deepcopy(data.get("intended_goal_position")),
                    "actual_goal_position": deepcopy(data.get("actual_goal_position")),
                    "keeper_goal_position": deepcopy(data.get("keeper_goal_position")),
                    "keeper_exposed": bool(data.get("keeper_exposed", False)),
                }
            )
        return event

    def shot_ledger_diagnostic(self) -> list[dict]:
        """Return an RNG-pure copy of canonical shot attempts."""
        return deepcopy(self._v13_shot_ledger)

    def shot_ledger_coverage(self) -> dict:
        """Compare the ledger with canonical statistics since its baseline."""
        expected_by_team = [
            int(self.stats[i].shots) - int(self._v13_shot_baseline[i])
            for i in (0, 1)
        ]
        ledger_by_team = [
            sum(1 for row in self._v13_shot_ledger if int(row["team"]) == i)
            for i in (0, 1)
        ]
        return {
            "expected_by_team": expected_by_team,
            "ledger_by_team": ledger_by_team,
            "expected_total": sum(expected_by_team),
            "ledger_total": len(self._v13_shot_ledger),
            "complete": expected_by_team == ledger_by_team,
        }

    def export_state(self) -> dict:
        data = super().export_state()
        data["v13_shot_ledger"] = self.shot_ledger_diagnostic()
        data["v13_shot_seq"] = int(self._v13_shot_seq)
        data["v13_shot_baseline"] = [int(v) for v in self._v13_shot_baseline]
        return data

    @classmethod
    def from_state_dict(cls, data: dict):
        obj = super().from_state_dict(data)
        raw = data.get("v13_shot_ledger")
        if isinstance(raw, list):
            obj._v13_shot_ledger = deepcopy(raw)
            obj._v13_shot_seq = int(data.get("v13_shot_seq", len(raw)))
            baseline = data.get("v13_shot_baseline", [0, 0])
            if not isinstance(baseline, list) or len(baseline) != 2:
                baseline = [0, 0]
            obj._v13_shot_baseline = [int(baseline[0]), int(baseline[1])]
        else:
            # Legacy v1.3 save: previous attempts are unknowable without
            # reconstructing public events, so start coverage from load time.
            obj._v13_shot_ledger = []
            obj._v13_shot_seq = 0
            obj._v13_shot_baseline = [int(obj.stats[0].shots), int(obj.stats[1].shots)]
        return obj

    @staticmethod
    def _defender_band_role_weight(position: str, zone: Zone) -> float:
        """Role likelihood for the player who actually engages the ball.

        ``zone`` is attack-relative. In the attacking team's DEF band the
        defending side is pressing high, so its forwards/attacking midfielders
        should be the first line of engagement. The old base fallback merged
        DEF and MID and therefore over-selected DM/CM even in a high press.
        """
        pos = str(position).upper()
        if pos == "GK":
            return 0.03 if zone.band == Band.BOX else 0.01
        if zone.band == Band.DEF:
            return {
                "ST": 1.25, "LW": 1.10, "RW": 1.10, "AM": 1.08,
                "CM": 0.80, "DM": 0.42, "LB": 0.28, "RB": 0.28, "CB": 0.16,
            }.get(pos, 0.38)
        if zone.band == Band.MID:
            return {
                "CM": 1.20, "DM": 1.15, "AM": 0.95, "LW": 0.76, "RW": 0.76,
                "LB": 0.70, "RB": 0.70, "ST": 0.55, "CB": 0.50,
            }.get(pos, 0.48)
        if zone.band == Band.ATT:
            return {
                "CB": 1.25, "DM": 1.15, "LB": 1.05, "RB": 1.05, "CM": 0.65,
                "AM": 0.35, "LW": 0.28, "RW": 0.28, "ST": 0.18,
            }.get(pos, 0.30)
        return {
            "CB": 1.70, "LB": 1.05, "RB": 1.05, "DM": 0.90, "CM": 0.38,
            "LW": 0.16, "RW": 0.16, "AM": 0.14, "ST": 0.08,
        }.get(pos, 0.18)

    def _defender_engagement_weight(self, ps: PlayerState, zone: Zone) -> float:
        pos = ps.player.position.upper()
        weight = self._defender_band_role_weight(pos, zone)

        # Lanes are attack-relative: attacking left maps to the defending RB
        # side, and attacking right maps to the defending LB side.
        if zone.lane == Lane.LEFT:
            if pos in {"RB", "RW"}:
                weight *= 1.34
            elif pos == "CB":
                weight *= 1.16
        elif zone.lane == Lane.RIGHT:
            if pos in {"LB", "LW"}:
                weight *= 1.34
            elif pos == "CB":
                weight *= 1.16
        elif pos in {"CB", "DM", "CM", "AM", "ST"}:
            weight *= 1.10

        reading = clamp(
            (
                0.38 * ps.effective("positioning")
                + 0.27 * ps.effective("anticipation")
                + 0.20 * ps.effective("pace")
                + 0.15 * ps.effective("tackling")
            ) / 100.0
        )
        energy = clamp(float(ps.energy))
        return max(0.001, weight * (0.78 + 0.22 * reading) * (0.82 + 0.18 * energy))

    def defender_engagement_diagnostic(self, team: int, zone: Zone) -> dict[str, float]:
        """RNG-pure normalized engagement shares for spatial regression tests."""
        rows = [
            (ps.player.name, self._defender_engagement_weight(ps, zone))
            for ps in self.teams[int(team)].on_field
        ]
        total = sum(weight for _, weight in rows) or 1.0
        return {name: weight / total for name, weight in rows}

    def _choose_defender(self, team, zone) -> PlayerState:
        """Choose the real local engager instead of a generic DM/CM fallback."""
        candidates = list(self.teams[int(team)].on_field)
        if not candidates:
            raise ValueError("No eligible player for defensive engagement.")
        return weighted_choice(
            self.rng,
            [(ps, self._defender_engagement_weight(ps, zone)) for ps in candidates],
        )

    def _tactical_foul_candidate(self, defending_team: int, zone: Zone) -> PlayerState:
        """Choose a plausible fouler without deterministically reusing one player.

        Positioning still matters strongly, but nearby teammates share the
        responsibility. Prior foul involvement and an existing caution make a
        player less likely to volunteer for the next cynical intervention.
        """
        candidates = [
            ps for ps in self.teams[int(defending_team)].on_field
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
                "DM": 1.35, "CM": 1.18, "CB": 1.08, "LB": 0.94, "RB": 0.94,
                "AM": 0.62, "LW": 0.46, "RW": 0.46, "ST": 0.30,
            }.get(pos, 0.45)
            if zone.lane == Lane.LEFT and pos in {"RB", "CB", "DM", "CM"}:
                positional *= 1.18
            elif zone.lane == Lane.RIGHT and pos in {"LB", "CB", "DM", "CM"}:
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

    def _choose_actor(self, team: int, zone: Zone) -> PlayerState:
        """Final goalkeeper guardrail against advanced open-play teleporting."""
        actor = super()._choose_actor(team, zone)
        if actor.player.position.upper() != "GK":
            return actor
        if zone.band == Band.DEF or self._keeper_attack_mode(team, zone) == "keeper_up":
            return actor
        eligible = [
            ps for ps in self.teams[team].on_field
            if not ps.red and ps.player.position.upper() != "GK"
        ]
        if not eligible:
            return actor
        return weighted_choice(
            self.rng,
            [(ps, 0.75 + 0.25 * ps.energy) for ps in eligible],
        )

    def _choose_target(self, team, zone, attacking=True, exclude=None):
        """Keep ordinary passes from placing the goalkeeper in an advanced zone."""
        target = super()._choose_target(
            team, zone, attacking=attacking, exclude=exclude
        )
        if target.player.position.upper() != "GK":
            return target
        allowed = (
            (not attacking and zone.band == Band.DEF)
            or self._keeper_attack_mode(team, zone) == "keeper_up"
        )
        if allowed:
            return target
        eligible = [
            ps for ps in self.teams[team].on_field
            if not ps.red
            and ps.player.position.upper() != "GK"
            and ps.player.name != exclude
        ]
        if not eligible:
            return target
        return weighted_choice(
            self.rng,
            [(ps, 0.75 + 0.25 * ps.energy) for ps in eligible],
        )

    def _choose_decision(self, actor, zone, tactics, ctx):
        """A goalkeeper cannot shoot unless the explicit keeper-up state permits it."""
        decision = super()._choose_decision(actor, zone, tactics, ctx)
        if actor.player.position.upper() != "GK" or decision != "shoot":
            return decision
        team = self._team_for_player_state(actor)
        if team is not None and self._keeper_attack_mode(team, zone) == "keeper_up":
            return decision
        return "long_ball" if zone.band == Band.DEF else "safe_pass"

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
            "position_familiarity", "assigned_position", "natural_position",
            "penalty_gain", "incoming_penalty_quality", "outgoing_penalty_quality",
        ):
            if key in candidate:
                value = candidate[key]
                data[key] = float(value) if isinstance(value, (int, float)) else value
        return data


MatchEngine = MatchEngineV13RulesHardening

__all__ = ["MatchEngineV13RulesHardening", "MatchEngine", "VERSION"]
