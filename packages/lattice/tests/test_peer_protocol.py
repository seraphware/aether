"""Tests for device peer protocol: handshake verification."""

from __future__ import annotations

from base64 import urlsafe_b64encode
from pathlib import Path

import pytest
from lattice.identity import load_or_create_identity
from lattice.peer_protocol import CHALLENGE_BYTES, make_challenge, verify_handshake


def _sign_b64(identity, message: bytes) -> str:
    signature_bytes = identity.sign(message)
    return urlsafe_b64encode(signature_bytes).rstrip(b'=').decode('ascii')


@pytest.fixture(autouse=True)
def temp_identity_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv('LATTICE_HOME', str(tmp_path))
    return tmp_path / 'identity.key'


def test_signed_challenge_returns_true() -> None:
    identity = load_or_create_identity()

    challenge = make_challenge()
    signature_b64 = _sign_b64(identity, challenge)

    is_verified = verify_handshake(identity.device_id, challenge, signature_b64)

    assert is_verified is True


def test_signed_something_else_returns_false() -> None:
    identity = load_or_create_identity()

    challenge = make_challenge()
    diff_challenge = make_challenge()
    signature_b64 = _sign_b64(identity, diff_challenge)

    is_verified = verify_handshake(identity.device_id, challenge, signature_b64)

    assert is_verified is False


def test_malformed_returns_false() -> None:
    identity = load_or_create_identity()

    challenge = make_challenge()

    is_verified = verify_handshake(identity.device_id, challenge, 'i think this is wrong')

    assert is_verified is False


def test_wrong_signer_returns_false(tmp_path: Path) -> None:
    identity = load_or_create_identity()

    challenge = make_challenge()
    other_path = tmp_path / 'other_identity.key'
    identity_b = load_or_create_identity(path=other_path)
    signature_b64 = _sign_b64(identity_b, challenge)

    is_verified = verify_handshake(identity.device_id, challenge, signature_b64)

    assert is_verified is False


def test_make_challenge_returns_correct_size() -> None:
    assert len(make_challenge()) == CHALLENGE_BYTES


def test_two_challenges_differ() -> None:
    assert make_challenge() != make_challenge()


def test_empty_signature_returns_false() -> None:
    identity = load_or_create_identity()
    challenge = make_challenge()
    assert verify_handshake(identity.device_id, challenge, '') is False
