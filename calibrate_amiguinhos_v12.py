from __future__ import annotations

import sys

import calibrate_amiguinhos as base
from engine_experiment_v12 import simulate_full_match_v12


if __name__ == "__main__":
    # Reuse the exact same benchmark/seeds as v1.1 and swap only the engine
    # candidate, so the before/after comparison is meaningful.
    base.simulate_full_match = simulate_full_match_v12
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    base.run(n)
