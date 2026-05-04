"""WebSocket endpoints: event firehose (UI) and peer connections (federation).
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from lattice.helpers import b64_encode
from lattice.identity import get_identity
from lattice.peer_protocol import (
    ClientHandshake,
    HandshakeFailed,
    ServerChallenge,
    ServerHandshakeOk,
    make_challenge,
    verify_handshake,
)
from lattice.peers import get_peer, mark_peer_seen

logger = structlog.get_logger(__name__)

router = APIRouter()

@router.websocket('/ws/events')
async def events_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    log = logger.bind(client=str(websocket.client))
    log.info('ws.connect')

    subscriptions: set[str] = set()

    async def read_loop() -> None:
        while True:
            msg = await websocket.receive_json()
            await _handle_message(websocket, msg, subscriptions, log)

    async def write_loop() -> None:
        n = 0
        while True:
            await asyncio.sleep(5)
            n += 1
            await websocket.send_json({'type': 'tick', 'n': n})

    try:
        await asyncio.gather(read_loop(), write_loop())
    except WebSocketDisconnect:
        log.info('ws.disconnect')
    except Exception:
        log.exception('ws.error')


async def _handle_message(
    websocket: WebSocket,
    msg: dict[str, Any],
    subscriptions: set[str],
    log: Any,
) -> None:
    msg_type = msg.get('type')

    if msg_type == 'subscribe':
        rooms = msg.get('rooms', [])
        if not isinstance(rooms, list):
            await websocket.send_json({'type': 'error', 'message': 'rooms must be a list'})
            return
        subscriptions.update(rooms)
        log.info('ws.subscribe', rooms=rooms, total=len(subscriptions))
        await websocket.send_json({'type': 'ack', 'subscriptions': sorted(subscriptions)})

    elif msg_type == 'unsubscribe':
        rooms = msg.get('rooms', [])
        if not isinstance(rooms, list):
            await websocket.send_json({'type': 'error', 'message': 'rooms must be a list'})
            return
        subscriptions.difference_update(rooms)
        log.info('ws.unsubscribe', rooms=rooms, total=len(subscriptions))
        await websocket.send_json({'type': 'ack', 'subscriptions': sorted(subscriptions)})

    else:
        await websocket.send_json(
            {'type': 'error', 'message': f'unknown message type: {msg_type!r}'}
        )


@router.websocket('/ws/peer')
async def peer_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    log = logger.bind(client=str(websocket.client))

    try:
        our_identity = get_identity()

        our_challenge = make_challenge()
        challenge_msg = ServerChallenge(
            type='challenge',
            challenge_hex=our_challenge.hex(),
            device_id=our_identity.device_id,
        )
        await websocket.send_json(challenge_msg.model_dump())

        raw = await websocket.receive_json()
        try:
            client_msg = ClientHandshake.model_validate(raw)
        except ValidationError:
            await websocket.send_json(
                HandshakeFailed(
                    type='handshake_failed',
                    reason='malformed handshake',
                ).model_dump()
            )
            return

        peer = get_peer(client_msg.device_id)
        if peer is None:
            await websocket.send_json(
                HandshakeFailed(
                    type='handshake_failed',
                    reason='unknown peer',
                ).model_dump()
            )
            return

        if not verify_handshake(client_msg.device_id, our_challenge, client_msg.signature_b64):
            await websocket.send_json(
                HandshakeFailed(
                    type='handshake_failed',
                    reason='invalid signature',
                ).model_dump()
            )
            return

        client_challenge = bytes.fromhex(client_msg.challenge_hex)
        our_signature = our_identity.sign(client_challenge)
        signature_b64 = b64_encode(our_signature)

        ok_msg = ServerHandshakeOk(
            type='handshake_ok',
            signature_b64=signature_b64,
        )
        await websocket.send_json(ok_msg.model_dump())

        mark_peer_seen(client_msg.device_id)
        log = log.bind(peer=client_msg.device_id)
        log.info('peer.connected')

        async for msg in websocket.iter_json():
            log.info('peer.message_received', msg=msg)

    except WebSocketDisconnect:
        log.info('peer.disconnected')
    except Exception:
        log.exception('peer.error')
