from __future__ import annotations

import sys

import calibrate_amiguinhos as base
from stable_engine import simulate_full_match


if __name__ == "__main__":
    # Reuse the exact same benchmark/seeds as v1.1 and swap only the stable
    # v1.2 engine, so the before/after comparison remains meaningful.
    base.simulate_full_match = simulate_full_match
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    base.run(n)
