from __future__ import annotations

from typing import Optional

from engine import (
    Band,
    Lane,
    MatchConfig,
    MatchEngine,
    PlayerState,
    Team,
    Zone,
    clamp,
    weighted_choice,
)


class MatchEngineV12(MatchEngine):
    """Calibration candidate for v1.2.

    Two deliberately narrow changes are tested here before touching the canonical
    engine.py:

    1. Local technical quality affects spatial pressure/support a little more,
       so large player-quality gaps are not washed out by tactical context.
    2. Full-back involvement in midfield/final-third actions responds to the
       side-specific overlap instruction.

    The score, shot count and result remain fully emergent.
    """

    def _team_phase_quality(self, team: int, attacking: bool) -> float:
        players = [
            ps for ps in self.teams[team].on_field
            if ps.player.position.upper() != "GK"
        ]
        if not players:
            return 50.0

        if attacking:
            def score(ps: PlayerState) -> float:
                return (
                    0.27 * ps.effective("passing")
                    + 0.23 * ps.effective("technique")
                    + 0.20 * ps.effective("vision")
                    + 0.17 * ps.effective("off_ball")
                    + 0.13 * ps.effective("composure")
                )
        else:
            def score(ps: PlayerState) -> float:
                return (
                    0.31 * ps.effective("positioning")
                    + 0.25 * ps.effective("anticipation")
                    + 0.24 * ps.effective("tackling")
                    + 0.12 * ps.effective("pace")
                    + 0.08 * ps.effective("strength")
                )

        return sum(score(ps) for ps in players) / len(players)

    def _spatial_context(self, attacking_team: int, zone: Zone) -> dict:
        ctx = super()._spatial_context(attacking_team, zone)

        attack_quality = self._team_phase_quality(attacking_team, attacking=True)
        defend_quality = self._team_phase_quality(1 - attacking_team, attacking=False)
        # A 10-point local-quality gap changes pressure by ~0.06, enough to be
        # meaningful without turning OVR into a deterministic result switch.
        gap = clamp((defend_quality - attack_quality) / 100.0, -0.18, 0.18)

        zone_factor = {
            Band.DEF: 0.75,
            Band.MID: 0.95,
            Band.ATT: 1.00,
            Band.BOX: 0.85,
        }[zone.band]

        ctx["pressure"] = clamp(ctx["pressure"] + 0.62 * gap * zone_factor)
        ctx["space"] = clamp(ctx["space"] - 0.42 * gap * zone_factor)
        ctx["support"] = clamp(ctx["support"] - 0.28 * gap * zone_factor)
        # High-quality attacks against weaker defensive units are also slightly
        # better at exploiting the space behind an aggressive line.
        ctx["space_behind"] = clamp(
            ctx["space_behind"] - 0.18 * gap * zone_factor
        )
        ctx["quality_gap"] = gap
        return ctx

    @staticmethod
    def _fullback_overlap_factor(position: str, zone: Zone, tactics, target: bool = False) -> float:
        pos = position.upper()
        if pos not in {"LB", "RB"}:
            return 1.0
        overlap = tactics.overlap_left if pos == "LB" else tactics.overlap_right
        if zone.band == Band.DEF:
            return 1.0
        if zone.band == Band.MID:
            # Mild influence while progressing.
            return clamp(0.72 + 0.70 * overlap, 0.72, 1.35)
        if zone.band == Band.ATT:
            # Stronger influence in the attacking third, where an overlap
            # instruction should actually change who appears in the move.
            return clamp(0.50 + 1.18 * overlap, 0.55, 1.45)
        # Full-backs should still be uncommon inside the box.
        return clamp(0.72 + 0.55 * overlap, 0.72, 1.25)

    def _choose_actor(self, team: int, zone: Zone) -> PlayerState:
        rt = self.teams[team]
        tactics = rt.team.tactics
        weights = []
        for ps in rt.on_field:
            pos = ps.player.position.upper()
            if pos == "GK":
                w = 0.03 if zone.band != Band.DEF else 0.12
            elif zone.band == Band.DEF:
                w = {"CB": 1.4, "LB": 1.1, "RB": 1.1, "DM": 1.0, "CM": 0.55, "AM": 0.25, "LW": 0.20, "RW": 0.20, "ST": 0.12}.get(pos, 0.35)
            elif zone.band == Band.MID:
                w = {"DM": 1.2, "CM": 1.5, "AM": 1.15, "LB": 0.65, "RB": 0.65, "LW": 0.85, "RW": 0.85, "ST": 0.45, "CB": 0.35}.get(pos, 0.5)
            elif zone.band == Band.ATT:
                w = {"AM": 1.35, "LW": 1.25, "RW": 1.25, "ST": 1.15, "CM": 0.75, "LB": 0.35, "RB": 0.35, "DM": 0.30, "CB": 0.10}.get(pos, 0.5)
            else:
                w = {"ST": 1.65, "LW": 1.05, "RW": 1.05, "AM": 1.15, "CM": 0.45, "LB": 0.16, "RB": 0.16, "DM": 0.12, "CB": 0.09}.get(pos, 0.4)

            if zone.lane == Lane.LEFT and pos in ("LB", "LW"):
                w *= 1.45
            if zone.lane == Lane.RIGHT and pos in ("RB", "RW"):
                w *= 1.45
            if zone.lane == Lane.CENTER and pos in ("CB", "DM", "CM", "AM", "ST"):
                w *= 1.25

            w *= self._fullback_overlap_factor(pos, zone, tactics)
            w *= 0.75 + 0.25 * ps.energy
            weights.append((ps, w))
        return weighted_choice(self.rng, weights)

    def _choose_target(self, team, zone, attacking=True, exclude=None) -> PlayerState:
        rt = self.teams[team]
        tactics = rt.team.tactics
        weights = []
        for ps in rt.on_field:
            if ps.player.name == exclude:
                continue
            pos = ps.player.position.upper()
            if attacking:
                w = {"ST": 1.55, "AM": 1.35, "LW": 1.25, "RW": 1.25, "CM": 0.75, "LB": 0.42, "RB": 0.42, "DM": 0.35, "CB": 0.12, "GK": 0.01}.get(pos, 0.5)
                w *= 0.70 + 0.30 * ps.effective("off_ball") / 100.0
                w *= self._fullback_overlap_factor(pos, zone, tactics, target=True)
            else:
                w = {"CB": 1.1, "LB": 0.95, "RB": 0.95, "DM": 1.2, "CM": 1.1, "AM": 0.65, "LW": 0.55, "RW": 0.55, "ST": 0.35, "GK": 0.20}.get(pos, 0.6)
                w *= 0.75 + 0.25 * ps.effective("positioning") / 100.0

            if zone.lane == Lane.LEFT and pos in ("LB", "LW"):
                w *= 1.25
            if zone.lane == Lane.RIGHT and pos in ("RB", "RW"):
                w *= 1.25
            weights.append((ps, w))
        return weighted_choice(self.rng, weights)


def simulate_full_match_v12(
    home: Team,
    away: Team,
    seed: Optional[int] = None,
    config: Optional[MatchConfig] = None,
) -> MatchEngineV12:
    engine = MatchEngineV12(home, away, seed=seed, config=config)
    guard = 0
    while not engine.state.ended and guard < 5000:
        engine.step()
        guard += 1
    if guard >= 5000:
        raise RuntimeError("Simulation guard reached.")
    return engine
