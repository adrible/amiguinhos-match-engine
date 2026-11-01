from __future__ import annotations

"""Public-event clock adapter for the v1.3 referee layer.

The stable engine emits public event minutes rounded to two decimals. Referee
follow-up events must use that same public clock; otherwise an internal value
such as 32.356 can sort before an already-emitted public 32.36 event.
"""

from engine import Event, EventType
from engine_experiment_v13_referee import (
    MatchEngineV13Referee as _RefereeBase,
    RefereeProfile,
)


class MatchEngineV13Referee(_RefereeBase):
    def _public_referee_minute(self) -> float:
        minute = round(float(self.minute), 2)
        if self.state.event_log:
            minute = max(minute, float(self.state.event_log[-1].minute))
        return minute

    def _queue_event(
        self,
        event_type: EventType,
        team: int,
        relevance: int,
        text_key: str,
        **data,
    ) -> None:
        self._referee_event_queue.append(
            Event(
                self._public_referee_minute(),
                int(team),
                event_type,
                int(relevance),
                text_key,
                data,
            )
        )

    def _emit_queued_event(self) -> Event:
        event = self._referee_event_queue.pop(0)
        if self.state.event_log:
            event.minute = max(float(event.minute), float(self.state.event_log[-1].minute))
        self.state.event_log.append(event)
        return event

    def _emit_deferred_card(self) -> Event:
        row = self._deferred_discipline.pop(0)
        event = Event(
            self._public_referee_minute(),
            int(row["team"]),
            EventType.CARD,
            2,
            "deferred_card_after_advantage",
            dict(row),
        )
        self.state.event_log.append(event)
        return event


MatchEngine = MatchEngineV13Referee

__all__ = ["RefereeProfile", "MatchEngineV13Referee", "MatchEngine"]
