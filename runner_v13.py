from __future__ import annotations

"""Live interactive runner for the v1.3 candidate.

Nothing is simulated at startup beyond constructing the current 0:00 engine
state. A session owns one live MatchEngine instance. The ``p`` command asks
that engine to advance *from its current state* until the next relevant event.
There is no precomputed event queue, no hidden full-match simulation and no
replay of a previously simulated result.

The live ``p`` interface returns a NarrationPacket rather than exposing a raw
event directly. Match physics remain untouched; the packet only adds
continuity, bridge events and explicit instructions for a live commentator.

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
from narration_packet_v13 import (
    NarrationStateV13,
    build_narration_packet,
    continuity_snapshot,
)


VENUE_MODES = ("neutral", "home_away", "shared_stadium")


class MatchSessionV13:
    """Small stateful facade around one live v1.3 engine."""

    def __init__(self, engine: MatchEngine):
        self.engine = engine
        self.narrator_state = NarrationStateV13.for_engine(engine)

    def _reset_narrator_state(self) -> None:
        self.narrator_state = NarrationStateV13.for_engine(self.engine)

    @classmethod
    def from_fixture(
        cls,
        home_key: str = "amiguinhos_u21",
        away_key: str = "flamengo_u21",
        *,
        seed: int = 0,
        auto_adapt: bool = False,
        allow_extra_time: bool = False,
        venue_mode: str = "neutral",
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
        venue_mode = str(venue_mode)
        if venue_mode not in VENUE_MODES:
            raise ValueError(f"venue_mode must be one of {VENUE_MODES}")

        home = load_team_for_v13(home_key)
        away = load_team_for_v13(away_key)
        venue_context = None if venue_mode == "neutral" else {
            "mode": venue_mode,
            "source": "live_runner",
        }
        engine = MatchEngine(
            home,
            away,
            seed=int(seed),
            config=MatchConfig(
                auto_tactical_adaptation=bool(auto_adapt),
                allow_extra_time=bool(allow_extra_time),
            ),
            venue_context=venue_context,
        )
        return cls(engine)

    @classmethod
    def from_official_final(cls) -> "MatchSessionV13":
        """Create the reserved live final session.

        Calling this method intentionally unlocks the previously declared seed.
        It must not be used for calibration, previews, dry runs or CI smokes.
        The Regional Internacional final is explicitly neutral-site unless a
        future competition record states otherwise.
        """
        return cls.from_fixture(
            OFFICIAL_FINAL_HOME,
            OFFICIAL_FINAL_AWAY,
            seed=OFFICIAL_FINAL_SEED,
            auto_adapt=True,
            allow_extra_time=True,
            venue_mode="neutral",
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
        """Compatibility API: advance to and return the next relevant raw event."""
        return self.engine.advance_until_relevant(min_relevance=min_relevance)

    def press_p_packet(self, *, min_relevance: Optional[int] = None) -> dict:
        """Advance on demand and return a narration-safe, self-contained packet.

        Raw duplicate/stale/background records can be consumed internally so a
        single user ``p`` still produces the next narratable moment rather than
        forcing the caller to understand engine bookkeeping.
        """
        packet = None
        before = continuity_snapshot(self.engine)
        for _ in range(256):
            event = self.engine.advance_until_relevant(min_relevance=min_relevance)
            # Consume only already-decided immediate aftermath, never a future
            # restart or deferred advantage card. All records remain in the log.
            queue = getattr(self.engine, "_referee_event_queue", [])
            if event.type in {EventType.FOUL, EventType.PENALTY, EventType.CARD} or event.text_key in {"player_reaction_to_foul", "mass_confrontation"}:
                for _ in range(32):
                    if not queue or abs(queue[0].minute - event.minute) >= .001:
                        break
                    aftermath = self.engine.step()
                    if aftermath.type in {EventType.PERIOD_END, EventType.MATCH_END}:
                        event = aftermath
                        break
            packet = build_narration_packet(
                self,
                event,
                self.narrator_state,
                before,
            )
            if packet.get("narrate") or event.type == EventType.MATCH_END:
                return packet
        if packet is None:  # defensive; loop always executes at least once
            raise RuntimeError("failed to build narration packet")
        raise RuntimeError("no narratable event found within 256 relevant records")

    def press_p_batch(self, count: int, *, min_relevance: Optional[int] = None) -> list[dict]:
        """Return N distinct live moments, stopping at the first period boundary."""
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100:
            raise ValueError("count must be an integer between 1 and 100")
        packets = []
        for _ in range(count):
            if self.engine.state.ended:
                break
            packet = self.press_p_packet(min_relevance=min_relevance)
            packets.append(packet)
            if packet["main_event"]["type"] in {"period_end", "match_end"}:
                break
        return packets

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


def _print_packet(packet: dict) -> None:
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))


def _print_help() -> None:
    print("Comandos:")
    print("  p              avança ao próximo momento narrável e retorna NarrationPacket")
    print("  p Nx           retorna os próximos N lances (ex.: p 5x, p 10x)")
    print("  p N            usa relevância mínima N apenas neste avanço")
    print("  .              avança exatamente um beat e mostra evento bruto (debug)")
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
            try:
                if len(parts) > 2:
                    raise ValueError("Use p, p Nx ou p N (relevância).")
                if len(parts) == 2 and parts[1].lower().endswith("x"):
                    packets = session.press_p_batch(int(parts[1][:-1]))
                else:
                    threshold = int(parts[1]) if len(parts) == 2 else None
                    packets = [session.press_p_packet(min_relevance=threshold)]
            except ValueError as exc:
                print(f"Comando inválido: {exc}")
                continue
            for packet in packets:
                _print_packet(packet)
            if session.engine.state.ended:
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
            session._reset_narrator_state()
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
    parser.add_argument("--venue-mode", choices=VENUE_MODES, default="neutral")
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
            venue_mode=args.venue_mode,
        )
    run_cli(session)


if __name__ == "__main__":
    main()
