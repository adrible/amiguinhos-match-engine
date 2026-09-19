"""Goal-plane execution, in metres, viewed by the shooter.

x = -3.66..3.66, z = 0..2.44. Coordinates outside the frame are misses.
The pre-shot xG is never changed here. Independent deterministic draws keep
intention, placement error and keeper positioning separate and replayable.
"""
from math import cos, log, pi, sqrt, hypot, erf
from engine import Band, Lane, clamp
from engine_experiment_v13_passing_texture import _stable_fraction


# A goal-plane error scale, not a target shot count. Freeze before holdout runs.
DISPERSION_SCALE = 1.80


def reference_target_probability(distance, pressure):
    """In-frame probability for ordinary execution across the intention mix.

    Integrate the same independent normal placement model against the goal
    mouth, excluding the frame. Reference skill/balance are fixed, so actual
    shooter skill, chosen target, weak foot and difficult techniques retain
    their real accuracy trade-offs. The chosen target is never normalized away.
    """
    spread = DISPERSION_SCALE * (1.20 - .75 * .60 + .18 * pressure + .18 * .30) * (distance / 12) ** .48
    def interval(lo, hi, mean, sigma):
        return .5 * (erf((hi-mean)/(sigma*sqrt(2))) - erf((lo-mean)/(sigma*sqrt(2))))
    targets = [(.16,0.,.8),(.18,3.12,2.12),(.18,2.8,1.2),(.21,2.95,.28),
               (.05,2.85,.75),(.05,2.85,1.15),(.05,2.85,1.55),(.12,2.25,.45)]
    return sum(weight * interval(-3.59,3.59,x,spread*1.9) * interval(-2.37,2.37,z,spread)
               for weight,x,z in targets)


def attribute(player, name, fallback):
    value = getattr(player.player, name, None)
    return player.effective(name) if value is not None else fallback


def keeper_response(keeper, x, z, keeper_x, distance, speed, shot_type):
    reflex = keeper.effective('reflexes') / 100
    positioning = keeper.effective('gk_positioning') / 100
    agility = attribute(keeper, 'gk_agility', (keeper.effective('reflexes') + keeper.effective('pace')) / 2) / 100
    reach = attribute(keeper, 'gk_reach', keeper.effective('gk_positioning')) / 100
    jump = attribute(keeper, 'gk_jump', (keeper.effective('strength') + keeper.effective('reflexes')) / 2) / 100
    close = clamp((18 - distance) / 14)
    high = clamp(z / 2.44)
    weights = {'reflexes': .22 + .25 * close, 'gk_positioning': .24,
               'gk_agility': .18 * (1 - high), 'gk_reach': .18,
               'gk_jump': .22 * high, 'one_on_one': .20 * close}
    values = dict(reflexes=reflex, gk_positioning=positioning, gk_agility=agility,
                  gk_reach=reach, gk_jump=jump, one_on_one=keeper.effective('one_on_one') / 100)
    ability = sum(weights[k] * values[k] for k in weights) / sum(weights.values())
    travel = hypot(x - keeper_x, max(0, z - .8))
    flight = distance / speed
    reachable = .65 + .65 * reach + (1.7 + 1.8 * agility) * max(0, flight - .18 + .10 * reflex)
    difficulty = clamp(.45 + .24 * (travel - reachable) + .20 * high - .28 * (ability - .7))
    if shot_type == 'chip':
        difficulty = clamp(difficulty + .08 * high)
    return dict(keeper_difficulty=difficulty, keeper_travel=travel,
                keeper_attribute_weights=weights, keeper_ability=100 * ability,
                spatial_conversion_multiplier=clamp(.45 + 1.25 * difficulty, .40, 1.65))


def shot_geometry(engine, p, shooter, keeper, selection):
    key = (engine.seed, engine.state.second, p.team, p.actor, p.origin, p.rebound_depth)
    def draw(tag):
        return _stable_fraction('goal-plane-v1', tag, *key)
    def gaussian(tag):
        return sqrt(-2 * log(max(1e-12, draw(tag + 'u')))) * cos(2 * pi * draw(tag + 'v'))
    quality = selection['execution_quality']
    side = -1 if p.zone.lane == Lane.LEFT else 1 if p.zone.lane == Lane.RIGHT else 0
    keeper_x = side * (1.15 + .45 * keeper.effective('gk_positioning') / 100)
    keeper_x += (draw('keeper-offset') - .5) * (1.2 - keeper.effective('gk_positioning') / 120)
    shot_type = selection['shot_type']
    r = draw('target')
    opposite = -1 if keeper_x > 0 else 1
    if r < .16:
        target, tx, tz = 'central', 0., .8
    elif r < .34:
        target, tx, tz = 'high_far_corner', opposite * 3.12, 2.12
    elif r < .52:
        target, tx, tz = 'mid_far_corner', opposite * 2.8, 1.20
    elif r < .73:
        target, tx, tz = 'low_far_corner', opposite * 2.95, .28
    elif r < .88:
        target, tx, tz = 'near_post', (side or -opposite) * 2.85, .55 + draw('near-height') * 1.2
    else:
        target, tx, tz = 'wrong_foot', -opposite * 2.25, .45
    if shot_type == 'chip':
        target, tx, tz = 'central_chip', opposite * .7, 1.95
    elif p.body_part == 'head' and draw('header') < .55:
        shot_type, target, tz = 'downward_header', 'low_far_corner', .23
    elif p.body_part != 'head' and p.pressure > .65 and draw('toe') < .23:
        shot_type = 'toe_poke'
    elif p.body_part != 'head' and side and shooter.effective('technique') > 80 and draw('outside') < .16:
        shot_type = 'outside_foot'
    elif p.body_part != 'head' and p.zone.band == Band.BOX and p.danger > .7 and draw('legs') < .12:
        shot_type, target, tx, tz = 'nutmeg', 'between_legs', keeper_x, .16
    preferred = str(shooter.player.preferred_foot).upper()
    if p.body_part in {'left_foot', 'right_foot'}:
        weak = preferred not in {'B', 'BOTH'} and p.body_part != ('left_foot' if preferred == 'L' else 'right_foot')
    else:
        weak = False
    balance = attribute(shooter, 'balance', (shooter.effective('strength') + shooter.effective('technique')) / 2) / 100
    weak_skill = attribute(shooter, 'weak_foot', shooter.effective('technique') * .72) / 100
    distance = {Band.BOX: 12., Band.ATT: 24., Band.MID: 40., Band.DEF: 65.}[p.zone.band]
    # Goal-plane spread grows with distance, pressure and difficult body shapes.
    spread = DISPERSION_SCALE * (1.20 - .75 * quality + .18 * p.pressure + .18 * (1 - balance)
              + (.20 * (1 - weak_skill) if weak else 0)) * (distance / 12) ** .48
    spread *= {'volley': 1.22, 'first_time': 1.10, 'outside_foot': 1.16,
               'chip': 1.14, 'toe_poke': 1.12}.get(shot_type, 1)
    x, z = tx + gaussian('horizontal') * spread * 1.9, tz + gaussian('vertical') * spread
    # Low strikes can bounce/skid: a below-ground error is projected upwards.
    z = abs(z)
    speed = {'chip': 13., 'directed_header': 16., 'downward_header': 17.,
             'power_header': 19., 'power': 31., 'volley': 28.}.get(shot_type, 24.)
    on_target = abs(x) < 3.66 and z < 2.44
    frame = (abs(abs(x) - 3.66) <= .07 and z <= 2.51) or (abs(z - 2.44) <= .07 and abs(x) <= 3.73)
    exposed = getattr(engine, '_keeper_is_exposed', lambda team: False)(1 - p.team)
    response = keeper_response(keeper, x, z, keeper_x, distance, speed, shot_type)
    actual = ('high' if z > 1.65 else 'low' if z < .65 else 'mid') + ('_center' if abs(x) < 1.2 else '_left' if x < 0 else '_right')
    return dict(shot_type=shot_type, shot_target=target, intended_goal_position={'x': tx, 'z': tz},
                actual_goal_position={'x': x, 'z': z}, actual_shot_region=actual,
                keeper_goal_position={'x': keeper_x, 'z': .8}, shot_speed_mps=speed,
                shot_distance_m=distance, shot_foot='head' if p.body_part == 'head' else 'weak' if weak else 'strong',
                reference_on_target_probability=reference_target_probability(distance, p.pressure),
                shot_execution_spread=spread, spatial_on_target=on_target and not frame,
                spatial_hits_frame=frame, keeper_exposed=exposed, open_goal=exposed, **response)
