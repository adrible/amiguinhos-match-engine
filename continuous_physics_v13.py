"""Deterministic SI-unit movement, ball dynamics and IFAB offside snapshots.

Pure functions have no match outcomes, identity bonuses or aggregate targets.
Z denotes ball contact-point height above ground (ground=0), not ball-centre Z.
The engine samples these dynamics on a fixed 100 ms grid.
"""
from dataclasses import asdict, dataclass
from math import atan2, cos, exp, hypot, isfinite, pi, sin, sqrt


def bounded(x, lo, hi):return max(lo,min(hi,x))


def finite(*values):
    if any(isinstance(x,bool) or not isfinite(float(x)) for x in values):
        raise ValueError('Physical values must be finite numbers')


def swept_disc_fraction(before, after, centre, radius):
    """First contact on a linear substep; None when the segment misses."""
    dx,dy=after[0]-before[0],after[1]-before[1]
    ox,oy=before[0]-centre[0],before[1]-centre[1]
    c=ox*ox+oy*oy-radius*radius
    if c<=0:return 0.
    a=dx*dx+dy*dy
    if a<1e-15:return None
    b=2.*(ox*dx+oy*dy);disc=b*b-4.*a*c
    if disc<0:return None
    t=(-b-sqrt(disc))/(2.*a)
    return t if 0.<=t<=1. else None


@dataclass
class PhysicalProfile:
    height: float = 1.82
    mass: float = 78.
    radius: float = .34
    acceleration: float = 3.7
    braking: float = 6.0
    turn_rate: float = 3.1
    sprint_speed: float = 9.6
    jump_speed: float = 3.4

    def validate(self):
        finite(*asdict(self).values())
        if not (1.4<=self.height<=2.3 and 40<=self.mass<=140 and .2<=self.radius<=.6
                and .5<=self.acceleration<=8 and 1<=self.braking<=12 and .3<=self.turn_rate<=8
                and 4<=self.sprint_speed<=12 and 0<=self.jump_speed<=5):
            raise ValueError('Invalid player physical profile')
        return self


@dataclass
class MotionState:
    vx: float = 0.
    vy: float = 0.
    heading: float = 0.
    z: float = 0.
    vz: float = 0.
    distance: float = 0.
    sprint_distance: float = 0.
    high_intensity_seconds: float = 0.
    positive_work: float = 0.
    peak_speed: float = 0.
    jumps: int = 0

    def validate(self):
        finite(*asdict(self).values())
        if min(self.z,self.distance,self.sprint_distance,self.high_intensity_seconds,self.positive_work,self.peak_speed,self.jumps)<0:
            raise ValueError('Negative accumulated motion state')
        return self


def move_player(x,y,state,profile,target,dt,*,effort=1.,energy=1.,grip=1.):
    """Acceleration, braking distance and bounded heading change, semi-implicit."""
    finite(x,y,dt,*target)
    if dt<0:raise ValueError('Negative physical time')
    if not dt:return x,y
    dx,dy=target[0]-x,target[1]-y;distance=hypot(dx,dy)
    speed=hypot(state.vx,state.vy)
    wanted=atan2(dy,dx) if distance>.02 else state.heading
    delta=(wanted-state.heading+pi)%(2*pi)-pi
    turn_limit=profile.turn_rate*dt*(.6+.4*grip)/(1.+speed/12.)
    state.heading += bounded(delta,-turn_limit,turn_limit)
    turn_cost=max(.2,cos(min(abs(delta),pi/2.)))
    cap=profile.sprint_speed*bounded(effort,0.,1.)*(.72+.28*bounded(energy,0.,1.))*sqrt(grip)
    desired=min(cap,sqrt(max(0.,2*profile.braking*grip*max(0.,distance-.08))))*turn_cost
    if distance<.08:desired=0.
    tx,ty=cos(state.heading)*desired,sin(state.heading)*desired
    ax,ay=tx-state.vx,ty-state.vy;dv=hypot(ax,ay)
    accelerating=desired>speed
    limit=(profile.acceleration if accelerating else profile.braking)*grip*dt*(.8+.2*bounded(energy,0.,1.))
    fraction=min(1.,limit/dv) if dv else 0.
    before2=speed*speed
    state.vx+=ax*fraction;state.vy+=ay*fraction
    newx,newy=x+state.vx*dt,y+state.vy*dt
    nx,ny=bounded(newx,0.,105.),bounded(newy,0.,68.)
    if nx!=newx:state.vx=0.
    if ny!=newy:state.vy=0.
    travelled=hypot(nx-x,ny-y);speed=hypot(state.vx,state.vy)
    state.distance+=travelled;state.peak_speed=max(state.peak_speed,speed)
    if speed>=7.:state.sprint_distance+=travelled;state.high_intensity_seconds+=dt
    state.positive_work+=max(0.,.5*profile.mass*(speed*speed-before2))
    if state.z>0 or state.vz>0:
        state.z=max(0.,state.z+state.vz*dt-.5*9.81*dt*dt);state.vz-=9.81*dt
        if state.z==0:state.vz=0.
    return nx,ny


def start_jump(state,profile,energy=1.):
    if state.z>.001 or state.vz>0:return False
    state.vz=profile.jump_speed*(.75+.25*bounded(energy,0.,1.));state.jumps+=1
    return True


def contact_height(state,profile,part='head'):
    return state.z+(profile.height*.94 if part=='head' else .18)


def resolve_collision(a,b,ma,mb,pa,pb,dt):
    """Inelastic normal impulse; correction separates overlapping body discs."""
    dx,dy=b[0]-a[0],b[1]-a[1];d=hypot(dx,dy);limit=pa.radius+pb.radius
    if d>=limit:return a,b,False
    nx,ny=(dx/d,dy/d) if d>1e-9 else (1.,0.)
    penetration=limit-d;inv_a,inv_b=1./pa.mass,1./pb.mass;total=inv_a+inv_b
    correction=max(0.,penetration-.002)*.75
    aa=(bounded(a[0]-nx*correction*inv_a/total,0.,105.),bounded(a[1]-ny*correction*inv_a/total,0.,68.))
    bb=(bounded(b[0]+nx*correction*inv_b/total,0.,105.),bounded(b[1]+ny*correction*inv_b/total,0.,68.))
    closing=(mb.vx-ma.vx)*nx+(mb.vy-ma.vy)*ny
    if closing<0:
        impulse=-(1.+.04)*closing/total
        ma.vx-=impulse*inv_a*nx;ma.vy-=impulse*inv_a*ny
        mb.vx+=impulse*inv_b*nx;mb.vy+=impulse*inv_b*ny
    return aa,bb,True


@dataclass
class BallState:
    x: float = 52.5
    y: float = 34.
    z: float = 0.
    vx: float = 0.
    vy: float = 0.
    vz: float = 0.
    bounces: int = 0
    distance: float = 0.

    def validate(self):
        finite(*asdict(self).values())
        if self.z<0 or self.bounces<0 or self.distance<0:raise ValueError('Invalid ball state')
        return self


def advance_ball(ball,dt,*,air_drag=.009,rolling=.65,restitution=.56,wind=(0.,0.)):
    finite(dt,air_drag,rolling,restitution,*wind)
    if dt<0 or air_drag<0 or rolling<0 or not 0<=restitution<=1:raise ValueError('Invalid ball physics')
    if not dt:return
    x0,y0=ball.x,ball.y
    air=ball.z>1e-7 or abs(ball.vz)>.01
    if air:
        rx,ry=ball.vx-wind[0],ball.vy-wind[1];speed=sqrt(rx*rx+ry*ry+ball.vz*ball.vz)
        factor=exp(-air_drag*speed*dt)
        ball.vx=wind[0]+rx*factor;ball.vy=wind[1]+ry*factor
        vz1=ball.vz*factor-9.81*dt
        z1=ball.z+.5*(ball.vz+vz1)*dt
        ball.x+=ball.vx*dt;ball.y+=ball.vy*dt
        if z1<0:
            # Split at impact; remaining time includes upward rebound.
            frac=bounded(ball.z/max(1e-12,ball.z-z1),0.,1.)
            impact=ball.vz+(vz1-ball.vz)*frac
            rebound=-impact*restitution;remaining=dt*(1.-frac)
            ball.bounces+=1
            ball.vx*=.82;ball.vy*=.82
            if rebound<.65:ball.z=0.;ball.vz=0.
            else:ball.z=max(0.,rebound*remaining-.5*9.81*remaining*remaining);ball.vz=rebound-9.81*remaining
        else:ball.z=z1;ball.vz=vz1
    else:
        speed=hypot(ball.vx,ball.vy);new=max(0.,speed-rolling*dt)
        factor=new/speed if speed else 0.;ball.vx*=factor;ball.vy*=factor
        ball.x+=ball.vx*dt;ball.y+=ball.vy*dt;ball.z=ball.vz=0.
    ball.distance+=hypot(ball.x-x0,ball.y-y0)


def flight_to_target(start,target,*,speed=18.,aerial=False,air_drag=.009):
    """Solve drag-aware initial velocity for a planned receiving point.

    The ball still may be intercepted or bounce and a receiver must actually
    reach it. The plan never determines the recipient or match outcome.
    """
    finite(*start,*target,speed,air_drag)
    if speed<=0 or min(start[2],target[2])<0:raise ValueError('Invalid flight plan')
    dx,dy=target[0]-start[0],target[1]-start[1];d=hypot(dx,dy)
    duration=max(.15,d/speed*(1.+air_drag*d*.45))
    finite(d,duration)
    if duration>30.:raise ValueError('Flight plan exceeds supported physical horizon')
    vx,vy=dx/duration,dy/duration
    vz=(target[2]-start[2])/duration+.5*9.81*duration if aerial or start[2]>0 or target[2]>0 else 0.
    # Shooting method: deterministic finite-difference Jacobian. No RNG.
    params=[vx,vy,vz]
    def end(values):
        b=BallState(*start,*values);left=duration
        while left>1e-9:
            h=min(.025,left);advance_ball(b,h,air_drag=air_drag,rolling=0.,restitution=0.);left-=h
        return (b.x,b.y,b.z)
    for _ in range(9):
        out=end(params);err=[target[i]-out[i] for i in range(3)]
        if max(map(abs,err))<.015:break
        # Horizontal coupling is mild; the diagonal derivative is stable.
        for i in range(3 if vz else 2):
            probe=params.copy();probe[i]+=.05;q=end(probe);derivative=(q[i]-out[i])/.05
            if abs(derivative)>.02:params[i]+=bounded(err[i]/derivative,-12.,12.)
    return BallState(*start,*params),duration


def offside_snapshot(team,ball,players,*,direction=1,second=0.,restart=None):
    """Law 11 position at the teammate's touch; flags are not an offence yet.

    Each player's x may be the supplied foremost playable body point. Hand/arm
    coordinates are deliberately absent. Keeper counts as an ordinary opponent.
    """
    if team not in (0,1) or direction not in (-1,1):raise ValueError('Invalid attacking team/direction')
    finite(ball['x'],ball['y'],second)
    def tx(x):return x if direction==1 else 105.-x
    opponents=sorted((tx(p['x']) for p in players if p['team']!=team and not p.get('red')),reverse=True)
    second_last=opponents[1] if len(opponents)>=2 else 0.
    line=max(tx(ball['x']),second_last)
    exempt=restart in {'corner','throw_in','goal_kick'}
    flagged=[]
    for p in players:
        if p['team']==team and not p.get('red'):
            point=tx(p['x'])
            if not exempt and point>52.5+1e-7 and point>line+1e-7:flagged.append(p['player'])
    return {'team':team,'second':second,'direction':direction,'ball':dict(ball),
            'second_last_defender_x':second_last,'line_x':line,'flagged':flagged,
            'exempt_restart':restart if exempt else None,'players':[dict(p) for p in players]}


def offside_interference(frame,player,*,participates=False,opponent_deliberate_play=False,deliberate_save=False):
    return bool(player in frame['flagged'] and participates
                and not (opponent_deliberate_play and not deliberate_save))
