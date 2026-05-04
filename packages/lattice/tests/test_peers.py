"""Tests for Peers, registration, listing, update."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from lattice.db import init_db, reset_db_for_tests
from lattice.peers import count_peers, get_peer, list_peers, mark_peer_seen, register_peer


@pytest.fixture(autouse=True)
def isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('LATTICE_HOME', str(tmp_path))
    reset_db_for_tests()
    init_db()


def test_register_peer_creates_peer() -> None:
    device_id = 'bob-id'
    url = 'test.com'
    label = 'bob'

    initial_fetched = get_peer(device_id)

    register_peer(device_id, label, url)

    fetched = get_peer(device_id)

    assert initial_fetched is None
    assert fetched.device_id == device_id


def test_register_peer_updates_existing() -> None:
    device_id = 'bob-id'
    url = 'test.com'
    label = 'bob'

    register_peer(device_id, 'wrong-label', 'wrong-url')

    register_peer(device_id, label, url)

    fetched = get_peer(device_id)
    assert fetched.device_id == device_id
    assert fetched.url == url
    assert fetched.label == label


def test_get_peer_returns_peer() -> None:
    device_id = 'bob-id'
    url = 'test.com'
    label = 'bob'

    register_peer(device_id, label, url)

    register_peer('test', 'test', 'test')

    fetched = get_peer(device_id)

    assert fetched.device_id == device_id
    assert fetched.url == url


def test_get_peer_not_found_returns_none() -> None:
    device_id = 'bob-id'
    url = 'test.com'
    label = 'bob'
    non_existent = 'missing'

    register_peer(device_id, label, url)

    fetched = get_peer(non_existent)

    assert fetched is None


def test_mark_peer_seen_sets_last_seen_at() -> None:
    device_id = 'bob-id'
    url = 'test.com'
    label = 'bob'

    register_peer(device_id, label, url)
    before = datetime.now(UTC)
    mark_peer_seen(device_id)
    after = datetime.now(UTC)

    fetched = get_peer(device_id)

    assert before <= fetched.last_seen_at <= after


def test_count_peers_returns_correct_number():
    ids = ['bob1', 'bob2', 'bob3']
    url = 'test.com'
    label = 'bob'

    for peer_id in ids:
        register_peer(peer_id, label, url)

    count = count_peers()
    assert count == 3


def test_list_events_pagination() -> None:
    ids = ['bob1', 'bob2', 'bob3', 'bob4', 'bob5']
    url = 'test.com'
    label = 'bob'

    for peer_id in ids:
        register_peer(peer_id, label, url)

    page1 = list_peers(limit=2, offset=0)
    page2 = list_peers(limit=2, offset=2)

    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].device_id != page2[0].device_id


def test_peers_persist_across_engine_resets(tmp_path) -> None:
    device_id = 'bob-id'
    url = 'test.com'
    label = 'bob'

    register_peer(device_id, label, url)
    reset_db_for_tests()
    init_db()

    fetched = get_peer(device_id)
    assert fetched.device_id == device_id
    assert fetched.url == url
    assert fetched.label == label
