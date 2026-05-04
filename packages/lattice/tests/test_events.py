"""Tests for the event envelope: creation, signing, verification."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from lattice.db import init_db, reset_db_for_tests
from lattice.events import (
    SCHEMA_VERSION,
    DuplicateEventError,
    Event,
    EventPayload,
    InvalidSignatureError,
    count_events,
    create_event,
    get_event,
    list_events,
    store_event,
)
from lattice.identity import load_or_create_identity
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('LATTICE_HOME', str(tmp_path))
    reset_db_for_tests()
    init_db()


@pytest.fixture
def identity():
    return load_or_create_identity()


def test_create_event_returns_signed_event(identity) -> None:
    event = create_event(
        identity=identity,
        event_type='test.hello',
        body={'text': 'world'},
    )

    assert isinstance(event, Event)
    assert event.payload.event_type == 'test.hello'
    assert event.payload.body == {'text': 'world'}
    assert event.payload.originating_device == identity.device_id
    assert event.payload.schema_version == SCHEMA_VERSION
    assert event.verify_signature() is True


def test_event_id_is_unique(identity) -> None:
    a = create_event(identity, 'test.a', {})
    b = create_event(identity, 'test.b', {})

    assert a.payload.event_id != b.payload.event_id


def test_sent_at_defaults_to_now(identity) -> None:
    before = datetime.now(UTC)
    event = create_event(identity, 'test.timestamp', {})
    after = datetime.now(UTC)

    assert before <= event.payload.sent_at <= after


def test_explicit_sent_at_is_preserved(identity) -> None:
    when = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    event = create_event(identity, 'test.t', {}, sent_at=when)

    assert event.payload.sent_at == when


def test_canonical_bytes_are_deterministic(identity) -> None:
    payload_a = EventPayload(
        event_id='01HG3Y7P5K8M9N2Q4R6T8V1W3Z',
        event_type='test.t',
        originating_device=identity.device_id,
        sent_at=datetime(2026, 1, 1, tzinfo=UTC),
        schema_version=SCHEMA_VERSION,
        body={'b': 2, 'a': 1},
    )
    payload_b = EventPayload(
        event_id='01HG3Y7P5K8M9N2Q4R6T8V1W3Z',
        event_type='test.t',
        originating_device=identity.device_id,
        sent_at=datetime(2026, 1, 1, tzinfo=UTC),
        schema_version=SCHEMA_VERSION,
        body={'a': 1, 'b': 2},
    )

    assert payload_a.canonical_bytes() == payload_b.canonical_bytes()


def test_verify_rejects_tampered_body(identity) -> None:
    real = create_event(identity, 'test.original', {'text': 'real'})
    forged_payload = EventPayload(
        event_id=real.payload.event_id,
        event_type=real.payload.event_type,
        originating_device=real.payload.originating_device,
        sent_at=real.payload.sent_at,
        schema_version=real.payload.schema_version,
        body={'text': 'forged'},  # different body
    )
    forged = Event(payload=forged_payload, signature_b64=real.signature_b64)

    assert forged.verify_signature() is False


def test_verify_rejects_wrong_signer(identity, tmp_path) -> None:
    real = create_event(identity, 'test.t', {})

    other_identity = load_or_create_identity(path=tmp_path / 'other.key')
    imposter_payload = EventPayload(
        event_id=real.payload.event_id,
        event_type=real.payload.event_type,
        originating_device=other_identity.device_id,  # wrong claim
        sent_at=real.payload.sent_at,
        schema_version=real.payload.schema_version,
        body=real.payload.body,
    )
    imposter = Event(payload=imposter_payload, signature_b64=real.signature_b64)

    assert imposter.verify_signature() is False


def test_verify_rejects_garbage_signature(identity) -> None:
    payload = EventPayload(
        event_id='01HG3Y7P5K8M9N2Q4R6T8V1W3Z',
        event_type='test.t',
        originating_device=identity.device_id,
        sent_at=datetime(2026, 1, 1, tzinfo=UTC),
        schema_version=SCHEMA_VERSION,
        body={},
    )
    bad = Event(payload=payload, signature_b64='!!!not-base64!!!')

    assert bad.verify_signature() is False


def test_event_round_trips_through_json(identity) -> None:
    original = create_event(identity, 'test.roundtrip', {'text': 'hello', 'count': 42})

    as_json = original.model_dump_json()
    reconstructed = Event.model_validate_json(as_json)

    assert reconstructed == original
    assert reconstructed.verify_signature() is True


def test_event_is_frozen(identity) -> None:
    event = create_event(identity, 'test.frozen', {'x': 1})

    with pytest.raises(ValidationError):
        event.payload.body = {'x': 2}

def test_store_and_get_event(identity) -> None:
    event = create_event(identity, 'test.t', {'text': 'hello'})
    store_event(event)

    fetched = get_event(event.payload.event_id)

    assert fetched == event
    assert fetched.verify_signature() is True


def test_get_missing_event_returns_none(identity) -> None:
    assert get_event('01HG3Y7P5K8M9N2Q4R6T8V1W3Z') is None


def test_store_rejects_invalid_signature(identity) -> None:
    event = create_event(identity, 'test.t', {})
    bad = Event(payload=event.payload, signature_b64='wrongsignature')

    with pytest.raises(InvalidSignatureError):
        store_event(bad)


def test_store_rejects_duplicate_event_id(identity) -> None:
    event = create_event(identity, 'test.t', {})
    store_event(event)

    with pytest.raises(DuplicateEventError):
        store_event(event)


def test_list_events_returns_in_chronological_order(identity) -> None:
    a = create_event(identity, 'test.a', {})
    b = create_event(identity, 'test.b', {})
    c = create_event(identity, 'test.c', {})

    store_event(b)
    store_event(a)
    store_event(c)

    listed = list_events()
    assert [e.payload.event_type for e in listed] == ['test.a', 'test.b', 'test.c']


def test_list_events_pagination(identity) -> None:
    for i in range(5):
        store_event(create_event(identity, f'test.{i}', {}))

    page1 = list_events(limit=2, offset=0)
    page2 = list_events(limit=2, offset=2)

    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].payload.event_id != page2[0].payload.event_id


def test_count_events(identity) -> None:
    assert count_events() == 0

    for i in range(3):
        store_event(create_event(identity, f'test.{i}', {}))

    assert count_events() == 3


def test_events_persist_across_engine_resets(identity, tmp_path) -> None:
    event = create_event(identity, 'test.persistent', {'text': 'saved'})
    store_event(event)

    reset_db_for_tests()
    init_db()

    fetched = get_event(event.payload.event_id)
    assert fetched == event


def test_corrupt_database_row_raises_on_read(identity) -> None:
    event = create_event(identity, 'test.t', {'original': True})
    store_event(event)

    from lattice.db import get_session
    from lattice.events import StoredEvent
    from sqlalchemy import update

    with get_session() as session:
        session.execute(
            update(StoredEvent)
            .where(StoredEvent.event_id == event.payload.event_id)
            .values(
                payload_json={**event.payload.model_dump(mode='json'), 'body': {'tampered': True}}
            )
        )

    with pytest.raises(InvalidSignatureError):
        get_event(event.payload.event_id)
