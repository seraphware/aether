"""Handshake protocol for peer authentication.
"""

from __future__ import annotations

import secrets
from typing import Literal

from pydantic import BaseModel

from lattice.helpers import b64_decode
from lattice.identity import verify

CHALLENGE_BYTES = 32

class ServerChallenge(BaseModel):
    type: Literal['challenge']
    challenge_hex: str
    device_id: str


class ClientHandshake(BaseModel):
    type: Literal['handshake']
    device_id: str
    signature_b64: str
    challenge_hex: str


class ServerHandshakeOk(BaseModel):
    type: Literal['handshake_ok']
    signature_b64: str


class HandshakeFailed(BaseModel):
    type: Literal['handshake_failed']
    reason: str



def make_challenge() -> bytes:
    return secrets.token_bytes(CHALLENGE_BYTES)


def verify_handshake(
    claimed_device_id: str,
    challenge: bytes,
    signature_b64: str,
) -> bool:
    try:
        signature_bytes = b64_decode(signature_b64)
    except (ValueError, Exception):
        return False
    return verify(claimed_device_id, challenge, signature_bytes)
