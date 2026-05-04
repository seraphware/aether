"""Tests for device identity: generation, persistence, signing, verification."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from lattice.identity import (
    DeviceIdentity,
    load_or_create_identity,
    verify,
)


@pytest.fixture
def temp_identity_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv('LATTICE_HOME', str(tmp_path))
    return tmp_path / 'identity.key'


def test_first_run_creates_identity(temp_identity_path: Path) -> None:
    assert not temp_identity_path.exists()

    identity = load_or_create_identity()

    assert temp_identity_path.exists()
    assert temp_identity_path.stat().st_size == 32
    assert isinstance(identity, DeviceIdentity)
    assert len(identity.device_id) >= 50
    assert identity.device_id == identity.device_id.lower()


def test_second_run_loads_same_identity(temp_identity_path: Path) -> None:
    first = load_or_create_identity()
    second = load_or_create_identity()

    assert first.device_id == second.device_id


def test_identity_file_has_restrictive_permissions(temp_identity_path: Path) -> None:
    if os.name == 'nt':
        pytest.skip('POSIX permissions not enforced the same way on Windows')

    load_or_create_identity()

    mode = temp_identity_path.stat().st_mode & 0o777
    assert mode == 0o600, f'expected 0o600, got {oct(mode)}'


def test_corrupt_identity_file_raises(temp_identity_path: Path) -> None:
    temp_identity_path.parent.mkdir(parents=True, exist_ok=True)
    temp_identity_path.write_bytes(b'not 32 bytes')

    with pytest.raises(ValueError, match='corrupt'):
        load_or_create_identity()


def test_sign_and_verify_roundtrip(temp_identity_path: Path) -> None:
    identity = load_or_create_identity()
    message = b'hello, lattice'

    signature = identity.sign(message)

    assert verify(identity.device_id, message, signature) is True


def test_verify_rejects_tampered_message(temp_identity_path: Path) -> None:
    identity = load_or_create_identity()
    signature = identity.sign(b'original')

    assert verify(identity.device_id, b'tampered', signature) is False


def test_verify_rejects_wrong_signer(temp_identity_path: Path, tmp_path: Path) -> None:
    """A signature from device A does not verify under device B's public key."""
    identity_a = load_or_create_identity()
    signature = identity_a.sign(b'hello')

    # Generate a second, separate identity at a different path.
    other_path = tmp_path / 'other_identity.key'
    identity_b = load_or_create_identity(path=other_path)

    # Sanity check: they're actually different.
    assert identity_a.device_id != identity_b.device_id

    # B's public key cannot verify A's signature.
    assert verify(identity_b.device_id, b'hello', signature) is False


def test_verify_rejects_garbage_signature(temp_identity_path: Path) -> None:
    """An obviously-bad signature is rejected without raising."""
    identity = load_or_create_identity()

    assert verify(identity.device_id, b'hello', b'\x00' * 64) is False
