from __future__ import annotations

import json
from pathlib import Path
import run_tournament_round1_v13 as base

PACK_PATH = Path("data/tournaments/torneio_16_times_engine_v13.json")
TOURNAMENT_BASIS = "interdimensional-16|2026-09-19|round-3|v1.3"

def main() -> None:
    base.TOURNAMENT_BASIS = TOURNAMENT_BASIS
    pack = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    result = base.run_fixture(pack, "A6", "brazil_2002", "bastard_munchen")
    print("BRAZIL_BASTARD_RESULT_BEGIN")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    print("BRAZIL_BASTARD_RESULT_END")

if __name__ == "__main__":
    main()
