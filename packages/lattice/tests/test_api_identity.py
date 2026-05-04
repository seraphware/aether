"""Tests for the /identity HTTP endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lattice.app import create_app
from lattice.identity import reset_identity_cache_for_tests


@pytest.fixture(autouse=True)
def isolate_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('LATTICE_HOME', str(tmp_path))
    reset_identity_cache_for_tests()


def test_identity_endpoint_returns_device_id() -> None:
    with TestClient(create_app()) as client:
        response = client.get('/identity')

        assert response.status_code == 200
        body = response.json()
        assert 'device_id' in body
        assert 'public_key_b32' in body
        assert body['device_id'] == body['public_key_b32']
        assert len(body['device_id']) >= 50


def test_identity_endpoint_is_stable_across_requests() -> None:
    with TestClient(create_app()) as client:
        first = client.get('/identity').json()
        second = client.get('/identity').json()

        assert first['device_id'] == second['device_id']
