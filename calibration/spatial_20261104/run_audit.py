"""Outcome-blind paired audit. Never mutates a runtime to hit real statistics."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import time
import traceback

parser = argparse.ArgumentParser()
parser.add_argument("--engine-root", type=Path, required=True)
parser.add_argument("--start-seed", type=int, required=True)
parser.add_argument("--count", type=int, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--parity-check", action="store_true")
args = parser.parse_args()
sys.path.insert(0, str(args.engine_root.resolve()))

from engine import make_generic_team, Band
from engine_experiment_v13 import MatchEngine
from real_match_benchmark_v13 import (
    STRENGTHS, STRENGTH_WEIGHTS, STYLES, STYLE_WEIGHTS, _weighted_pick,
    _engine_match_record, RESERVED_OFFICIAL_FINAL_SEED,
)
from shot_accuracy_diagnostics_v13 import ShotAuditEngine, _context_cell
from narration_packet_v13 import _public_clock_components


class ObservedEngine(ShotAuditEngine):
    def __init__(self, *a, **kw):
        self.audit_counts = Counter()
        self.audit_examples = []
        self.audit_distances = defaultdict(list)
        self.audit_shots = []
        super().__init__(*a, **kw)

    def violation(self, name, **data):
        self.audit_counts[name] += 1
        if len(self.audit_examples) < 16:
            self.audit_examples.append({"kind": name, "second": self.state.second, **data})

    def _advance_clock(self, seconds, possession_team):
        spatial = hasattr(self, "pitch_snapshot") and getattr(self, "_xy_ready", False)
        before = {(t, ps.player.name): (ps.x, ps.y) for t, rt in enumerate(self.teams)
                  for ps in rt.on_field} if spatial else {}
        super()._advance_clock(seconds, possession_team)
        if spatial and seconds > 0:
            for t, rt in enumerate(self.teams):
                for ps in rt.on_field:
                    old = before.get((t, ps.player.name))
                    if old is None:
                        continue
                    speed = math.hypot(ps.x-old[0], ps.y-old[1])/seconds
                    self.audit_counts["movement_samples"] += 1
                    self.audit_counts["max_speed_mps"] = max(self.audit_counts["max_speed_mps"], speed)
                    if speed > 8.5 + 1e-7:
                        self.violation("speed_limit_violation", player=ps.player.name, speed=speed)

    def _resolve_shot(self, p):
        spatial = hasattr(self, "pitch_snapshot")
        origin = None
        if spatial:
            try:
                ps = self.teams[p.team].by_name(p.actor)
                origin = (ps.x, ps.y, self._xy_ball["z"])
            except KeyError:
                pass
        nearest = min((math.hypot(o.x-ps.x,o.y-ps.y) for o in self.teams[1-p.team].on_field),default=105.) if origin else None
        count = len(self.shot_audit)
        event = super()._resolve_shot(p)
        if len(self.shot_audit) == count:
            return event
        shot = self.shot_audit[-1]
        point = event.data.get("shot_origin_coordinates")
        if point:
            origin = (point["x"], point["y"], point["z"])
        shot["body_part"] = event.data.get("body_part", shot["body_part"])
        record = {k: shot[k] for k in ("body_part", "band", "origin", "xg", "pressure", "danger", "on_target", "goal", "blocked")}
        record["cell"] = _context_cell(shot)
        record["nearest_defender_metres"] = nearest
        if origin is not None:
            direction = self.attack_direction(p.team)
            goal_x = 105. if direction == 1 else 0.
            distance = math.hypot(goal_x-origin[0], 34.-origin[1])
            proxy = {Band.BOX: 12., Band.ATT: 24., Band.MID: 40., Band.DEF: 65.}[p.zone.band]
            used = event.data.get("shot_distance_m", proxy)
            geometry = event.data.get("shot_geometry_context", {})
            used = geometry.get("distance", used)
            record.update(distance=distance, x=origin[0], y=origin[1], z=origin[2],
                          angle=geometry.get("angle"), team_y=origin[1] if direction == 1 else 68.-origin[1], team_x=origin[0] if direction == 1 else 105.-origin[0],
                          distance_used=used, inside_box=(origin[0] if direction == 1 else 105.-origin[0])>=88.5 and abs(origin[1]-34.)<=20.16)
            self.audit_distances["used_distance_error"].append(abs(distance-used))
            self.audit_distances["shot_metres"].append(distance)
            self.audit_distances["zone_distance_absolute_error"].append(abs(distance-proxy))
            self.audit_counts["shots_with_coordinates"] += 1
            if abs(distance-proxy) > 10:
                self.violation("shot_distance_proxy_gap_over_10m", player=p.actor,
                               band=p.zone.band.value, physical_metres=distance, proxy_metres=proxy)
            team_x = origin[0] if direction == 1 else 105.-origin[0]
            if p.zone.band == Band.BOX:
                self.audit_counts["box_labelled_shots"] += 1
                if not (team_x >= 88.5 and abs(origin[1]-34.) <= 20.16):
                    self.violation("box_label_outside_physical_penalty_area", player=p.actor,
                                   x=origin[0], y=origin[1], physical_metres=distance)
            if shot["body_part"] == "head":
                self.audit_counts["headers_with_height"] += 1
                self.audit_distances["header_ball_height"].append(origin[2])
                if origin[2] < .5:
                    self.violation("header_ball_height_below_0_5m", player=p.actor, z=origin[2])
        self.audit_shots.append(record)
        return event

    def step(self):
        event = super().step()
        if not hasattr(self, "pitch_snapshot"):
            return event
        frame = self.pitch_snapshot()
        self.audit_counts["spatial_frames"] += 1
        if len(frame["players"]) != sum(len(rt.on_field) for rt in self.teams):
            self.violation("active_frame_count_mismatch")
        for p in frame["players"]:
            if not all(math.isfinite(p[k]) for k in ("x", "y")) or not (0 <= p["x"] <= 105 and 0 <= p["y"] <= 68):
                self.violation("invalid_player_point", player=p["player"], x=p["x"], y=p["y"])
        ball = frame["ball"]
        if not all(math.isfinite(ball[k]) for k in ("x", "y", "z")) or ball["z"] < 0:
            self.violation("invalid_ball_xyz", ball=ball)
        self.audit_counts["airborne_frames"] += int(ball["z"] > .5)
        self.audit_counts["live_flight_frames"] += int(frame["ball_flight"] is not None)
        self.audit_counts["max_ball_height"] = max(self.audit_counts["max_ball_height"], ball["z"])
        owner = ball["owner"]
        if owner:
            try:
                ps = self.teams[owner["team"]].by_name(owner["player"])
                gap = math.hypot(ps.x-ball["x"], ps.y-ball["y"])
                if gap > 2.:
                    self.violation("owner_ball_gap_over_2m", player=ps.player.name, gap=gap)
            except KeyError:
                self.violation("inactive_ball_owner", owner=owner)
        return event


def fixture(seed, cls=ObservedEngine):
    rng = random.Random(f"v13-real-population:{seed}")
    hs, aws = [int(_weighted_pick(rng, STRENGTHS, STRENGTH_WEIGHTS)) for _ in range(2)]
    hstyle, astyle = [_weighted_pick(rng, STYLES, STYLE_WEIGHTS) for _ in range(2)]
    return cls(make_generic_team(f"Benchmark Home {seed}", hs, hstyle, seed=900000+seed*2),
               make_generic_team(f"Benchmark Away {seed}", aws, astyle, seed=900001+seed*2),
               seed=seed, venue_context={"mode": "home_away", "source": "real_league_benchmark"}), {
                   "home_strength": hs, "away_strength": aws, "home_style": hstyle, "away_style": astyle}


def complete(engine):
    for _ in range(7000):
        if engine.state.ended:
            break
        engine.step()
    if not engine.state.ended:
        raise RuntimeError("Simulation guard reached")
    coverage = engine.shot_ledger_coverage()
    if not coverage["complete"]:
        raise AssertionError("Incomplete shot ledger")
    ledger = engine.shot_ledger_diagnostic()
    if len({r["shot_id"] for r in ledger}) != len(ledger):
        raise AssertionError("Duplicate shot ID")
    if abs(sum(r["xg"] for r in ledger)-sum(s.xg for s in engine.stats)) > 1e-7:
        raise AssertionError("xG accounting mismatch")
    return _engine_match_record(engine)


def match_extra(engine):
    stop = getattr(engine, "_v13_stoppage", {}) or {}
    announced = stop.get("announced_seconds_by_marker", {}) or {}
    count = Counter()
    count["recorded_pass_events"] = 0
    for event in engine.state.event_log:
        d = event.data or {}
        typ = event.type.value
        if typ == "goal" and not d.get("shootout"):
            count["goals_90plus_raw_clock"] += int(event.minute >= 90.)
            public_second, _ = _public_clock_components(engine, float(event.minute)*60.)
            count["goals_90plus_public_clock"] += int(public_second >= 90.*60.)
        if event.text_key == "safe_pass" or (typ == "progression" and d.get("kind") in {"progressive_pass", "switch", "long_ball"}):
            count["recorded_pass_events"] += 1
        if d.get("goalkeeper_one_v_one"):
            count["one_v_ones"] += 1
            count["one_v_one_goals"] += int(typ == "goal")
        if event.text_key in {"penalty_goal", "penalty_saved", "penalty_missed"} and not d.get("shootout"):
            count["penalties"] += 1
            count["penalty_goals"] += int(typ == "goal")
        count["muscular_injuries"] += int(event.text_key == "muscular_load_injury")
        count["substitutions"] += int(typ == "substitution")
    return {"first_half_added": float(announced.get("45", 0.))/60,
            "second_half_added": float(announced.get("90", 0.))/60,
            "final_minute": engine.minute, "xg": sum(s.xg for s in engine.stats), **count}


seeds = list(range(args.start_seed, args.start_seed+args.count))
if RESERVED_OFFICIAL_FINAL_SEED in seeds or args.count <= 0:
    raise ValueError("Invalid or quarantined seed schedule")
result = {"engine_commit": subprocess.check_output(["git", "-C", str(args.engine_root), "rev-parse", "HEAD"], text=True).strip(),
          "seed_policy": "contiguous_unfiltered", "seeds": seeds, "matches": [], "failures": [],
          "spatial_counts": Counter(), "spatial_distances": defaultdict(list),
          "spatial_examples": [], "shots": [], "shot_groups": {}, "shot_cells": {}, "parity_checked": False}
groups, cells = defaultdict(Counter), defaultdict(Counter)
started = time.monotonic()
for index, seed in enumerate(seeds):
    try:
        engine, population = fixture(seed)
        row = complete(engine)
        if args.parity_check and index == 0:
            control, _ = fixture(seed, MatchEngine)
            complete(control)
            if engine.export_state() != control.export_state():
                raise AssertionError("Audit observer changed engine state or RNG")
            result["parity_checked"] = True
        result["matches"].append({"seed": seed, "stats": row, "population": population,
                                  "extra": match_extra(engine)})
        for name, value in engine.audit_counts.items():
            if name.startswith("max_"):
                result["spatial_counts"][name] = max(result["spatial_counts"][name], value)
            else:
                result["spatial_counts"][name] += value
        for name, values in engine.audit_distances.items():
            result["spatial_distances"][name].extend(values)
        if len(result["spatial_examples"]) < 40:
            result["spatial_examples"].extend({"seed": seed, **r} for r in engine.audit_examples[:4])
        result["shots"].extend({"seed": seed, **shot} for shot in engine.audit_shots)
        for shot in engine.audit_shots:
            group = groups[shot["body_part"]]
            for key, value in (("attempts", 1), ("sot", shot["on_target"]), ("goals", shot["goal"]),
                               ("blocked", shot["blocked"]), ("xg", shot["xg"])):
                group[key] += value
            if shot["band"] == "box":
                cell = cells[shot["body_part"]+"|"+shot["cell"]]
                cell["attempts"] += 1
                cell["sot"] += shot["on_target"]
                cell["goals"] += shot["goal"]
    except Exception:
        result["failures"].append({"seed": seed, "traceback": traceback.format_exc()})
    if (index+1) % 25 == 0:
        print(f"{index+1}/{len(seeds)} complete; failures={len(result['failures'])}; seconds={time.monotonic()-started:.1f}", flush=True)
result["shot_groups"] = groups
result["shot_cells"] = cells
result["seconds"] = time.monotonic()-started
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
print(f"saved {args.output}; completed={len(result['matches'])}; failures={len(result['failures'])}", flush=True)
