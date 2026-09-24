# v1.3 Defensive Intelligence — Integration Notes

Current top candidate class:

```python
from engine_experiment_v13_defense import MatchEngineV13Defense
```

Inheritance chain:

```text
stable v1.2
  -> spatial/geolocal decisions + creativity + boldness
  -> off-ball movement + anticipation
  -> body orientation + preferred foot
  -> contextual defensive intelligence
```

The frozen v1.2 files should remain unchanged until the v1.3 candidate is
fully calibrated and explicitly promoted.

## Files added by this layer

- `engine_experiment_v13_defense.py`
- `test_defensive_intelligence.py`
- `DEFENSIVE_INTELLIGENCE_v13.md`

## Regression command

```bash
python -m unittest -v \
  test_engine_base.py \
  test_spatial_decisions.py \
  test_offball_anticipation.py \
  test_body_orientation.py \
  test_defensive_intelligence.py
```

Expected at this candidate snapshot: **49 tests**.

## Next recommended work

Before promotion, run matchup/tier calibration and inspect whether the defensive
layer over-compresses chance quality. The candidate intentionally uses one
primary response per beat to avoid recreating the old stacked-defence problem.
