"""Tests for WebSocket endpoints: /ws/events and /ws/peer."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lattice.app import create_app
from lattice.db import init_db, reset_db_for_tests
from lattice.helpers import b64_encode
from lattice.identity import get_identity, load_or_create_identity, reset_identity_cache_for_tests
from lattice.peer_protocol import make_challenge, verify_handshake
from lattice.peers import register_peer


@pytest.fixture(autouse=True)
def isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('LATTICE_HOME', str(tmp_path))
    reset_identity_cache_for_tests()
    reset_db_for_tests()
    init_db()


def test_subscribe_returns_ack_with_subscriptions() -> None:
    with TestClient(create_app()) as client:
        with client.websocket_connect('/ws/events') as ws:
            ws.send_json({'type': 'subscribe', 'rooms': ['alpha', 'beta']})
            response = ws.receive_json()

        assert response['type'] == 'ack'
        assert response['subscriptions'] == ['alpha', 'beta']


def test_unsubscribe_removes_rooms() -> None:
    with TestClient(create_app()) as client:
        with client.websocket_connect('/ws/events') as ws:
            ws.send_json({'type': 'subscribe', 'rooms': ['alpha', 'beta', 'gamma']})
            ws.receive_json()  # discard initial ack

            ws.send_json({'type': 'unsubscribe', 'rooms': ['beta']})
            response = ws.receive_json()

        assert response['type'] == 'ack'
        assert response['subscriptions'] == ['alpha', 'gamma']


def test_unknown_message_type_returns_error() -> None:
    with TestClient(create_app()) as client:
        with client.websocket_connect('/ws/events') as ws:
            ws.send_json({'type': 'explode'})
            response = ws.receive_json()

        assert response['type'] == 'error'
        assert 'unknown message type' in response['message']


def test_subscribe_with_invalid_rooms_returns_error() -> None:
    with TestClient(create_app()) as client:
        with client.websocket_connect('/ws/events') as ws:
            ws.send_json({'type': 'subscribe', 'rooms': 'alpha'})  # string, not list
            response = ws.receive_json()

        assert response['type'] == 'error'
        assert 'rooms must be a list' in response['message']

def test_peer_handshake_succeeds_for_registered_peer(tmp_path: Path) -> None:
    our_identity = get_identity()
    other_path = tmp_path / 'other_identity.key'
    peer_identity = load_or_create_identity(path=other_path)

    with TestClient(create_app()) as client:
        peer_device_id = peer_identity.device_id
        register_peer(
            device_id=peer_device_id,
            label='test-peer',
            url='ws://test/ws/peer',
        )
    with client.websocket_connect('/ws/peer') as ws:
        challenge_msg = ws.receive_json()
        assert challenge_msg['type'] == 'challenge'
        assert challenge_msg['device_id'] == our_identity.device_id
        server_challenge = bytes.fromhex(challenge_msg['challenge_hex'])

        client_signature = b64_encode(peer_identity.sign(server_challenge))
        client_challenge = make_challenge()
        ws.send_json({
            'type': 'handshake',
            'device_id': peer_identity.device_id,
            'signature_b64': client_signature,
            'challenge_hex': client_challenge.hex(),
        })

        ok_msg = ws.receive_json()
        assert ok_msg['type'] == 'handshake_ok'
        assert verify_handshake(
            our_identity.device_id,
            client_challenge,
            ok_msg['signature_b64'],
        ) is True

def test_peer_handshake_fails_for_unknown_peer(tmp_path: Path) -> None:
    our_identity = get_identity()
    other_path = tmp_path / 'other_identity.key'
    peer_identity = load_or_create_identity(path=other_path)

    with TestClient(create_app()) as client, client.websocket_connect('/ws/peer') as ws:
        challenge_msg = ws.receive_json()
        assert challenge_msg['type'] == 'challenge'
        assert challenge_msg['device_id'] == our_identity.device_id
        server_challenge = bytes.fromhex(challenge_msg['challenge_hex'])

        client_signature = b64_encode(peer_identity.sign(server_challenge))
        client_challenge = make_challenge()
        ws.send_json({
            'type': 'handshake',
            'device_id': peer_identity.device_id,
            'signature_b64': client_signature,
            'challenge_hex': client_challenge.hex(),
        })

        fail_msg = ws.receive_json()
        assert fail_msg['type'] == 'handshake_failed'
        assert fail_msg['reason'] == 'unknown peer'

def test_peer_handshake_fails_with_invalid_signature(tmp_path: Path) -> None:
    our_identity = get_identity()
    other_path = tmp_path / 'other_identity.key'
    third_path = tmp_path / 'third_identity.key'
    peer_identity = load_or_create_identity(path=other_path)
    third_identity = load_or_create_identity(path=third_path)

    with TestClient(create_app()) as client:
        peer_device_id = peer_identity.device_id
        register_peer(
            device_id=peer_device_id,
            label='test-peer',
            url='ws://test/ws/peer',
        )
    with client.websocket_connect('/ws/peer') as ws:
        challenge_msg = ws.receive_json()
        assert challenge_msg['type'] == 'challenge'
        assert challenge_msg['device_id'] == our_identity.device_id
        server_challenge = bytes.fromhex(challenge_msg['challenge_hex'])

        client_signature = b64_encode(third_identity.sign(server_challenge))
        client_challenge = make_challenge()
        ws.send_json({
            'type': 'handshake',
            'device_id': peer_identity.device_id,
            'signature_b64': client_signature,
            'challenge_hex': client_challenge.hex(),
        })

        fail_msg = ws.receive_json()
        assert fail_msg['type'] == 'handshake_failed'
        assert fail_msg['reason'] == 'invalid signature'

def test_peer_handshake_fails_with_malformed_message(tmp_path: Path) -> None:
    our_identity = get_identity()
    other_path = tmp_path / 'other_identity.key'
    peer_identity = load_or_create_identity(path=other_path)

    with TestClient(create_app()) as client:
        peer_device_id = peer_identity.device_id
        register_peer(
            device_id=peer_device_id,
            label='test-peer',
            url='ws://test/ws/peer',
        )
    with client.websocket_connect('/ws/peer') as ws:

        challenge_msg = ws.receive_json()
        assert challenge_msg['type'] == 'challenge'
        assert challenge_msg['device_id'] == our_identity.device_id
        server_challenge = bytes.fromhex(challenge_msg['challenge_hex'])

        client_signature = b64_encode(peer_identity.sign(server_challenge))
        client_challenge = make_challenge()
        ws.send_json({
            'tywae': 'handshake',
            'devawsice_id': peer_identity.device_id,
            'signddasature_b64': client_signature,
            'challenaswge_hex': client_challenge.hex(),
        })

        fail_msg = ws.receive_json()
        assert fail_msg['type'] == 'handshake_failed'
        assert fail_msg['reason'] == 'malformed handshake'
