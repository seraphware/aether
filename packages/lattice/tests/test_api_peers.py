"""Tests for the /peers HTTP endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lattice.app import create_app
from lattice.db import init_db, reset_db_for_tests
from lattice.identity import reset_identity_cache_for_tests


@pytest.fixture(autouse=True)
def isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets its own identity, DB, and caches."""
    monkeypatch.setenv('LATTICE_HOME', str(tmp_path))
    reset_identity_cache_for_tests()
    reset_db_for_tests()
    init_db()


def test_post_peers_returns_204() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            '/peers',
            json={'device_id': 'test.id', 'label': 'test.label', 'url': 'test.url'},
        )

        assert response.status_code == 204


def test_get_peers_list_returns_pagination_metadata() -> None:
    with TestClient(create_app()) as client:
        for i in range(3):
            device_id = f'test.id{i}'
            client.post(
                '/peers', json={'device_id': device_id, 'label': 'test.label', 'url': 'test.url'}
            )

        response = client.get('/peers')
        assert response.status_code == 200
        body = response.json()
        assert body['total'] == 3
        assert body['limit'] == 100
        assert body['offset'] == 0
        assert len(body['peers']) == 3


def test_get_peer_by_id_returns_peer() -> None:
    device_id = 'test.id'
    with TestClient(create_app()) as client:
        client.post(
            '/peers',
            json={'device_id': device_id, 'label': 'test.label', 'url': 'test.url'}
        )

        response = client.get(f'/peers/{device_id}')
        body = response.json()
        assert response.status_code == 200
        assert body['device_id'] == device_id


def test_get_unknown_peer_returns_404() -> None:
    with TestClient(create_app()) as client:
        response = client.get('/peers/01HG3Y7P5K8M9N2Q4R6T8V1W3Z')
        assert response.status_code == 404


def test_register_peer_updates() -> None:
    device_id = 'test.id'
    new_label = 'test_label2'
    with TestClient(create_app()) as client:
        client.post(
            '/peers',
            json={'device_id': device_id, 'label': 'test.label', 'url': 'test.url'}
        )
        client.post('/peers',
            json={'device_id': device_id, 'label': new_label, 'url': 'test.url'}
        )

        response = client.get(f'/peers/{device_id}')
        body = response.json()
        assert response.status_code == 200
        assert body['device_id'] == device_id
        assert body['label'] == new_label
