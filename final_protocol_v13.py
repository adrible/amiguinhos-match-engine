from __future__ import annotations

"""Non-result-based seed protocol for the official v1.3 final.

The seed is derived from an immutable match identity string, not from any
simulation outcome.  Calibration code must never run the official seed for the
Amiguinhos U21 x Flamengo U21 final.  The live runner may opt in explicitly
only when the official match is actually started.
"""

import hashlib

OFFICIAL_FINAL_HOME = "amiguinhos_u21"
OFFICIAL_FINAL_AWAY = "flamengo_u21"
OFFICIAL_FINAL_IDENTITY = (
    "amiguinhos_u21|flamengo_u21|regional_internacional_u21|final"
)
OFFICIAL_FINAL_HASH = hashlib.sha256(OFFICIAL_FINAL_IDENTITY.encode("utf-8")).hexdigest()
OFFICIAL_FINAL_SEED = int(OFFICIAL_FINAL_HASH[:8], 16)

# Published here before the official live simulation.  Changing the identity
# string or derivation rule after inspecting an outcome would violate protocol.
EXPECTED_OFFICIAL_FINAL_HASH = (
    "6be46927575f409c1dec1e9509214db2a47583884dd52f3851efa117d0d32e80"
)
EXPECTED_OFFICIAL_FINAL_SEED = 1810131239

if OFFICIAL_FINAL_HASH != EXPECTED_OFFICIAL_FINAL_HASH:
    raise RuntimeError("official final identity/hash protocol changed")
if OFFICIAL_FINAL_SEED != EXPECTED_OFFICIAL_FINAL_SEED:
    raise RuntimeError("official final seed derivation changed")


def is_official_final_fixture(home_key: str, away_key: str) -> bool:
    return (
        str(home_key) == OFFICIAL_FINAL_HOME
        and str(away_key) == OFFICIAL_FINAL_AWAY
    )


def is_reserved_official_seed(home_key: str, away_key: str, seed: int) -> bool:
    return is_official_final_fixture(home_key, away_key) and int(seed) == OFFICIAL_FINAL_SEED


def assert_calibration_seed_allowed(home_key: str, away_key: str, seed: int) -> None:
    if is_reserved_official_seed(home_key, away_key, seed):
        raise RuntimeError(
            "official final seed is reserved for the live final runner and "
            "cannot be used by calibration/stress harnesses"
        )
