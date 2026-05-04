"""Tests for peer connections, handshakes."""

from collections.abc import Callable
from pathlib import Path

import pytest
from lattice.helpers import b64_encode
from lattice.identity import load_or_create_identity
from lattice.peer_connections import _do_outbound_handshake
from lattice.peer_protocol import (
    ClientHandshake,
    HandshakeFailed,
    ServerChallenge,
    ServerHandshakeOk,
    make_challenge,
)
from websockets.exceptions import ConnectionClosed


class FakeWebSocket:
    def __init__(
            self,
            on_send: Callable[[str], str | None] | None = None,
    )->None:
        self.on_send = on_send

        self._pending_recv: list[str] = []

        self.sent: list[str] = []
    def queue_recv(self, msg: str) -> None:
        self._pending_recv.append(msg)

    async def recv(self) -> str:
        if not self._pending_recv:
            raise ConnectionClosed(None, None)
        return self._pending_recv.pop(0)

    async def send(self, msg: str):
        self.sent.append(msg)
        if self.on_send is not None:
            response = self.on_send(msg)
            if response is not None:
                self.queue_recv(response)

@pytest.fixture(autouse=True)
def temp_identity_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Each test gets a fresh identity in a temp dir, not ~/.lattice."""
    monkeypatch.setenv('LATTICE_HOME', str(tmp_path))
    return tmp_path / 'identity.key'

async def test_outbound_handshake_succeeds_with_matching_peer_identity(tmp_path: Path) -> None:
    our_identity = load_or_create_identity()
    other_path = tmp_path / 'other_identity.key'
    peer_identity = load_or_create_identity(path=other_path)
    challenge = make_challenge()
    initial_challenge_json = ServerChallenge(
            type='challenge',
            challenge_hex=challenge.hex(),
            device_id=peer_identity.device_id,
        ).model_dump_json()
    def server_responds_to_handshake(sent_msg: str) -> str:
        """When the client sends the handshake, sign their challenge and return ok."""
        client_msg = ClientHandshake.model_validate_json(sent_msg)
        client_challenge = bytes.fromhex(client_msg.challenge_hex)
        return ServerHandshakeOk(
            type="handshake_ok",
            signature_b64=b64_encode(peer_identity.sign(client_challenge)),
        ).model_dump_json()
    fake_ws = FakeWebSocket(on_send=server_responds_to_handshake)
    fake_ws.queue_recv(initial_challenge_json)
    result = await _do_outbound_handshake(fake_ws, our_identity, peer_identity.device_id)
    assert result is True

async def test_outbound_handshake_fails_when_server_identity_mismatches(tmp_path: Path) -> None:
    our_identity = load_or_create_identity()
    other_path = tmp_path / 'other_identity.key'
    peer_identity = load_or_create_identity(path=other_path)
    third_path = tmp_path / 'third_identity.key'
    third_identity = load_or_create_identity(path=third_path)
    challenge = make_challenge()
    initial_challenge_json = ServerChallenge(
            type='challenge',
            challenge_hex=challenge.hex(),
            device_id=third_identity.device_id,
        ).model_dump_json()
    def server_responds_to_handshake(sent_msg: str) -> str:
        client_msg = ClientHandshake.model_validate_json(sent_msg)
        client_challenge = bytes.fromhex(client_msg.challenge_hex)
        return ServerHandshakeOk(
            type="handshake_ok",
            signature_b64=b64_encode(peer_identity.sign(client_challenge)),
        ).model_dump_json()
    fake_ws = FakeWebSocket(on_send=server_responds_to_handshake)
    fake_ws.queue_recv(initial_challenge_json)
    result = await _do_outbound_handshake(fake_ws, our_identity, peer_identity.device_id)
    assert result is False

async def test_outbound_handshake_fails_with_malformed_challenge(tmp_path: Path) -> None:
    our_identity = load_or_create_identity()
    other_path = tmp_path / 'other_identity.key'
    peer_identity = load_or_create_identity(path=other_path)
    challenge = make_challenge()
    initial_challenge_json = ServerChallenge(
            type='challenge',
            challenge_hex=challenge.hex(),
            device_id=peer_identity.device_id,
        ).model_dump_json()
    def server_responds_to_handshake(sent_msg: str) -> str:
        return "{'type': 'subscribe', 'rooms': ['alpha', 'beta']}"
    fake_ws = FakeWebSocket(on_send=server_responds_to_handshake)
    fake_ws.queue_recv(initial_challenge_json)
    result = await _do_outbound_handshake(fake_ws, our_identity, peer_identity.device_id)
    assert result is False

async def test_outbound_handshake_fails_when_servers_signature_is_invalid(tmp_path: Path) -> None:
    our_identity = load_or_create_identity()
    other_path = tmp_path / 'other_identity.key'
    peer_identity = load_or_create_identity(path=other_path)
    other_path = tmp_path / 'third_identity.key'
    third_identity = load_or_create_identity(path=other_path)
    challenge = make_challenge()
    initial_challenge_json = ServerChallenge(
            type='challenge',
            challenge_hex=challenge.hex(),
            device_id=peer_identity.device_id,
        ).model_dump_json()
    def server_responds_to_handshake(sent_msg: str) -> str:
        """When the client sends the handshake, sign their challenge and return ok."""
        client_msg = ClientHandshake.model_validate_json(sent_msg)
        client_challenge = bytes.fromhex(client_msg.challenge_hex)
        return ServerHandshakeOk(
            type="handshake_ok",
            signature_b64=b64_encode(third_identity.sign(client_challenge)),
        ).model_dump_json()
    fake_ws = FakeWebSocket(on_send=server_responds_to_handshake)
    fake_ws.queue_recv(initial_challenge_json)
    result = await _do_outbound_handshake(fake_ws, our_identity, peer_identity.device_id)
    assert result is False

async def test_outbound_handshake_fails_when_server_replies_with_handshake_failed(
    tmp_path: Path
) -> None:
    our_identity = load_or_create_identity()
    other_path = tmp_path / 'other_identity.key'
    peer_identity = load_or_create_identity(path=other_path)
    challenge = make_challenge()
    initial_challenge_json = ServerChallenge(
            type='challenge',
            challenge_hex=challenge.hex(),
            device_id=peer_identity.device_id,
        ).model_dump_json()
    def server_responds_to_handshake(sent_msg: str) -> str:
        return HandshakeFailed(
            type="handshake_failed",
            reason="this is a test",
        ).model_dump_json()
    fake_ws = FakeWebSocket(on_send=server_responds_to_handshake)
    fake_ws.queue_recv(initial_challenge_json)
    result = await _do_outbound_handshake(fake_ws, our_identity, peer_identity.device_id)
    assert result is False
