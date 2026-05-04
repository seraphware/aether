"""Events: wire envelope, signing, persistence, repository functions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from ulid import ULID

from lattice.db import Base, UTCDateTime, get_session
from lattice.helpers import b64_decode, b64_encode
from lattice.identity import DeviceIdentity, verify

logger = structlog.get_logger(__name__)

# Bump this when the envelope schema changes incompatibly.
SCHEMA_VERSION = 1


class EventPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str = Field(description='ULID. Time-sortable unique identifier.')
    event_type: str = Field(description='Dotted namespace, e.g. "chat.message_sent".')
    originating_device: str = Field(
        description='Base32 device ID of the device that created this event.'
    )
    sent_at: datetime = Field(description='Wall-clock time at the originating device.')
    schema_version: int = Field(description='Envelope schema version.')
    body: dict[str, Any] = Field(description='Event-type-specific content.')

    def canonical_bytes(self) -> bytes:
        as_dict = self.model_dump(mode='json')
        return json.dumps(
            as_dict,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False,
        ).encode('utf-8')


class Event(BaseModel):

    model_config = ConfigDict(frozen=True)

    payload: EventPayload
    signature_b64: str = Field(
        description='Base64-encoded Ed25519 signature over payload.canonical_bytes().'
    )

    def verify_signature(self) -> bool:
        try:
            signature = b64_decode(self.signature_b64)
        except ValueError:
            return False
        return verify(
            self.payload.originating_device,
            self.payload.canonical_bytes(),
            signature,
        )


def create_event(
    identity: DeviceIdentity,
    event_type: str,
    body: dict[str, Any],
    *,
    sent_at: datetime | None = None,
) -> Event:
    payload = EventPayload(
        event_id=str(ULID()),
        event_type=event_type,
        originating_device=identity.device_id,
        sent_at=sent_at or datetime.now(UTC),
        schema_version=SCHEMA_VERSION,
        body=body,
    )
    signature = identity.sign(payload.canonical_bytes())
    return Event(payload=payload, signature_b64=b64_encode(signature))


class StoredEvent(Base):
    __tablename__ = 'events'

    event_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    originating_device: Mapped[str] = mapped_column(String(64), index=True)
    sent_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    schema_version: Mapped[int] = mapped_column()
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    signature_b64: Mapped[str] = mapped_column(String(128))


class EventStoreError(Exception):
    """Base class for event store failures."""


class InvalidSignatureError(EventStoreError):
    """An event's signature did not verify. Should never happen on read."""


class DuplicateEventError(EventStoreError):
    """An event with this event_id already exists."""


def store_event(event: Event) -> None:
    if not event.verify_signature():
        raise InvalidSignatureError(f'event {event.payload.event_id} has invalid signature')

    with get_session() as session:
        existing = session.get(StoredEvent, event.payload.event_id)
        if existing is not None:
            raise DuplicateEventError(f'event {event.payload.event_id} already stored')

        row = StoredEvent(
            event_id=event.payload.event_id,
            event_type=event.payload.event_type,
            originating_device=event.payload.originating_device,
            sent_at=event.payload.sent_at,
            schema_version=event.payload.schema_version,
            payload_json=event.payload.model_dump(mode='json'),
            signature_b64=event.signature_b64,
        )
        session.add(row)
        logger.info(
            'events.stored',
            event_id=event.payload.event_id,
            event_type=event.payload.event_type,
        )


def get_event(event_id: str) -> Event | None:
    with get_session() as session:
        row = session.get(StoredEvent, event_id)
        if row is None:
            return None
        return _row_to_event_verified(row)


def list_events(*, limit: int = 100, offset: int = 0) -> list[Event]:
    if limit < 1 or limit > 1000:
        raise ValueError(f'limit must be between 1 and 1000, got {limit}')
    if offset < 0:
        raise ValueError(f'offset must be non-negative, got {offset}')

    with get_session() as session:
        rows = (
            session.query(StoredEvent)
            .order_by(StoredEvent.event_id)
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_row_to_event_verified(row) for row in rows]


def count_events() -> int:
    with get_session() as session:
        return session.query(StoredEvent).count()


def _row_to_event_verified(row: StoredEvent) -> Event:
    payload = EventPayload(**row.payload_json)
    event = Event(payload=payload, signature_b64=row.signature_b64)

    if not event.verify_signature():
        logger.error(
            'events.invalid_signature_on_read',
            event_id=row.event_id,
        )
        raise InvalidSignatureError(
            f'stored event {row.event_id} has invalid signature — database may be corrupted'
        )

    return event
