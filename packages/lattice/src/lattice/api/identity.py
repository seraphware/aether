"""HTTP endpoints exposing this node's identity.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from lattice.identity import DeviceIdentity, get_identity
from pydantic import BaseModel

router = APIRouter(prefix='/identity', tags=['identity'])


class IdentityResponse(BaseModel):
    device_id: str
    public_key_b32: str



@router.get('', response_model=IdentityResponse)
def get_my_identity(identity: DeviceIdentity = Depends(get_identity)) -> IdentityResponse:
    return IdentityResponse(
        device_id=identity.device_id,
        public_key_b32=identity.device_id,  # same value, semantic alias
    )
