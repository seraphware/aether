"""HTTP endpoints for registering fetching and updating Peers."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from lattice.peer_connection_service import get_peer_connection_service
from lattice.peers import (
    count_peers,
    get_peer,
    list_peers,
    register_peer,
)
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix='/peers', tags=['peers'])

class RegisterPeerRequest(BaseModel):
    device_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    url: str = Field(min_length=1)


class PeerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    device_id: str
    label: str
    url: str
    created_at: datetime
    last_seen_at: datetime | None


class PeerListResponse(BaseModel):

    total: int
    limit: int
    offset: int
    peers: list[PeerResponse]


@router.post('', response_model=None, status_code=204)
async def register_peer_endpoint(request: RegisterPeerRequest) -> None:
    register_peer(
        device_id=request.device_id,
        label=request.label,
        url=request.url,
    )

    peer = get_peer(request.device_id)
    if peer is not None:
        get_peer_connection_service().add_peer(peer)

@router.get('', response_model=PeerListResponse)
def list_peers_endpoint(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> PeerListResponse:
    return PeerListResponse(
        total=count_peers(),
        limit=limit,
        offset=offset,
        peers=list_peers(limit=limit, offset=offset),
    )


@router.get('/{device_id}', response_model=PeerResponse)
def get_peer_endpoint(device_id: str) -> PeerResponse:
    peer = get_peer(device_id)
    if peer is None:
        raise HTTPException(status_code=404, detail=f'peer for {device_id} not found')
    return peer
