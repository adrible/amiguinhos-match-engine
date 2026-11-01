from __future__ import annotations

"""v1.3 derived individual-role layer.

Roles are inferred from the player's existing position, attributes and team
instructions. They are not new ratings and never improve execution directly.
A sufficiently clear role profile only nudges decision and receiver preference,
so the same footballer can still choose differently when space, pressure,
score, fatigue or tactics demand it.
"""

from engine import Band, Lane, PlayerState, Zone, clamp
from engine_experiment_v13_injuries import MatchEngineV13Injuries

VERSION = "1.3-candidate-derived-roles"


class MatchEngineV13Roles(MatchEngineV13Injuries):
    @staticmethod
    def _role_attr(actor: PlayerState, name: str) -> float:
        """Raw 0..1 profile input: roles describe identity, not current execution."""
        return clamp(float(actor.player.attr(name)) / 100.0)

    def player_role_profile(self, actor: PlayerState) -> dict:
        pos = actor.player.position.upper()
        a = lambda name: self._role_attr(actor, name)
        team = self._team_for_player_state(actor)
        tactics = self.teams[team].team.tactics if team is not None else None
        width = 0.50 if tactics is None else clamp(float(tactics.width))
        directness = 0.45 if tactics is None else clamp(float(tactics.directness))
        pressing = 0.50 if tactics is None else clamp(float(tactics.pressing))
        overlap_left = 0.35 if tactics is None else clamp(float(tactics.overlap_left))
        overlap_right = 0.35 if tactics is None else clamp(float(tactics.overlap_right))

        if pos == "GK":
            scores = {
                "distributor_keeper": clamp(
                    0.30 * a("passing") + 0.24 * a("technique") + 0.18 * a("composure")
                    + 0.14 * a("vision") + 0.14 * a("anticipation")
                ),
                "shot_stopper": clamp(
                    0.27 * a("reflexes") + 0.22 * a("one_on_one") + 0.21 * a("gk_positioning")
                    + 0.18 * a("handling") + 0.12 * a("composure")
                ),
            }
        elif pos == "CB":
            scores = {
                "ball_playing_defender": clamp(
                    0.24 * a("passing") + 0.19 * a("vision") + 0.17 * a("technique")
                    + 0.16 * a("composure") + 0.14 * a("anticipation") + 0.10 * a("positioning")
                ),
                "stopper": clamp(
                    0.24 * a("tackling") + 0.20 * a("strength") + 0.16 * a("heading")
                    + 0.14 * a("aggression") + 0.14 * a("positioning") + 0.12 * a("anticipation")
                ),
                "cover_defender": clamp(
                    0.23 * a("pace") + 0.22 * a("anticipation") + 0.22 * a("positioning")
                    + 0.13 * a("discipline") + 0.10 * a("composure") + 0.10 * a("tackling")
                ),
            }
        elif pos in {"LB", "RB"}:
            overlap_instruction = overlap_left if pos == "LB" else overlap_right
            scores = {
                "overlapping_fullback": clamp(
                    0.18 * a("pace") + 0.17 * a("stamina") + 0.18 * a("crossing")
                    + 0.13 * a("off_ball") + 0.12 * a("dribbling") + 0.12 * a("technique")
                    + 0.10 * overlap_instruction
                ),
                "inverted_fullback": clamp(
                    0.22 * a("passing") + 0.20 * a("vision") + 0.17 * a("technique")
                    + 0.16 * a("positioning") + 0.13 * a("anticipation") + 0.07 * a("composure")
                    + 0.05 * (1.0 - width)
                ),
                "defensive_fullback": clamp(
                    0.24 * a("tackling") + 0.22 * a("positioning") + 0.16 * a("anticipation")
                    + 0.14 * a("discipline") + 0.12 * a("strength") + 0.07 * a("stamina")
                    + 0.05 * (1.0 - overlap_instruction)
                ),
            }
        elif pos in {"DM", "CM"}:
            scores = {
                "deep_playmaker": clamp(
                    0.28 * a("passing") + 0.24 * a("vision") + 0.18 * a("technique")
                    + 0.15 * a("composure") + 0.15 * a("anticipation")
                    + (0.025 if pos == "DM" else 0.0)
                ),
                "ball_winner": clamp(
                    0.27 * a("tackling") + 0.24 * a("positioning") + 0.18 * a("anticipation")
                    + 0.13 * a("strength") + 0.10 * a("stamina") + 0.08 * a("aggression")
                    + 0.025 * pressing
                ),
                "box_to_box": clamp(
                    0.18 * a("stamina") + 0.16 * a("pace") + 0.16 * a("off_ball")
                    + 0.14 * a("passing") + 0.12 * a("tackling") + 0.12 * a("dribbling")
                    + 0.12 * a("anticipation")
                ),
            }
        elif pos == "AM":
            scores = {
                "between_lines_creator": clamp(
                    0.28 * a("vision") + 0.23 * a("passing") + 0.20 * a("technique")
                    + 0.16 * a("composure") + 0.13 * a("anticipation")
                ),
                "shadow_runner": clamp(
                    0.25 * a("off_ball") + 0.22 * a("finishing") + 0.18 * a("dribbling")
                    + 0.16 * a("pace") + 0.12 * a("anticipation") + 0.07 * a("composure")
                ),
            }
        elif pos in {"LW", "RW"}:
            foot = str(actor.player.preferred_foot or "R").upper()
            inverted = 1.0 if (pos == "LW" and foot == "R") or (pos == "RW" and foot == "L") else 0.0
            scores = {
                "touchline_winger": clamp(
                    0.22 * a("crossing") + 0.19 * a("pace") + 0.18 * a("dribbling")
                    + 0.14 * a("technique") + 0.13 * a("off_ball") + 0.08 * a("vision")
                    + 0.06 * width
                ),
                "inside_forward": clamp(
                    0.23 * a("finishing") + 0.20 * a("dribbling") + 0.18 * a("technique")
                    + 0.15 * a("off_ball") + 0.12 * a("pace") + 0.07 * a("composure")
                    + 0.05 * inverted
                ),
                "wide_creator": clamp(
                    0.23 * a("vision") + 0.20 * a("passing") + 0.18 * a("crossing")
                    + 0.16 * a("technique") + 0.13 * a("composure") + 0.06 * a("dribbling")
                    + 0.04 * width
                ),
            }
        elif pos == "ST":
            scores = {
                "target_forward": clamp(
                    0.30 * a("strength") + 0.23 * a("heading") + 0.17 * a("composure")
                    + 0.12 * a("technique") + 0.10 * a("passing") + 0.08 * a("anticipation")
                    + 0.025 * directness
                ),
                "channel_runner": clamp(
                    0.29 * a("pace") + 0.28 * a("off_ball") + 0.17 * a("anticipation")
                    + 0.14 * a("composure") + 0.12 * a("dribbling")
                ),
                "poacher": clamp(
                    0.31 * a("finishing") + 0.22 * a("off_ball") + 0.17 * a("anticipation")
                    + 0.15 * a("composure") + 0.10 * a("pace") + 0.05 * a("technique")
                ),
            }
        else:
            scores = {"balanced_role": 0.50}

        ranked = sorted(scores.items(), key=lambda item: (-float(item[1]), item[0]))
        primary, primary_score = ranked[0]
        secondary, secondary_score = ranked[1] if len(ranked) > 1 else (None, 0.0)
        margin = max(0.0, float(primary_score) - float(secondary_score))
        clarity = clamp((float(primary_score) - 0.50) / 0.42)
        separation = clamp(0.48 + 3.0 * margin, 0.48, 1.0)
        conviction = clamp(clarity * separation)
        return {
            "position": pos,
            "primary": primary,
            "primary_score": round(float(primary_score), 6),
            "secondary": secondary,
            "secondary_score": round(float(secondary_score), 6),
            "margin": round(margin, 6),
            "conviction": round(conviction, 6),
            "scores": {name: round(float(value), 6) for name, value in scores.items()},
        }

    def role_diagnostic(self, actor: PlayerState) -> dict:
        """RNG-pure public role diagnostic."""
        return self.player_role_profile(actor)

    ROLE_ACTION_DELTAS = {
        "ball_playing_defender": {"safe_pass": 0.08, "progressive_pass": 0.11, "long_ball": 0.13, "carry": 0.02},
        "stopper": {"safe_pass": 0.08, "progressive_pass": -0.03, "carry": -0.08, "dribble": -0.10},
        "cover_defender": {"safe_pass": 0.07, "progressive_pass": 0.03, "carry": -0.03},
        "overlapping_fullback": {"carry": 0.07, "dribble": 0.05, "cross": 0.14, "progressive_pass": 0.05},
        "inverted_fullback": {"safe_pass": 0.08, "progressive_pass": 0.10, "switch": 0.07, "cross": -0.08},
        "defensive_fullback": {"safe_pass": 0.09, "long_ball": 0.04, "carry": -0.07, "cross": -0.05},
        "deep_playmaker": {"safe_pass": 0.08, "progressive_pass": 0.12, "switch": 0.14, "long_ball": 0.09, "carry": -0.05},
        "ball_winner": {"safe_pass": 0.05, "progressive_pass": -0.03, "carry": -0.05, "dribble": -0.08},
        "box_to_box": {"carry": 0.08, "progressive_pass": 0.07, "shoot": 0.04, "safe_pass": 0.02},
        "between_lines_creator": {"safe_pass": 0.04, "progressive_pass": 0.08, "through_ball": 0.13, "shoot": -0.03},
        "shadow_runner": {"carry": 0.05, "dribble": 0.06, "shoot": 0.11, "through_ball": -0.03},
        "touchline_winger": {"carry": 0.07, "dribble": 0.05, "cross": 0.15, "shoot": -0.04},
        "inside_forward": {"carry": 0.06, "dribble": 0.09, "shoot": 0.13, "cross": -0.12},
        "wide_creator": {"safe_pass": 0.03, "progressive_pass": 0.07, "through_ball": 0.11, "cross": 0.09},
        "target_forward": {"safe_pass": 0.08, "shoot": 0.06, "dribble": -0.08, "carry": -0.03},
        "channel_runner": {"carry": 0.06, "dribble": 0.05, "shoot": 0.08, "safe_pass": -0.03},
        "poacher": {"shoot": 0.12, "carry": -0.04, "dribble": -0.04, "through_ball": -0.05},
    }

    def _decision_weights(self, actor, zone, tactics, ctx):
        items = super()._decision_weights(actor, zone, tactics, ctx)
        profile = self.player_role_profile(actor)
        conviction = float(profile["conviction"])
        if conviction <= 0.0:
            return items
        deltas = self.ROLE_ACTION_DELTAS.get(str(profile["primary"]), {})
        out = []
        for action, weight in items:
            delta = float(deltas.get(action, 0.0))
            factor = clamp(1.0 + conviction * delta, 0.82, 1.18)
            out.append((action, max(0.001, float(weight) * factor)))
        return out

    def _base_target_weights(
        self,
        team: int,
        zone: Zone,
        actor: PlayerState | None,
        ctx: dict | None = None,
    ):
        weights = super()._base_target_weights(team, zone, actor, ctx)
        context = ctx or {}
        space_behind = clamp(float(context.get("space_behind", 0.45)))
        support = clamp(float(context.get("support", 0.50)))
        out = []
        for ps, weight in weights:
            profile = self.player_role_profile(ps)
            role = str(profile["primary"])
            conviction = float(profile["conviction"])
            bonus = 0.0
            if role == "target_forward" and zone.band in {Band.MID, Band.ATT}:
                bonus = 0.075 * conviction * (0.75 + 0.25 * support)
            elif role == "channel_runner" and zone.band in {Band.ATT, Band.BOX}:
                bonus = 0.10 * conviction * (0.55 + 0.75 * space_behind)
            elif role == "poacher" and zone.band == Band.BOX:
                bonus = 0.085 * conviction
            elif role == "between_lines_creator" and zone.band in {Band.MID, Band.ATT}:
                bonus = 0.060 * conviction
            elif role == "shadow_runner" and zone.band in {Band.ATT, Band.BOX}:
                bonus = 0.065 * conviction
            elif role == "deep_playmaker" and zone.band in {Band.DEF, Band.MID}:
                bonus = 0.055 * conviction
            elif role == "overlapping_fullback" and zone.band in {Band.MID, Band.ATT}:
                same_side = (zone.lane == Lane.LEFT and ps.player.position.upper() == "LB") or (
                    zone.lane == Lane.RIGHT and ps.player.position.upper() == "RB"
                )
                bonus = (0.070 if same_side else 0.025) * conviction
            elif role == "inside_forward" and zone.band in {Band.ATT, Band.BOX}:
                bonus = 0.060 * conviction
            elif role == "wide_creator" and zone.band in {Band.MID, Band.ATT}:
                bonus = 0.045 * conviction
            out.append((ps, float(weight) * clamp(1.0 + bonus, 0.90, 1.14)))
        return out


MatchEngine = MatchEngineV13Roles
