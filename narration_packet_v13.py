from __future__ import annotations

"""Narration-safe adapter for the v1.3 live runner.

This module does not alter match physics, RNG, tactics or event generation.
It only converts the events already produced by the MatchEngine into a
self-contained packet for a live commentator/LLM.

Goals:
- the displayed clock never goes backwards, including after save/load;
- causally necessary low-relevance events are carried as bridge events;
- two records from the same incident are not narrated twice;
- cards are narrated only from their public card event, never pre-announced by a foul;
- repeated background/micro-adjustment messages are suppressed;
- restarts and possession transitions are explicit;
- internal metrics and implementation details are recursively removed.
"""

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Iterable


BRIDGE_TYPES = {
    "turnover",
    "foul",
    "card",
    "offside",
    "corner",
    "free_kick",
    "rebound",
    "substitution",
    "injury",
    "period_end",
    "match_end",
}

# Data useful to the simulator but inappropriate for a live caller. Matching is
# recursive so nested zone/pending/restart structures cannot leak metrics.
_HIDDEN_DATA_TOKENS = (
    "probability",
    "chance",
    "danger",
    "xg",
    "execution",
    "roll",
    "threshold",
    "relevance",
    "multiplier",
    "attribute_weights",
    "ability",
    "spread",
    "difficulty",
    "score_delta",
)

NARRATOR_RULES = [
    "Narrate as a live football commentator in pt-BR.",
    "Never mention the simulation engine, code, RNG, internal state or that an event was returned by a command.",
    "Never expose internal probabilities, danger values, execution scores, rolls, thresholds or hidden ratings.",
    "Never invent an action that is not supported by main_event, bridge_events or continuity.",
    "Never announce the same incident twice. If multiple records belong to one incident, consolidate them.",
    "A card must only be announced when a card event is present; never infer or pre-announce discipline from a foul or advantage event.",
    "Include bridge_events when they are needed to explain a change of possession, restart, discipline or causal continuity.",
    "Never display a clock earlier than continuity.previous_display_clock.",
    "If an action remains pending, end naturally on anticipation; never say that the engine or system stopped.",
    "Do not turn repeated tactical background adjustments into separate headline events unless the packet explicitly marks them narratable.",
    "Describe shot_target and intended_shot_region as intention only; left/right are viewed by the shooter; actual_shot_region and the outcome describe where the ball went. A blocked ball never reached the goal plane.",
    "Resolve resolved_pending_action before describing the resulting shot, clearance or keeper claim.",
    "Describe a successful deception or dribble_move when it creates separation; do not invent a successful duel from a failed attempt.",
    "Use pass_technique together with pass_purpose and pass_technique_executed; a technique attempt does not guarantee a completed pass.",
    "Mention keeper_returned_team, keeper_up and empty_goal_team when present; never invent a counterattack.",
    "Use circulation_summary for the uneventful interval and match the emotional tone to contextual_emotion without inventing chances.",
    "Use the scoreboard and clock from this packet as authoritative for the narration.",
]


@dataclass
class NarrationStateV13:
    """Ephemeral narrator state; separate from deterministic match state."""

    consumed_log_index: int = 0
    last_display_second: float = 0.0
    narrated_incidents: set[str] = field(default_factory=set)
    recent_signatures: dict[str, float] = field(default_factory=dict)
    recent_cards: dict[str, float] = field(default_factory=dict)
    period_anchor_marker: int = 0

    @classmethod
    def for_engine(cls, engine: Any) -> "NarrationStateV13":
        # Existing log entries are historical and must not be re-narrated.
        # Presentation time is period-aware: stoppage time remains attached to
        # the period that produced it, while a restored second-half session
        # resumes from the 45:00 public clock rather than the accumulated raw
        # simulation clock.
        state = getattr(engine, "state", None)
        log = getattr(state, "event_log", []) or []
        try:
            raw_second = max(0.0, float(getattr(state, "second", 0.0)))
        except (TypeError, ValueError):
            raw_second = 0.0
        public_second, anchor = _public_clock_components(
            engine, raw_second, include_current_period_end=True
        )
        return cls(
            consumed_log_index=len(log),
            last_display_second=public_second,
            period_anchor_marker=anchor,
        )


def _event_type(event: Any) -> str:
    value = getattr(getattr(event, "type", None), "value", None)
    return str(value if value is not None else getattr(event, "type", "unknown"))


def _team_name(session: Any, team: Any) -> str | None:
    if team not in (0, 1):
        return None
    try:
        return session.engine.teams[int(team)].team.name
    except Exception:
        return None


def minute_to_second(minute: Any) -> float:
    try:
        return max(0.0, float(minute) * 60.0)
    except (TypeError, ValueError):
        return 0.0


def format_clock_from_second(second: float) -> str:
    total = max(0, int(round(float(second))))
    minutes, seconds = divmod(total, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _period_end_points(engine: Any) -> list[tuple[float, int]]:
    points: list[tuple[float, int]] = []
    state = getattr(engine, "state", None)
    for event in (getattr(state, "event_log", []) or []):
        if _event_type(event) != "period_end":
            continue
        data = getattr(event, "data", {}) or {}
        try:
            marker = int(data.get("marker"))
        except (TypeError, ValueError, AttributeError):
            continue
        points.append((minute_to_second(getattr(event, "minute", 0.0)), marker))
    return points


def _public_clock_components(
    engine: Any,
    raw_second: float,
    *,
    include_current_period_end: bool = False,
) -> tuple[float, int]:
    """Map accumulated engine time to the public football match clock.

    The engine intentionally keeps a continuous physical clock, so first-half
    stoppage time is still present internally when the second half starts.
    Public presentation must not carry that stoppage into the second-half
    minute count. The latest completed period gives the cumulative offset.
    """
    raw_second = max(0.0, float(raw_second))
    latest_end_second: float | None = None
    latest_marker = 0
    tolerance = 0.51 if include_current_period_end else -0.51
    for end_second, marker in _period_end_points(engine):
        if end_second <= raw_second + tolerance and marker >= latest_marker:
            latest_end_second = end_second
            latest_marker = marker

    if latest_end_second is None:
        return raw_second, 0

    cumulative_offset = max(0.0, latest_end_second - latest_marker * 60.0)
    return max(latest_marker * 60.0, raw_second - cumulative_offset), latest_marker


def format_match_clock(
    engine: Any,
    raw_second: float,
    *,
    include_current_period_end: bool = False,
) -> str:
    public_second, anchor = _public_clock_components(
        engine,
        raw_second,
        include_current_period_end=include_current_period_end,
    )

    markers = list(getattr(getattr(engine, "state", None), "period_markers", []) or [])
    next_marker = next((int(m) for m in markers if int(m) > anchor), None)
    if next_marker is not None and public_second > next_marker * 60.0 + 0.51:
        added = public_second - next_marker * 60.0
        added_total = max(0, int(round(added)))
        added_minutes, added_seconds = divmod(added_total, 60)
        return f"{next_marker:02d}+{added_minutes:02d}:{added_seconds:02d}"

    return format_clock_from_second(public_second)


def _is_hidden_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(token in lowered for token in _HIDDEN_DATA_TOKENS)


def _sanitize_value(value: Any) -> Any:
    """Convert to JSON-ish data while recursively removing internal metrics."""
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, nested in value.items():
            if _is_hidden_key(key):
                continue
            clean[str(key)] = _sanitize_value(nested)
        return clean
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return _sanitize_value(enum_value)
    return str(value)


def _sanitize_data(data: Any) -> dict:
    clean = _sanitize_value(data)
    return clean if isinstance(clean, dict) else {}


def event_fact(event: Any, session: Any) -> dict:
    etype = _event_type(event)
    facts = _sanitize_data(getattr(event, "data", {}))

    # The referee model intentionally emits a separate public CARD event. The
    # underlying foul record also contains the future/queued card for state
    # integrity, but exposing it here makes a commentator announce the same card
    # twice and pre-announces deferred yellows after advantage.
    if etype == "foul":
        facts.pop("card", None)

    return {
        "clock": format_match_clock(
            session.engine,
            minute_to_second(getattr(event, "minute", 0.0)),
        ),
        "type": etype,
        "team": getattr(event, "team", None),
        "team_name": _team_name(session, getattr(event, "team", None)),
        "text_key": getattr(event, "text_key", ""),
        "facts": facts,
    }


def _compact_state_value(value: Any) -> Any:
    if value is None:
        return None
    if is_dataclass(value):
        raw = asdict(value)
        # Keep only continuity fields useful to a commentator. Internal danger
        # and probability-like values are deliberately absent and recursive
        # sanitization applies to nested zone/target structures as well.
        preferred = (
            "team",
            "actor",
            "kind",
            "target",
            "defender",
            "origin",
            "body_part",
            "zone",
        )
        compact = {key: raw[key] for key in preferred if key in raw}
        return _sanitize_value(compact or raw)
    return _sanitize_value(value)


def continuity_snapshot(engine: Any) -> dict:
    state = engine.state
    return {
        "second": float(getattr(state, "second", 0.0)),
        "possession": _sanitize_value(getattr(state, "possession", None)),
        "restart": _compact_state_value(getattr(state, "restart", None)),
        "pending": _compact_state_value(getattr(state, "pending", None)),
    }


def _actor_tokens(event: Any) -> tuple[str, ...]:
    data = getattr(event, "data", {}) or {}
    if not isinstance(data, dict):
        return ()
    names: list[str] = []
    for key in (
        "player",
        "actor",
        "offender",
        "fouler",
        "tackler",
        "attacker",
        "shooter",
        "receiver",
        "defender",
        "victim",
    ):
        value = data.get(key)
        if isinstance(value, str) and value:
            names.append(value.strip().lower())
    return tuple(sorted(set(names)))


def _incident_group(event: Any) -> str:
    etype = _event_type(event)
    if etype in {"foul", "card"}:
        return "discipline"
    if etype in {"shot", "goal", "save", "block", "miss", "post", "rebound", "corner"}:
        return "attempt"
    return etype


def incident_id(event: Any) -> str:
    # Hundredth-minute bucket keeps records emitted for the same incident close
    # together while preserving deterministic IDs across a live session.
    minute_bucket = round(float(getattr(event, "minute", 0.0)), 2)
    actors = ",".join(_actor_tokens(event)) or "-"
    return f"{minute_bucket:.2f}|{getattr(event, 'team', None)}|{_incident_group(event)}|{actors}"


def _signature(event: Any) -> str:
    return f"{getattr(event, 'team', None)}|{_event_type(event)}|{getattr(event, 'text_key', '')}"


def _is_background_repeat(event: Any, state: NarrationStateV13, raw_second: float) -> bool:
    # Repeated info events such as the same screen-center micro-adjustment should
    # not repeatedly interrupt live commentary. Four minutes is a narration
    # cooldown only; it does not alter tactics or engine state.
    if _event_type(event) != "info" or event.data.get("resolved_pending_action") or event.data.get("deception_success") or event.data.get("pass_technique"):
        return False
    sig = _signature(event)
    previous = state.recent_signatures.get(sig)
    state.recent_signatures[sig] = raw_second
    return previous is not None and raw_second - previous < 240.0


def _card_signature(event: Any) -> str | None:
    if _event_type(event) != "card":
        return None
    data = getattr(event, "data", {}) or {}
    if not isinstance(data, dict):
        return None
    player = data.get("player")
    card = data.get("card")
    if not player or not card:
        return None
    return f"{getattr(event, 'team', None)}|{str(player).strip().lower()}|{str(card).strip().lower()}"


def _is_duplicate_card(event: Any, state: NarrationStateV13, raw_second: float) -> bool:
    """Suppress duplicate public records for the same shown card.

    The card kind is part of the key, so a later second-yellow-red is not
    mistaken for a duplicate of the player's earlier yellow.
    """
    sig = _card_signature(event)
    if sig is None:
        return False
    previous = state.recent_cards.get(sig)
    state.recent_cards[sig] = raw_second
    return previous is not None and 0.0 <= raw_second - previous < 120.0


def _score(session: Any) -> dict:
    home = session.engine.teams[0].team.name
    away = session.engine.teams[1].team.name
    h, a = session.engine.score
    return {
        "home": home,
        "away": away,
        "home_goals": int(h),
        "away_goals": int(a),
    }


def _bridge_events(events: Iterable[Any], main_event: Any, session: Any) -> list[dict]:
    bridges: list[dict] = []
    for event in events:
        if event is main_event:
            continue
        if (_event_type(event) in BRIDGE_TYPES or event.text_key in {"player_reaction_to_foul", "mass_confrontation", "referee_warning"} or event.data.get("resolved_pending_action") or event.data.get("deception_success") or event.data.get("dribble_move") or event.data.get("pass_technique")):
            bridges.append(event_fact(event, session))
    return bridges


def build_narration_packet(
    session: Any,
    main_event: Any,
    narrator_state: NarrationStateV13,
    before: dict,
) -> dict:
    """Build one self-contained narration packet from already-generated events."""

    engine = session.engine
    log = getattr(engine.state, "event_log", []) or []
    start = min(narrator_state.consumed_log_index, len(log))
    generated = list(log[start:])
    narrator_state.consumed_log_index = len(log)

    raw_second = minute_to_second(getattr(main_event, "minute", 0.0))
    public_second, event_anchor = _public_clock_components(engine, raw_second)

    if event_anchor != narrator_state.period_anchor_marker:
        previous_second = event_anchor * 60.0
        narrator_state.last_display_second = previous_second
        narrator_state.period_anchor_marker = event_anchor
    else:
        previous_second = narrator_state.last_display_second

    stale_clock = public_second + 0.51 < previous_second

    inc_id = incident_id(main_event)
    duplicate_incident = inc_id in narrator_state.narrated_incidents
    duplicate_card = _is_duplicate_card(main_event, narrator_state, raw_second)
    background_repeat = _is_background_repeat(main_event, narrator_state, raw_second)

    narrate = not (stale_clock or duplicate_incident or duplicate_card or background_repeat)
    if stale_clock:
        reason = "stale_clock_event"
    elif duplicate_incident:
        reason = "incident_already_narrated"
    elif duplicate_card:
        reason = "card_already_narrated"
    elif background_repeat:
        reason = "repeated_background_event"
    else:
        reason = None
        narrator_state.narrated_incidents.add(inc_id)
        narrator_state.last_display_second = max(previous_second, public_second)

    display_second = max(previous_second, public_second)
    after = continuity_snapshot(engine)
    packet_clock = format_match_clock(engine, raw_second)

    # A period-end event belongs to the period that just finished, so its own
    # display remains in added time (e.g. 45+03:28). Only subsequent events
    # adopt the next period's base clock.
    if _event_type(main_event) == "period_end":
        data = getattr(main_event, "data", {}) or {}
        try:
            marker = int(data.get("marker"))
        except (TypeError, ValueError, AttributeError):
            marker = event_anchor
        narrator_state.period_anchor_marker = marker
        narrator_state.last_display_second = marker * 60.0

    # Summaries are grounded in actual low-relevance pass records, not time alone.
    circulation = [e for e in generated if e.text_key == "safe_pass"]
    summary = None
    elapsed = raw_second - float(before.get("second", raw_second))
    if elapsed >= 90 and len(circulation) >= 3:
        summary = {"elapsed_seconds": round(elapsed), "safe_passes": len(circulation),
                   "teams": sorted({e.team for e in circulation if e.team in (0, 1)})}
    h, a = engine.score
    emotion = "normal"
    if public_second >= 85 * 60 and abs(h - a) <= 1:
        emotion = "late_close_match"
    if main_event.data.get("open_goal") or main_event.data.get("empty_goal_team") is not None:
        emotion = "exposed_goal"
    elif main_event.type.value in {"goal", "save", "post", "penalty"} and public_second >= 85 * 60:
        emotion = "decisive_late_chance"
    return {
        "command": "P_RESULT",
        "circulation_summary": summary,
        "contextual_emotion": emotion,
        "sequence": len(log),
        "narrate": narrate,
        "skip_reason": reason,
        "clock": packet_clock,
        "score": _score(session),
        "main_event": event_fact(main_event, session),
        "bridge_events": _bridge_events(generated, main_event, session),
        "continuity": {
            "previous_display_clock": format_clock_from_second(previous_second),
            "raw_event_clock": packet_clock,
            "clock_must_not_go_back": True,
            "possession_before": before.get("possession"),
            "possession_after": after.get("possession"),
            "restart_before": before.get("restart"),
            "restart_after": after.get("restart"),
            "restart_resolved": before.get("restart") is not None and before.get("restart") != after.get("restart"),
            "pending_before": before.get("pending"),
            "pending_after": after.get("pending"),
            "incident_id": inc_id,
        },
        "narration_instructions": {
            "style": "live_football_commentary",
            "language": "pt-BR",
            "rules": list(NARRATOR_RULES),
        },
    }
