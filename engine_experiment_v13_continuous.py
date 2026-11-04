"""Opt-in v1.3 continuous football engine; public runner mode 'continuous'.

Every simulated pass is released, travels and has one terminal outcome. Player
movement is integrated at 10 Hz with persisted velocity, acceleration limits,
turning, physical contact, drag/bounce and jumping. The event engine still owns
competition rules, discipline, substitutions and the public match clock.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from math import atan2, cos, exp, hypot, isfinite, log, pi, sin, sqrt

from engine import Band, EventType, Lane, PendingAction, Zone, MatchEngine as BaseClockEngine, clamp, weighted_choice
from engine_experiment_v13_coordinate_play import MatchEngineV13CoordinatePlay, MODEL
from engine_experiment_v13_coordinates import MatchEngineV13Coordinates
from engine_experiment_v13_rules_hardening import MatchEngineV13RulesHardening
from continuous_physics_v13 import (BallState, MotionState, PhysicalProfile, advance_ball,
    contact_height, finite, flight_to_target, move_player, offside_interference,
    offside_snapshot, resolve_collision, start_jump, swept_disc_fraction)
from spatial_shot_v13 import _stable_fraction, keeper_response

ENGINE_VERSION='1.3-candidate-continuous'
TICK=.1


class MatchEngineV13Continuous(MatchEngineV13CoordinatePlay):
    def __init__(self,*args,**kwargs):
        self._continuous_ready=False
        super().__init__(*args,**kwargs)
        self._init_continuous()
        self._continuous_ready=True
        self._reset_kickoff_coordinates()

    @staticmethod
    def _key(team,name):return f'{team}::{name}'

    def _draw(self,tag,*parts):
        return _stable_fraction('continuous-v1',self.seed,self._cs_action,tag,*parts)

    def _normal(self,tag,*parts):
        return sqrt(-2*log(max(1e-12,self._draw(tag+'u',*parts))))*cos(2*pi*self._draw(tag+'v',*parts))

    def _init_continuous(self):
        self._cs_motion={};self._cs_profiles={};self._cs_profile_sources={};self._cs_targets={}
        self._cs_events=[];self._cs_passes=[];self._cs_shots=[];self._cs_possessions=[]
        self._cs_action=0;self._cs_seq=0;self._cs_ticks=0;self._cs_remainder=0.;self._cs_auto_targets=None
        self._cs_time=float(self.state.second);self._cs_possession=None
        self._cs_totals={'controlled_seconds':[0.,0.],'loose_seconds':0.,'dead_seconds':0.,'in_play_seconds':0.,'collisions':0,'bounces':0}
        self._cs_ball=BallState(self._xy_ball['x'],self._xy_ball['y'],self._xy_ball['z'])
        self._cs_transport=None;self._cs_offside=None;self._cs_restart_point=None
        self._cs_last_touch=None;self._cs_last_assist=None;self._cs_pressure=None
        self._cs_shot_live=None;self._cs_keeper_target=None;self._cs_air_contact=None;self._cs_control_part='foot';self._cs_foul_contact=None
        self._cs_hold=False;self._cs_dead=False;self._cs_clock_depth=0
        self._cs_ensure_players()

    def attack_direction(self,team):
        team=self._team(team)
        phase=min(int(self.state.period_index),max(0,len(self.state.period_markers)-1))
        return (1 if team==0 else -1)*(-1 if phase%2 else 1)

    def _cs_ensure_players(self):
        for team,rt in enumerate(self.teams):
            for ps in rt.on_field:
                key=self._key(team,ps.player.name)
                if key in self._cs_motion:continue
                self._cs_profile_sources[key]='derived_role_prior'
                self._cs_motion[key]=MotionState(heading=0. if self.attack_direction(team)==1 else pi)
                u=_stable_fraction('physical-height',self.seed,team,ps.player.name)
                height={'GK':1.9,'CB':1.88,'ST':1.84,'DM':1.83}.get(ps.player.position,1.77)+(u-.5)*.12
                self._cs_profiles[key]=PhysicalProfile(height=height,mass=68.+(height-1.65)*55.,
                    radius=.31+(height-1.65)*.12,acceleration=2.+.022*ps.player.pace,
                    braking=4.5+.025*(ps.player.balance or ps.player.technique),
                    turn_rate=2.3+.012*ps.player.technique,sprint_speed=6.+.045*ps.player.pace,
                    jump_speed=2.5+.008*ps.player.pace+.005*ps.player.strength).validate()

    def set_player_physical_profile(self,team,player,**changes):
        self.teams[self._team(team)].by_name(player);key=self._key(team,player)
        p=PhysicalProfile(**{**asdict(self._cs_profiles[key]),**changes}).validate()
        self._cs_profiles[key]=p;self._cs_profile_sources[key]='explicit'

    def _record(self,kind,team=None,player=None,**data):
        self._cs_seq+=1
        row={'id':self._cs_seq,'second':self._cs_time,'kind':kind,'team':team,'player':player,**data}
        self._cs_events.append(row);return row

    def _end_control(self,reason):
        if self._cs_possession is not None:
            row={**self._cs_possession,'end_second':self._cs_time,'reason':reason}
            row['duration']=row['end_second']-row['start_second'];self._cs_possessions.append(row)
            self._cs_possession=None

    def _control(self,team,ps,*,source='loose',part='foot'):
        previous=self._xy_ball.get('owner')
        if self._cs_possession is None or self._cs_possession['team']!=team:
            self._end_control('turnover');self._cs_possession={'team':team,'start_second':self._cs_time,'origin':source}
        if previous is not None and previous['team']!=team:
            self._record('turnover',team,ps.player.name,from_team=previous['team'],source=source)
        self.state.possession=team;self.state.zone=self._physical_zone(team,ps)
        self._xy_ball={'x':ps.x,'y':ps.y,'z':0.,'owner':{'team':team,'player':ps.player.name}}
        self._cs_control_part=part
        self._cs_ball=BallState(ps.x,ps.y,1.1 if part=='hands' else 0.)
        self._xy_ball['z']=self._cs_ball.z
        self._cs_last_touch={'team':team,'player':ps.player.name,'second':self._cs_time,'deliberate':True}
        self._record('reception',team,ps.player.name,source=source,part=part,x=ps.x,y=ps.y,z=0.)
        self._record('control',team,ps.player.name,pressure=self._physical_pressure(team,ps.x,ps.y))

    def _loose(self,reason):
        self._xy_ball['owner']=None
        if reason not in {'release','shot_rebound','loose_ball'}:self._end_control(reason)

    def _physical_pressure(self,team,x,y):
        distances=[hypot(p.x-x,p.y-y) for p in self.teams[1-team].on_field if not p.red]
        return 1.-exp(-sum(exp(-d/3.5) for d in distances))

    def _physical_players(self):
        return [{'team':t,'player':p.player.name,'x':p.x,'y':p.y,'red':p.red,
                 'keeper':p is self._goalkeeper(t)} for t,rt in enumerate(self.teams) for p in rt.on_field]

    def freeze_offside(self,team,*,restart=None,body_points=None):
        direction=self.attack_direction(team);players=self._physical_players()
        explicit={}
        if body_points is not None:
            active={(p['team'],p['player']) for p in players}
            for point in body_points:
                if (point['team'],point['player']) not in active:raise ValueError('Unknown body point player')
                if point['part'] in {'hand','arm'}:continue
                if point['part'] not in {'head','torso','foot'}:raise ValueError('Unsupported playable body part')
                finite(point['x']);key=(point['team'],point['player'])
                explicit[key]=max(explicit.get(key,-float('inf')),point['x']*direction)
        for player in players:
            key=self._key(player['team'],player['player']);centre=player['x']
            front=explicit.get((player['team'],player['player']))
            player['centre_x']=centre
            player['x']=(front*direction if front is not None else centre+direction*(self._cs_profiles[key].radius*.65+min(.18,hypot(self._cs_motion[key].vx,self._cs_motion[key].vy)*.015)))
        ball={'x':self._xy_ball['x']+direction*.11,'y':self._xy_ball['y'],'z':self._xy_ball['z']}
        frame=offside_snapshot(team,ball,players,direction=direction,second=self._cs_time,restart=restart)
        frame['body_point_source']='tracking_and_profile' if body_points is not None else 'profile_disc_and_lean'
        frame['ball_centre']=dict(self._xy_ball)
        self._cs_offside=frame;return deepcopy(frame)

    def offside_line_diagnostic(self,attacking_team,zone,ctx=None,*,actor=None,target=None):
        previous=self._cs_offside
        try:frame=self.freeze_offside(attacking_team)
        finally:self._cs_offside=previous
        return {'mode':'geometric','frame':frame,'actor':actor,'target':target,'target_in_offside_position':bool(target in frame['flagged']) if target else None,'position_is_not_offence':True}

    def jump_player(self,team,player):
        team=self._team(team);ps=self.teams[team].by_name(player);key=self._key(team,player)
        started=start_jump(self._cs_motion[key],self._cs_profiles[key],ps.energy)
        if started:
            ps.energy=clamp(ps.energy-.0015,.18,1.)
            self._record('jump',team,player,vertical_speed=self._cs_motion[key].vz)
        return started

    def note_deliberate_opponent_play(self,team,*,save=False):
        if self._cs_offside and team!=self._cs_offside['team'] and not save:self._cs_offside=None
        self._record('opponent_play',team,deliberate_save=bool(save))

    def _run_towards(self,ps,target,metres):
        # Legacy call sites now declare an intention; only clock integration moves.
        for team,rt in enumerate(self.teams):
            if any(p is ps for p in rt.on_field):
                self._cs_targets[self._key(team,ps.player.name)]=(float(target[0]),float(target[1]),.9);break
        return 0.

    def _motion_targets(self):
        result={};ball=self._cs_ball
        owner=self._xy_ball.get('owner')
        if owner is None and self._cs_transport:
            owner={'team':self._cs_transport['team'],'player':self._cs_transport['receiver']}
        elif owner is None and self._cs_shot_live:
            owner={'team':self._cs_shot_live['team'],'player':self._cs_shot_live['shooter']}
        for team,rt in enumerate(self.teams):
            anchors=self._formation_anchors(team);bx,by=self._to_team(team,ball.x,ball.y)
            tactics=rt.team.tactics;keeper=self._goalkeeper(team)
            chase=sorted([p for p in rt.on_field if not p.red and p is not keeper],key=lambda p:hypot(p.x-ball.x,p.y-ball.y))
            pressers={p.player.name for p in chase[:max(1,round(1.+2.*tactics.pressing))]}
            for ps in rt.on_field:
                key=self._key(team,ps.player.name);ax,ay=anchors[ps.player.name]
                if ps is keeper:
                    ax=3.5+max(0.,bx-40.)*.10;ay=34.+(by-34.)*.15
                    effort=.65
                else:
                    has_ball=bool(owner and owner['team']==team)
                    ax += (8. if has_ball else -6.)+(bx-52.5)*.35+(tactics.defensive_line-.5)*12.
                    ay=34.+(ay-34.)*(.65+.65*tactics.width)+(by-34.)*.18
                    effort=.55+.28*tactics.tempo if has_ball else .5+.35*tactics.pressing
                    if owner and owner['team']!=team and ps.player.name in pressers:
                        ax,ay=self._to_team(team,ball.x,ball.y);effort=.65+.35*tactics.pressing
                if owner and owner['team']==team and ps is not keeper and owner['player']!=ps.player.name:
                    opponents=sorted((self._to_team(team,o.x,o.y)[0] for o in self.teams[1-team].on_field if not o.red),reverse=True)
                    if len(opponents)>=2:ax=min(ax,max(bx,opponents[1])-.6)
                if self.minute>=70:
                    if self.score[team]<self.score[1-team]:effort=min(1.,effort*1.1)
                    elif self.score[team]>self.score[1-team]:effort*=.94
                result[key]=(*self._to_world(team,clamp(ax,1.,104.),clamp(ay,1.,67.)),effort)
        if owner:
            defending=1-owner['team'];defenders=[p for p in self.teams[defending].on_field if not p.red and p is not self._goalkeeper(defending)]
            attackers=[p for p in self.teams[owner['team']].on_field if not p.red and p is not self._goalkeeper(owner['team'])]
            pairs=sorted((hypot(d.x-a.x,d.y-a.y),i,j) for i,d in enumerate(defenders) for j,a in enumerate(attackers))
            used_d=set();used_a=set();bx,by=self._to_team(defending,ball.x,ball.y);tactics=self.teams[defending].team.tactics
            for _,i,j in pairs:
                if i in used_d or j in used_a:continue
                used_d.add(i);used_a.add(j);ps=defenders[i];attacker=attackers[j]
                ax,ay=self._to_team(defending,attacker.x,attacker.y)
                goal_dist=hypot(ax,ay-34.);mark=(.6+.6*(1.-tactics.pressing)) if attacker.player.name==owner['player'] else 1.3+1.3*(1.-tactics.pressing)
                tx=ax-mark*ax/max(1.,goal_dist)
                if ps.player.position in {'CB','LB','RB'}:tx+=(tactics.defensive_line-.5)*12.
                ty=ay-mark*(ay-34.)/max(1.,goal_dist)
                tx=min(tx,bx+25.-10.*tactics.compactness)
                if ps.player.position in {'DM','CM'}:
                    tx=clamp(bx*(.56+.18*tactics.pressing),12.,42.)
                    ty=34.+(by-34.)*.45
                    if ps.player.position=='CM':ty+=7. if self._to_team(defending,ps.x,ps.y)[1]>=34. else -7.
                result[self._key(defending,ps.player.name)]=(*self._to_world(defending,clamp(tx,1.,104.),clamp(ty,1.,67.)),.65+.35*tactics.pressing)
        return result

    def _tick(self,dt,targets):
        self._cs_ensure_players()
        if not self._cs_dead:
            self.state.second=self._cs_time
            BaseClockEngine._advance_clock(self,dt,self.state.possession)
        self._cs_time=round(self._cs_time+dt,9);self._cs_ticks+=1
        if self._cs_auto_targets is None or self._cs_ticks%5==1:self._cs_auto_targets=self._motion_targets()
        targets=dict(self._cs_auto_targets);targets.update(self._cs_targets)
        if self._cs_transport:targets[self._key(self._cs_transport['team'],self._cs_transport['receiver'])]=(*self._cs_transport.get('run_target',self._cs_transport['target'][:2]),1.)
        env=self._v13_environment;grip={'dry':1.,'normal':.98,'slick':.86,'heavy':.82}[env['pitch']]
        grip*=.94 if env['weather']=='rain' else .88 if env['weather']=='heavy_rain' else 1.
        if self._cs_keeper_target and self._cs_time>=self._cs_keeper_target[2]:
            targets=dict(targets);targets[self._cs_keeper_target[0]]=self._cs_keeper_target[1]
        environment=self._environment_effects()
        environment_load=1.+.16*environment['heat_load']+.13*environment['heavy_ground_load']
        active=[]
        for team,rt in enumerate(self.teams):
            for ps in rt.on_field:
                if ps.red:continue
                key=self._key(team,ps.player.name);motion=self._cs_motion[key];profile=self._cs_profiles[key]
                target=targets.get(key,(ps.x,ps.y,0.));before=motion.positive_work
                ps.x,ps.y=move_player(ps.x,ps.y,motion,profile,target[:2],dt,effort=target[2],energy=ps.energy,grip=grip)
                # Physical work supplements existing metabolic/load accounting.
                work=(motion.positive_work-before)/(profile.mass*1000.)
                speed=hypot(motion.vx,motion.vy)
                if not self._cs_dead:
                    metabolic=dt*speed/10000.*.035+dt*max(0.,speed-7.)/2000.*.03
                    extra=dt/60.*(.00034*environment['heat_load']+.00024*environment['heavy_ground_load']+.00006*environment['cold_load'])
                    ps.energy=clamp(ps.energy-work*.0015*(1.2-ps.player.stamina/250.)-metabolic-extra,.18,1.)
                    row=getattr(self,'_v13_load_state',{}).get(key)
                    if row is not None:
                        tactics=rt.team.tactics
                        intensity=(.78+.18*tactics.tempo+.18*tactics.pressing)*(1.+.30*clamp((.62-ps.energy)/.44))*(1.08-.16*clamp((ps.player.stamina-45.)/50.))*environment_load
                        row['load']+=dt/60.*intensity*(.6+.4*speed/4.)
                        row['peak']=max(row['peak'],row['load'])
                active.append((team,ps,key))
        # Spatial hash avoids an all-pairs collision scan every physics tick.
        grid={}
        for team,ps,key in active:
            cell=(int(ps.x//2),int(ps.y//2))
            for gx in range(cell[0]-1,cell[0]+2):
                for gy in range(cell[1]-1,cell[1]+2):
                    for ot,op,ok in grid.get((gx,gy),()):
                        if hypot(ps.x-op.x,ps.y-op.y)>1.2:continue
                        a,b,hit=resolve_collision((ps.x,ps.y),(op.x,op.y),self._cs_motion[key],self._cs_motion[ok],self._cs_profiles[key],self._cs_profiles[ok],dt)
                        if hit:
                            ps.x,ps.y=a;op.x,op.y=b;self._cs_totals['collisions']+=1
            grid.setdefault(cell,[]).append((team,ps,key))
        if self._cs_dead:self._cs_totals['dead_seconds']+=dt;return
        self._cs_totals['in_play_seconds']+=dt
        owner=self._xy_ball.get('owner')
        if owner:
            try:
                ps=self.teams[owner['team']].by_name(owner['player']);self._cs_ball=BallState(ps.x,ps.y,1.1 if self._cs_control_part=='hands' else 0.)
                self._xy_ball.update(x=ps.x,y=ps.y,z=self._cs_ball.z);self._cs_totals['controlled_seconds'][owner['team']]+=dt
                pressure=self._physical_pressure(owner['team'],ps.x,ps.y)
                band=2 if pressure>.7 else 1 if pressure>.35 else 0
                if self._cs_pressure!=(owner['team'],owner['player'],band):
                    self._cs_pressure=(owner['team'],owner['player'],band)
                    self._record('pressure',owner['team'],owner['player'],value=pressure,band=band)
                self._physical_challenge(owner['team'],ps,dt)
            except KeyError:self._loose('player_removed')
        else:
            self._cs_totals['loose_seconds']+=dt
            if self._cs_air_contact and self.state.pending and self._cs_time-self._cs_air_contact['second']<=.21:
                return
            before=(self._cs_ball.x,self._cs_ball.y,self._cs_ball.z);bounces=self._cs_ball.bounces
            advance_ball(self._cs_ball,dt,air_drag=.009,rolling={'dry':.72,'normal':.65,'slick':.45,'heavy':.95}[env['pitch']]*(.9 if env['weather']=='rain' else .8 if env['weather']=='heavy_rain' else 1.),
                         restitution={'dry':.58,'normal':.54,'slick':.47,'heavy':.38}[env['pitch']]*(.92 if env['weather'] in {'rain','heavy_rain'} else 1.),wind=(float(env['wind'])*2.,0.))
            self._xy_ball.update(x=self._cs_ball.x,y=self._cs_ball.y,z=self._cs_ball.z)
            if self._cs_ball.bounces>bounces:
                self._cs_totals['bounces']+=self._cs_ball.bounces-bounces
                self._record('bounce',x=self._cs_ball.x,y=self._cs_ball.y,z=self._cs_ball.z)
            if self._cs_transport:self._transport_contact(before,dt,active)
            elif self._cs_shot_live and self._cs_shot_live['result'] is None:self._shot_contact(before,active)

    def _integrate(self,seconds):
        self._cs_ensure_players();targets={}
        total=self._cs_remainder+float(seconds);ticks=int((total+1e-9)/TICK)
        self._cs_remainder=round(total-ticks*TICK,10)
        for _ in range(ticks):self._tick(TICK,targets)

    def _move_players(self,seconds):
        if getattr(self,'_continuous_ready',False):self._integrate(max(0.,float(seconds)))
        else:super()._move_players(seconds)

    def _advance_clock(self,seconds,possession_team):
        if not getattr(self,'_continuous_ready',False):return super()._advance_clock(seconds,possession_team)
        finite(seconds)
        if seconds<0:raise ValueError('Negative match time')
        target=round(self.state.second+seconds,9)
        self._integrate(seconds)
        self.state.second=target

    def advance_physics(self,seconds,*,possession_team=None):
        """Public live advance with persisted 100 ms residual, never a replay."""
        self._advance_clock(seconds,self.state.possession if possession_team is None else self._team(possession_team))
        return self.pitch_snapshot()

    def launch_ball(self,x,y,*,z=0.,speed=18.,aerial=False,receiver=None,kind='pass'):
        x,y,z=self._ball_point(x,y,z)
        start=(self._xy_ball['x'],self._xy_ball['y'],self._xy_ball['z'])
        ball,duration=flight_to_target(start,(x,y,z),speed=speed,aerial=aerial)
        self._cs_ball=ball;self._loose('release')
        self._xyz_flight={'model':'drag-bounce-v1','start_second':self.state.second,'duration':duration,
                          'start':dict(zip(('x','y','z'),start)),'target':{'x':x,'y':y,'z':z},
                          'aerial':bool(aerial or z>0),'vertical_velocity':ball.vz,'receiver':deepcopy(receiver),'kind':kind}
        return deepcopy(self._xyz_flight)

    def ball_position_at(self,second=None):
        if not getattr(self,'_continuous_ready',False):return super().ball_position_at(second)
        second=self.state.second if second is None else float(second);finite(second)
        if second<self._cs_time-1e-6:raise ValueError('Continuous prediction cannot reconstruct an unretained past frame')
        ball=deepcopy(self._cs_ball);left=second-self._cs_time
        while left>1e-9:
            h=min(TICK,left);advance_ball(ball,h,wind=(float(self._v13_environment['wind'])*2.,0.));left-=h
        return {'x':ball.x,'y':ball.y,'z':ball.z}

    def _advance_ball(self):pass  # integrated once by the physical clock

    def _reset_kickoff_coordinates(self):
        super()._reset_kickoff_coordinates()
        if not getattr(self,'_continuous_ready',False):return
        self._end_control('kickoff');self._cs_ball=BallState();self._cs_transport=None;self._cs_offside=None
        self._cs_targets={};self._cs_ensure_players()
        for motion in self._cs_motion.values():motion.vx=motion.vy=motion.vz=motion.z=0.
        team=self.state.possession
        ps=min((p for p in self.teams[team].on_field if p is not self._goalkeeper(team)),key=lambda p:hypot(p.x-52.5,p.y-34.))
        ps.x,ps.y=52.5,34.;self._control(team,ps,source='kickoff')

    def _emit(self,typ,team,relevance,text_key,**data):
        event=MatchEngineV13RulesHardening._emit(self,typ,team,relevance,text_key,**data)
        if not getattr(self,'_continuous_ready',False):return event
        if typ==EventType.GOAL and not data.get('shootout'):self._reset_kickoff_coordinates()
        event.data['ball_coordinates']=deepcopy(self._xy_ball)
        event.data['clock_accounted']=True
        return event

    def set_tracking_frame(self,players,*,ball=None,require_all=True):
        players=list(players);updates=[]
        for row in players:
            if ('vx' in row)!=('vy' in row):raise ValueError('Tracking velocity needs vx and vy')
            values={k:float(row[k]) for k in ('vx','vy','z','vz') if k in row}
            for k in values:finite(row[k])
            if values.get('z',0.)<0 or hypot(values.get('vx',0.),values.get('vy',0.))>15.:raise ValueError('Invalid player tracking motion')
            updates.append((self._key(row['team'],row['player']),values))
        velocity={}
        if ball is not None:
            if any(k in ball for k in ('vx','vy','vz')) and not all(k in ball for k in ('vx','vy','vz')):raise ValueError('Ball velocity needs vx, vy and vz')
            velocity={k:float(ball[k]) for k in ('vx','vy','vz') if k in ball}
            for k in velocity:finite(ball[k])
        super().set_tracking_frame(players,ball=ball,require_all=require_all)
        if getattr(self,'_continuous_ready',False):
            self._cs_ensure_players()
            for key,values in updates:
                for k,v in values.items():setattr(self._cs_motion[key],k,v)
                if 'vx' in values:self._cs_motion[key].heading=atan2(values['vy'],values['vx'])
            if ball is not None:
                self._cs_ball=BallState(self._xy_ball['x'],self._xy_ball['y'],self._xy_ball['z'],**velocity)
                if self._cs_transport:self._finish_pass('cancelled',reason='external_tracking_replaced_flight')
                self._cs_offside=None
            self._cs_auto_targets=None
            self._record('tracking_frame',source='external')

    def tracking_events(self,after_id=0):return deepcopy([r for r in self._cs_events if r['id']>after_id])

    def tracking_diagnostic(self):
        return {'schema':1,'physics_tick_seconds':TICK,'events':len(self._cs_events),'passes':len(self._cs_passes),
                'completed_passes':sum(p['status']=='completed' for p in self._cs_passes),
                'open_passes':sum(p['status']=='in_flight' for p in self._cs_passes),
                'totals':deepcopy(self._cs_totals),'players':{k:asdict(v) for k,v in self._cs_motion.items()},
                'possession_segments':deepcopy(self._cs_possessions),'shots':deepcopy(self._cs_shots)}

    def _physical_challenge(self,team,actor,dt):
        if self._cs_foul_contact or self._cs_dead:return
        candidates=[p for p in self.teams[1-team].on_field if not p.red and p is not self._goalkeeper(1-team) and hypot(p.x-actor.x,p.y-actor.y)<1.35]
        if not candidates:return
        defender=min(candidates,key=lambda p:hypot(p.x-actor.x,p.y-actor.y))
        dm=self._cs_motion[self._key(1-team,defender.player.name)];am=self._cs_motion[self._key(team,actor.player.name)]
        closing=hypot(dm.vx-am.vx,dm.vy-am.vy)
        foul_rate=max(.001,.055+.04*defender.effective('aggression')/100.-.03*defender.effective('discipline')/100.+.004*closing)*clamp(closing/3.,.05,1.)
        if self._draw('contact-foul',self._cs_ticks,defender.player.name)<1.-exp(-foul_rate*dt):
            self._cs_foul_contact={'team':1-team,'defender':defender.player.name,'attacker':actor.player.name,'x':actor.x,'y':actor.y,'second':self._cs_time}
            self._record('foul_contact',1-team,defender.player.name,attacker=actor.player.name,x=actor.x,y=actor.y,closing_speed=closing)
            return
        tackle_rate=.06+.12*defender.effective('tackling')/max(1.,actor.effective('dribbling'))
        if self._draw('foot-tackle',self._cs_ticks,defender.player.name)<1.-exp(-tackle_rate*dt):
            self._record('turnover',1-team,defender.player.name,from_team=team,source='physical_tackle')
            self._control(1-team,defender,source='physical_tackle')

    def _handle_physical_foul(self):
        contact=self._cs_foul_contact;self._cs_foul_contact=None
        if contact is None:return None
        try:
            defender=self.teams[contact['team']].by_name(contact['defender'])
            attacker=self.teams[1-contact['team']].by_name(contact['attacker'])
        except KeyError:return self._emit(EventType.INFO,self.state.possession,0,'physical_contact_resolved')
        self._cs_restart_point=(contact['x'],contact['y']);self._loose('foul');self.state.pending=None
        if self._cs_transport:self._finish_pass('cancelled',reason='foul')
        return self._commit_foul(contact['team'],defender,attacker,self._physical_zone(1-contact['team'],attacker))

    def _finish_pass(self,status,*,team=None,player=None,reason=None):
        tr=self._cs_transport
        if tr is None:return
        row=self._cs_passes[tr['pass_index']]
        if row['status']!='in_flight':return
        try:
            intended=self.teams[tr['team']].by_name(tr['receiver'])
            row['arrival_gap']=hypot(intended.x-self._cs_ball.x,intended.y-self._cs_ball.y)
            row['receiver_at_terminal']={'x':intended.x,'y':intended.y,'z':self._cs_motion[self._key(tr['team'],tr['receiver'])].z}
        except KeyError:row['arrival_gap']=None
        row['terminal_ball_speed']=hypot(self._cs_ball.vx,self._cs_ball.vy)
        row.update(status=status,end_second=self._cs_time,end_x=self._cs_ball.x,end_y=self._cs_ball.y,
                   end_z=self._cs_ball.z,actual_receiver=player,receiving_team=team,reason=reason)
        self._record('pass_'+status,row['team'],row['passer'],pass_id=row['id'],receiver=player,reason=reason)
        self._cs_transport=None;self._xyz_flight=None

    def _transport_contact(self,before,dt,active):
        tr=self._cs_transport
        if tr is None:return
        ball=self._cs_ball;elapsed=self._cs_time-tr['start_second']
        if not (0<=ball.x<=105 and 0<=ball.y<=68):
            self._finish_pass('out',reason='boundary');self._end_control('out');return
        remaining=tr['arrival_second']-self._cs_time
        candidates=[]
        for team,ps,key in active:
            if ps.player.name==tr['passer'] and team==tr['team'] and elapsed<.35:continue
            if tr['last_contact'].get(key,-10)>self._cs_time-.25:continue
            motion=self._cs_motion[key];profile=self._cs_profiles[key]
            dist=hypot(ps.x-ball.x,ps.y-ball.y)
            intended=team==tr['team'] and ps.player.name==tr['receiver']
            delta=tr['target'][2]-profile.height*.94
            vjump=profile.jump_speed*(.75+.25*ps.energy)
            lead=(vjump-sqrt(max(0.,vjump*vjump-2.*9.81*max(0.,delta))))/9.81
            if tr['aerial'] and delta>0 and vjump*vjump>=2.*9.81*delta and (intended or team!=tr['team']) and -.05<remaining<lead+.06 and dist<2.:
                if start_jump(motion,profile,ps.energy):self._record('jump',team,ps.player.name,height=motion.z,vertical_speed=motion.vz)
            # Swept ball segment: a fast low pass cannot tunnel through a foot.
            gap=self._segment_distance((ps.x,ps.y),before[:2],(ball.x,ball.y))
            head=abs(ball.z-contact_height(motion,profile,'head'))<=.28 and gap<.72
            foot=ball.z<=motion.z+.45 and gap<.60
            if not (head or foot):continue
            if intended and remaining>.35 and not foot:continue
            candidates.append((gap-.25*(ps.effective('anticipation')/100.),team,ps,key,'head' if head and not foot else 'foot'))
        if not candidates:return
        _,team,ps,key,part=min(candidates,key=lambda r:r[0]);tr['last_contact'][key]=self._cs_time
        if self._cs_offside and team==tr['team'] and offside_interference(self._cs_offside,ps.player.name,participates=True):
            self._finish_pass('offside',team=team,player=ps.player.name,reason='active_reception')
            self.stats[team].offsides+=1;self._cs_last_offside=deepcopy(self._cs_offside)
            self._cs_restart_point=(ps.x,ps.y);self.state.restart='free_kick';self.state.restart_team=1-team
            self.state.restart_zone=self._physical_zone(1-team,ps);self._loose('offside');return
        pressure=self._physical_pressure(team,ps.x,ps.y)
        skill=ps.effective('heading' if part=='head' else 'technique')/100.
        speed=hypot(ball.vx,ball.vy)
        perceived_pressure=clamp(pressure+self._venue_effects(team)['pressure_shift'])
        wet=self._environment_effects()['surface_control_penalty']
        control=clamp((.72+.26*skill-.005*speed-.12*perceived_pressure-wet) if part=='head' else (.90+.12*skill-.003*speed-.08*perceived_pressure-.4*wet),.10,.99)
        if self._draw('first-touch',self._cs_seq,key)<control:
            passer_team=tr['team'];source=tr['kind'];pid=self._cs_passes[tr['pass_index']]['id']
            reception={'team':team,'player':ps.player.name,'x':ball.x,'y':ball.y,'z':ball.z,'part':part,'second':self._cs_time,'pass_id':pid}
            self._cs_last_reception=reception
            self._finish_pass('completed' if team==passer_team and ps.player.name!=tr['passer'] else 'intercepted' if team!=passer_team else 'recovered',team=team,player=ps.player.name)
            if team!=passer_team:
                self.note_deliberate_opponent_play(team)
                self._record('turnover',team,ps.player.name,from_team=passer_team,source='interception')
            else:
                self._cs_last_assist={'team':team,'receiver':ps.player.name,'kind':source,'second':self._cs_time,'pass_id':pid,'contact':deepcopy(reception),'restart':self._cs_passes[tr['pass_index']]['restart']}
            if part=='head' and team!=passer_team:
                ball.vx=self.attack_direction(team)*(8.+ps.effective('heading')*.1)
                ball.vy=(self._draw('header-clearance-side',ps.player.name)-.5)*8.;ball.vz=2.5
                self._cs_last_touch={'team':team,'player':ps.player.name,'second':self._cs_time,'deliberate':True}
                self._end_control('headed_clearance');self._record('headed_clearance',team,ps.player.name,x=ball.x,y=ball.y,z=ball.z)
                return
            if part=='head' and team==passer_team:
                p=PendingAction(team,ps.player.name,'shoot',self._physical_zone(team,ps),.5,pressure,origin=source,body_part='head')
                utility=self._calculate_xg(p,ps,None,self._goalkeeper(1-team))
                options=self.action_values(team,ps)['passes']
                if utility>=max((r[2] for r in options),default=.01)*.45:
                    self._cs_air_contact=reception;self.state.pending=p
                    self._cs_ball.vx=self._cs_ball.vy=self._cs_ball.vz=0.
                    self._record('aerial_strike_ready',team,ps.player.name,z=reception['z'])
                    return
                self._cs_ball.vx*=.12;self._cs_ball.vy*=.12;self._cs_ball.vz=-.6;self._record('headed_control',team,ps.player.name,z=reception['z'])
                return
            self._control(team,ps,source=source,part=part)
        else:
            self._record('miscontrol',team,ps.player.name,part=part,x=ball.x,y=ball.y,z=ball.z,pressure=pressure)
            ball.vx*=.48;ball.vy*=.48;ball.vz=abs(ball.vz)*.35 if part=='head' else ball.vz
            if team!=tr['team'] and speed<12. and part=='foot':self.note_deliberate_opponent_play(team)

    def _pass_plan(self,team,target,kind,*,speed,height):
        key=self._key(team,target.player.name);motion=self._cs_motion[key];profile=self._cs_profiles[key]
        x,y=target.x,target.y
        if kind in {'through_ball','cross','cutback'}:
            tx,ty=self._to_team(team,x,y)
            if kind=='cross':tx=max(tx,95.);ty=34.+(ty-34.)*.35
            elif kind=='cutback':tx=max(90.,min(99.,tx));ty=34.+(ty-34.)*.4
            else:tx=min(102.,tx+7.)
            run=self._to_world(team,tx,ty)
        else:
            actor=self._xy_ball;dx,dy=x-actor['x'],y-actor['y'];length=max(.1,hypot(dx,dy))
            candidates=[(x+motion.vx*.4,y+motion.vy*.4),(x-.7*dx/length,y-.7*dy/length),
                        (x+dy/length,y-dx/length),(x-dy/length,y+dx/length)]
            opponents=[o for o in self.teams[1-team].on_field if not o.red]
            run=max(candidates,key=lambda pt:min(hypot(o.x-pt[0],o.y-pt[1]) for o in opponents)-.3*hypot(pt[0]-x,pt[1]-y))
        run=(clamp(run[0],.2,104.8),clamp(run[1],.2,67.8))
        grip={'dry':1.,'normal':.98,'slick':.86,'heavy':.82}[self._v13_environment['pitch']]
        grip*=.94 if self._v13_environment['weather']=='rain' else .88 if self._v13_environment['weather']=='heavy_rain' else 1.
        duration=max(.15,hypot(x-self._xy_ball['x'],y-self._xy_ball['y'])/speed)
        # Rendezvous solve: predict the receiver under the very same motion
        # intention/acceleration law used during flight, including braking.
        for _ in range(8):
            probe=deepcopy(motion);px,py=x,y;left=duration
            while left>1e-9:
                h=min(TICK,left);px,py=move_player(px,py,probe,profile,run,h,effort=1.,energy=target.energy,grip=grip);left-=h
            d=hypot(px-self._xy_ball['x'],py-self._xy_ball['y'])
            next_duration=max(.15,d/speed*(1.+.009*d*.45))
            if abs(next_duration-duration)<.003:break
            duration=next_duration
        return {'point':(clamp(px,.2,104.8),clamp(py,.2,67.8)),'run_target':run,'duration':duration,'height':height}

    def _pass_point(self,team,target,kind):
        return self._pass_plan(team,target,kind,speed=18. if kind in {'cross','long_ball'} else 14.,height=0.)['point']

    def _execute_physical_pass(self,team,actor,target,kind='safe_pass',*,restart=None,wait=True):
        # The release frame is frozen before either the receiver run or flight.
        if self._xy_ball.get('owner')!={'team':team,'player':actor.player.name}:
            return self._acquire_loose()
        pressure=self._physical_pressure(team,actor.x,actor.y)
        frame=self.freeze_offside(team,restart=restart)
        technique=actor.effective('crossing' if kind=='cross' else 'passing')/100.
        aerial=kind in {'cross','long_ball'}
        profile=self._cs_profiles[self._key(team,target.player.name)]
        jump_speed=profile.jump_speed*(.75+.25*target.energy)
        height=profile.height*.94+.70*jump_speed*jump_speed/(2.*9.81) if aerial else 0.
        speed=20.+5.*technique if aerial else 10.+6.*technique
        plan=self._pass_plan(team,target,kind,speed=speed,height=height);point=plan['point']
        distance=hypot(point[0]-actor.x,point[1]-actor.y)
        clearance=min((self._segment_distance((p.x,p.y),(actor.x,actor.y),point) for p in self.teams[1-team].on_field if not p.red),default=68.)
        technique=actor.effective('crossing' if kind=='cross' else 'passing')/100.
        perceived_pressure=clamp(pressure+self._venue_effects(team)['pressure_shift'])
        spread=(.06+.012*distance*(1.-technique)+.20*perceived_pressure+self._environment_effects()['surface_control_penalty'])
        actual=(point[0]+self._normal('pass-x',actor.player.name)*spread,point[1]+self._normal('pass-y',actor.player.name)*spread)
        start={'x':actor.x,'y':actor.y,'z':self._xy_ball['z']}
        flight=self.launch_ball(actual[0],actual[1],z=height,speed=speed,aerial=aerial,kind=kind)
        row={'id':len(self._cs_passes)+1,'team':team,'passer':actor.player.name,'receiver':target.player.name,'kind':kind,
             'start_second':self._cs_time,'x':start['x'],'y':start['y'],'z':start['z'],'target_x':point[0],'target_y':point[1],
             'actual_target_x':actual[0],'actual_target_y':actual[1],'distance':distance,'pressure':pressure,'line_clearance':clearance,
             'height':height,'speed':speed,'status':'in_flight','offside_frame':frame,'restart':restart}
        self._cs_passes.append(row);self._record('pass_release',team,actor.player.name,pass_id=row['id'],receiver=target.player.name,kind_of_pass=kind,line_clearance=clearance,pressure=pressure,x=start['x'],y=start['y'],z=start['z'])
        self._cs_transport={'team':team,'passer':actor.player.name,'receiver':target.player.name,'kind':kind,'target':[point[0],point[1],height],'run_target':list(plan['run_target']),
                            'aerial':aerial,'start_second':self._cs_time,'arrival_second':self._cs_time+flight['duration'],'pass_index':len(self._cs_passes)-1,'last_contact':{}}
        if not wait:return deepcopy(row)
        deadline=self._cs_time+flight['duration']+2.5
        while self._cs_transport is not None and self._cs_time<deadline:
            self._advance_clock(.2,team)
        if self._cs_transport is not None:self._finish_pass('incomplete',reason='no_control_at_arrival')
        self._cs_targets.pop(self._key(team,target.player.name),None)
        owner=self._xy_ball.get('owner')
        if row['status']=='offside':
            return self._emit(EventType.OFFSIDE,team,2,'offside',passer=actor.player.name,runner=target.player.name,offside_frame=frame)
        if row['status']=='out':return self._out_of_play(team)
        if owner and owner['team']==team:
            self.state.zone=self._physical_zone(team,self.teams[team].by_name(owner['player']))
            attacking=self._to_team(team,point[0],point[1])[0]>self._to_team(team,start['x'],start['y'])[0]+8.
            return self._emit(EventType.PROGRESSION if attacking else EventType.INFO,team,1 if attacking else 0,'physical_pass_completed',actor=actor.player.name,target=owner['player'],kind=kind,pass_id=row['id'])
        return self._emit(EventType.TURNOVER,team,1,'physical_pass_incomplete',actor=actor.player.name,kind=kind,pass_id=row['id'],reason=row['status'])

    def release_pass(self,team,passer,receiver,kind='safe_pass',*,restart=None):
        team=self._team(team);actor=self.teams[team].by_name(passer);target=self.teams[team].by_name(receiver)
        if self._cs_transport or self._cs_shot_live:raise ValueError('A ball action is already in flight')
        if actor is target or self._xy_ball.get('owner')!={'team':team,'player':passer}:raise ValueError('Passer must control the ball; receiver must differ')
        if kind not in {'safe_pass','progressive_pass','through_ball','cross','cutback','long_ball'}:raise ValueError('Unknown physical pass')
        self._cs_action+=1
        return self._execute_physical_pass(team,actor,target,kind,restart=restart,wait=False)

    def _shot_frame(self,team,shooter):
        keeper=self._goalkeeper(1-team);x,y=self._to_team(team,shooter.x,shooter.y);kx,ky=self._to_team(team,keeper.x,keeper.y)
        g=self.shot_geometry_context(PendingAction(team,shooter.player.name,'shoot',self._physical_zone(team,shooter),.5,.5),shooter)
        defenders=[{'player':p.player.name,'x':p.x,'y':p.y,'distance':hypot(p.x-shooter.x,p.y-shooter.y)} for p in self.teams[1-team].on_field if not p.red]
        return {**g,'second':self._cs_time,'x':shooter.x,'y':shooter.y,'z':self._xy_ball['z'],
                'pressure':self._physical_pressure(team,shooter.x,shooter.y),'keeper':{'player':keeper.player.name,'x':keeper.x,'y':keeper.y,'team_x':kx,'team_y':ky},
                'keeper_depth':105.-kx,'keeper_lateral':abs(ky-34.),'defenders':defenders,'nearest_defender':min(d['distance'] for d in defenders)}

    def _calculate_xg(self,p,shooter,defender,keeper):
        if p.origin=='penalty':return .76
        from continuous_shot_model_v13 import chance
        return chance(self._shot_frame(p.team,shooter),header=p.body_part=='head',source=p.origin)

    def action_values(self,team,actor):
        """Opportunity cost makes speculative shots unattractive without quotas."""
        x,y=self._to_team(team,actor.x,actor.y);keeper=self._goalkeeper(1-team)
        p=PendingAction(team,actor.player.name,'shoot',self._physical_zone(team,actor),.5,.5,origin='open_play')
        raw_shot=self._calculate_xg(p,actor,None,keeper)
        motion=self._cs_motion[self._key(team,actor.player.name)]
        goal_x=105. if self.attack_direction(team)==1 else 0.
        angle=abs((atan2(34.-actor.y,goal_x-actor.x)-motion.heading+pi)%(2*pi)-pi)
        readiness=.35+.65*max(0.,cos(angle))
        shot=raw_shot*readiness
        options=[]
        for target in self.teams[team].on_field:
            if target is actor or target.red:continue
            tx,ty=self._to_team(team,target.x,target.y)
            d=hypot(target.x-actor.x,target.y-actor.y)
            if d<2.:continue
            clearance=min((self._segment_distance((o.x,o.y),(actor.x,actor.y),(target.x,target.y)) for o in self.teams[1-team].on_field if not o.red),default=68.)
            success=clamp(.9-.0025*d+.06*(actor.effective('passing')/100.)-.16*exp(-clearance/2.),.1,.99)
            target_p=PendingAction(team,target.player.name,'shoot',self._physical_zone(team,target),.5,.5)
            quality=self._calculate_xg(target_p,target,None,keeper)
            possession_value=.08/(1.+exp(-(tx-64.)/13.))+.5*quality
            continuation=success*(.004+possession_value+.008*min(1.,clearance/6.))
            line=sorted((self._to_team(team,o.x,o.y)[0] for o in self.teams[1-team].on_field if not o.red),reverse=True)
            offside_line=max(x,line[1] if len(line)>1 else 0.)
            lead_time=max(.15,d/14.);m=self._cs_motion[self._key(team,target.player.name)]
            lead=max(0.,m.vx*self.attack_direction(team))*lead_time+.3*self._cs_profiles[self._key(team,target.player.name)].acceleration*lead_time*lead_time
            kind='cutback' if x>94 and abs(y-34)>6 and tx<x-3 and abs(ty-34)<12 else 'cross' if x>78 and abs(y-34)>13 and tx>82 and abs(ty-34)<12 else 'through_ball' if tx<=offside_line and tx+lead>offside_line+1. and tx>x+5 else 'safe_pass' if tx<x+5 else 'progressive_pass'
            if tx>52.5 and tx>offside_line+1e-7:
                awareness=max(.001,1.-actor.effective('vision')/100.)**2
                success*=awareness;continuation*=awareness
            if (x<40 and tx>x+18) or (clearance<.8 and d>25):kind='long_ball'
            survival=.65 if kind in {'cross','long_ball'} else clamp((clearance-.35)/1.8,.04,1.)
            success*=survival;continuation*=survival
            if kind=='cross':continuation*=.75+self.teams[team].team.tactics.cross_frequency*.5
            options.append((target,kind,max(.00001,continuation),success))
        nearest=min(hypot(o.x-actor.x,o.y-actor.y) for o in self.teams[1-team].on_field if not o.red)
        carry_value=.08/(1.+exp(-(min(103.,x+5.)-64.)/13.))+.5*shot
        carry=carry_value*(.45+.5*actor.effective('dribbling')/100.)*(.45+.55*min(1.,nearest/5.))
        return {'shot':shot,'passes':options,'carry':carry,'pressure':self._physical_pressure(team,actor.x,actor.y)}

    def _choose_actor(self,team,zone):
        owner=self._xy_ball.get('owner')
        if owner and owner['team']==team:
            try:return self.teams[team].by_name(owner['player'])
            except KeyError:pass
        return min((p for p in self.teams[team].on_field if not p.red),key=lambda p:hypot(p.x-self._cs_ball.x,p.y-self._cs_ball.y))

    def _acquire_loose(self):
        ball=self._cs_ball
        if not (0<=ball.x<=105 and 0<=ball.y<=68):return self._out_of_play(self._cs_last_touch['team'] if self._cs_last_touch else self.state.possession)
        candidates=[]
        for team,rt in enumerate(self.teams):
            ps=min((p for p in rt.on_field if not p.red),key=lambda p:hypot(p.x-ball.x,p.y-ball.y))
            self._cs_targets[self._key(team,ps.player.name)]=(ball.x,ball.y,1.);candidates.append((team,ps))
        self._advance_clock(.6,self.state.possession)
        for team,ps in sorted(candidates,key=lambda row:hypot(row[1].x-ball.x,row[1].y-ball.y)):
            profile=self._cs_profiles[self._key(team,ps.player.name)];motion=self._cs_motion[self._key(team,ps.player.name)]
            if hypot(ps.x-ball.x,ps.y-ball.y)<=1. and ball.z<=motion.z+.5:
                self._control(team,ps,source='loose_ball');break
        for team,ps in candidates:self._cs_targets.pop(self._key(team,ps.player.name),None)
        return self._emit(EventType.INFO,self.state.possession,0,'physical_loose_ball')

    def _carry(self,team,actor,zone,ctx):
        direction=self.attack_direction(team);pressure=self._physical_pressure(team,actor.x,actor.y)
        lateral=(self._draw('dribble-side')-.5)*4.
        target=(clamp(actor.x+direction*5.,1.,104.),clamp(actor.y+lateral,1.,67.))
        key=self._key(team,actor.player.name);self._cs_targets[key]=(*target,.72+.28*self.teams[team].team.tactics.tempo)
        self._record('carry_start',team,actor.player.name,x=actor.x,y=actor.y)
        self._advance_clock(1.6,team);self._cs_targets.pop(key,None)
        if self._cs_foul_contact:return self._handle_physical_foul()
        if self._xy_ball.get('owner')!={'team':team,'player':actor.player.name}:return self._emit(EventType.TURNOVER,team,1,'physical_pressure_turnover',loser=actor.player.name)
        opponents=[p for p in self.teams[1-team].on_field if not p.red]
        defender=min(opponents,key=lambda p:hypot(p.x-actor.x,p.y-actor.y));gap=hypot(defender.x-actor.x,defender.y-actor.y)
        if gap<1.2:
            foul=.035*(defender.effective('aggression')/60.)*(1.2-defender.effective('discipline')/200.)
            if self._draw('physical-foul')<foul:
                self._cs_restart_point=(actor.x,actor.y);self._loose('foul')
                return self._commit_foul(1-team,defender,actor,self._physical_zone(team,actor))
            tackle=clamp(.35+(defender.effective('tackling')-actor.effective('dribbling'))/160.,.05,.8)
            if self._draw('physical-tackle')<tackle:
                self._record('turnover',1-team,defender.player.name,from_team=team,source='tackle')
                self._control(1-team,defender,source='tackle');return self._emit(EventType.TURNOVER,team,1,'physical_tackle',loser=actor.player.name,winner=defender.player.name)
        self.state.zone=self._physical_zone(team,actor)
        self._record('carry_end',team,actor.player.name,x=actor.x,y=actor.y,pressure=pressure)
        return self._emit(EventType.PROGRESSION,team,1,'physical_carry',actor=actor.player.name)

    def _open_play_step(self):
        self._cs_action+=1
        if self._cs_foul_contact:return self._handle_physical_foul()
        if self._cs_transport:
            team=self._cs_transport['team'];self._advance_clock(.2,team)
            return self._emit(EventType.INFO,team,0,'physical_ball_in_flight')
        if self._xy_ball.get('owner') is None:return self._acquire_loose()
        team=self._xy_ball['owner']['team'];actor=self.teams[team].by_name(self._xy_ball['owner']['player'])
        self.state.possession=team;self.state.zone=self._physical_zone(team,actor)
        tactics=self.teams[team].team.tactics
        losing=self.score[team]<self.score[1-team] and self.minute>=70
        winning=self.score[team]>self.score[1-team] and self.minute>=70
        delay=(.7+1.8*(1.-tactics.tempo))*(.8 if losing else 1.2 if winning else 1.)
        self._cs_targets[self._key(team,actor.player.name)]=(actor.x,actor.y,.3)
        self._advance_clock(delay,team);self._cs_targets.pop(self._key(team,actor.player.name),None)
        if self._cs_foul_contact:return self._handle_physical_foul()
        current=self._xy_ball.get('owner')
        if current!={'team':team,'player':actor.player.name}:return self._emit(EventType.TURNOVER,team,1,'physical_pressure_turnover',loser=actor.player.name)
        values=self.action_values(team,actor)
        best=max([values['carry']]+[r[2] for r in values['passes']])
        confidence=(.84+.4*self._draw('decision-threshold'))*(.88 if losing else 1.12 if winning else 1.)
        impulsive=self._draw('decision-error')<((1.-actor.effective('composure')/100.)**4*.01*(1.+values['pressure']))
        if values['shot']>best*confidence or impulsive:
            p=PendingAction(team,actor.player.name,'shoot',self._physical_zone(team,actor),danger=values['shot'],pressure=values['pressure'],origin='open_play')
            return self._resolve_shot(p)
        if values['carry']>best*.9 and values['pressure']<.6:return self._carry(team,actor,self.state.zone,values)
        if not values['passes']:return self._carry(team,actor,self.state.zone,values)
        target,kind,_,_=weighted_choice(self.rng,[(r,r[2]**2) for r in values['passes']])
        return self._execute_physical_pass(team,actor,target,kind)

    def _safe_pass(self,team,actor,zone,ctx):
        options=self.action_values(team,actor)['passes']
        target=max(options,key=lambda r:r[2])[0]
        return self._execute_physical_pass(team,actor,target,'safe_pass')

    def _progressive_action(self,team,actor,zone,kind,ctx):
        options=self.action_values(team,actor)['passes'];target=max(options,key=lambda r:r[2])[0]
        return self._execute_physical_pass(team,actor,target,kind)

    def _create_or_resolve_danger(self,team,actor,zone,kind,ctx):
        if kind=='shoot':return self._resolve_shot(PendingAction(team,actor.player.name,'shoot',self._physical_zone(team,actor),.5,ctx.get('pressure',.5)))
        if kind=='dribble':return self._carry(team,actor,zone,ctx)
        options=self.action_values(team,actor)['passes'];target=max(options,key=lambda r:r[2])[0]
        return self._execute_physical_pass(team,actor,target,kind)

    def _resolve_pending(self):
        p=self.state.pending;self.state.pending=None
        owner=self._xy_ball.get('owner')
        if not owner:
            if p and getattr(self,'_cs_air_contact',None):return self._resolve_shot(p)
            return self._acquire_loose()
        actor=self.teams[owner['team']].by_name(owner['player'])
        if p and p.kind=='shoot' and owner=={'team':p.team,'player':p.actor}:return self._resolve_shot(p)
        return self._open_play_step()

    def _shot_contact(self,before,active):
        shot=self._cs_shot_live;ball=self._cs_ball
        if not shot:return
        team=shot['team'];direction=self.attack_direction(team);goal_x=105. if direction==1 else 0.
        crossed=(before[0]-goal_x)*direction<=0 and (ball.x-goal_x)*direction>=0
        goal_fraction=(goal_x-before[0])/(ball.x-before[0]) if crossed and ball.x!=before[0] else float('inf')
        endpoint=(ball.x,ball.y,ball.z)
        contacts=[]
        for ot,ps,key in active:
            if ot==team:continue
            motion=self._cs_motion[key];profile=self._cs_profiles[key]
            keeper=ps is self._goalkeeper(ot)
            if keeper:
                if not shot['on_frame'] or self._cs_time-shot['start_second']<shot['reaction']:continue
                reach=.35+.50*profile.height+.004*(ps.player.gk_reach or ps.player.gk_positioning)
                vertical=profile.height*1.25+motion.z
            else:reach=profile.radius+.16;vertical=profile.height+motion.z
            fraction=swept_disc_fraction(before,endpoint,(ps.x,ps.y),reach)
            if fraction is None or fraction>=goal_fraction:continue
            height=before[2]+fraction*(endpoint[2]-before[2])
            if height>vertical:continue
            contacts.append((fraction,ot,ps,key,keeper))
        for fraction,ot,ps,key,keeper in sorted(contacts,key=lambda row:(row[0],row[1],row[3])):
            if keeper:
                probability=clamp(.50+.3*ps.effective('handling')/100.+.25*ps.effective('reflexes')/100.-.005*hypot(ball.vx,ball.vy),.1,.98)
                if self._draw('keeper-catch',key,self._cs_seq)>probability:continue
            ball.x,ball.y,ball.z=tuple(before[i]+fraction*(endpoint[i]-before[i]) for i in range(3))
            if keeper:
                shot['result']='save';shot['keeper']=ps.player.name
                if self._draw('keeper-spill',key)<.48-.42*ps.effective('handling')/100.:
                    ball.vx*=-.3;ball.vy*=.4;ball.vz=abs(ball.vz)*.3;shot['spill']=True
                    self._cs_last_touch={'team':ot,'player':ps.player.name,'second':self._cs_time,'deliberate':False,'save':True}
                    self.note_deliberate_opponent_play(ot,save=True)
                else:self._control(ot,ps,source='save',part='hands')
                return
            shot['result']='block';shot['blocker']=ps.player.name
            dx,dy=ball.x-ps.x,ball.y-ps.y;d=hypot(dx,dy)
            nx,ny=(dx/d,dy/d) if d>.001 else (-direction,0.)
            closing=ball.vx*nx+ball.vy*ny
            if closing<0:ball.vx-=1.35*closing*nx;ball.vy-=1.35*closing*ny
            ball.vx*=.7;ball.vy*=.7;ball.vz=abs(ball.vz)*.35
            self._record('body_block',ot,ps.player.name,x=ball.x,y=ball.y,z=ball.z)
            self._cs_last_touch={'team':ot,'player':ps.player.name,'second':self._cs_time,'deliberate':False}
            return
        if crossed:
            f=goal_fraction;y=before[1]+f*(ball.y-before[1]);z=before[2]+f*(ball.z-before[2]);side=abs(y-34.)
            ball.x,ball.y,ball.z=goal_x,y,z
            shot['crossing']={'x':goal_x,'y':y,'z':z}
            post=(abs(side-3.66)<=.11 and z<=2.55) or (abs(z-2.44)<=.11 and side<=3.77)
            if post:
                ball.vx*=-.65;ball.vy*=.65;ball.vz*=.65;shot['result']='post'
            elif side<3.55 and z<2.33:shot['result']='goal'
            else:shot['result']='miss'
            return
        if not (0<=ball.y<=68 and -1<=ball.x<=106):shot['result']='miss'

    def _resolve_shot(self,p):
        team=p.team;shooter=self.teams[team].by_name(p.actor)
        owner=self._xy_ball.get('owner');air=getattr(self,'_cs_air_contact',None)
        head=bool(air and air['team']==team and air['player']==p.actor and self._cs_time-air['second']<=.3)
        if owner!={'team':team,'player':p.actor} and not head:
            self._record('shot_not_released',team,p.actor,reason='no_control_or_aerial_contact')
            return self._acquire_loose()
        p.body_part='head' if head else 'left_foot' if shooter.player.preferred_foot=='L' else 'right_foot'
        if not head and p.origin!='penalty':
            key=self._key(team,p.actor);motion=self._cs_motion[key]
            goal_x=105. if self.attack_direction(team)==1 else 0.
            wanted=atan2(34.-shooter.y,goal_x-shooter.x)
            angle=abs((wanted-motion.heading+pi)%(2*pi)-pi)
            preparation=.15+angle/self._cs_profiles[key].turn_rate+hypot(motion.vx,motion.vy)/self._cs_profiles[key].braking*.25
            self._cs_targets[key]=(clamp(shooter.x+self.attack_direction(team)*.4,0.,105.),shooter.y,.25)
            self._advance_clock(preparation,team);self._cs_targets.pop(key,None)
            if self._cs_foul_contact:return self._handle_physical_foul()
            if self._xy_ball.get('owner')!={'team':team,'player':p.actor}:
                return self._emit(EventType.TURNOVER,team,1,'physical_shot_preparation_lost',loser=p.actor)
        p.zone=self._physical_zone(team,shooter);p.pressure=self._physical_pressure(team,shooter.x,shooter.y)
        assist=self._cs_last_assist
        if p.origin not in {'penalty','free_kick'} and assist and assist['team']==team and assist['receiver']==p.actor and self._cs_time-assist['second']<=5.:
            p.origin=assist['kind']
        elif getattr(self,'_cs_last_shot',None) and self._cs_last_shot['team']==team and self._cs_time-self._cs_last_shot['second']<=8.:
            p.origin='rebound'
        elif p.origin not in {'penalty','free_kick'}:p.origin='open_play'
        if self._cs_possession and self._cs_possession.get('origin')=='corner' and p.origin not in {'penalty','free_kick'}:p.origin='corner'
        frame=self._shot_frame(team,shooter)
        if head:frame.update(x=air['x'],y=air['y'],z=air['z'],second=air['second'])
        self._cs_air_contact=None
        keeper=self._goalkeeper(1-team);xg=self._calculate_xg(p,shooter,None,keeper)
        from spatial_shot_v13 import shot_geometry
        geometry=shot_geometry(self,p,shooter,keeper,self.shot_selection_diagnostic(shooter,p,keeper))
        if p.origin=='penalty':
            quality=(shooter.effective('finishing')+shooter.effective('composure'))/200.
            side=-1. if self._draw('penalty-side')<.5 else 1.
            geometry['actual_goal_position']={'x':side*2.85+self._normal('penalty-x')*(.22+.65*(1.-quality)), 'z':abs(.5+self._normal('penalty-z')*.35)}
            geometry['spatial_on_target']=abs(geometry['actual_goal_position']['x'])<3.55 and geometry['actual_goal_position']['z']<2.33
        goal_y=34.+geometry['actual_goal_position']['x'];goal_z=geometry['actual_goal_position']['z']
        end_x,end_y=self._to_world(team,105.,goal_y)
        self._xy_ball={'x':frame['x'],'y':frame['y'],'z':frame['z'],'owner':None}
        self.launch_ball(end_x,end_y,z=goal_z,speed=geometry['shot_speed_mps'],aerial=True,kind='shot')
        reaction=.13+.15*(1.-keeper.effective('reflexes')/100.)
        shot={'team':team,'shooter':p.actor,'start_second':self._cs_time,'on_frame':geometry['spatial_on_target'],'result':None,'reaction':reaction,'crossing':None}
        self._cs_shot_live=shot;duration=self._xyz_flight['duration']
        kkey=self._key(1-team,keeper.player.name)
        # Respond to the actual execution target after reaction time. No result
        # has been sampled or selected when this movement target is declared.
        fraction=clamp((keeper.x-frame['x'])/(end_x-frame['x']),0.,1.) if abs(end_x-frame['x'])>1e-6 else 1.
        intercept_y=frame['y']+fraction*(end_y-frame['y'])
        self._cs_keeper_target=(kkey,(keeper.x,clamp(intercept_y,1.,67.),1.),self._cs_time+reaction)
        self.stats[team].shots+=1;self.stats[team].xg+=xg
        if xg>=.3:self.stats[team].big_chances+=1
        self._record('shot_release',team,p.actor,x=frame['x'],y=frame['y'],z=frame['z'],body=p.body_part,xg=xg,pressure=p.pressure,keeper=frame['keeper'])
        deadline=self._cs_time+duration+1.
        while shot['result'] is None and self._cs_time<deadline:self._advance_clock(.1,team)
        outcome=shot['result'] or 'miss';terminal={'x':self._cs_ball.x,'y':self._cs_ball.y,'z':self._cs_ball.z}
        self._cs_shot_live=None;self._cs_keeper_target=None;self._xyz_flight=None
        if outcome in {'goal','save'}:self.stats[team].on_target+=1
        if outcome=='goal':
            self.stats[team].goals+=1;typ=EventType.GOAL;key='physical_goal'
            self.state.restart='kickoff';self.state.restart_team=1-team;self.state.restart_zone=Zone(Band.MID,Lane.CENTER)
        elif outcome=='save':
            self.stats[1-team].saves+=1;typ=EventType.SAVE;key='physical_save'
        elif outcome=='block':self.stats[team].blocked+=1;typ=EventType.BLOCK;key='physical_shot_blocked'
        elif outcome=='post':self.stats[team].posts+=1;typ=EventType.POST;key='physical_shot_hits_post'
        else:typ=EventType.MISS;key='physical_shot_missed'
        row={'team':team,'player':p.actor,'body_part':p.body_part,'origin':p.origin,'xg':xg,'frame':frame,
             'goal':outcome=='goal','on_target':outcome in {'goal','save'},'blocked':outcome=='block','post':outcome=='post',
             'outcome':outcome,'pass_id':assist['pass_id'] if assist and p.origin==assist['kind'] else None,
             'actual_crossing':shot['crossing'],'terminal':terminal,'shot_geometry':geometry}
        self._cs_shots.append(row);self._cs_last_shot={'team':team,'second':self._cs_time,'result':outcome}
        if outcome not in {'goal','save'} or shot.get('spill'):self._loose('shot_rebound')
        if outcome=='miss':self._set_out_restart(team)
        event=self._emit(typ,team,5 if outcome=='goal' else 3,key,shooter=p.actor,scorer=p.actor if outcome=='goal' else None,
                         keeper=shot.get('keeper'),defender=shot.get('blocker'),xg=xg,origin=p.origin,body_part=p.body_part,
                         shot_origin_coordinates={k:frame[k] for k in ('x','y','z')},shot_contact_frame=frame,
                         actual_goal_position=({'x':self._to_team(team,shot['crossing']['x'],shot['crossing']['y'])[1]-34.,'z':shot['crossing']['z']} if shot['crossing'] else None),
                         projected_goal_position=geometry['actual_goal_position'],shot_ball_coordinates=terminal,pressure=p.pressure,physical_outcome=outcome)
        self._cs_last_assist=None;return event

    def _set_out_restart(self,last_team):
        ball=self._cs_ball
        if ball.y<0 or ball.y>68:
            team=1-last_team;self.state.restart='throw_in'
            self._cs_restart_point=(clamp(ball.x,1.,104.),0. if ball.y<0 else 68.)
        else:
            defending=next(t for t in (0,1) if (self.attack_direction(t)==1 and ball.x<52.5) or (self.attack_direction(t)==-1 and ball.x>=52.5))
            if last_team==defending:
                team=1-defending;self.state.restart='corner';self.stats[team].corners+=1
                self._cs_restart_point=(0. if ball.x<52.5 else 105.,0. if ball.y<34 else 68.)
            else:
                team=defending;self.state.restart='goal_kick';self._cs_restart_point=self._to_world(team,5.5,34.)
        self.state.restart_team=team;self.state.restart_zone=self._physical_zone(team,self._choose_actor(team,self.state.zone))
        self._cs_transport=None;self._cs_offside=None;self._loose('out')

    def _out_of_play(self,last_team):
        if not self.state.restart:self._set_out_restart(last_team)
        return self._emit(EventType.INFO,self.state.restart_team,1,'physical_out_of_play',restart=self.state.restart,point=self._cs_restart_point)

    def _apply_clock_for_event(self,event,*,had_pending=False):
        event.data['clock_accounted']=True
        event.data['keeper_clock_accounted']=True

    def _restart_exclusion(self,team,kind,point):
        for other,rt in enumerate(self.teams):
            for ps in rt.on_field:
                x,y=self._to_team(team,ps.x,ps.y);old=(ps.x,ps.y)
                if kind=='kickoff':
                    x=min(x,52.5) if other==team else max(x,52.5)
                    ps.x,ps.y=self._to_world(team,x,y)
                if other==team:continue
                if kind=='goal_kick' and x<16.6 and abs(y-34.)<20.26:
                    ps.x,ps.y=self._to_world(team,16.7,y)
                if kind in {'free_kick','corner','kickoff'}:
                    dx,dy=ps.x-point[0],ps.y-point[1];d=hypot(dx,dy)
                    if d<9.15:
                        if d<1e-6:dx,dy=self.attack_direction(team),0.;d=1.
                        ps.x=clamp(point[0]+dx/d*9.16,0.,105.);ps.y=clamp(point[1]+dy/d*9.16,0.,68.)
                if old!=(ps.x,ps.y):
                    m=self._cs_motion[self._key(other,ps.player.name)];m.vx=m.vy=0.
                    self._record('referee_restart_placement',other,ps.player.name,restart=kind,x=ps.x,y=ps.y)

    def _resolve_v13_kickoff(self,team,*,reason):
        self.state.possession=team
        self._reset_kickoff_coordinates()
        self._restart_exclusion(team,'kickoff',(52.5,34.))
        actor=self.teams[team].by_name(self._xy_ball['owner']['player'])
        target=min((p for p in self.teams[team].on_field if p is not actor and p is not self._goalkeeper(team)),key=lambda p:hypot(p.x-actor.x,p.y-actor.y))
        return self._execute_physical_pass(team,actor,target,'safe_pass',restart='kickoff')

    def _resolve_restart(self):
        kind,team=self.state.restart,self.state.restart_team
        if team not in (0,1):raise RuntimeError('Restart must have an attacking team')
        self._cs_action+=1
        if kind=='kickoff':
            self.state.restart=self.state.restart_team=self.state.restart_zone=None;self.state.possession=team
            self._advance_dead_clock(12.,8.,reason='kickoff');self._reset_kickoff_coordinates()
            return self._emit(EventType.INFO,team,0,'kickoff')
        zone=self.state.restart_zone or self.state.zone
        point=self._to_world(team,94.,34.) if kind=='penalty' else self._cs_restart_point
        if point is None:
            # A foul without a stored point uses the fouled physical location,
            # never the previous shot's goal-line endpoint or a sector proxy.
            ps=self._choose_actor(team,zone);point=(ps.x,ps.y)
        point=(clamp(point[0],0.,105.),clamp(point[1],0.,68.))
        taker=self._goalkeeper(team) if kind=='goal_kick' else min((p for p in self.teams[team].on_field if not p.red and p is not self._goalkeeper(team)),key=lambda p:hypot(p.x-point[0],p.y-point[1]))
        self._cs_targets[self._key(team,taker.player.name)]=(*point,.8)
        setup={'corner':20.,'throw_in':10.,'goal_kick':14.,'free_kick':18.,'penalty':35.}.get(kind,12.)
        self._advance_dead_clock(setup,max(0.,setup-10.),reason=kind)
        # Referee-held dead-ball placement is explicit. It is not live movement.
        taker.x,taker.y=point;self._cs_motion[self._key(team,taker.player.name)].vx=0.;self._cs_motion[self._key(team,taker.player.name)].vy=0.
        self._cs_targets.pop(self._key(team,taker.player.name),None)
        self._restart_exclusion(team,kind,point)
        self._cs_ball=BallState(*point);self._xy_ball={'x':point[0],'y':point[1],'z':0.,'owner':None}
        self.state.restart=self.state.restart_team=self.state.restart_zone=None;self.state.possession=team
        self._cs_offside=None;self._cs_restart_point=None;self._control(team,taker,source=kind)
        self._record('restart',team,taker.player.name,restart=kind,x=point[0],y=point[1])
        if kind=='penalty':
            return self._resolve_shot(PendingAction(team,taker.player.name,'shoot',Zone(Band.BOX,Lane.CENTER),.76,.05,origin='penalty'))
        if kind=='free_kick':
            p=PendingAction(team,taker.player.name,'shoot',self._physical_zone(team,taker),.5,.1,origin='free_kick')
            values=self.action_values(team,taker)
            if values['shot']>max(v[2] for v in values['passes']):return self._resolve_shot(p)
        options=self.action_values(team,taker)['passes']
        target=max(options,key=lambda r:r[2])[0]
        return self._execute_physical_pass(team,taker,target,'cross' if kind=='corner' else 'long_ball' if kind=='goal_kick' and self.teams[team].team.tactics.directness>.65 else 'safe_pass',restart=kind)

    def _advance_dead_clock(self,elapsed_seconds,recoverable_seconds,*,reason):
        if not getattr(self,'_continuous_ready',False):return super()._advance_dead_clock(elapsed_seconds,recoverable_seconds,reason=reason)
        before=self.state.second;super()._advance_dead_clock(elapsed_seconds,recoverable_seconds,reason=reason)
        old=self._cs_dead;self._cs_dead=True
        try:self._integrate(self.state.second-before)
        finally:self._cs_dead=old

    def _switch_possession(self,new_team,zone,transition=0.):
        if getattr(self,'_continuous_ready',False) and new_team!=self.state.possession:self._loose('legacy_transition')
        return super()._switch_possession(new_team,zone,transition)

    def _check_period_boundary(self):
        event=super()._check_period_boundary()
        if event is not None:
            self._end_control('period_end')
            if self._cs_transport:self._finish_pass('cancelled',reason='period_end')
            self._cs_offside=None
        return event

    def substitute(self,team,out_name,in_name):
        event=super().substitute(team,out_name,in_name);self._cs_ensure_players()
        key=self._key(team,in_name);self._cs_motion[key]=MotionState(heading=0. if self.attack_direction(team)==1 else pi)
        if self._cs_transport and self._cs_transport['team']==team and self._cs_transport['receiver']==out_name:self._finish_pass('cancelled',reason='receiver_substituted')
        self._advance_dead_clock(18.,12.,reason='substitution')
        self._record('substitution',team,in_name,outgoing=out_name)
        return event

    def step(self):
        first=self._cs_seq
        event=MatchEngineV13Coordinates.step(self)
        if event.type==EventType.MATCH_END:
            self._end_control('match_end')
            if self._cs_transport:self._finish_pass('cancelled',reason='match_end')
        event.data['continuous_event_ids']=[r['id'] for r in self._cs_events if r['id']>first]
        event.data['engine_mode']='continuous'
        return event

    def pitch_snapshot(self):
        data=super().pitch_snapshot()
        if getattr(self,'_continuous_ready',False):
            data['physics_tick_seconds']=TICK;data['physics_second']=self._cs_time
            for p in data['players']:
                key=self._key(p['team'],p['player']);m=self._cs_motion[key];profile=self._cs_profiles[key]
                p.update(vx=m.vx,vy=m.vy,speed_mps=hypot(m.vx,m.vy),z=m.z,vz=m.vz,heading=m.heading,height=profile.height,mass=profile.mass,physical_profile_source=self._cs_profile_sources.get(key,'derived_role_prior'))
            data['ball_velocity']={k:getattr(self._cs_ball,k) for k in ('vx','vy','vz')}
        return data

    def snapshot(self):
        data=super().snapshot()
        if getattr(self,'_continuous_ready',False):
            data['engine_mode']='continuous';data['engine_version']=ENGINE_VERSION;data['continuous']={'physics_second':self._cs_time,'tick_seconds':TICK,'passes':len(self._cs_passes),'completed_passes':sum(p['status']=='completed' for p in self._cs_passes),'events':self._cs_seq}
        return data

    def export_state(self):
        data=super().export_state()
        data['v13_continuous']={'schema':1,'motion':{k:asdict(v) for k,v in self._cs_motion.items()},'profiles':{k:asdict(v) for k,v in self._cs_profiles.items()},'profile_sources':dict(self._cs_profile_sources),
            'targets':{k:list(v) for k,v in self._cs_targets.items()},'ball':asdict(self._cs_ball),'events':deepcopy(self._cs_events),'passes':deepcopy(self._cs_passes),
            'shots':deepcopy(self._cs_shots),'possessions':deepcopy(self._cs_possessions),'action':self._cs_action,'seq':self._cs_seq,'ticks':self._cs_ticks,
            'remainder':self._cs_remainder,'physics_second':self._cs_time,'possession':deepcopy(self._cs_possession),'totals':deepcopy(self._cs_totals),
            'transport':deepcopy(self._cs_transport),'offside':deepcopy(self._cs_offside),'restart_point':self._cs_restart_point,
            'last_touch':deepcopy(self._cs_last_touch),'last_assist':deepcopy(self._cs_last_assist),'pressure':self._cs_pressure,
            'last_shot':deepcopy(getattr(self,'_cs_last_shot',None)),'air_contact':deepcopy(getattr(self,'_cs_air_contact',None)),
            'foul_contact':deepcopy(self._cs_foul_contact),'control_part':getattr(self,'_cs_control_part','foot'),'auto_targets':deepcopy(self._cs_auto_targets)}
        return data

    @classmethod
    def from_state_dict(cls,data):
        obj=super().from_state_dict(data);obj._continuous_ready=False;obj._init_continuous()
        raw=data.get('v13_continuous')
        if raw:
            if raw['schema']!=1:raise ValueError('Unsupported continuous state schema')
            obj._cs_motion={k:MotionState(**v).validate() for k,v in raw['motion'].items()}
            obj._cs_profiles={k:PhysicalProfile(**v).validate() for k,v in raw['profiles'].items()}
            obj._cs_profile_sources=dict(raw.get('profile_sources',{}))
            obj._cs_targets={k:tuple(v) for k,v in raw['targets'].items()};obj._cs_ball=BallState(**raw['ball']).validate()
            for key,field in [('events','events'),('passes','passes'),('shots','shots'),('possessions','possessions'),('action','action'),('seq','seq'),('ticks','ticks'),('remainder','remainder'),('physics_second','time'),('possession','possession'),('totals','totals'),('transport','transport'),('offside','offside'),('restart_point','restart_point'),('last_touch','last_touch'),('last_assist','last_assist'),('pressure','pressure'),('last_shot','last_shot'),('air_contact','air_contact'),('control_part','control_part')]:
                setattr(obj,'_cs_'+field,deepcopy(raw.get(key)))
            obj._cs_foul_contact=deepcopy(raw.get('foul_contact'))
            obj._cs_auto_targets={k:tuple(v) for k,v in raw.get('auto_targets',{}).items()} if raw.get('auto_targets') else None
            if obj._cs_pressure is not None:obj._cs_pressure=tuple(obj._cs_pressure)
            finite(obj._cs_time,obj._cs_remainder)
            if not 0<=obj._cs_remainder<TICK or abs(obj.state.second-obj._cs_time-obj._cs_remainder)>.0001:raise ValueError('Inconsistent continuous clock')
            if obj._cs_restart_point is not None:obj._cs_restart_point=tuple(obj._cs_restart_point)
        obj._continuous_ready=True;obj._cs_ensure_players();return obj


MatchEngine=MatchEngineV13Continuous
