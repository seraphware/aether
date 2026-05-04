"""peer connections functions.
"""
import asyncio
import json

import structlog
import websockets
from pydantic import ValidationError
from websockets.exceptions import ConnectionClosed

from lattice.helpers import b64_encode
from lattice.identity import DeviceIdentity
from lattice.peer_protocol import (
    ClientHandshake,
    ServerChallenge,
    ServerHandshakeOk,
    make_challenge,
    verify_handshake,
)
from lattice.peers import Peer

logger = structlog.get_logger(__name__)

def handle_message(json):
    # do we sanitize here?
    logger.info("peer.message_received", msg=json)

async def maintain_peer_connection(peer: Peer, identity: DeviceIdentity) -> None:
    backoff = 1.0
    while True:
        try:
            async with websockets.connect(peer.url) as ws:
                valid_handshake = await _do_outbound_handshake(ws, identity, peer.device_id)
                if valid_handshake:
                    backoff = 1.0
                    async for raw in ws:
                        handle_message(json.loads(raw))
        except ConnectionClosed:
            logger.info("peer.disconnected")
        except Exception:
            logger.exception("peer.error")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60.0)

async def _do_outbound_handshake(ws, our_identity, expected_device_id) -> bool:
    raw = await ws.recv()
    try:
        challenge_msg = ServerChallenge.model_validate_json(raw)
    except ValidationError:
        return False
    if challenge_msg.device_id != expected_device_id:
        return False
    server_challenge = bytes.fromhex(challenge_msg.challenge_hex)

    client_signature = b64_encode(our_identity.sign(server_challenge))
    client_challenge = make_challenge()
    await ws.send(
        ClientHandshake(
            type='handshake',
            device_id = our_identity.device_id,
            signature_b64 = client_signature,
            challenge_hex = client_challenge.hex()
        ).model_dump_json()
    )
    raw = await ws.recv()
    try:
        ok_msg = ServerHandshakeOk.model_validate_json(raw)
    except ValidationError:
        return False
    return verify_handshake(expected_device_id, client_challenge, ok_msg.signature_b64)
