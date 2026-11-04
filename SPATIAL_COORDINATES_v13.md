# Player XY and ball XYZ — first spatial stage

Branch: `feature/player-xy-ball-xyz-v13`, based on the validated v1.3 candidate.
This branch uses `from engine_experiment_v13 import MatchEngine` as usual.

## Coordinate contract

- Fixed world frame, in metres: pitch length 105 along x, width 68 along y.
- Every active `PlayerState` is a `PitchPlayerState` with persistent `x` and `y`.
  Bench players have no invented on-pitch location. Departed players disappear
  from the active frame. Substitute players inherit the vacated physical point.
- The ball has `x`, `y`, `z` and optional ownership. `z=0` is ground level;
  positive z is height above the pitch. A ball may cross field boundaries.
- Team 0 attacks towards +x in the first half, team 1 towards -x. Directions
  switch at half-time and at the extra-time interval. Full time alone does not
  switch them again. Kickoffs reset the tactical shapes between live phases.
- Both spatial axes rotate when converting between a team's attacking frame
  and world coordinates. A possession change alone never mirrors the world.

## Read current positions

```python
frame = engine.pitch_snapshot()
# frame['players']: team, player, role, x, y for every active player
# frame['ball']: x, y, z, owner
# frame['ball_flight']: declared flight, or None

point = engine.player_coordinates(0, 'Gabriel Adib')
reading = engine.spatial_reading(0, 'Gabriel Adib')
# nearest_opponent_distance, nearby_support, ball_height, pass distances
# and opponent clearance from each possible passing segment
```

`engine.snapshot()['pitch']` and the live `p` narration packet include the frame.
Reading a frame or trajectory does not move players, change RNG, simulate future
match events or expose a chosen future match outcome. Returned data are detached
copies. The clock advances the state; repeated reads do not.

## Read an external tracking frame

```python
engine.set_tracking_frame(
    [{'team': 0, 'player': name, 'x': x, 'y': y}, ...],  # all active players
    ball={'x': 55.0, 'y': 20.0, 'z': 1.8},
)
# A caller must supply actual names and numbers in place of the example above.

engine.set_player_coordinates(0, 'Gabriel Adib', 55.0, 20.0)
```

Complete frames require every active player exactly once. Explicit partial
frames can use `require_all=False`. Invalid coordinates, duplicates, missing
players or invalid ownership reject the whole update before any mutation. Player
points must be on the pitch; ball points must be finite and height non-negative.
The source marker distinguishes supplied frames from simulated movement.
Advancing a supplied frame continues simulation; replaying an entire external
tracking feed requires the caller to supply subsequent frames.

## Movement and decisions

Players move towards formation/role anchors adjusted for possession, the ball,
width, compactness, mentality and defensive line. Displacement during a clock
advance is limited by effective pace and energy. Moving to a new sector does not
assign every player the sector's centre or rebuild coordinates on each read.

Actual distances contribute to pressure, free space, nearby support, receiver
selection and defensive engagement. A defender standing near the ball receives
more engagement weight than the same defender far away. Pass options account
for length and opponents near the passing segment. A high ball also changes
receiving weights through heading ability. These readings consume no new RNG.

The previously accepted venue contribution is added at its original strength
after blending the non-venue context with geometry; no venue coefficients,
player ratings or desired score totals are modified.

## Ball height and trajectories

```python
engine.launch_ball(80.0, 34.0, z=1.6, speed=18.0, aerial=True, kind='cross')
flight = engine.pitch_snapshot()['ball_flight']
midpoint = engine.ball_position_at(flight['start_second'] + flight['duration']/2)
# midpoint is x/y/z on the declared flight; this read does not advance the game.
```

Ground rolls keep z=0. Aerial trajectories use constant horizontal velocity and
vertical acceleration of -9.81 m/s². The declared endpoint, endpoint height and
horizontal speed determine flight duration and initial vertical velocity.
Movement advances with the match clock, including a partially completed flight.
An unowned airborne tracking point with no supplied trajectory falls under
gravity from zero initial vertical velocity, rather than hovering.
Pending aerial deliveries can retain an active flight between engine beats.
Existing shot geometry supplies the resolved goal-mouth height; shot origin and
terminal coordinates are also exposed in world XYZ, while a goal resets the
current ball to the centre. A blocked shot has no fabricated goal-plane arrival.

## Persistence and scope

`export_state` stores player points, ball ownership/height, source and in-flight
trajectory in `v13_coordinates` schema 1. Restoring the same state and commands
preserves future events and RNG exactly. Legacy saves receive a deterministic
initial layout marked `legacy_migration`, without RNG draws. Previously played
matches must stay pinned to their old runtime for exact historical replay.

This first stage retains the event/zone engine: it is not a complete continuous
22-player collision simulation. Ball spin, aerodynamic drag, rebounds off player
meshes, a coordinate-based offside law, and exact 3D interception/contact are
future work. Receiving and shot outcomes still use the existing contextual
resolvers. The positions are persistent inputs to current decisions, not a claim
of tracking data measured from real football.

The previous 92.07/100 benchmark belongs to the earlier candidate. It does not
certify this spatial branch. Population behaviour must be evaluated independently
before this branch is promoted or frozen. No calibration is forced from a small
smoke sample. Main, the validated snapshot and the reserved final seed are outside
this implementation's changes.

## Verification

```bash
python -m unittest -v test_v13_coordinates.py
python -m unittest -v test_runner_v13.py test_v13_venue.py test_spatial_execution_narration_v13.py
python diagnostics_v13.py 30
```

The coordinate module is included in the existing candidate CI suite. Tests cover
all active player points, finite/bounded input and atomic ingestion, meaningful
pressure/pass/defender geometry, speed limits, formation changes, venue effects,
substitution/removal, save/load and legacy migration, live packets, ball height,
gravity, ground rolls, mid-flight persistence and invalid trajectory rejection.
