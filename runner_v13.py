from __future__ import annotations

"""Live interactive runner for the v1.3 candidate.

Nothing is simulated at startup beyond constructing the current 0:00 engine
state. A session owns one live MatchEngine instance. The ``p`` command asks
that engine to advance *from its current state* until the next relevant event.
There is no precomputed event queue, no hidden full-match simulation and no
replay of a previously simulated result.

Candidate-only historical test fixtures are loaded through
``historical_2014_v13`` and remain isolated from frozen v1.2 tournament data.

The official final seed is reserved. Normal fixture creation rejects it for
the Amiguinhos U21 x Flamengo U21 final; only the explicit official-final
factory/CLI flag may unlock it when the live final is actually started.
"""

import argparse
import json
from pathlib import Path
from typing import Optional

from engine import Event, EventType, MatchConfig
from engine_experiment_v13 import MatchEngine
from final_protocol_v13 import (
    OFFICIAL_FINAL_AWAY,
    OFFICIAL_FINAL_HOME,
    OFFICIAL_FINAL_SEED,
    is_reserved_official_seed,
)
from historical_2014_v13 import load_team_for_v13


class MatchSessionV13:
    """Small stateful facade around one live v1.3 engine."""

    def __init__(self, engine: MatchEngine):
        self.engine = engine

    @classmethod
    def from_fixture(
        cls,
        home_key: str = "amiguinhos_u21",
        away_key: str = "flamengo_u21",
        *,
        seed: int = 0,
        auto_adapt: bool = False,
        allow_extra_time: bool = False,
        allow_reserved_final_seed: bool = False,
    ) -> "MatchSessionV13":
        if (
            is_reserved_official_seed(home_key, away_key, seed)
            and not allow_reserved_final_seed
        ):
            raise RuntimeError(
                "official final seed is reserved; use the explicit official-final "
                "runner only when the live final is actually starting"
            )

        home = load_team_for_v13(home_key)
        away = load_team_for_v13(away_key)
        engine = MatchEngine(
            home,
            away,
            seed=int(seed),
            config=MatchConfig(
                auto_tactical_adaptation=bool(auto_adapt),
                allow_extra_time=bool(allow_extra_time),
            ),
        )
        return cls(engine)

    @classmethod
    def from_official_final(cls) -> "MatchSessionV13":
        """Create the reserved live final session.

        Calling this method intentionally unlocks the previously declared seed.
        It must not be used for calibration, previews, dry runs or CI smokes.
        """
        return cls.from_fixture(
            OFFICIAL_FINAL_HOME,
            OFFICIAL_FINAL_AWAY,
            seed=OFFICIAL_FINAL_SEED,
            auto_adapt=True,
            allow_extra_time=True,
            allow_reserved_final_seed=True,
        )

    @classmethod
    def from_json(cls, payload: str) -> "MatchSessionV13":
        return cls(MatchEngine.from_json(payload))

    @property
    def pristine(self) -> bool:
        return bool(
            self.engine.state.second == 0.0
            and not self.engine.state.event_log
            and self.engine.state.pending is None
            and self.engine.state.restart is None
            and sum(st.goals for st in self.engine.stats) == 0
            and sum(st.shots for st in self.engine.stats) == 0
        )

    def press_p(self, *, min_relevance: Optional[int] = None) -> Event:
        """Advance the live match on demand to the next relevant event."""
        return self.engine.advance_until_relevant(min_relevance=min_relevance)

    def step_once(self) -> Event:
        """Advance exactly one engine beat; useful for debugging only."""
        return self.engine.step()

    def snapshot(self) -> dict:
        return self.engine.snapshot()

    def export_json(self) -> str:
        return self.engine.export_json()

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.write_text(self.export_json(), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | Path) -> "MatchSessionV13":
        payload = Path(path).read_text(encoding="utf-8")
        return cls.from_json(payload)


def event_view(event: Event, session: MatchSessionV13) -> dict:
    home = session.engine.teams[0].team.name
    away = session.engine.teams[1].team.name
    return {
        "minute": round(float(event.minute), 2),
        "type": event.type.value,
        "team": event.team,
        "team_name": (
            session.engine.teams[event.team].team.name
            if event.team in (0, 1) else None
        ),
        "relevance": event.relevance,
        "text_key": event.text_key,
        "data": event.data,
        "score": {
            "home": home,
            "away": away,
            "home_goals": session.engine.stats[0].goals,
            "away_goals": session.engine.stats[1].goals,
        },
    }


def _score_line(session: MatchSessionV13) -> str:
    h, a = session.engine.score
    home = session.engine.teams[0].team.name
    away = session.engine.teams[1].team.name
    return f"{session.engine.minute:05.2f}' | {home} {h} x {a} {away}"


def _print_event(event: Event, session: MatchSessionV13) -> None:
    view = event_view(event, session)
    print(_score_line(session))
    print(
        f"[{view['type']}] {view['text_key']} "
        f"({view['team_name'] or 'neutro'})"
    )
    if view["data"]:
        print(json.dumps(view["data"], ensure_ascii=False, sort_keys=True))


def _print_help() -> None:
    print("Comandos:")
    print("  p              avança ao próximo evento relevante")
    print("  p N            usa relevância mínima N apenas neste avanço")
    print("  .              avança exatamente um beat (debug)")
    print("  s              mostra o snapshot atual sem avançar")
    print("  save ARQUIVO   salva o estado v1.3 completo")
    print("  load ARQUIVO   restaura o estado v1.3 completo")
    print("  q              encerra o runner")


def run_cli(session: MatchSessionV13) -> None:
    print("v1.3 live runner — nenhuma partida foi pré-simulada.")
    print(_score_line(session))
    _print_help()

    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not raw:
            continue

        parts = raw.split()
        command = parts[0].lower()

        if command in {"q", "quit", "exit"}:
            return
        if command in {"h", "help", "?"}:
            _print_help()
            continue
        if command in {"s", "status", "snapshot"}:
            print(json.dumps(session.snapshot(), ensure_ascii=False, indent=2, sort_keys=True))
            continue
        if command == "p":
            threshold = None
            if len(parts) > 1:
                try:
                    threshold = int(parts[1])
                except ValueError:
                    print("Relevância precisa ser um inteiro.")
                    continue
            event = session.press_p(min_relevance=threshold)
            _print_event(event, session)
            if event.type == EventType.MATCH_END:
                print("Fim de jogo.")
            continue
        if command == ".":
            event = session.step_once()
            _print_event(event, session)
            continue
        if command == "save" and len(parts) == 2:
            target = session.save(parts[1])
            print(f"Estado salvo em {target}")
            continue
        if command == "load" and len(parts) == 2:
            try:
                restored = MatchSessionV13.load(parts[1])
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                print(f"Falha ao carregar: {exc}")
                continue
            session.engine = restored.engine
            print(f"Estado restaurado: {_score_line(session)}")
            continue

        print("Comando desconhecido. Digite 'help'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Live v1.3 match runner")
    parser.add_argument("--home", default="amiguinhos_u21")
    parser.add_argument("--away", default="flamengo_u21")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--auto-adapt", action="store_true")
    parser.add_argument("--extra-time", action="store_true")
    parser.add_argument("--official-final", action="store_true")
    parser.add_argument("--load", dest="load_path")
    args = parser.parse_args()

    if args.official_final and args.load_path:
        parser.error("--official-final cannot be combined with --load")

    if args.load_path:
        session = MatchSessionV13.load(args.load_path)
    elif args.official_final:
        session = MatchSessionV13.from_official_final()
    else:
        session = MatchSessionV13.from_fixture(
            args.home,
            args.away,
            seed=args.seed,
            auto_adapt=args.auto_adapt,
            allow_extra_time=args.extra_time,
        )
    run_cli(session)


if __name__ == "__main__":
    main()
