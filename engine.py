from __future__ import annotations

from dataclasses import dataclass, field, replace, asdict, fields
from enum import Enum
from collections import Counter
from typing import Optional, Iterable
import math
import random
import json
import ast


# ----------------------------- helpers ---------------------------------

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))

def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))

def weighted_choice(rng: random.Random, items):
    """items: iterable[(value, weight)]"""
    items = [(v, max(0.0, w)) for v, w in items]
    total = sum(w for _, w in items)
    if total <= 0:
        return items[0][0]
    r = rng.random() * total
    acc = 0.0
    for value, weight in items:
        acc += weight
        if r <= acc:
            return value
    return items[-1][0]


class Lane(str, Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class Band(str, Enum):
    DEF = "defensive_third"
    MID = "middle_third"
    ATT = "final_third"
    BOX = "box"


@dataclass(frozen=True)
class Zone:
    band: Band
    lane: Lane

    def mirror(self) -> "Zone":
        # Ball changes perspective when possession changes.
        order = {
            Band.DEF: Band.ATT,
            Band.MID: Band.MID,
            Band.ATT: Band.DEF,
            Band.BOX: Band.DEF,
        }
        lane = {Lane.LEFT: Lane.RIGHT, Lane.CENTER: Lane.CENTER, Lane.RIGHT: Lane.LEFT}[self.lane]
        return Zone(order[self.band], lane)


DEF_C = Zone(Band.DEF, Lane.CENTER)
MID_C = Zone(Band.MID, Lane.CENTER)


class EventType(str, Enum):
    INFO = "info"
    PROGRESSION = "progression"
    DANGER = "danger"
    TURNOVER = "turnover"
    FOUL = "foul"
    CARD = "card"
    OFFSIDE = "offside"
    SHOT = "shot"
    GOAL = "goal"
    SAVE = "save"
    BLOCK = "block"
    MISS = "miss"
    POST = "post"
    CORNER = "corner"
    FREE_KICK = "free_kick"
    PENALTY = "penalty"
    REBOUND = "rebound"
    SUBSTITUTION = "substitution"
    INJURY = "injury"
    PERIOD_END = "period_end"
    MATCH_END = "match_end"


@dataclass
class Event:
    minute: float
    team: int
    type: EventType
    relevance: int
    text_key: str
    data: dict = field(default_factory=dict)


# ----------------------------- data model ---------------------------------

@dataclass
class Player:
    name: str
    position: str
    overall: int = 75

    pace: int = 75
    passing: int = 75
    vision: int = 75
    technique: int = 75
    dribbling: int = 75
    crossing: int = 75
    finishing: int = 75
    long_shots: int = 75
    heading: int = 75

    strength: int = 75
    tackling: int = 75
    positioning: int = 75
    anticipation: int = 75
    composure: int = 75
    off_ball: int = 75

    stamina: int = 75
    aggression: int = 60
    discipline: int = 70

    reflexes: int = 40
    handling: int = 40
    gk_positioning: int = 40
    one_on_one: int = 40

    preferred_foot: str = "R"
    # Optional v1.3 attributes; old rosters use explicit derived fallbacks.
    gk_reach: Optional[int] = None
    gk_jump: Optional[int] = None
    gk_agility: Optional[int] = None
    balance: Optional[int] = None
    weak_foot: Optional[int] = None

    def attr(self, name: str) -> int:
        return int(getattr(self, name))


@dataclass
class PlayerState:
    player: Player
    energy: float = 1.0
    yellow: int = 0
    red: bool = False
    injured: bool = False
    minutes: float = 0.0

    def effective(self, attr: str) -> float:
        raw = float(self.player.attr(attr))
        # Fatigue is mild at first, then increasingly meaningful.
        if self.energy >= 0.65:
            factor = 0.96 + 0.04 * ((self.energy - 0.65) / 0.35)
        else:
            factor = 0.78 + 0.18 * (self.energy / 0.65)
        if self.yellow and attr in ("tackling", "aggression"):
            factor *= 0.94
        if self.injured:
            factor *= 0.76
        return raw * factor


@dataclass
class Tactics:
    formation: str = "4-2-3-1"
    mentality: float = 0.0
    tempo: float = 0.50
    width: float = 0.50
    pressing: float = 0.50
    defensive_line: float = 0.50
    compactness: float = 0.55
    directness: float = 0.45
    counter: float = 0.55
    overlap_left: float = 0.35
    overlap_right: float = 0.35
    cross_frequency: float = 0.45
    risk: float = 0.50

    def normalized(self) -> "Tactics":
        d = self.__dict__.copy()
        for k, v in d.items():
            if isinstance(v, float):
                d[k] = clamp(v, -1.0 if k == "mentality" else 0.0, 1.0)
        return Tactics(**d)


@dataclass
class Team:
    name: str
    starters: list[Player]
    bench: list[Player] = field(default_factory=list)
    tactics: Tactics = field(default_factory=Tactics)


@dataclass
class TeamRuntime:
    team: Team
    on_field: list[PlayerState]
    bench: list[Player]
    substitutions: int = 0

    def by_name(self, name: str) -> PlayerState:
        for p in self.on_field:
            if p.player.name == name:
                return p
        raise KeyError(name)


@dataclass
class TeamStats:
    goals: int = 0
    shots: int = 0
    on_target: int = 0
    blocked: int = 0
    posts: int = 0
    xg: float = 0.0
    big_chances: int = 0
    corners: int = 0
    fouls: int = 0
    yellow: int = 0
    red: int = 0
    offsides: int = 0
    saves: int = 0
    final_third_entries: int = 0
    possession_seconds: float = 0.0


@dataclass
class PendingAction:
    team: int
    actor: str
    kind: str
    zone: Zone
    danger: float
    pressure: float
    target: Optional[str] = None
    defender: Optional[str] = None
    origin: str = "open_play"
    body_part: str = "foot"
    rebound_depth: int = 0


@dataclass
class MatchConfig:
    regulation_minutes: int = 90
    allow_extra_time: bool = False
    max_substitutions: int = 5
    allow_extra_time_substitution: bool = True
    relevant_threshold: int = 2
    direct_red_enabled: bool = True
    injuries_enabled: bool = True
    auto_tactical_adaptation: bool = False


@dataclass
class MatchState:
    second: float = 0.0
    possession: int = 0
    kickoff_team: int = 0
    extra_time_kickoff_team: Optional[int] = None
    zone: Zone = MID_C
    phase: str = "normal"
    transition_boost: float = 0.0
    pending: Optional[PendingAction] = None
    restart: Optional[str] = None
    restart_team: Optional[int] = None
    restart_zone: Optional[Zone] = None
    period_markers: list[int] = field(default_factory=lambda: [45, 90])
    period_index: int = 0
    ended: bool = False
    event_log: list[Event] = field(default_factory=list)


class MatchEngine:
    """Event-driven football simulator."""

    MATCH_FLOW_LOG_MU = -0.04
    MATCH_FLOW_LOG_SIGMA = 0.32

    def __init__(self, home: Team, away: Team, seed: Optional[int] = None, config: Optional[MatchConfig] = None):
        if len(home.starters) != 11 or len(away.starters) != 11:
            raise ValueError("Each team must have exactly 11 starters.")
        self.rng = random.Random(seed)
        self.seed = seed
        self.match_flow = clamp(self.rng.lognormvariate(self.MATCH_FLOW_LOG_MU, self.MATCH_FLOW_LOG_SIGMA), 0.35, 1.65)
        self.config = config or MatchConfig()
        self.teams = [
            TeamRuntime(home, [PlayerState(p) for p in home.starters], list(home.bench)),
            TeamRuntime(away, [PlayerState(p) for p in away.starters], list(away.bench)),
        ]
        self.stats = [TeamStats(), TeamStats()]
        kickoff_team = self.rng.randrange(2)
        self.state = MatchState(possession=kickoff_team, kickoff_team=kickoff_team)

    @property
    def minute(self) -> float:
        return self.state.second / 60.0

    @property
    def score(self) -> tuple[int, int]:
        return self.stats[0].goals, self.stats[1].goals

    def snapshot(self) -> dict:
        total_poss = sum(s.possession_seconds for s in self.stats) or 1.0
        pending = None if not self.state.pending else self._pending_to_dict(self.state.pending)
        return {
            "minute": round(self.minute, 2),
            "score": list(self.score),
            "match_flow": round(self.match_flow, 3),
            "possession_team": self.state.possession,
            "kickoff_team": self.state.kickoff_team,
            "phase": self.state.phase,
            "transition_boost": round(self.state.transition_boost, 4),
            "zone": self._zone_data(self.state.zone),
            "pending": pending,
            "restart": self.state.restart,
            "restart_team": self.state.restart_team,
            "formations": [rt.team.tactics.formation for rt in self.teams],
            "on_field_count": [len(rt.on_field) for rt in self.teams],
            "stats": [{**asdict(st), "possession_pct": round(100.0 * st.possession_seconds / total_poss, 1), "xg": round(st.xg, 2)} for st in self.stats],
            "energy": {rt.team.name: {ps.player.name: round(ps.energy, 3) for ps in rt.on_field} for rt in self.teams},
        }

    def export_state(self) -> dict:
        return {
            "version": 2,
            "seed": self.seed,
            "rng_state": repr(self.rng.getstate()),
            "match_flow": self.match_flow,
            "config": asdict(self.config),
            "teams": [self._runtime_to_dict(rt) for rt in self.teams],
            "stats": [asdict(st) for st in self.stats],
            "state": {
                "second": self.state.second,
                "possession": self.state.possession,
                "kickoff_team": self.state.kickoff_team,
                "extra_time_kickoff_team": self.state.extra_time_kickoff_team,
                "zone": self._zone_data(self.state.zone),
                "phase": self.state.phase,
                "transition_boost": self.state.transition_boost,
                "pending": None if not self.state.pending else self._pending_to_dict(self.state.pending),
                "restart": self.state.restart,
                "restart_team": self.state.restart_team,
                "restart_zone": None if self.state.restart_zone is None else self._zone_data(self.state.restart_zone),
                "period_markers": list(self.state.period_markers),
                "period_index": self.state.period_index,
                "ended": self.state.ended,
                "event_log": [self._event_to_dict(ev) for ev in self.state.event_log],
            },
        }

    def export_json(self) -> str:
        return json.dumps(self.export_state(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_state_dict(cls, data: dict) -> "MatchEngine":
        obj = cls.__new__(cls)
        obj.seed = data.get("seed")
        obj.rng = random.Random()
        obj.rng.setstate(ast.literal_eval(data["rng_state"]))
        obj.match_flow = float(data["match_flow"])
        obj.config = MatchConfig(**data["config"])
        obj.teams = [obj._runtime_from_dict(rt) for rt in data["teams"]]
        obj.stats = [TeamStats(**st) for st in data["stats"]]
        sd = data["state"]
        obj.state = MatchState(second=float(sd["second"]), possession=int(sd["possession"]), kickoff_team=int(sd.get("kickoff_team", sd["possession"])), extra_time_kickoff_team=sd.get("extra_time_kickoff_team"), zone=obj._zone_from_dict(sd["zone"]), phase=sd.get("phase", "normal"), transition_boost=float(sd.get("transition_boost", 0.0)), pending=None if sd.get("pending") is None else obj._pending_from_dict(sd["pending"]), restart=sd.get("restart"), restart_team=sd.get("restart_team"), restart_zone=None if sd.get("restart_zone") is None else obj._zone_from_dict(sd["restart_zone"]), period_markers=list(sd.get("period_markers", [45, 90])), period_index=int(sd.get("period_index", 0)), ended=bool(sd.get("ended", False)), event_log=[obj._event_from_dict(ev) for ev in sd.get("event_log", [])])
        return obj

    @classmethod
    def from_json(cls, payload: str) -> "MatchEngine":
        return cls.from_state_dict(json.loads(payload))

    @staticmethod
    def _player_to_dict(player: Player) -> dict:
        return {f.name: getattr(player, f.name) for f in fields(Player)}

    @staticmethod
    def _player_from_dict(data: dict) -> Player:
        return Player(**data)

    @classmethod
    def _player_state_to_dict(cls, ps: PlayerState) -> dict:
        return {"player": cls._player_to_dict(ps.player), "energy": ps.energy, "yellow": ps.yellow, "red": ps.red, "injured": ps.injured, "minutes": ps.minutes}

    @classmethod
    def _player_state_from_dict(cls, data: dict) -> PlayerState:
        return PlayerState(player=cls._player_from_dict(data["player"]), energy=float(data.get("energy", 1.0)), yellow=int(data.get("yellow", 0)), red=bool(data.get("red", False)), injured=bool(data.get("injured", False)), minutes=float(data.get("minutes", 0.0)))

    @classmethod
    def _runtime_to_dict(cls, rt: TeamRuntime) -> dict:
        return {"name": rt.team.name, "tactics": asdict(rt.team.tactics), "on_field": [cls._player_state_to_dict(ps) for ps in rt.on_field], "bench": [cls._player_to_dict(p) for p in rt.bench], "substitutions": rt.substitutions}

    @classmethod
    def _runtime_from_dict(cls, data: dict) -> TeamRuntime:
        on_field = [cls._player_state_from_dict(ps) for ps in data["on_field"]]
        bench = [cls._player_from_dict(p) for p in data.get("bench", [])]
        team = Team(name=data["name"], starters=[ps.player for ps in on_field], bench=list(bench), tactics=Tactics(**data["tactics"]))
        return TeamRuntime(team, on_field, bench, int(data.get("substitutions", 0)))

    @staticmethod
    def _pending_to_dict(p: PendingAction) -> dict:
        return {"team": p.team, "actor": p.actor, "kind": p.kind, "zone": {"band": p.zone.band.value, "lane": p.zone.lane.value}, "danger": p.danger, "pressure": p.pressure, "target": p.target, "defender": p.defender, "origin": p.origin, "body_part": p.body_part, "rebound_depth": p.rebound_depth}

    @classmethod
    def _pending_from_dict(cls, d: dict) -> PendingAction:
        return PendingAction(team=int(d["team"]), actor=d["actor"], kind=d["kind"], zone=cls._zone_from_dict(d["zone"]), danger=float(d["danger"]), pressure=float(d["pressure"]), target=d.get("target"), defender=d.get("defender"), origin=d.get("origin", "open_play"), body_part=d.get("body_part", "foot"), rebound_depth=int(d.get("rebound_depth", 0)))

    @staticmethod
    def _zone_from_dict(d: dict) -> Zone:
        return Zone(Band(d["band"]), Lane(d["lane"]))

    @staticmethod
    def _event_to_dict(ev: Event) -> dict:
        return {"minute": ev.minute, "team": ev.team, "type": ev.type.value, "relevance": ev.relevance, "text_key": ev.text_key, "data": ev.data}

    @staticmethod
    def _event_from_dict(d: dict) -> Event:
        return Event(minute=float(d["minute"]), team=int(d["team"]), type=EventType(d["type"]), relevance=int(d["relevance"]), text_key=d["text_key"], data=dict(d.get("data", {})))

    def advance_until_relevant(self, min_relevance: Optional[int] = None, max_steps: int = 500) -> Event:
        threshold = self.config.relevant_threshold if min_relevance is None else min_relevance
        if self.state.pending or self.state.restart:
            return self.step()
        last = None
        for _ in range(max_steps):
            last = self.step()
            if last.relevance >= threshold or last.type in (EventType.PERIOD_END, EventType.MATCH_END):
                return last
        return last or Event(self.minute, self.state.possession, EventType.INFO, 0, "no_event")

    def step(self) -> Event:
        if self.state.ended:
            return self._emit(EventType.MATCH_END, self.state.possession, 5, "match_already_ended")
        if self.state.restart:
            return self._resolve_restart()
        if self.state.pending:
            return self._resolve_pending()
        boundary_event = self._check_period_boundary()
        if boundary_event:
            return boundary_event
        return self._open_play_step()

    def set_tactics(self, team: int, **changes) -> None:
        t = self.teams[team].team.tactics
        data = t.__dict__.copy()
        for key, value in changes.items():
            if key not in data:
                raise KeyError(f"Unknown tactic: {key}")
            data[key] = value
        self.teams[team].team.tactics = Tactics(**data).normalized()

    def substitute(self, team: int, out_name: str, in_name: str) -> Event:
        if self.state.pending is not None:
            raise ValueError("Resolve the live pending action before making a substitution.")
        rt = self.teams[team]
        limit = self.config.max_substitutions
        if self.config.allow_extra_time_substitution and self.minute >= 90.0 and self.state.period_markers == [105, 120]:
            limit += 1
        if rt.substitutions >= limit:
            raise ValueError("Substitution limit reached.")
        out_state = rt.by_name(out_name)
        incoming = next((p for p in rt.bench if p.name == in_name), None)
        if incoming is None:
            raise KeyError(f"{in_name} is not on the bench.")
        rt.on_field.remove(out_state)
        rt.bench.remove(incoming)
        rt.on_field.append(PlayerState(incoming, energy=1.0))
        rt.substitutions += 1
        return self._emit(EventType.SUBSTITUTION, team, 2, "substitution", out=out_name, in_player=in_name)

    def override_pending(self, kind: str, target: Optional[str] = None) -> None:
        if not self.state.pending:
            raise ValueError("There is no pending dangerous action.")
        allowed = {"shoot", "cross", "cutback", "through_ball", "dribble"}
        if kind not in allowed:
            raise ValueError(f"kind must be one of {sorted(allowed)}")
        self.state.pending.kind = kind
        if target is not None:
            self.teams[self.state.pending.team].by_name(target)
            self.state.pending.target = target

    def start_extra_time(self) -> None:
        if self.minute < 90 or self.score[0] != self.score[1]:
            raise ValueError("Extra time can only start after a tied regulation match.")
        self.state.ended = False
        self.state.period_markers = [105, 120]
        self.state.period_index = 0
        self.state.second = max(self.state.second, 90 * 60)
        self.state.restart = None
        self.state.pending = None
        self.state.phase = "normal"
        self.state.transition_boost = 0.0
        et_kickoff = self.rng.randrange(2)
        self.state.extra_time_kickoff_team = et_kickoff
        self.state.possession = et_kickoff
        self.state.zone = MID_C

    def take_shootout_penalty(self, team: int, taker_name: str, keeper_name: Optional[str] = None) -> Event:
        taker = self.teams[team].by_name(taker_name)
        opp = 1 - team
        keeper = self.teams[opp].by_name(keeper_name) if keeper_name else self._goalkeeper(opp)
        taker_score = 0.45 * taker.effective("finishing") + 0.30 * taker.effective("composure") + 0.25 * taker.effective("technique")
        keeper_score = 0.40 * keeper.effective("reflexes") + 0.35 * keeper.effective("one_on_one") + 0.25 * keeper.effective("gk_positioning")
        p_goal = clamp(0.76 + (taker_score - keeper_score) / 260.0, 0.58, 0.91)
        goal = self.rng.random() < p_goal
        return self._emit(EventType.GOAL if goal else EventType.SAVE, team, 5, "shootout_penalty_goal" if goal else "shootout_penalty_missed", taker=taker_name, keeper=keeper.player.name, p_goal=round(p_goal, 3), shootout=True)

    def _open_play_step(self) -> Event:
        team = self.state.possession
        opp = 1 - team
        zone = self.state.zone
        tactics = self.teams[team].team.tactics
        def_tactics = self.teams[opp].team.tactics
        self._update_phase(zone)
        if self.config.auto_tactical_adaptation:
            self._maybe_auto_adapt()
            tactics = self.teams[team].team.tactics
            def_tactics = self.teams[opp].team.tactics
        actor = self._choose_actor(team, zone)
        context = self._spatial_context(team, zone)
        avg_tempo = 0.5 * (tactics.tempo + def_tactics.tempo)
        cadence = self.match_flow * (0.78 + 0.44 * avg_tempo)
        duration = self.rng.uniform(15.0, 36.0) / max(0.30, cadence)
        self._advance_clock(duration, team)
        if zone.band != Band.BOX:
            defender = self._choose_defender(opp, zone)
            generic_foul_p = clamp(0.010 + 0.025 * context["pressure"] + 0.007 * def_tactics.pressing + max(0.0, defender.effective("aggression") - 65.0) / 1800.0, 0.008, 0.050)
            if self.rng.random() < generic_foul_p:
                return self._commit_foul(opp, defender, actor, zone)
        decision = self._choose_decision(actor, zone, tactics, context)
        return self._execute_decision(team, actor, zone, decision, context)

    def _choose_decision(self, actor: PlayerState, zone: Zone, tactics: Tactics, ctx: dict) -> str:
        vision = actor.effective("vision") / 100.0
        composure = actor.effective("composure") / 100.0
        risk = clamp(0.5 * tactics.risk + 0.3 * tactics.mentality + 0.2 * vision)
        if zone.band == Band.DEF:
            items = [("safe_pass", 0.48 - 0.18 * tactics.directness), ("progressive_pass", 0.27 + 0.16 * tactics.directness), ("carry", 0.12 + 0.10 * actor.effective("dribbling") / 100), ("long_ball", 0.08 + 0.14 * tactics.directness)]
        elif zone.band == Band.MID:
            items = [("safe_pass", 0.25 - 0.08 * risk), ("progressive_pass", 0.26 + 0.11 * risk), ("carry", 0.13 + 0.09 * actor.effective("dribbling") / 100), ("switch", 0.09 + 0.08 * tactics.width), ("through_ball", 0.08 + 0.15 * vision * (0.5 + ctx["space_behind"])), ("long_ball", 0.05 + 0.08 * tactics.directness)]
        elif zone.band == Band.ATT:
            wide = zone.lane != Lane.CENTER
            items = [("safe_pass", 0.10), ("progressive_pass", 0.14), ("carry", 0.12 + 0.12 * actor.effective("dribbling") / 100), ("through_ball", 0.12 + 0.19 * vision * (0.5 + ctx["space_behind"])), ("cross", (0.08 + 0.22 * tactics.cross_frequency) if wide else 0.04), ("cutback", (0.08 + 0.12 * tactics.width) if wide else 0.04), ("shoot", 0.06 + 0.12 * risk + 0.08 * actor.effective("long_shots") / 100)]
        else:
            items = [("shoot", 0.38 + 0.16 * actor.effective("finishing") / 100), ("cutback", 0.13 + 0.12 * vision), ("dribble", 0.10 + 0.10 * actor.effective("dribbling") / 100), ("safe_pass", 0.08 + 0.08 * composure), ("cross", 0.05 if zone.lane != Lane.CENTER else 0.01)]
        if self.rng.random() > (0.55 + 0.35 * composure):
            items.append(("shoot", 0.13) if zone.band in (Band.ATT, Band.BOX) else ("long_ball", 0.10))
        return weighted_choice(self.rng, items)

    def _execute_decision(self, team, actor, zone, decision, ctx) -> Event:
        if decision == "safe_pass": return self._safe_pass(team, actor, zone, ctx)
        if decision in ("progressive_pass", "switch", "long_ball"): return self._progressive_action(team, actor, zone, decision, ctx)
        if decision == "carry": return self._carry(team, actor, zone, ctx)
        if decision in ("through_ball", "cross", "cutback", "shoot", "dribble"): return self._create_or_resolve_danger(team, actor, zone, decision, ctx)
        raise RuntimeError(decision)

    def _safe_pass(self, team, actor, zone, ctx) -> Event:
        target = self._choose_target(team, zone, attacking=False, exclude=actor.player.name)
        score = 0.45 * actor.effective("passing") + 0.25 * actor.effective("composure") + 0.15 * target.effective("positioning") + 15.0 * ctx["support"] - 20.0 * ctx["pressure"]
        p = clamp(logistic((score - 45.0) / 11.0), 0.58, 0.97)
        if self.rng.random() < p:
            if self.rng.random() < 0.30:
                self.state.zone = Zone(zone.band, self.rng.choice(list(Lane)))
            self._drain(actor, 0.0012)
            return self._emit(EventType.INFO, team, 0, "safe_pass", actor=actor.player.name, target=target.player.name)
        return self._turnover(team, actor, zone, "bad_safe_pass", ctx, severity=0.25)

    def _progressive_action(self, team, actor, zone, kind, ctx) -> Event:
        target = self._choose_target(team, zone, attacking=True, exclude=actor.player.name, action=kind)
        pass_attr, vision, tech = actor.effective("passing"), actor.effective("vision"), actor.effective("technique")
        difficulty = {"progressive_pass": 0.44, "switch": 0.50, "long_ball": 0.57}[kind]
        score = 0.38 * pass_attr + 0.25 * vision + 0.15 * tech + 13.0 * ctx["support"] + 10.0 * ctx["space"] - 22.0 * ctx["pressure"] - 22.0 * difficulty
        p = clamp(logistic((score - 38.0) / 10.0), 0.26, 0.91)
        if kind == "long_ball": p = clamp(p + 0.10 * ctx["space_behind"], 0.22, 0.90)
        self._drain(actor, 0.0016 if kind != "long_ball" else 0.0010)
        if self.rng.random() >= p: return self._turnover(team, actor, zone, f"{kind}_failed", ctx, severity=0.45)
        new_zone = self._progress_zone(zone, kind)
        self.state.zone = new_zone
        if new_zone.band == Band.ATT and zone.band != Band.ATT: self.stats[team].final_third_entries += 1
        danger = clamp(0.07 + 0.11 * ctx["space"] + 0.08 * ctx["space_behind"] + 0.09 * self.state.transition_boost + (vision - 72.0) / 300.0)
        if new_zone.band in (Band.ATT, Band.BOX) and self.rng.random() < danger:
            self.state.pending = PendingAction(team=team, actor=target.player.name, kind=self._natural_next_action(new_zone), zone=new_zone, danger=danger, pressure=self._spatial_context(team, new_zone)["pressure"], defender=self._choose_defender(1 - team, new_zone).player.name, origin="progression")
            return self._emit(EventType.DANGER, team, 3 if danger >= 0.62 else 2, "progression_creates_danger", actor=actor.player.name, target=target.player.name, kind=kind, zone=self._zone_data(new_zone), danger=round(danger, 3))
        self.state.transition_boost *= 0.55
        return self._emit(EventType.PROGRESSION, team, 1, "progression", actor=actor.player.name, target=target.player.name, kind=kind, zone=self._zone_data(new_zone))

    def _carry(self, team, actor, zone, ctx) -> Event:
        defender = self._choose_defender(1 - team, zone)
        atk = 0.40 * actor.effective("dribbling") + 0.25 * actor.effective("pace") + 0.20 * actor.effective("technique") + 0.15 * actor.effective("strength")
        deff = 0.40 * defender.effective("tackling") + 0.25 * defender.effective("positioning") + 0.20 * defender.effective("pace") + 0.15 * defender.effective("strength")
        p = clamp(0.50 + (atk - deff) / 170.0 + 0.18 * ctx["space"] - 0.11 * ctx["pressure"], 0.20, 0.82)
        self._drain(actor, 0.0030); self._drain(defender, 0.0024)
        foul_p = self._foul_probability(defender, actor, ctx)
        if self.rng.random() < p:
            new_zone = self._progress_zone(zone, "carry"); self.state.zone = new_zone
            if new_zone.band == Band.ATT and zone.band != Band.ATT: self.stats[team].final_third_entries += 1
            if new_zone.band in (Band.ATT, Band.BOX):
                danger = clamp(0.12 + 0.14 * ctx["space"] + 0.10 * self.state.transition_boost)
                if self.rng.random() < danger:
                    self.state.pending = PendingAction(team, actor.player.name, self._natural_next_action(new_zone), new_zone, danger, ctx["pressure"], defender=defender.player.name, origin="carry")
                    return self._emit(EventType.DANGER, team, 2 if danger < 0.65 else 3, "carry_creates_danger", actor=actor.player.name, defender=defender.player.name, zone=self._zone_data(new_zone), danger=round(danger, 3))
            return self._emit(EventType.PROGRESSION, team, 1, "carry_success", actor=actor.player.name, defender=defender.player.name, zone=self._zone_data(new_zone))
        if self.rng.random() < foul_p: return self._commit_foul(1 - team, defender, actor, zone)
        return self._turnover(team, actor, zone, "dispossessed", ctx, severity=0.55)

    def _create_or_resolve_danger(self, team, actor, zone, kind, ctx) -> Event:
        if kind == "shoot":
            pending = PendingAction(team, actor.player.name, "shoot", zone, danger=self._shot_danger(zone, actor, ctx), pressure=ctx["pressure"], defender=self._choose_defender(1 - team, zone).player.name, origin="open_play")
            if zone.band == Band.BOX:
                self.state.pending = pending
                return self._emit(EventType.DANGER, team, 3, "shooting_opportunity", actor=actor.player.name, zone=self._zone_data(zone), danger=round(pending.danger, 3))
            return self._resolve_shot(pending)
        target = self._choose_target(team, zone, attacking=True, exclude=actor.player.name)
        if kind == "through_ball":
            def_line = self.teams[1 - team].team.tactics.defensive_line
            runner_intel = (target.effective("off_ball") + target.effective("anticipation")) / 200.0
            offside_p = clamp(0.05 + 0.15 * def_line - 0.08 * runner_intel, 0.02, 0.20)
            if self.rng.random() < offside_p:
                self.stats[team].offsides += 1
                self._switch_possession(1 - team, Zone(Band.DEF, zone.lane), transition=0.0)
                return self._emit(EventType.OFFSIDE, team, 2, "offside", passer=actor.player.name, runner=target.player.name)
        defender = self._choose_defender(1 - team, zone)
        danger = self._danger_score(team, actor, target, zone, kind, ctx)
        execution = 0.25 * actor.effective("passing") + 0.20 * actor.effective("vision") + 0.20 * actor.effective("technique") + (0.20 * actor.effective("crossing") if kind in ("cross", "cutback") else 0.0) + (0.15 * actor.effective("dribbling") if kind == "dribble" else 0.0)
        if kind not in ("cross", "cutback", "dribble"): execution += 0.15 * actor.effective("passing")
        defending = 0.45 * defender.effective("positioning") + 0.35 * defender.effective("anticipation") + 0.20 * defender.effective("tackling")
        p_create = clamp(0.20 + (execution - defending) / 210.0 + 0.10 * ctx["space"] + 0.07 * ctx["space_behind"] - 0.18 * ctx["pressure"], 0.05, 0.56)
        self._drain(actor, 0.0020)
        if self.rng.random() >= p_create:
            if self.rng.random() < self._foul_probability(defender, actor, ctx): return self._commit_foul(1 - team, defender, actor, zone)
            return self._turnover(team, actor, zone, f"{kind}_stopped", ctx, severity=0.50)
        new_zone = self._danger_zone(zone, kind); self.state.zone = new_zone
        if new_zone.band == Band.ATT and zone.band != Band.ATT: self.stats[team].final_third_entries += 1
        self.state.pending = PendingAction(team=team, actor=target.player.name if kind != "dribble" else actor.player.name, kind=self._natural_next_action(new_zone, source=kind), zone=new_zone, danger=danger, pressure=self._spatial_context(team, new_zone)["pressure"], target=None, defender=defender.player.name, origin=kind, body_part="head" if kind == "cross" and self.rng.random() < 0.48 else "foot")
        relevance = 4 if danger >= 0.76 else 3 if danger >= 0.58 else 2
        return self._emit(EventType.DANGER, team, relevance, "danger_created", creator=actor.player.name, receiver=self.state.pending.actor, kind=kind, zone=self._zone_data(new_zone), danger=round(danger, 3))

    def _resolve_pending(self) -> Event:
        p = self.state.pending; self.state.pending = None
        actor = self._named_or_fallback(p.team, p.actor, role="actor", zone=p.zone)
        zone = p.zone; ctx = self._spatial_context(p.team, zone)
        if p.kind == "shoot": return self._resolve_shot(p)
        if p.kind in ("cross", "cutback", "through_ball"):
            target = self.teams[p.team].by_name(p.target) if p.target else self._choose_target(p.team, zone, attacking=True, exclude=actor.player.name, action=p.kind)
            defender = self._named_or_fallback(1 - p.team, p.defender, role="defender", zone=zone)
            attr = "crossing" if p.kind in ("cross", "cutback") else "passing"
            atk = 0.42 * actor.effective(attr) + 0.26 * actor.effective("vision") + 0.18 * actor.effective("technique") + 0.14 * target.effective("off_ball")
            deff = 0.42 * defender.effective("positioning") + 0.32 * defender.effective("anticipation") + 0.26 * defender.effective("tackling")
            p_success = clamp(0.46 + (atk - deff) / 175.0 + 0.18 * p.danger - 0.13 * ctx["pressure"], 0.16, 0.86)
            if self.rng.random() >= p_success:
                if p.kind in ("cross", "cutback") and self.rng.random() < 0.28: return self._award_corner(p.team, actor.player.name)
                return self._turnover(p.team, actor, zone, f"{p.kind}_cleared", ctx, severity=0.40)
            quality_boost = {"through_ball": 0.32, "cutback": 0.30, "cross": 0.08}[p.kind]
            shot_pending = PendingAction(team=p.team, actor=target.player.name, kind="shoot", zone=Zone(Band.BOX, Lane.CENTER if p.kind != "cutback" else zone.lane), danger=clamp(p.danger + quality_boost), pressure=clamp(ctx["pressure"] - 0.10 * p.danger), defender=defender.player.name, origin=p.kind, body_part=("head" if p.kind == "cross" and target.player.heading >= target.player.finishing else "foot"), rebound_depth=p.rebound_depth)
            return self._resolve_shot(shot_pending)
        if p.kind == "dribble":
            defender = self._named_or_fallback(1 - p.team, p.defender, role="defender", zone=zone)
            atk = 0.45 * actor.effective("dribbling") + 0.25 * actor.effective("pace") + 0.20 * actor.effective("technique") + 0.10 * actor.effective("composure")
            deff = 0.45 * defender.effective("tackling") + 0.30 * defender.effective("positioning") + 0.25 * defender.effective("pace")
            success = clamp(0.48 + (atk - deff) / 165 + 0.12 * p.danger, 0.18, 0.80)
            self._drain(actor, 0.0030)
            if self.rng.random() < success:
                p.kind = "shoot"; p.zone = Zone(Band.BOX, zone.lane); p.danger = clamp(p.danger + 0.10); p.pressure = clamp(p.pressure - 0.10)
                return self._resolve_shot(p)
            foul_p = self._foul_probability(defender, actor, ctx)
            if zone.band == Band.BOX and self.rng.random() < foul_p: return self._award_penalty(p.team, defender, actor)
            return self._turnover(p.team, actor, zone, "dribble_stopped", ctx, severity=0.50)
        raise RuntimeError(f"Unknown pending kind: {p.kind}")

    @staticmethod
    def _shot_goal_probability(xg: float, block_p: float, p_on_target: float,
                               finisher: float, keeper: float) -> float:
        """Conditional goal probability after an unblocked shot reaches target.

        xG describes the situation. Execution quality modifies conversion here.
        A positive conversion floor would manufacture probability mass for tiny
        chances. The denominator is the actual chance of reaching this stage;
        only an epsilon protects division by zero. The existing upper execution
        cap remains explicit, so extreme chances can still be ceiling-limited.
        """
        reach_target = max(1e-12, (1.0 - block_p) * p_on_target)
        execution = max(0.0, 1.0 + (finisher - keeper) / 240.0)
        return clamp(xg * execution / reach_target, 0.0, 0.86)

    def _resolve_shot(self, p: PendingAction) -> Event:
        team = p.team; shooter = self._named_or_fallback(team, p.actor, role="actor", zone=p.zone); opp = 1 - team
        defender = self._named_or_fallback(opp, p.defender, role="defender", zone=p.zone); keeper = self._goalkeeper(opp)
        xg = self._calculate_xg(p, shooter, defender, keeper); big = xg >= 0.30; st = self.stats[team]
        prepare_spatial = getattr(self, "_prepare_spatial_shot", None)
        if prepare_spatial is not None:
            self._active_spatial_shot = prepare_spatial(p, shooter, keeper)
        st.shots += 1; st.xg += xg
        if big: st.big_chances += 1
        pressure = clamp(p.pressure)
        block_p = clamp(0.07 + 0.23 * pressure + (defender.effective("positioning") - 70.0) / 260.0 - 0.07 * p.danger, 0.03, 0.34)
        if self.rng.random() < block_p:
            st.blocked += 1; self._drain(shooter, 0.0015); r = self.rng.random()
            if r < 0.26: return self._award_corner(team, shooter.player.name, shot_xg=xg)
            if r < 0.48 and p.rebound_depth < 2: return self._create_rebound(team, p, shooter, xg, blocked=True)
            self._switch_possession(opp, Zone(Band.DEF, p.zone.lane), transition=0.30)
            return self._emit(EventType.BLOCK, team, 3 if big else 2, "shot_blocked", shooter=shooter.player.name, defender=defender.player.name, xg=round(xg, 3), big_chance=big, origin=p.origin, danger=round(p.danger, 3), pressure=round(p.pressure, 3))
        technique = 0.40 * shooter.effective("finishing") + 0.25 * shooter.effective("technique") + 0.20 * shooter.effective("composure") + 0.15 * (shooter.effective("heading") if p.body_part == "head" else shooter.effective("finishing"))
        base_acc = {Band.BOX: 0.56, Band.ATT: 0.31, Band.MID: 0.18, Band.DEF: 0.08}[p.zone.band]
        p_on_target = clamp(base_acc + (technique - 72.0) / 170.0 + 0.12 * p.danger - 0.20 * pressure, 0.10, 0.86)
        spatial = getattr(self, "_active_spatial_shot", None)
        on_target = spatial["spatial_on_target"] if spatial else self.rng.random() < p_on_target
        if not on_target:
            post_p = clamp(0.018 + 0.08 * xg, 0.015, 0.055)
            if (spatial["spatial_hits_frame"] if spatial else self.rng.random() < post_p):
                st.posts += 1
                if self.rng.random() < 0.42 and p.rebound_depth < 2: return self._create_rebound(team, p, shooter, xg, blocked=False, post=True)
                self._switch_possession(opp, DEF_C, transition=0.0)
                return self._emit(EventType.POST, team, 4, "shot_hits_post", shooter=shooter.player.name, xg=round(xg, 3), big_chance=big, origin=p.origin, danger=round(p.danger, 3), pressure=round(p.pressure, 3))
            self._switch_possession(opp, DEF_C, transition=0.0)
            return self._emit(EventType.MISS, team, 3 if big else 2, "shot_missed", shooter=shooter.player.name, xg=round(xg, 3), big_chance=big, body_part=p.body_part, origin=p.origin, danger=round(p.danger, 3), pressure=round(p.pressure, 3))
        st.on_target += 1
        finisher = 0.45 * shooter.effective("finishing") + 0.30 * shooter.effective("composure") + 0.25 * shooter.effective("technique")
        gk = 0.40 * keeper.effective("reflexes") + 0.35 * keeper.effective("gk_positioning") + 0.25 * keeper.effective("one_on_one")
        p_goal_if_ot = self._shot_goal_probability(xg, block_p, p_on_target, finisher, gk)
        if spatial:
            # Situation xG remains untouched. Geometry and specialist keeper
            # ability affect conversion only, after physical on-target execution.
            p_goal_if_ot = self._shot_goal_probability(
                xg, block_p, spatial.get("reference_on_target_probability", p_on_target),
                finisher, spatial["keeper_ability"])
            p_goal_if_ot = clamp(p_goal_if_ot * spatial["spatial_conversion_multiplier"], 0., .98)
            if spatial["keeper_exposed"]:
                p_goal_if_ot = 1.0  # An unblocked, in-frame ball cannot be saved by an absent keeper.
        if self.rng.random() < p_goal_if_ot:
            st.goals += 1; self.state.pending = None; self.state.restart = "kickoff"; self.state.restart_team = opp; self.state.restart_zone = MID_C; self.state.transition_boost = 0.0
            return self._emit(EventType.GOAL, team, 5, "goal", scorer=shooter.player.name, keeper=keeper.player.name, xg=round(xg, 3), big_chance=big, origin=p.origin, body_part=p.body_part, danger=round(p.danger, 3), pressure=round(p.pressure, 3))
        self.stats[opp].saves += 1
        spill = clamp(0.20 + (78.0 - keeper.effective("handling")) / 190.0 + 0.08 * xg - 0.10 * p.rebound_depth, 0.07, 0.34)
        if spatial:
            spill = clamp(spill + .06 * spatial["keeper_difficulty"] + .002 * (spatial["shot_speed_mps"] - 24), .07, .45)
        if self.rng.random() < spill and p.rebound_depth < 2: return self._create_rebound(team, p, shooter, xg, blocked=False)
        self._switch_possession(opp, DEF_C, transition=0.0)
        return self._emit(EventType.SAVE, team, 4 if big else 3, "shot_saved", shooter=shooter.player.name, keeper=keeper.player.name, xg=round(xg, 3), big_chance=big, body_part=p.body_part, origin=p.origin, danger=round(p.danger, 3), pressure=round(p.pressure, 3))

    def _create_rebound(self, team, p, shooter, xg, blocked=False, post=False) -> Event:
        candidate = self._choose_target(team, Zone(Band.BOX, Lane.CENTER), attacking=True, exclude=shooter.player.name)
        danger = clamp(0.40 + 0.35 * xg - 0.12 * p.rebound_depth)
        self.state.pending = PendingAction(team=team, actor=candidate.player.name, kind="shoot" if self.rng.random() < 0.68 else "cutback", zone=Zone(Band.BOX, self.rng.choice(list(Lane))), danger=danger, pressure=clamp(p.pressure + 0.05), defender=self._choose_defender(1 - team, Zone(Band.BOX, Lane.CENTER)).player.name, origin="rebound", rebound_depth=p.rebound_depth + 1)
        return self._emit(EventType.REBOUND, team, 4, "rebound_live", shooter=shooter.player.name, next_player=candidate.player.name, previous_xg=round(xg, 3), blocked=blocked, post=post)

    def _award_corner(self, team, creator: str, shot_xg: Optional[float] = None) -> Event:
        self.stats[team].corners += 1; self.state.restart = "corner"; self.state.restart_team = team; self.state.restart_zone = Zone(Band.ATT, self.rng.choice([Lane.LEFT, Lane.RIGHT])); self.state.phase = "restart"
        return self._emit(EventType.CORNER, team, 3, "corner_awarded", creator=creator, shot_xg=None if shot_xg is None else round(shot_xg, 3))

    def _award_penalty(self, team, defender: PlayerState, attacker: PlayerState, foul_already_counted: bool = False, card_already: Optional[str] = None) -> Event:
        if not foul_already_counted: self.stats[1 - team].fouls += 1
        generated_card = card_already is None
        card = card_already if card_already is not None else self._maybe_card(1 - team, defender, severity=0.75)
        if generated_card and card: self._record_card_event(1 - team, defender, card)
        self.state.restart = "penalty"; self.state.restart_team = team; self.state.restart_zone = Zone(Band.BOX, Lane.CENTER); self.state.phase = "restart"
        return self._emit(EventType.PENALTY, team, 5, "penalty_awarded", fouled=attacker.player.name, defender=defender.player.name, card=card)

    def _resolve_restart(self) -> Event:
        kind, team = self.state.restart, self.state.restart_team; zone = self.state.restart_zone or MID_C
        self.state.restart = None; self.state.restart_team = None; self.state.restart_zone = None
        if kind == "kickoff":
            self._switch_possession(team, MID_C, transition=0.0); return self._emit(EventType.INFO, team, 0, "kickoff")
        if kind == "corner":
            taker = self._best_player(team, ("crossing", "technique", "vision"), exclude_positions={"GK"})
            target = self._best_player(team, ("heading", "strength", "off_ball"), exclude_positions={"GK"}, exclude_names={taker.player.name})
            defender = self._best_player(1 - team, ("heading", "positioning", "strength"), exclude_positions={"GK"})
            delivery = 0.45 * taker.effective("crossing") + 0.30 * taker.effective("technique") + 0.25 * taker.effective("vision")
            duel = 0.45 * target.effective("heading") + 0.25 * target.effective("strength") + 0.20 * target.effective("off_ball") + 0.10 * delivery - (0.45 * defender.effective("heading") + 0.30 * defender.effective("positioning") + 0.25 * defender.effective("strength"))
            p_contact = clamp(0.24 + duel / 220.0, 0.10, 0.52)
            if self.rng.random() < p_contact:
                return self._resolve_shot(PendingAction(team, target.player.name, "shoot", Zone(Band.BOX, Lane.CENTER), danger=clamp(0.45 + duel / 180.0, 0.25, 0.78), pressure=0.58, defender=defender.player.name, origin="corner", body_part="head"))
            if self.rng.random() < 0.30:
                second = self._choose_target(team, Zone(Band.ATT, Lane.CENTER), attacking=True)
                self.state.pending = PendingAction(team, second.player.name, self.rng.choice(["shoot", "cross", "through_ball"]), Zone(Band.ATT, Lane.CENTER), danger=0.38, pressure=0.45, origin="second_ball")
                return self._emit(EventType.REBOUND, team, 3, "corner_second_ball", player=second.player.name)
            self._switch_possession(1 - team, DEF_C, transition=0.45); return self._emit(EventType.INFO, team, 1, "corner_cleared")
        if kind == "free_kick":
            taker = self._best_player(team, ("technique", "long_shots", "composure"), exclude_positions={"GK"})
            if zone.band == Band.ATT and zone.lane == Lane.CENTER and self.rng.random() < 0.45:
                return self._resolve_shot(PendingAction(team, taker.player.name, "shoot", zone, danger=0.34, pressure=0.05, origin="free_kick"))
            target = self._best_player(team, ("heading", "strength", "off_ball"), exclude_positions={"GK"}, exclude_names={taker.player.name})
            self.state.pending = PendingAction(team, taker.player.name, "cross", zone, danger=0.42, pressure=0.20, target=target.player.name, origin="free_kick")
            return self._emit(EventType.FREE_KICK, team, 3, "free_kick_delivery_pending", taker=taker.player.name, target=target.player.name)
        if kind == "penalty":
            taker = self._best_player(team, ("finishing", "composure", "technique"), exclude_positions={"GK"}); keeper = self._goalkeeper(1 - team)
            taker_score = 0.45 * taker.effective("finishing") + 0.30 * taker.effective("composure") + 0.25 * taker.effective("technique"); keeper_score = 0.40 * keeper.effective("reflexes") + 0.35 * keeper.effective("one_on_one") + 0.25 * keeper.effective("gk_positioning")
            xg = clamp(0.76 + (taker_score - keeper_score) / 300.0, 0.62, 0.88); self.stats[team].shots += 1; self.stats[team].xg += xg; self.stats[team].big_chances += 1
            if self.rng.random() < xg:
                self.stats[team].on_target += 1; self.stats[team].goals += 1; self.state.restart = "kickoff"; self.state.restart_team = 1 - team; self.state.restart_zone = MID_C; self.state.phase = "restart"
                return self._emit(EventType.GOAL, team, 5, "penalty_goal", scorer=taker.player.name, keeper=keeper.player.name, xg=round(xg, 3))
            on_target = self.rng.random() < 0.72
            if on_target:
                self.stats[team].on_target += 1; self.stats[1 - team].saves += 1; outcome, key = EventType.SAVE, "penalty_saved"
            else: outcome, key = EventType.MISS, "penalty_missed"
            self._switch_possession(1 - team, DEF_C, transition=0.0)
            return self._emit(outcome, team, 5, key, taker=taker.player.name, keeper=keeper.player.name, xg=round(xg, 3))
        raise RuntimeError(f"Unknown restart: {kind}")

    def _commit_foul(self, defending_team, defender, attacker, zone) -> Event:
        self.stats[defending_team].fouls += 1
        severity = clamp(0.25 + defender.effective("aggression") / 180.0 - defender.effective("discipline") / 260.0 + (0.10 if zone.band in (Band.ATT, Band.BOX) else 0.0) + self.rng.uniform(-0.08, 0.10))
        card = self._maybe_card(defending_team, defender, severity); attacking_team = 1 - defending_team; injury = None
        if self.config.injuries_enabled:
            injury_p = clamp(0.0015 + 0.020 * max(0.0, severity - 0.45), 0.001, 0.018)
            if self.rng.random() < injury_p: attacker.injured = True; injury = "injured"
        if zone.band == Band.BOX:
            ev = self._award_penalty(attacking_team, defender, attacker, foul_already_counted=True, card_already=card)
            if card: self._record_card_event(defending_team, defender, card)
            if injury: self._record_injury_event(attacking_team, attacker, defender)
            return ev
        self.state.restart = "free_kick"; self.state.restart_team = attacking_team; self.state.restart_zone = zone; self.state.transition_boost = 0.0; self.state.phase = "restart"
        ev = self._emit(EventType.FOUL, attacking_team, 3 if zone.band == Band.ATT else (2 if card or injury else 1), "foul", fouled=attacker.player.name, defender=defender.player.name, zone=self._zone_data(zone), card=card, injury=injury)
        if card: self._record_card_event(defending_team, defender, card)
        if injury: self._record_injury_event(attacking_team, attacker, defender)
        return ev

    def _maybe_card(self, team, defender, severity) -> Optional[str]:
        aggression = defender.effective("aggression") / 100.0; discipline = defender.effective("discipline") / 100.0
        if self.config.direct_red_enabled:
            direct_red_p = clamp(0.002 + 0.055 * max(0.0, severity - 0.62) + 0.012 * aggression - 0.010 * discipline, 0.001, 0.045)
            if self.rng.random() < direct_red_p:
                defender.red = True; self.stats[team].red += 1
                if defender in self.teams[team].on_field: self.teams[team].on_field.remove(defender)
                return "direct_red"
        yellow_p = clamp(0.08 + 0.30 * severity + 0.12 * aggression - 0.10 * discipline, 0.04, 0.48)
        if self.rng.random() >= yellow_p: return None
        if defender.yellow:
            defender.red = True; self.stats[team].yellow += 1; self.stats[team].red += 1
            if defender in self.teams[team].on_field: self.teams[team].on_field.remove(defender)
            return "second_yellow_red"
        defender.yellow = 1; self.stats[team].yellow += 1; return "yellow"

    def _record_card_event(self, team: int, defender: PlayerState, card: str) -> None:
        self._emit(EventType.CARD, team, 2 if card == "yellow" else 4, "card_shown", player=defender.player.name, card=card)

    def _record_injury_event(self, team: int, player: PlayerState, caused_by: Optional[PlayerState] = None) -> None:
        self._emit(EventType.INJURY, team, 3, "player_injured", player=player.player.name, caused_by=None if caused_by is None else caused_by.player.name)

    def _formation_profile(self, team: int) -> dict:
        formation = self.teams[team].team.tactics.formation
        try: parts = [int(x) for x in formation.split("-") if x.strip().isdigit()]
        except Exception: parts = []
        if len(parts) < 2 or sum(parts) != 10: parts = [4, 5, 1]
        defenders, attackers = parts[0], parts[-1]; midfielders = 10 - defenders - attackers
        rt = self.teams[team]; outfield = [ps for ps in rt.on_field if ps.player.position.upper() != "GK"]; actual = {"def": 0, "mid": 0, "att": 0}
        for ps in outfield:
            pos = ps.player.position.upper()
            if pos in {"CB", "LB", "RB"}: actual["def"] += 1
            elif pos in {"DM", "CM", "AM"}: actual["mid"] += 1
            else: actual["att"] += 1
        return {"def": defenders, "mid": midfielders, "att": attackers, "actual_def": actual["def"], "actual_mid": actual["mid"], "actual_att": actual["att"], "outfield": len(outfield), "availability": clamp(len(outfield) / 10.0, 0.0, 1.0)}

    def _line_presence(self, team: int, line: str) -> float:
        prof = self._formation_profile(team); intended = max(1, prof[line]); actual = prof[f"actual_{line}"]
        return clamp(0.55 * (actual / intended) + 0.45 * prof["availability"], 0.35, 1.25)

    def _spatial_context(self, attacking_team: int, zone: Zone) -> dict:
        atk = self.teams[attacking_team].team.tactics; deff = self.teams[1 - attacking_team].team.tactics; atk_prof = self._formation_profile(attacking_team); def_prof = self._formation_profile(1 - attacking_team)
        central = zone.lane == Lane.CENTER; wide = not central
        if zone.band == Band.DEF: defending_line, base_line = "att", 2
        elif zone.band == Band.MID: defending_line, base_line = "mid", 4
        else: defending_line, base_line = "def", 4
        line_count = def_prof[defending_line]; line_presence = self._line_presence(1 - attacking_team, defending_line); formation_pressure = (line_count - base_line) * 0.035 * line_presence
        central_pressure = 0.25 * deff.compactness if central else -0.13 * deff.compactness; wide_space = 0.18 * deff.compactness if wide else 0.02
        line_pressure = 0.18 * deff.defensive_line if zone.band == Band.MID else 0.10 * deff.defensive_line if zone.band == Band.ATT else 0.0
        press_zone_factor = {Band.DEF: 0.75, Band.MID: 1.00, Band.ATT: 0.86, Band.BOX: 0.55}[zone.band]
        missing_defenders = max(0, 10 - def_prof["outfield"])
        pressure = clamp(0.12 + 0.42 * deff.pressing * press_zone_factor + central_pressure + line_pressure + formation_pressure - 0.075 * missing_defenders - 0.09 * self.state.transition_boost + self.rng.uniform(-0.06, 0.06))
        space_behind = clamp(0.10 + 0.42 * deff.defensive_line + 0.15 * deff.pressing + 0.18 * self.state.transition_boost + 0.06 * missing_defenders - 0.12 * (1.0 if zone.band == Band.DEF else 0.0))
        overlap = atk.overlap_left if zone.lane == Lane.LEFT else atk.overlap_right if zone.lane == Lane.RIGHT else 0.0
        if zone.band in (Band.ATT, Band.BOX): attack_shape = (atk_prof["att"] - 2) * 0.045 + (atk_prof["mid"] - 4) * 0.012
        elif zone.band == Band.MID: attack_shape = (atk_prof["mid"] - 4) * 0.035
        else: attack_shape = (atk_prof["def"] - 4) * 0.018 + (atk_prof["mid"] - 4) * 0.012
        missing_attackers = max(0, 10 - atk_prof["outfield"])
        support = clamp(0.28 + 0.24 * atk.mentality + 0.18 * atk.tempo + 0.16 * overlap + attack_shape + 0.13 * self.state.transition_boost - 0.085 * missing_attackers)
        space = clamp(0.48 - 0.42 * pressure + wide_space + 0.12 * atk.width * (1.0 if wide else -0.25) + 0.12 * self.state.transition_boost + 0.035 * missing_defenders)
        return {"pressure": pressure, "space": space, "space_behind": space_behind, "support": support, "wide_space": clamp(wide_space), "attacking_availability": atk_prof["availability"], "defending_availability": def_prof["availability"]}

    def _danger_score(self, team, actor, target, zone, kind, ctx) -> float:
        base = {"through_ball": 0.38, "cross": 0.30, "cutback": 0.43, "dribble": 0.35, "shoot": 0.24}.get(kind, 0.34)
        creator = 0.42 * actor.effective("vision") + 0.34 * actor.effective("technique") + 0.24 * (actor.effective("crossing") if kind in ("cross", "cutback") else actor.effective("passing"))
        receiver = 0.55 * target.effective("off_ball") + 0.25 * target.effective("anticipation") + 0.20 * target.effective("pace")
        return clamp(base + (creator - 74.0) / 180.0 + (receiver - 74.0) / 240.0 + 0.24 * ctx["space"] + 0.20 * ctx["space_behind"] * (1.0 if kind == "through_ball" else 0.45) + 0.14 * self.state.transition_boost - 0.19 * ctx["pressure"])

    def _shot_danger(self, zone, shooter, ctx) -> float:
        base = {Band.BOX: 0.56, Band.ATT: 0.22, Band.MID: 0.09, Band.DEF: 0.03}[zone.band]
        if zone.lane != Lane.CENTER: base -= 0.08
        return clamp(base + (shooter.effective("off_ball") - 72.0) / 220.0 + 0.16 * ctx["space"] - 0.18 * ctx["pressure"])

    def _calculate_xg(self, p, shooter, defender, keeper) -> float:
        zone_base = {Band.BOX: 0.090, Band.ATT: 0.026, Band.MID: 0.009, Band.DEF: 0.003}[p.zone.band]
        if p.zone.band == Band.BOX: zone_base += 0.035 if p.zone.lane == Lane.CENTER else -0.020
        origin_bonus = {"through_ball": 0.100, "cutback": 0.120, "rebound": 0.060, "corner": -0.020, "free_kick": -0.010, "open_play": 0.0, "progression": 0.014, "carry": 0.040, "second_ball": -0.005, "cross": -0.015, "transition": 0.038}.get(p.origin, 0.0)
        if p.body_part == "head": origin_bonus -= 0.018
        return clamp(zone_base + origin_bonus + 0.28 * (p.danger - 0.48) - 0.10 * (p.pressure - 0.4), 0.003, 0.66)

    def _turnover(self, losing_team, actor, zone, reason, ctx, severity=0.5) -> Event:
        gaining = 1 - losing_team; losing_t = self.teams[losing_team].team.tactics
        lane_overlap = losing_t.overlap_left if zone.lane == Lane.LEFT else losing_t.overlap_right if zone.lane == Lane.RIGHT else 0.0
        exposure = clamp(0.16 + 0.26 * losing_t.pressing + 0.22 * losing_t.defensive_line + 0.18 * lane_overlap + 0.20 * severity)
        transition = exposure if self.teams[gaining].team.tactics.counter > self.rng.random() else exposure * 0.45
        new_zone = zone.mirror()
        if zone.band == Band.DEF and transition > 0.55: new_zone = Zone(Band.ATT, zone.lane)
        elif zone.band == Band.MID and transition > 0.68: new_zone = Zone(Band.ATT, zone.lane)
        self._switch_possession(gaining, new_zone, transition)
        relevance = 2 if transition > 0.62 and new_zone.band == Band.ATT else 1
        if relevance >= 2:
            receiver = self._choose_actor(gaining, new_zone)
            self.state.pending = PendingAction(gaining, receiver.player.name, self._natural_next_action(new_zone), new_zone, danger=clamp(0.40 + 0.35 * transition), pressure=self._spatial_context(gaining, new_zone)["pressure"], origin="transition")
            return self._emit(EventType.DANGER, gaining, 2, "dangerous_turnover", loser=actor.player.name, reason=reason, receiver=receiver.player.name, zone=self._zone_data(new_zone), transition=round(transition, 3))
        return self._emit(EventType.TURNOVER, gaining, 1, "turnover", loser=actor.player.name, reason=reason, zone=self._zone_data(new_zone))

    def _switch_possession(self, new_team, zone, transition=0.0):
        self.state.possession = new_team; self.state.zone = zone; self.state.transition_boost = clamp(transition); self.state.phase = "transition" if transition > 0.20 else self._phase_for_zone(zone)

    def _named_or_fallback(self, team: int, name: Optional[str], role: str, zone: Zone) -> PlayerState:
        if name:
            try: return self.teams[team].by_name(name)
            except KeyError: pass
        return self._choose_defender(team, zone) if role == "defender" else self._choose_actor(team, zone)

    def _choose_actor(self, team: int, zone: Zone) -> PlayerState:
        rt = self.teams[team]; weights = []
        for ps in rt.on_field:
            pos = ps.player.position.upper()
            if pos == "GK": w = 0.03 if zone.band != Band.DEF else 0.12
            elif zone.band == Band.DEF: w = {"CB": 1.4, "LB": 1.1, "RB": 1.1, "DM": 1.0, "CM": 0.55, "AM": 0.25, "LW": 0.20, "RW": 0.20, "ST": 0.12}.get(pos, 0.35)
            elif zone.band == Band.MID: w = {"DM": 1.2, "CM": 1.5, "AM": 1.15, "LB": 0.65, "RB": 0.65, "LW": 0.85, "RW": 0.85, "ST": 0.45, "CB": 0.35}.get(pos, 0.5)
            elif zone.band == Band.ATT: w = {"AM": 1.35, "LW": 1.25, "RW": 1.25, "ST": 1.15, "CM": 0.75, "LB": 0.35, "RB": 0.35, "DM": 0.30, "CB": 0.10}.get(pos, 0.5)
            else: w = {"ST": 1.65, "LW": 1.05, "RW": 1.05, "AM": 1.15, "CM": 0.45, "LB": 0.16, "RB": 0.16, "DM": 0.12, "CB": 0.09}.get(pos, 0.4)
            if zone.lane == Lane.LEFT and pos in ("LB", "LW"): w *= 1.45
            if zone.lane == Lane.RIGHT and pos in ("RB", "RW"): w *= 1.45
            if zone.lane == Lane.CENTER and pos in ("CB", "DM", "CM", "AM", "ST"): w *= 1.25
            w *= 0.75 + 0.25 * ps.energy; weights.append((ps, w))
        return weighted_choice(self.rng, weights)

    def _attacking_target_quality(self, ps: PlayerState, action: Optional[str] = None) -> float:
        """Return contextual attacking movement quality without hard-selecting a star.

        The old target model was mostly position-driven, so elite attackers and
        ordinary players in the same role were too similar as receivers. This
        keeps selection probabilistic but lets the action reward the attributes
        that actually make a player a plausible target.
        """
        off_ball = ps.effective("off_ball")
        anticipation = ps.effective("anticipation")
        finishing = ps.effective("finishing")
        composure = ps.effective("composure")
        technique = ps.effective("technique")
        heading = ps.effective("heading")
        strength = ps.effective("strength")

        if action == "cross":
            return 0.32 * off_ball + 0.25 * anticipation + 0.28 * heading + 0.15 * strength
        if action in ("through_ball", "cutback"):
            return 0.36 * off_ball + 0.22 * anticipation + 0.27 * finishing + 0.15 * composure
        return 0.42 * off_ball + 0.22 * anticipation + 0.18 * technique + 0.18 * finishing

    def _choose_target(self, team, zone, attacking=True, exclude=None, action=None) -> PlayerState:
        rt = self.teams[team]; weights = []
        for ps in rt.on_field:
            if ps.player.name == exclude: continue
            pos = ps.player.position.upper()
            if attacking:
                base = {"ST": 1.55, "AM": 1.35, "LW": 1.25, "RW": 1.25, "CM": 0.75, "LB": 0.42, "RB": 0.42, "DM": 0.35, "CB": 0.12, "GK": 0.01}.get(pos, 0.5)
                quality = self._attacking_target_quality(ps, action)
                # Context matters, but never enough to turn selection into a quota.
                # A strong target is preferred rather than guaranteed.
                w = base * (0.55 + 0.65 * quality / 100.0)
            else:
                w = {"CB": 1.1, "LB": 0.95, "RB": 0.95, "DM": 1.2, "CM": 1.1, "AM": 0.65, "LW": 0.55, "RW": 0.55, "ST": 0.35, "GK": 0.20}.get(pos, 0.6) * (0.75 + 0.25 * ps.effective("positioning") / 100.0)
            if zone.lane == Lane.LEFT and pos in ("LB", "LW"): w *= 1.25
            if zone.lane == Lane.RIGHT and pos in ("RB", "RW"): w *= 1.25
            weights.append((ps, w))
        return weighted_choice(self.rng, weights)

    def _choose_defender(self, team, zone) -> PlayerState:
        rt = self.teams[team]; weights = []
        for ps in rt.on_field:
            pos = ps.player.position.upper()
            if pos == "GK": w = 0.03
            elif zone.band == Band.BOX: w = {"CB": 1.7, "LB": 1.0, "RB": 1.0, "DM": 0.85, "CM": 0.35}.get(pos, 0.15)
            elif zone.band == Band.ATT: w = {"CB": 1.25, "LB": 1.05, "RB": 1.05, "DM": 1.15, "CM": 0.65}.get(pos, 0.25)
            else: w = {"DM": 1.2, "CM": 1.0, "LB": 0.75, "RB": 0.75, "CB": 0.65}.get(pos, 0.35)
            if zone.lane == Lane.LEFT and pos in ("RB", "CB"): w *= 1.20
            if zone.lane == Lane.RIGHT and pos in ("LB", "CB"): w *= 1.20
            weights.append((ps, w))
        return weighted_choice(self.rng, weights)

    def _goalkeeper(self, team) -> PlayerState:
        for ps in self.teams[team].on_field:
            if ps.player.position.upper() == "GK": return ps
        return self._best_player(team, ("reflexes", "handling", "gk_positioning"))

    def _best_player(self, team, attrs, exclude_positions=None, exclude_names=None) -> PlayerState:
        exclude_positions = exclude_positions or set(); exclude_names = exclude_names or set()
        candidates = [ps for ps in self.teams[team].on_field if ps.player.position.upper() not in exclude_positions and ps.player.name not in exclude_names]
        if not candidates: raise ValueError("No eligible player for selection.")
        return max(candidates, key=lambda ps: sum(ps.effective(a) for a in attrs))

    def _advance_clock(self, seconds: float, possession_team: int):
        self.state.second += seconds; self.stats[possession_team].possession_seconds += seconds
        self.state.transition_boost *= math.exp(-seconds / 38.0)
        if self.state.transition_boost < 0.01: self.state.transition_boost = 0.0
        for ti, rt in enumerate(self.teams):
            tactics = rt.team.tactics
            for ps in rt.on_field:
                ps.minutes += seconds / 60.0; base = seconds / 60.0 * 0.00255; role = ps.player.position.upper(); run_load = 1.0
                if role in ("LW", "RW", "LB", "RB", "CM"): run_load += 0.12
                if ti != possession_team: run_load += 0.28 * tactics.pressing
                else: run_load += 0.16 * tactics.tempo
                run_load += 0.08 * max(0.0, tactics.mentality) + 0.06 * tactics.defensive_line
                load = base * run_load * (1.14 - ps.player.stamina / 520.0); ps.energy = clamp(ps.energy - load, 0.18, 1.0)

    def _drain(self, ps: PlayerState, amount: float):
        ps.energy = clamp(ps.energy - amount * (1.12 - ps.player.stamina / 500.0), 0.18, 1.0)

    def _check_period_boundary(self) -> Optional[Event]:
        if self.state.period_index >= len(self.state.period_markers): return None
        marker = self.state.period_markers[self.state.period_index]
        if self.minute < marker: return None
        self.state.period_index += 1; self.state.pending = None; self.state.restart = None; self.state.transition_boost = 0.0
        if self.state.period_index >= len(self.state.period_markers):
            if marker == 90 and self.config.allow_extra_time and self.score[0] == self.score[1]:
                self.state.ended = True; return self._emit(EventType.PERIOD_END, self.state.possession, 5, "regulation_end_tied")
            self.state.ended = True; return self._emit(EventType.MATCH_END, self.state.possession, 5, "match_end")
        if marker == 45: self.state.possession = 1 - self.state.kickoff_team
        elif marker == 105 and self.state.extra_time_kickoff_team is not None: self.state.possession = 1 - self.state.extra_time_kickoff_team
        else: self.state.possession = 1 - self.state.possession
        self.state.zone = MID_C; self.state.phase = "build_up"
        return self._emit(EventType.PERIOD_END, self.state.possession, 5, "period_end", marker=marker)

    def _phase_for_zone(self, zone: Zone) -> str:
        if zone.band == Band.DEF: return "build_up"
        if zone.band == Band.MID: return "progression"
        if zone.band == Band.ATT: return "final_third"
        return "chance_creation"

    def _update_phase(self, zone: Zone) -> None:
        self.state.phase = "transition" if self.state.transition_boost > 0.20 else self._phase_for_zone(zone)

    def _maybe_auto_adapt(self) -> None:
        minute = self.minute
        if minute < 55 or int(minute) % 5 != 0 or self.rng.random() > 0.10: return
        h, a = self.score
        for team, diff in ((0, h - a), (1, a - h)):
            t = self.teams[team].team.tactics
            if diff < 0 and minute >= 65: self.set_tactics(team, mentality=min(0.85, t.mentality + 0.08), tempo=min(0.85, t.tempo + 0.05), risk=min(0.88, t.risk + 0.06), pressing=min(0.86, t.pressing + 0.04))
            elif diff > 0 and minute >= 75: self.set_tactics(team, mentality=max(-0.75, t.mentality - 0.05), risk=max(0.18, t.risk - 0.04), compactness=min(0.88, t.compactness + 0.04))

    def _progress_zone(self, zone: Zone, kind: str) -> Zone:
        lane = zone.lane
        if kind == "switch": lane = Lane.RIGHT if lane == Lane.LEFT else Lane.LEFT if lane == Lane.RIGHT else self.rng.choice([Lane.LEFT, Lane.RIGHT])
        elif self.rng.random() < 0.24: lane = self.rng.choice(list(Lane))
        band = Band.MID if zone.band == Band.DEF else Band.ATT if zone.band == Band.MID else (Band.BOX if self.rng.random() < 0.28 else Band.ATT) if zone.band == Band.ATT else Band.BOX
        return Zone(band, lane)

    def _danger_zone(self, zone: Zone, kind: str) -> Zone:
        if kind in ("through_ball", "cutback", "dribble"): return Zone(Band.BOX, zone.lane if kind == "dribble" else Lane.CENTER)
        if kind == "cross": return Zone(Band.BOX, Lane.CENTER)
        return self._progress_zone(zone, kind)

    def _natural_next_action(self, zone: Zone, source: Optional[str] = None) -> str:
        if zone.band == Band.BOX:
            if source == "cross": return "shoot"
            return weighted_choice(self.rng, [("shoot", 0.68), ("cutback", 0.17), ("dribble", 0.15)])
        if zone.band == Band.ATT:
            if zone.lane == Lane.CENTER: return weighted_choice(self.rng, [("through_ball", 0.38), ("shoot", 0.26), ("dribble", 0.22), ("cutback", 0.14)])
            return weighted_choice(self.rng, [("cross", 0.38), ("cutback", 0.28), ("dribble", 0.20), ("through_ball", 0.14)])
        return "through_ball"

    def _foul_probability(self, defender, attacker, ctx) -> float:
        aggression = defender.effective("aggression") / 100.0; discipline = defender.effective("discipline") / 100.0; attacker_dribble = attacker.effective("dribbling") / 100.0
        return clamp(0.025 + 0.10 * aggression + 0.05 * attacker_dribble + 0.05 * ctx["pressure"] - 0.08 * discipline, 0.015, 0.18)

    def _zone_data(self, zone: Zone) -> dict:
        return {"band": zone.band.value, "lane": zone.lane.value}

    def _emit(self, typ, team, relevance, text_key, **data) -> Event:
        ev = Event(minute=round(self.minute, 2), team=team, type=typ, relevance=relevance, text_key=text_key, data=data); self.state.event_log.append(ev); return ev


POSITION_TEMPLATE = {
    "GK": dict(reflexes=82, handling=80, gk_positioning=81, one_on_one=80, passing=65, vision=60, technique=62, pace=50, finishing=25, long_shots=25, heading=45, tackling=35, positioning=76, anticipation=72, composure=73, off_ball=35, stamina=70, strength=72, dribbling=45, crossing=35),
    "CB": dict(pace=68, passing=69, vision=65, technique=66, dribbling=58, crossing=50, finishing=45, long_shots=45, heading=80, strength=82, tackling=81, positioning=80, anticipation=78, composure=72, off_ball=55, stamina=76, aggression=72, discipline=72),
    "LB": dict(pace=80, passing=72, vision=68, technique=72, dribbling=74, crossing=78, finishing=52, long_shots=58, heading=62, strength=68, tackling=74, positioning=73, anticipation=72, composure=68, off_ball=72, stamina=82, aggression=64, discipline=72),
    "RB": dict(pace=80, passing=72, vision=68, technique=72, dribbling=74, crossing=78, finishing=52, long_shots=58, heading=62, strength=68, tackling=74, positioning=73, anticipation=72, composure=68, off_ball=72, stamina=82, aggression=64, discipline=72),
    "DM": dict(pace=70, passing=77, vision=74, technique=74, dribbling=68, crossing=62, finishing=55, long_shots=64, heading=70, strength=77, tackling=80, positioning=80, anticipation=79, composure=76, off_ball=66, stamina=82, aggression=72, discipline=74),
    "CM": dict(pace=73, passing=81, vision=80, technique=79, dribbling=76, crossing=70, finishing=65, long_shots=72, heading=62, strength=70, tackling=70, positioning=74, anticipation=77, composure=78, off_ball=76, stamina=82, aggression=63, discipline=74),
    "AM": dict(pace=77, passing=81, vision=84, technique=83, dribbling=82, crossing=74, finishing=75, long_shots=78, heading=58, strength=64, tackling=48, positioning=70, anticipation=76, composure=80, off_ball=82, stamina=76, aggression=52, discipline=74),
    "LW": dict(pace=84, passing=74, vision=74, technique=80, dribbling=84, crossing=78, finishing=74, long_shots=72, heading=55, strength=63, tackling=45, positioning=66, anticipation=73, composure=75, off_ball=82, stamina=78, aggression=50, discipline=74),
    "RW": dict(pace=84, passing=74, vision=74, technique=80, dribbling=84, crossing=78, finishing=74, long_shots=72, heading=55, strength=63, tackling=45, positioning=66, anticipation=73, composure=75, off_ball=82, stamina=78, aggression=50, discipline=74),
    "ST": dict(pace=78, passing=66, vision=68, technique=76, dribbling=75, crossing=55, finishing=84, long_shots=73, heading=80, strength=79, tackling=38, positioning=64, anticipation=77, composure=80, off_ball=84, stamina=76, aggression=64, discipline=72),
}
DEFAULT_XI = ["GK", "RB", "CB", "CB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
DEFAULT_BENCH = ["GK", "CB", "LB", "RB", "DM", "CM", "AM", "RW", "LW", "ST"]


def _scaled_player(name: str, position: str, strength: int, rng: random.Random) -> Player:
    template = POSITION_TEMPLATE[position]; kwargs = {}; delta = strength - 75
    for attr, base in template.items(): kwargs[attr] = int(max(20, min(95, round(base + delta * 0.72 + rng.gauss(0, 3.2)))))
    overall = int(max(55, min(92, round(strength + rng.gauss(0, 2.0)))))
    return Player(name=name, position=position, overall=overall, **kwargs)


def make_generic_team(name: str, strength: int = 75, style: str = "balanced", seed: int = 1) -> Team:
    rng = random.Random(seed)
    starters = [_scaled_player(f"{name} {pos}{i+1}", pos, strength, rng) for i, pos in enumerate(DEFAULT_XI)]
    bench = [_scaled_player(f"{name} B{pos}{i+1}", pos, strength - 1, rng) for i, pos in enumerate(DEFAULT_BENCH)]
    styles = {
        "balanced": Tactics(),
        "attacking": Tactics(mentality=0.55, tempo=0.67, width=0.62, pressing=0.67, defensive_line=0.65, compactness=0.50, directness=0.52, counter=0.63, overlap_left=0.62, overlap_right=0.62, cross_frequency=0.48, risk=0.65),
        "defensive": Tactics(mentality=-0.52, tempo=0.35, width=0.42, pressing=0.36, defensive_line=0.28, compactness=0.78, directness=0.43, counter=0.62, overlap_left=0.18, overlap_right=0.18, cross_frequency=0.42, risk=0.28),
        "pressing": Tactics(mentality=0.25, tempo=0.70, width=0.52, pressing=0.86, defensive_line=0.74, compactness=0.62, directness=0.48, counter=0.70, overlap_left=0.45, overlap_right=0.45, cross_frequency=0.40, risk=0.58),
        "direct": Tactics(mentality=0.18, tempo=0.64, width=0.58, pressing=0.48, defensive_line=0.46, compactness=0.50, directness=0.82, counter=0.76, overlap_left=0.38, overlap_right=0.38, cross_frequency=0.66, risk=0.61),
    }
    if style not in styles: raise ValueError(f"Unknown style {style!r}. Choose from {sorted(styles)}")
    return Team(name=name, starters=starters, bench=bench, tactics=styles[style])


def simulate_full_match(home: Team, away: Team, seed: Optional[int] = None, config: Optional[MatchConfig] = None) -> MatchEngine:
    engine = MatchEngine(home, away, seed=seed, config=config); guard = 0
    while not engine.state.ended and guard < 5000:
        engine.step(); guard += 1
    if guard >= 5000: raise RuntimeError("Simulation guard reached.")
    return engine
