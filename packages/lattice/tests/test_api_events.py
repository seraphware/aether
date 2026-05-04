"""Tests for the /events HTTP endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lattice.app import create_app
from lattice.db import init_db, reset_db_for_tests
from lattice.events import Event
from lattice.identity import reset_identity_cache_for_tests


@pytest.fixture(autouse=True)
def isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('LATTICE_HOME', str(tmp_path))
    reset_identity_cache_for_tests()
    reset_db_for_tests()
    init_db()


def test_post_events_returns_signed_event() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            '/events',
            json={'event_type': 'test.echo', 'body': {'text': 'hello'}},
        )

        assert response.status_code == 200
        event = Event.model_validate(response.json())
        assert event.payload.event_type == 'test.echo'
        assert event.payload.body == {'text': 'hello'}
        assert event.verify_signature() is True


def test_post_events_uses_node_identity() -> None:
    with TestClient(create_app()) as client:

        identity = client.get('/identity').json()
        response = client.post(
            '/events',
            json={'event_type': 'test.echo', 'body': {}},
        )
        event = Event.model_validate(response.json())

        assert event.payload.originating_device == identity['device_id']


def test_post_events_validates_request_shape() -> None:
    with TestClient(create_app()) as client:
        response = client.post('/events', json={'event_type': 'test.t'})  # no body

        assert response.status_code == 422


def test_each_post_creates_unique_event_id() -> None:
    with TestClient(create_app()) as client:
        a = client.post('/events', json={'event_type': 'test.a', 'body': {}}).json()
        b = client.post('/events', json={'event_type': 'test.b', 'body': {}}).json()

        assert a['payload']['event_id'] != b['payload']['event_id']


def test_get_events_list_returns_pagination_metadata() -> None:
    with TestClient(create_app()) as client:
        for i in range(3):
            event_type = f'test.{i}'
            client.post('/events', json={'event_type': event_type, 'body': {}})

        response = client.get('/events')
        assert response.status_code == 200
        body = response.json()
        assert body['total'] == 3
        assert body['limit'] == 100
        assert body['offset'] == 0
        assert len(body['events']) == 3


def test_get_event_by_id_returns_event() -> None:
    with TestClient(create_app()) as client:
        posted = client.post('/events', json={'event_type': 'test.t', 'body': {}}).json()
        event_id = posted['payload']['event_id']

        response = client.get(f'/events/{event_id}')
        assert response.status_code == 200
        assert response.json() == posted


def test_get_unknown_event_returns_404() -> None:
    with TestClient(create_app()) as client:
        response = client.get('/events/01HG3Y7P5K8M9N2Q4R6T8V1W3Z')
        assert response.status_code == 404
