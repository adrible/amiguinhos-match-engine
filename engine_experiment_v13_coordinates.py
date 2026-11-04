"""Persistent player XY, ball XYZ and geometric situation reading.

The fixed world frame is 105 x 68 metres. Team 0 attacks towards +x in the
first half; team 1 attacks towards -x. Both axes rotate at a change of ends.
This is a spatial layer for the event engine, not a frame-by-frame ball solver.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from math import exp, hypot, isfinite, sqrt
from copy import deepcopy

from engine import Band, Lane, PlayerState, clamp
from engine_experiment_v13_rules_hardening import MatchEngineV13RulesHardening

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
COORDINATE_SCHEMA = 1
GRAVITY = 9.81


@dataclass
class PitchPlayerState(PlayerState):
    x: float | None = None
    y: float | None = None


class MatchEngineV13Coordinates(MatchEngineV13RulesHardening):
    """Keep individual locations in match state and consume them in decisions."""

    def __init__(self, *args, **kwargs):
        self._xy_ready = False
        super().__init__(*args, **kwargs)
        self._xy_ball = {"x": 52.5, "y": 34.0, "z": 0.0, "owner": None}
        self._xyz_flight = None
        self._xy_source = "simulated"
        self._initialise_coordinates(kickoff=True)
        self._xy_ready = True

    @staticmethod
    def _point(x, y):
        if isinstance(x, bool) or isinstance(y, bool):
            raise ValueError("Coordinates must be finite metres, not booleans")
        x, y = float(x), float(y)
        if not (isfinite(x) and isfinite(y) and 0 <= x <= PITCH_LENGTH and 0 <= y <= PITCH_WIDTH):
            raise ValueError("Coordinates must lie within x=0..105 and y=0..68 metres")
        return x, y

    @staticmethod
    def _team(team):
        if isinstance(team, bool) or team not in (0, 1):
            raise ValueError("team must be 0 or 1")
        return int(team)

    @staticmethod
    def _height(z):
        if isinstance(z, bool):
            raise ValueError("Ball height must be finite non-negative metres")
        z = float(z)
        if not isfinite(z) or z < 0:
            raise ValueError("Ball height must be finite non-negative metres")
        return z

    @classmethod
    def _ball_point(cls, x, y, z=0.):
        # A ball may cross a touchline/goal line. Player bounds are different.
        if isinstance(x, bool) or isinstance(y, bool):
            raise ValueError("Ball coordinates must be finite metres")
        x, y = float(x), float(y)
        if not (isfinite(x) and isfinite(y)):
            raise ValueError("Ball coordinates must be finite metres")
        return x, y, cls._height(z)

    def launch_ball(self, x, y, *, z=0., speed=18., aerial=False, receiver=None, kind="pass"):
        """Declare a ball flight/roll, then advance it with the match clock.

        Gravity applies to aerial flights; ground rolls keep z=0. Horizontal
        velocity is constant in this first stage. No spin, drag or bounce solver
        is claimed. Receiving height and speed define the vertical launch speed.
        """
        x, y, z = self._ball_point(x, y, z)
        speed = float(speed)
        if not isfinite(speed) or speed <= 0:
            raise ValueError("Ball speed must be finite and positive")
        if receiver is not None:
            self.teams[self._team(receiver["team"])].by_name(receiver["player"])
        start = {k: self._xy_ball[k] for k in ("x", "y", "z")}
        duration = max(.25, hypot(x - start["x"], y - start["y"]) / speed)
        aerial = bool(aerial or z > 0 or start["z"] > 0)
        vz = (z - start["z"]) / duration + .5 * GRAVITY * duration if aerial else 0.
        if not (isfinite(duration) and isfinite(vz)):
            raise ValueError("Ball trajectory exceeds finite physical bounds")
        self._xyz_flight = {
            "start_second": self.state.second, "duration": duration,
            "start": start, "target": {"x": x, "y": y, "z": z},
            "aerial": aerial, "vertical_velocity": vz,
            "receiver": deepcopy(receiver), "kind": kind,
        }
        self._xy_ball["owner"] = None
        return deepcopy(self._xyz_flight)

    def ball_position_at(self, second=None):
        """RNG-pure sample of the declared trajectory, in world metres."""
        if second is None:
            second = self.state.second
        second = float(second)
        if not isfinite(second):
            raise ValueError("Sample time must be finite")
        flight = self._xyz_flight
        if flight is None:
            return {k: self._xy_ball[k] for k in ("x", "y", "z")}
        elapsed = clamp(second - flight["start_second"], 0., flight["duration"])
        t = elapsed / flight["duration"]
        start, end = flight["start"], flight["target"]
        z = (start["z"] + flight["vertical_velocity"] * elapsed
             - .5 * GRAVITY * elapsed * elapsed) if flight["aerial"] else 0.
        if t >= 1.:
            z = end["z"]
        return {"x": start["x"] + (end["x"] - start["x"]) * t,
                "y": start["y"] + (end["y"] - start["y"]) * t,
                "z": max(0., z)}

    def _advance_ball(self):
        flight = self._xyz_flight
        if flight is None:
            return
        self._xy_ball.update(self.ball_position_at())
        if self.state.second >= flight["start_second"] + flight["duration"]:
            receiver = flight["receiver"]
            self._xyz_flight = None
            if receiver is not None:
                try:
                    ps = self.teams[receiver["team"]].by_name(receiver["player"])
                    if hypot(ps.x - self._xy_ball["x"], ps.y - self._xy_ball["y"]) <= 2.:
                        self._xy_ball["owner"] = deepcopy(receiver)
                except KeyError:
                    pass

    def attack_direction(self, team):
        team = self._team(team)
        # period_index reaches 2 at full time: do not spuriously switch ends.
        half = min(int(self.state.period_index), 1)
        return (1 if team == 0 else -1) * (-1 if half else 1)

    def _to_world(self, team, x, y):
        return (x, y) if self.attack_direction(team) == 1 else (105.0 - x, 68.0 - y)

    def _to_team(self, team, x, y):
        return self._to_world(team, x, y)

    def _formation_anchors(self, team):
        rt = self.teams[team]
        try:
            rows = [int(p) for p in rt.team.tactics.formation.split("-")]
        except (ValueError, AttributeError):
            rows = []
        if len(rows) < 2 or any(p <= 0 for p in rows) or sum(rows) != 10:
            rows = [4, 2, 3, 1]
        depth = {"GK": 0, "CB": 1, "LB": 2, "RB": 2, "DM": 3,
                 "CM": 4, "AM": 5, "LW": 6, "RW": 6, "ST": 7}
        lateral = {"LB": -1, "LW": -1, "RB": 1, "RW": 1}
        # Stable roster order breaks ties. Names never alter physical quality.
        keeper = self._goalkeeper(team) if rt.on_field else None
        outfield = sorted([p for p in rt.on_field if p is not keeper],
                          key=lambda p: depth.get(p.player.position, 4))
        result = {}
        cursor = 0
        for i, count in enumerate(rows):
            line = sorted(outfield[cursor:cursor + count],
                          key=lambda p: lateral.get(p.player.position, 0))
            cursor += count
            for j, ps in enumerate(line):
                x = 24.0 + 58.0 * i / (len(rows) - 1)
                y = 68.0 * (j + 1) / (len(line) + 1)
                result[ps.player.name] = (x, y)
        if keeper is not None:
            result[keeper.player.name] = (5.5, 34.0)
        return result

    @staticmethod
    def _as_pitch_state(ps):
        if isinstance(ps, PitchPlayerState):
            return ps
        return PitchPlayerState(**{f.name: getattr(ps, f.name) for f in fields(PlayerState)})

    def _initialise_coordinates(self, *, kickoff=False):
        for team, rt in enumerate(self.teams):
            rt.on_field = [self._as_pitch_state(ps) for ps in rt.on_field]
            anchors = self._formation_anchors(team)
            for ps in rt.on_field:
                if ps.x is None or ps.y is None:
                    x, y = anchors[ps.player.name]
                    if kickoff and ps.player.position != "GK":
                        x *= .60
                    ps.x, ps.y = self._to_world(team, x, y)
                self._point(ps.x, ps.y)

    def player_coordinates(self, team, player):
        ps = self.teams[self._team(team)].by_name(player)
        return {"x": ps.x, "y": ps.y}

    def pitch_snapshot(self):
        """A detached, RNG-pure current frame; only active players have a point."""
        return {
            "schema": COORDINATE_SCHEMA, "units": "metres", "frame": "fixed_world",
            "length": 105.0, "width": 68.0, "second": self.state.second,
            "source": self._xy_source,
            "attack_directions": [self.attack_direction(0), self.attack_direction(1)],
            "ball": deepcopy(self._xy_ball),
            "ball_flight": deepcopy(self._xyz_flight),
            "players": [
                {"team": team, "player": ps.player.name, "role": ps.player.position,
                 "x": ps.x, "y": ps.y}
                for team, rt in enumerate(self.teams) for ps in rt.on_field if not ps.red
            ],
        }

    def set_tracking_frame(self, players, *, ball=None, require_all=True):
        """Atomically read a world-coordinate frame from an external caller.

        By default every active player must occur once. A partial frame can be
        explicitly requested for manual interventions. No RNG is consumed.
        """
        pending = {}
        for row in players:
            team = self._team(row["team"])
            name = row["player"]
            ps = self.teams[team].by_name(name)
            if ps.red or (team, name) in pending:
                raise ValueError("Duplicate or inactive player in tracking frame")
            pending[team, name] = (ps, self._point(row["x"], row["y"]))
        active = {(t, ps.player.name) for t, rt in enumerate(self.teams)
                  for ps in rt.on_field if not ps.red}
        if require_all and set(pending) != active:
            raise ValueError("A complete tracking frame must contain every active player")
        new_ball = deepcopy(self._xy_ball)
        if ball is not None:
            x, y, z = self._ball_point(ball["x"], ball["y"], ball.get("z", 0.))
            owner = deepcopy(ball.get("owner"))
            if owner is not None:
                key = (self._team(owner["team"]), owner["player"])
                if key not in active:
                    raise ValueError("Ball owner must be an active player")
            new_ball = {"x": x, "y": y, "z": z, "owner": owner}
        for ps, (x, y) in pending.values():
            ps.x, ps.y = x, y
        self._xy_ball = new_ball
        if ball is not None:
            self._xyz_flight = None
        self._xy_source = "external"

    def set_player_coordinates(self, team, player, x, y):
        self.set_tracking_frame([{"team": team, "player": player, "x": x, "y": y}],
                                require_all=False)

    @staticmethod
    def _segment_distance(point, start, end):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length2 = dx * dx + dy * dy
        if length2 == 0:
            return hypot(point[0] - start[0], point[1] - start[1])
        t = clamp(((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length2)
        return hypot(point[0] - start[0] - t * dx, point[1] - start[1] - t * dy)

    def spatial_reading(self, team, player=None, *, include_passes=True):
        """Read real distances, nearby support and pass corridors without RNG."""
        team = self._team(team)
        if player is None:
            origin = (self._xy_ball["x"], self._xy_ball["y"])
            owner = self._xy_ball.get("owner")
            if owner is not None and owner["team"] == team:
                player = owner["player"]
        else:
            ps = self.teams[team].by_name(player)
            origin = (ps.x, ps.y)
        opponents = [p for p in self.teams[1 - team].on_field if not p.red]
        distances = [hypot(p.x - origin[0], p.y - origin[1]) for p in opponents]
        support = [p for p in self.teams[team].on_field
                   if not p.red and p.player.name != player
                   and hypot(p.x - origin[0], p.y - origin[1]) <= 15.0]
        passes = []
        for ps in self.teams[team].on_field if include_passes else ():
            if ps.red or ps.player.name == player:
                continue
            end = (ps.x, ps.y)
            clearance = min((self._segment_distance((p.x, p.y), origin, end)
                             for p in opponents), default=68.0)
            passes.append({"player": ps.player.name,
                           "distance": hypot(end[0] - origin[0], end[1] - origin[1]),
                           "opponent_clearance": clearance})
        return {"origin": {"x": origin[0], "y": origin[1]},
                "ball_height": self._xy_ball["z"],
                "nearest_opponent_distance": min(distances, default=105.0),
                "local_pressure": 1.0 - exp(-sum(exp(-d / 7.0) for d in distances)),
                "nearby_support": len(support), "passes": passes}

    def _spatial_context(self, team, zone):
        ctx = super()._spatial_context(team, zone)
        if not getattr(self, "_xy_ready", False):
            return ctx
        reading = self.spatial_reading(team, include_passes=False)
        # Blend football geometry into the pre-venue situation, then retain the
        # previously accepted venue contribution at its original strength.
        venue = self._venue_effects(team)
        pressure_shift, support_shift, space_shift = (
            venue["pressure_shift"], venue["support_shift"], venue["space_shift"])
        ctx["pressure"] = clamp(.75 * (ctx["pressure"] - pressure_shift)
                                + .25 * reading["local_pressure"] + pressure_shift)
        ctx["support"] = clamp(.85 * (ctx["support"] - support_shift)
                               + .15 * min(1., reading["nearby_support"] / 3.) + support_shift)
        ctx["space"] = clamp(.8 * (ctx["space"] - space_shift)
                             + .2 * min(1., reading["nearest_opponent_distance"] / 15.) + space_shift)
        ctx["nearest_opponent_metres"] = reading["nearest_opponent_distance"]
        ctx["ball_height_metres"] = reading["ball_height"]
        ctx["aerial_ball"] = reading["ball_height"] > .5
        return ctx

    def _base_target_weights(self, team, zone, actor, ctx=None):
        rows = super()._base_target_weights(team, zone, actor, ctx)
        if not getattr(self, "_xy_ready", False) or actor is None:
            return rows
        passing = {r["player"]: r for r in self.spatial_reading(team, actor.player.name)["passes"]}
        height = self._xy_ball["z"]
        return [(ps, weight * (.65 + .35 * min(1., passing[ps.player.name]["opponent_clearance"] / 5.))
                 / (1. + passing[ps.player.name]["distance"] / 90.)
                 * (.65 + .35 * ps.effective("heading") / 100. if height > 1.5 else 1.))
                for ps, weight in rows]

    def _defender_engagement_weight(self, ps, zone):
        weight = super()._defender_engagement_weight(ps, zone)
        if not getattr(self, "_xy_ready", False):
            return weight
        d = hypot(ps.x - self._xy_ball["x"], ps.y - self._xy_ball["y"])
        return weight * (.35 + .65 * exp(-d / 16.0))

    def _move_players(self, seconds):
        if seconds <= 0:
            return
        for team, rt in enumerate(self.teams):
            anchors = self._formation_anchors(team)
            keeper = self._goalkeeper(team) if rt.on_field else None
            bx, by = self._to_team(team, self._xy_ball["x"], self._xy_ball["y"])
            tactics = rt.team.tactics
            for ps in rt.on_field:
                ax, ay = anchors[ps.player.name]
                if ps is keeper:
                    ax = 5.5 + max(0., bx - 52.5) * .10
                    if getattr(self, "_v13_keeper_up_team", None) == team:
                        ax = 86.
                    ay = 34. + (by - 34.) * .12
                else:
                    possession_shift = 6. if self.state.possession == team else -5.
                    ax += possession_shift + (bx - 52.5) * .18 + tactics.mentality * 5.
                    if ps.player.position in {"CB", "LB", "RB"}:
                        ax += (tactics.defensive_line - .5) * 16.
                    ay = 34. + (ay - 34.) * (.7 + .6 * tactics.width)
                    ay += (by - 34.) * .16 * tactics.compactness
                tx, ty = self._to_world(team, clamp(ax, 1., 104.), clamp(ay, 1., 67.))
                dx, dy = tx - ps.x, ty - ps.y
                distance = hypot(dx, dy)
                speed = (3.0 + .05 * ps.effective("pace")) * (.6 + .4 * ps.energy)
                fraction = min(1., speed * seconds / distance) if distance else 0.
                ps.x += dx * fraction
                ps.y += dy * fraction
        owner = self._xy_ball["owner"]
        if owner is not None and self._xyz_flight is None:
            try:
                ps = self.teams[owner["team"]].by_name(owner["player"])
                self._xy_ball.update(x=ps.x, y=ps.y)
            except KeyError:
                self._xy_ball["owner"] = None
        self._xy_source = "simulated"

    def _advance_clock(self, seconds, possession_team):
        if getattr(self, "_xy_ready", False):
            # A supplied airborne point with no velocity/owner cannot hover.
            # With no observed velocity, assume an initial vertical velocity 0.
            if self._xyz_flight is None and self._xy_ball["z"] > 0 and self._xy_ball["owner"] is None:
                start = {k: self._xy_ball[k] for k in ("x", "y", "z")}
                self._xyz_flight = {
                    "start_second": self.state.second,
                    "duration": sqrt(2. * start["z"] / GRAVITY),
                    "start": start, "target": {**start, "z": 0.},
                    "aerial": True, "vertical_velocity": 0.,
                    "receiver": None, "kind": "free_fall",
                }
            self._move_players(max(0., float(seconds)))
        result = super()._advance_clock(seconds, possession_team)
        if getattr(self, "_xy_ready", False):
            self._advance_ball()
        return result

    def _reset_kickoff_coordinates(self):
        for rt in self.teams:
            for ps in rt.on_field:
                ps.x = ps.y = None
        self._initialise_coordinates(kickoff=True)
        self._xy_ball = {"x": 52.5, "y": 34., "z": 0., "owner": None}
        self._xyz_flight = None

    def _check_period_boundary(self):
        direction = self.attack_direction(0)
        event = super()._check_period_boundary()
        if self.attack_direction(0) != direction:
            self._reset_kickoff_coordinates()
        return event

    def start_extra_time(self):
        super().start_extra_time()
        self._reset_kickoff_coordinates()

    def substitute(self, team, out_name, in_name):
        outgoing = self.teams[self._team(team)].by_name(out_name)
        point = (outgoing.x, outgoing.y)
        event = super().substitute(team, out_name, in_name)
        rt = self.teams[team]
        rt.on_field = [self._as_pitch_state(ps) for ps in rt.on_field]
        incoming = rt.by_name(in_name)
        incoming.x, incoming.y = point
        if self._xy_ball["owner"] == {"team": team, "player": out_name}:
            self._xy_ball["owner"] = None
        if self._xyz_flight is not None and self._xyz_flight.get("receiver") == {"team": team, "player": out_name}:
            self._xyz_flight["receiver"] = None
        event.data["ball_coordinates"] = deepcopy(self._xy_ball)
        return event

    def _emit(self, typ, team, relevance, text_key, **data):
        event = super()._emit(typ, team, relevance, text_key, **data)
        if not getattr(self, "_xy_ready", False):
            return event
        kind = event.type.value
        if kind == "goal" and not data.get("shootout"):
            self._reset_kickoff_coordinates()
        elif kind in {"corner", "free_kick", "penalty", "offside", "miss", "post", "block"}:
            self._xy_ball["owner"] = None
            self._xy_ball["z"] = 0.
            self._xyz_flight = None
            restart = self.state.restart
            restart_team = self.state.restart_team
            if restart and restart_team in (0, 1):
                zone = self.state.restart_zone or self.state.zone
                x = {Band.DEF: 18., Band.MID: 52.5, Band.ATT: 80., Band.BOX: 94.}[zone.band]
                y = {Lane.LEFT: 12., Lane.CENTER: 34., Lane.RIGHT: 56.}[zone.lane]
                if restart == "corner":
                    x, y = 105., 0. if zone.lane == Lane.LEFT else 68.
                elif restart == "penalty":
                    x, y = 94., 34.
                self._xy_ball["x"], self._xy_ball["y"] = self._to_world(restart_team, x, y)
        elif kind in {"progression", "danger", "turnover", "save", "rebound"} or text_key == "safe_pass" or text_key.startswith("kickoff_"):
            pending = self.state.pending
            owner_team = int(self.state.possession)
            name = None
            if pending is not None and kind == "danger":
                owner_team, name = pending.team, pending.actor
            elif kind == "save":
                owner_team, name = 1 - team, data.get("keeper")
            elif kind != "turnover":
                name = data.get("target") or data.get("receiver") or data.get("next_player") or data.get("actor")
            else:
                name = data.get("winner") or data.get("defender")
            if isinstance(name, str):
                try:
                    ps = self.teams[owner_team].by_name(name)
                    if ps.x is not None:
                        self._xy_ball = {"x": ps.x, "y": ps.y, "z": 0.,
                                         "owner": {"team": owner_team, "player": name}}
                except KeyError:
                    self._xy_ball["owner"] = None
            else:
                self._xy_ball["owner"] = None
            self._xyz_flight = None
            # A pending aerial delivery remains a live flight until the next
            # beat; completed ground circulation is already at its receiver.
            if kind == "danger" and self.state.pending is not None:
                pending = self.state.pending
                delivery = data.get("kind") or pending.origin
                if delivery in {"cross", "long_ball", "corner"}:
                    actor_name = data.get("creator") or data.get("actor") or data.get("crosser")
                    try:
                        actor = self.teams[pending.team].by_name(actor_name)
                        receiver = self.teams[pending.team].by_name(pending.actor)
                        self._xy_ball = {"x": actor.x, "y": actor.y, "z": 0., "owner": None}
                        self.launch_ball(receiver.x, receiver.y, z=1.6 if pending.body_part == "head" else 0.,
                                         speed=18., aerial=True,
                                         receiver={"team": pending.team, "player": pending.actor}, kind=delivery)
                    except KeyError:
                        pass
        event.data["ball_coordinates"] = deepcopy(self._xy_ball)
        return event

    def _resolve_shot(self, pending):
        try:
            shooter = self.teams[pending.team].by_name(pending.actor)
            origin = {"x": shooter.x, "y": shooter.y, "z": self._xy_ball["z"]}
        except KeyError:
            origin = {k: self._xy_ball[k] for k in ("x", "y", "z")}
        event = super()._resolve_shot(pending)
        event.data["shot_origin_coordinates"] = origin
        # Existing shot physics already resolves horizontal goal-mouth position
        # and height. Map those facts to the same world XYZ frame as the ball.
        actual = event.data.get("actual_goal_position")
        if isinstance(actual, dict):
            x, y = self._to_world(pending.team, 105., 34. + float(actual["x"]))
            point = {"x": x, "y": y, "z": max(0., float(actual["z"]))}
            event.data["shot_ball_coordinates"] = point
            # Goals reset to the centre; keeper-held saves restart on the ground.
            # Other resolved shots retain their actual terminal height in state.
            if event.type.value not in {"goal", "save"} and not self.state.restart:
                self._xy_ball = {**point, "owner": None}
                self._xyz_flight = None
        event.data["ball_coordinates"] = deepcopy(self._xy_ball)
        return event

    def step(self):
        event = super().step()
        owner = self._xy_ball["owner"]
        if owner is not None and not any(ps.player.name == owner["player"]
                                        for ps in self.teams[owner["team"]].on_field):
            self._xy_ball["owner"] = None
        if self._xyz_flight is not None:
            receiver = self._xyz_flight.get("receiver")
            if receiver is not None and not any(
                p.player.name == receiver["player"] for p in self.teams[receiver["team"]].on_field
            ):
                self._xyz_flight["receiver"] = None
        # A returned event carries a compact point, while snapshots carry all players.
        event.data["ball_coordinates"] = deepcopy(self._xy_ball)
        return event

    def snapshot(self):
        data = super().snapshot()
        if getattr(self, "_xy_ready", False):
            data["pitch"] = self.pitch_snapshot()
        return data

    @classmethod
    def _player_state_to_dict(cls, ps):
        data = super()._player_state_to_dict(ps)
        data.update(x=getattr(ps, "x", None), y=getattr(ps, "y", None))
        return data

    @classmethod
    def _player_state_from_dict(cls, data):
        ps = cls._as_pitch_state(super()._player_state_from_dict(data))
        x, y = data.get("x"), data.get("y")
        if (x is None) != (y is None):
            raise ValueError("Player coordinates must contain both x and y")
        if x is not None:
            ps.x, ps.y = cls._point(x, y)
        return ps

    def export_state(self):
        data = super().export_state()
        data["v13_coordinates"] = {"schema": COORDINATE_SCHEMA,
                                   "ball": deepcopy(self._xy_ball), "source": self._xy_source,
                                   "flight": deepcopy(self._xyz_flight)}
        return data

    @classmethod
    def from_state_dict(cls, data):
        obj = super().from_state_dict(data)
        obj._xy_ready = False
        raw = data.get("v13_coordinates")
        if raw is not None and raw.get("schema") != COORDINATE_SCHEMA:
            raise ValueError("Unsupported coordinate schema")
        obj._xy_source = raw.get("source", "simulated") if raw else "legacy_migration"
        obj._xy_ball = deepcopy(raw["ball"]) if raw else {"x": 52.5, "y": 34., "z": 0., "owner": None}
        obj._xy_ball["z"] = obj._height(obj._xy_ball.get("z", 0.))
        obj._xyz_flight = deepcopy(raw.get("flight")) if raw else None
        obj._ball_point(obj._xy_ball["x"], obj._xy_ball["y"], obj._xy_ball["z"])
        if obj._xyz_flight is not None:
            flight = obj._xyz_flight
            duration = float(flight["duration"])
            start_second = float(flight["start_second"])
            vz = float(flight["vertical_velocity"])
            if (not all(isfinite(v) for v in (duration, start_second, vz))
                    or duration <= 0 or start_second < 0 or start_second > obj.state.second):
                raise ValueError("Invalid saved ball trajectory")
            for point in (flight["start"], flight["target"]):
                obj._ball_point(point["x"], point["y"], point["z"])
            receiver = flight.get("receiver")
            if receiver is not None:
                obj.teams[obj._team(receiver["team"])].by_name(receiver["player"])
        obj._initialise_coordinates(kickoff=raw is None)
        owner = obj._xy_ball.get("owner")
        if owner is not None:
            obj.teams[obj._team(owner["team"])].by_name(owner["player"])
        obj._xy_ready = True
        return obj


MatchEngine = MatchEngineV13Coordinates
