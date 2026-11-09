"""Event-scale movement intentions and shots from measured player geometry.

No outcomes or match totals are consulted by movement or the xG model.
StatsBomb reference coefficients describe average chance quality, not finishing.
"""
from copy import deepcopy
from math import atan2, exp, hypot
from pathlib import Path
import json

from engine import Band, Lane, Zone, clamp, weighted_choice
from engine_experiment_v13_coordinates import MatchEngineV13Coordinates
from spatial_shot_v13 import _stable_fraction

# Context calibration on the first 600 synthetic league fixtures (112000–112599),
# frozen before the independent 114000–114299 validation. No score quotas.
CONTEXT_LOGIT_OFFSET = .14
OPEN_PLAY_TIME_SCALE = .96
FIRST_CAUTION_SCALE = 1.16

MODEL = json.loads((Path(__file__).parent / 'data/spatial_shot_reference_v13.json').read_text())['coefficients']


class MatchEngineV13CoordinatePlay(MatchEngineV13Coordinates):
    def __init__(self, *args, **kwargs):
        self._movement_plan = None
        self._movement_budget = {}
        self._delivery = None
        super().__init__(*args, **kwargs)

    def _intended_point(self, team, ps, zone):
        u = _stable_fraction('receiving-depth', self.seed, self.state.second, team, ps.player.name)
        v = _stable_fraction('receiving-width', self.seed, self.state.second, team, ps.player.name)
        # Intent describes the action's sector; reach is still limited by pace
        # and elapsed time. Wide lanes retain shooting-angle disadvantages.
        x = {Band.DEF: 18.+16*u, Band.MID: 38.+27*u,
             Band.ATT: 80.+15*u, Band.BOX: 89.+12*u}[zone.band]
        y = {Lane.LEFT: 15.+12*v, Lane.CENTER: 27.+14*v,
             Lane.RIGHT: 41.+12*v}[zone.lane]
        aerial_runner = getattr(self, '_aerial_runner', None)
        if zone.band == Band.BOX and (getattr(self, '_receiving_action', None) in {'cross','cutback','through_ball'} or aerial_runner == (team, ps.player.name) or getattr(self, '_corner_setup_team', None) == team):
            x, y = 93.+9*u, 27.+14*v
        return self._to_world(team, x, y)

    def _run_towards(self, ps, target, metres):
        dx, dy = target[0]-ps.x, target[1]-ps.y
        distance = hypot(dx, dy)
        fraction = min(1., max(0., metres)/distance) if distance else 0.
        ps.x += dx*fraction
        ps.y += dy*fraction
        owner = self._xy_ball.get('owner')
        if owner and self.teams[owner['team']].by_name(owner['player']) is ps and self._xyz_flight is None:
            self._xy_ball.update(x=ps.x, y=ps.y)
        return distance*fraction

    def _choose_actor(self, team, zone):
        ps = super()._choose_actor(team, zone)
        if getattr(self, '_planning_open_play', False):
            self._movement_plan = (team, ps.player.name, zone)
        return ps

    def _open_play_step(self):
        self._planning_open_play = True
        try:
            return super()._open_play_step()
        finally:
            self._planning_open_play = False

    def _switch_possession(self, new_team, zone, transition=0.0):
        if new_team != self.state.possession:
            self._delivery = None
        return super()._switch_possession(new_team, zone, transition)

    def _resolve_pending(self):
        p = self.state.pending
        if p is not None:
            zone = Zone(Band.BOX, p.zone.lane) if p.kind == 'dribble' else p.zone
            if p.origin in {'cross','corner'} and p.kind == 'shoot':
                zone = Zone(Band.BOX, Lane.CENTER)
                self._aerial_runner = (p.team, p.actor)
            self._movement_plan = (p.team, p.actor, zone)
            actor = self.teams[p.team].by_name(p.actor)
            destination = self._intended_point(p.team, actor, zone)
            distance = hypot(destination[0]-actor.x, destination[1]-actor.y)
            self._advance_clock(min(5., max(.5, distance/6.)), p.team)
            if p.kind in {'cross', 'long_ball'}:
                self._delivery = {'team':p.team, 'creator':p.actor, 'x':actor.x, 'y':actor.y,
                                  'kind':p.kind, 'second':self.state.second}
        previous = getattr(self, '_receiving_action', None)
        self._receiving_action = p.kind if p is not None else None
        try:
            return super()._resolve_pending()
        finally:
            self._receiving_action = previous

    def _move_players(self, seconds):
        before = {(t, ps.player.name): (ps.x, ps.y) for t, rt in enumerate(self.teams) for ps in rt.on_field}
        super()._move_players(seconds)
        plan = getattr(self, '_movement_plan', None)
        self._movement_budget = {}
        for t, rt in enumerate(self.teams):
            for ps in rt.on_field:
                old = before[t, ps.player.name]
                allowance = (3.+.05*ps.effective('pace'))*(.6+.4*ps.energy)*max(0., seconds)
                zone = None
                if plan and (t, ps.player.name) == plan[:2]:
                    zone = plan[2]
                elif getattr(self, '_corner_setup_team', None) == t and ps.player.name in getattr(self, '_corner_runners', set()):
                    zone = Zone(Band.BOX, Lane.CENTER)
                hold = getattr(self, '_contact_hold', None)
                if hold and (t, ps.player.name) == hold[:2]:
                    ps.x, ps.y = old
                    zone = None
                if zone is not None:
                    ps.x, ps.y = old
                    fixed = getattr(self, '_restart_taker', None)
                    target = fixed[2] if fixed and (t, ps.player.name) == fixed[:2] else self._intended_point(t, ps, zone)
                    self._run_towards(ps, target, allowance)
                travelled = hypot(ps.x-old[0], ps.y-old[1])
                self._movement_budget[t, ps.player.name] = max(0., allowance-travelled)
        owner = self._xy_ball.get('owner')
        if owner and self._xyz_flight is None:
            ps = self.teams[owner['team']].by_name(owner['player'])
            self._xy_ball.update(x=ps.x, y=ps.y)

    def _create_or_resolve_danger(self, team, actor, zone, kind, ctx):
        self._receiving_action = kind
        try:
            return super()._create_or_resolve_danger(team, actor, zone, kind, ctx)
        finally:
            self._receiving_action = None

    def _carry(self, team, actor, zone, ctx):
        intent = Zone({Band.DEF:Band.MID, Band.MID:Band.ATT, Band.ATT:Band.BOX, Band.BOX:Band.BOX}[zone.band], zone.lane)
        remaining = self._movement_budget.get((team, actor.player.name), 0.)
        used = self._run_towards(actor, self._intended_point(team, actor, intent), remaining)
        self._movement_budget[team, actor.player.name] = max(0., remaining-used)
        return super()._carry(team, actor, zone, ctx)

    def _choose_target(self, team, zone, attacking=True, exclude=None, action=None):
        previous = getattr(self, '_receiving_action', None)
        self._receiving_action = action or previous
        try:
            ps = super()._choose_target(team, zone, attacking, exclude, action)
        finally:
            self._receiving_action = previous
        if getattr(self, '_xy_ready', False) and attacking:
            action = action or getattr(self, '_receiving_action', None)
            band = Band.BOX if action in {'cross','cutback','through_ball'} else {Band.DEF:Band.MID, Band.MID:Band.ATT, Band.ATT:Band.ATT, Band.BOX:Band.BOX}[zone.band]
            receiving_zone = Zone(band, Lane.CENTER if action in {'cross','cutback','through_ball'} else zone.lane)
            remaining = getattr(self, '_movement_budget', {}).get((team, ps.player.name), 0.)
            used = self._run_towards(ps, self._intended_point(team, ps, receiving_zone), remaining)
            self._movement_budget[team, ps.player.name] = max(0., remaining-used)
        return ps

    def _base_target_weights(self, team, zone, actor, ctx=None):
        rows = super()._base_target_weights(team, zone, actor, ctx)
        if getattr(self, '_xy_ready', False) and getattr(self, '_receiving_action', None) in {'cross','cutback','through_ball'}:
            result = []
            for ps, weight in rows:
                target = self._intended_point(team, ps, Zone(Band.BOX,Lane.CENTER))
                required = hypot(target[0]-ps.x,target[1]-ps.y)
                available = self._movement_budget.get((team,ps.player.name),0.)
                result.append((ps,weight*exp(-max(0.,required-available)/8.)))
            return result
        return rows

    def _advance_clock(self, seconds, possession_team):
        # Beats represent circulation as well as preparation. Explicit new
        # receiving runs and restart set-up replace part of that old envelope.
        if getattr(self, '_planning_open_play', False):
            seconds *= OPEN_PLAY_TIME_SCALE
        return super()._advance_clock(seconds, possession_team)

    def shot_geometry_context(self, p, shooter):
        x, y = self._to_team(p.team, shooter.x, shooter.y)
        dx, dy = 105.-x, 34.-y
        return {'distance': hypot(dx, dy),
                'angle': abs(atan2(3.66-dy, max(.1,dx))-atan2(-3.66-dy, max(.1,dx))),
                'inside_box': x >= 88.5 and abs(dy) <= 20.16}

    def _physical_zone(self, team, ps):
        return self._physical_zone_at(team, ps.x, ps.y)

    def _physical_zone_at(self, team, world_x, world_y):
        x, y = self._to_team(team, world_x, world_y)
        band = Band.BOX if x >= 88.5 and abs(y-34.) <= 20.16 else Band.ATT if x >=70 else Band.MID if x>=35 else Band.DEF
        lane = Lane.LEFT if y<27 else Lane.RIGHT if y>41 else Lane.CENTER
        return Zone(band, lane)

    def _calculate_xg(self, p, shooter, defender, keeper):
        g = self.shot_geometry_context(p, shooter)
        features = {'intercept': 1., 'distance': g['distance'], 'angle': g['angle'],
                    'header': p.body_part == 'head', 'pressure': p.pressure,
                    'cross': p.origin in {'cross','corner'}, 'cutback': p.origin == 'cutback',
                    'freekick': p.origin == 'free_kick'}
        score = CONTEXT_LOGIT_OFFSET + sum(MODEL[k]*features[k] for k in MODEL)
        return clamp(1./(1.+exp(-score)), .001, .95)

    def _card_probabilities(self, defending_team, defender, incident, zone, foul_count_after):
        probs = super()._card_probabilities(defending_team,defender,incident,zone,foul_count_after)
        if not defender.yellow:
            probs = {**probs, 'yellow':min(1.,FIRST_CAUTION_SCALE*probs['yellow'])}
        return probs

    def _emit(self, event_type, team, relevance, text_key, **data):
        if getattr(self, '_xy_ready', False) and event_type.value == 'danger':
            name = data.get('creator') or data.get('crosser') or data.get('actor')
            if name and data.get('kind') in {'cross','long_ball'}:
                try:
                    ps = self.teams[team].by_name(name)
                    self._delivery = {'team': team, 'creator': name, 'x': ps.x, 'y': ps.y,
                                      'kind': data['kind'], 'second': self.state.second}
                except KeyError:
                    pass
        return super()._emit(event_type, team, relevance, text_key, **data)

    def _resolve_restart(self):
        corner = self.state.restart == 'corner'
        if corner:
            self._corner_setup_team = self.state.restart_team
            outfield = [p for p in self.teams[self.state.restart_team].on_field if p.player.position != 'GK' and not p.red]
            self._corner_runners = {p.player.name for p in sorted(outfield, key=lambda p:p.effective('heading')+p.effective('off_ball'), reverse=True)[:7]}
            self._delivery = {'team': self.state.restart_team, 'x': self._xy_ball['x'],
                              'y': self._xy_ball['y'], 'kind': 'corner', 'second': self.state.second}
            self._advance_clock(12., self.state.restart_team)
        elif self.state.restart == 'free_kick':
            team = self.state.restart_team
            taker = self._best_player(team, ('technique','long_shots','composure'), exclude_positions={'GK'})
            point = (self._xy_ball['x'],self._xy_ball['y'])
            self._restart_taker = (team,taker.player.name,point)
            self._movement_plan = (team,taker.player.name,self.state.restart_zone or self.state.zone)
            self._advance_clock(min(12.,hypot(taker.x-point[0],taker.y-point[1])/6.),team)
        try:
            return super()._resolve_restart()
        finally:
            self._corner_setup_team = None
            self._restart_taker = None

    def _corner_target(self, team, taker, zone, pattern):
        rows = []
        for ps in self.teams[team].on_field:
            if ps.red or ps.player.position == 'GK' or ps is taker:
                continue
            x, y = self._to_team(team, ps.x, ps.y)
            distance = hypot(94.-x, 34.-y)
            skill = .4*ps.effective('heading')+.3*ps.effective('off_ball')+.3*ps.effective('anticipation')
            rows.append((ps, max(.001, skill*exp(-distance/12.))))
        return weighted_choice(self.rng, rows)

    def _rebound_attacker_rows(self, team, shooter, zone):
        rows = super()._rebound_attacker_rows(team, shooter, zone)
        point = getattr(self, '_rebound_point', None) or self._to_world(team,94.,34.)
        return [(ps, w*exp(-hypot(ps.x-point[0],ps.y-point[1])/12.)) for ps,w in rows]

    def _rebound_defender_rows(self, team, zone):
        rows = super()._rebound_defender_rows(team, zone)
        point = getattr(self, '_rebound_point', None) or self._to_world(1-team,94.,34.)
        return [(ps, w*exp(-hypot(ps.x-point[0],ps.y-point[1])/12.)) for ps,w in rows]

    def _create_rebound(self, team, p, shooter, xg, blocked=False, post=False):
        self._rebound_point = (shooter.x,shooter.y) if blocked else self._to_world(team,102.,34.)
        try:
            return super()._create_rebound(team,p,shooter,xg,blocked=blocked,post=post)
        finally:
            self._rebound_point = None

    def _resolve_shot(self, p):
        shooter = self.teams[p.team].by_name(p.actor)
        p.zone = self._physical_zone(p.team, shooter)
        delivery = getattr(self, '_delivery', None)
        valid = (delivery and delivery['team'] == p.team and
                 0 <= self.state.second-delivery['second'] <= 100 and
                 p.origin in {'cross','corner','long_ball'})
        observed = (self._xy_source == 'external' and .6 <= self._xy_ball['z'] <= 2.8
                    and hypot(shooter.x-self._xy_ball['x'],shooter.y-self._xy_ball['y']) <= 2.)
        # Only an actual aerial delivery can yield an aerial contact. Ground
        # shots use the preferred foot, including when a legacy selector asked
        # for a header without a delivery.
        requested = getattr(self, '_v13_forced_shot_body_part', None)
        head = (valid or observed) and (p.body_part == 'head' or requested and requested.get('part') == 'head')
        if head:
            part = 'head'
        elif requested and requested.get('team') == p.team and requested.get('actor') == p.actor and requested.get('part') != 'head':
            part = requested['part']
        else:
            ctx = {'pressure':p.pressure, 'space':1.-p.pressure, 'space_behind':.35, 'support':.5}
            part = self._select_action_body_part(shooter, 'shoot', p.zone, ctx, source=p.origin or 'open_play')
            if part not in {'left_foot', 'right_foot'}:
                part = 'left_foot' if str(shooter.player.preferred_foot).upper() == 'L' else 'right_foot'
        if part not in {'head','left_foot','right_foot'}:
            part = 'left_foot' if str(shooter.player.preferred_foot).upper() == 'L' else 'right_foot'
        if valid:
            self._xy_ball = {'x': delivery['x'], 'y': delivery['y'], 'z': 0., 'owner': None}
            flight = self.launch_ball(shooter.x, shooter.y, z=1.6 if head else .2,
                                      speed=18., aerial=True, kind=delivery['kind'])
            # The event engine treats contact as the terminal instant of this
            # delivery; the clock and all other players advance by flight time.
            contact = (shooter.x, shooter.y)
            self._movement_plan = (p.team, p.actor, p.zone)
            self._contact_hold = (p.team, p.actor, contact)
            try:
                self._advance_clock(flight['duration'], p.team)
            finally:
                self._contact_hold = None
            shooter.x, shooter.y = contact
            self._xy_ball.update(x=shooter.x, y=shooter.y, z=1.6 if head else .2, owner=None)
            self._xyz_flight = None
        else:
            self._xy_ball.update(x=shooter.x, y=shooter.y)
            if not observed and self._xy_ball['z'] > .5:
                # An unrelated stale flight is not a shot assist.
                self._xy_ball['z'] = 0.
            self._xyz_flight = None
        self._v13_forced_shot_body_part = {'team':p.team, 'actor':p.actor, 'part':part,
                                          'modifier':self._part_execution_modifier(shooter, 'shoot', part)}
        p.body_part = part
        geometry = self.shot_geometry_context(p, shooter)
        self._contact_hold = (p.team, p.actor, (shooter.x, shooter.y))
        self._movement_plan = None
        contact_height = self._xy_ball['z']
        origin = {'x':shooter.x, 'y':shooter.y, 'z':contact_height}
        try:
            event = super()._resolve_shot(p)
        finally:
            self._contact_hold = None
        event.data['shot_origin_coordinates'] = origin
        event.data['shot_geometry_context'] = geometry
        event.data['delivery_origin_coordinates'] = deepcopy(delivery) if valid else ({'source':'external_frame','z':contact_height} if observed else None)
        self._delivery = None
        return event

    def step(self):
        self._movement_budget = {}
        self._movement_plan = None
        self._aerial_runner = None
        try:
            event = super().step()
            owner = self._xy_ball.get('owner')
            if owner is not None and self._xyz_flight is None:
                ps = self.teams[owner['team']].by_name(owner['player'])
                self._xy_ball.update(x=ps.x,y=ps.y)
                event.data['ball_coordinates'] = deepcopy(self._xy_ball)
            return event
        finally:
            self._movement_budget = {}
            self._movement_plan = None
            self._aerial_runner = None

    def export_state(self):
        data = super().export_state()
        data['v13_coordinate_play'] = {'delivery': deepcopy(getattr(self, '_delivery', None))}
        return data

    @classmethod
    def from_state_dict(cls, data):
        obj = super().from_state_dict(data)
        obj._delivery = deepcopy(data.get('v13_coordinate_play', {}).get('delivery'))
        if obj._delivery is not None:
            d = obj._delivery
            obj._team(d['team'])
            obj._point(d['x'], d['y'])
            if not isinstance(d['second'], (float,int)) or not 0 <= d['second'] <= obj.state.second or d['kind'] not in {'cross','corner','long_ball'}:
                raise ValueError('Invalid saved delivery')
        obj._movement_budget = {}
        obj._movement_plan = None
        return obj
