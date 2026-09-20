from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=utcnow)


@dataclass
class AggregateRoot:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def record_event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self._events.append(DomainEvent(event_type=event_type, payload=payload or {}))
