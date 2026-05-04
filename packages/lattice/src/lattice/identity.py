"""Device identity: Ed25519 keypair generation, persistence, signing, verification.
"""

from __future__ import annotations

import os
from base64 import b32decode, b32encode
from dataclasses import dataclass
from pathlib import Path

import structlog
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

logger = structlog.get_logger(__name__)
_cached_identity: DeviceIdentity | None = None


@dataclass(frozen=True)
class DeviceIdentity:

    signing_key: SigningKey

    @property
    def verify_key(self) -> VerifyKey:
        return self.signing_key.verify_key

    @property
    def device_id(self) -> str:
        return b32encode(bytes(self.verify_key)).decode('ascii').rstrip('=').lower()

    def sign(self, message: bytes) -> bytes:
        return self.signing_key.sign(message).signature


def verify(public_key_b32: str, message: bytes, signature: bytes) -> bool:
    try:
        padded = public_key_b32.upper()
        padded += '=' * (-len(padded) % 8)
        public_key_bytes = b32decode(padded)
        VerifyKey(public_key_bytes).verify(message, signature)
        return True
    except (BadSignatureError, ValueError):
        return False

def _default_identity_path() -> Path:
    home = os.environ.get('LATTICE_HOME')
    if home:
        return Path(home) / 'identity.key'
    return Path.home() / '.lattice' / 'identity.key'

def get_identity() -> DeviceIdentity:
    global _cached_identity
    if _cached_identity is None:
        _cached_identity = load_or_create_identity()
    return _cached_identity


def reset_identity_cache_for_tests() -> None:
    """Test-only helper: clear the cached identity so the next call reloads."""
    global _cached_identity
    _cached_identity = None


def load_or_create_identity(path: Path | None = None) -> DeviceIdentity:
    path = path or _default_identity_path()
    log = logger.bind(path=str(path))

    if path.exists():
        seed = path.read_bytes()
        if len(seed) != 32:
            raise ValueError(
                f'identity file at {path} is corrupt: expected 32 bytes, got {len(seed)}'
            )
        identity = DeviceIdentity(SigningKey(seed))
        log.info('identity.loaded', device_id=identity.device_id)
        return identity

    log.info('identity.generating')
    path.parent.mkdir(parents=True, exist_ok=True)
    signing_key = SigningKey.generate()
    seed = bytes(signing_key)

    tmp_path = path.with_suffix('.key.tmp')
    tmp_path.write_bytes(seed)
    tmp_path.chmod(0o600)
    tmp_path.replace(path)

    identity = DeviceIdentity(signing_key)
    log.info('identity.created', device_id=identity.device_id)
    return identity
