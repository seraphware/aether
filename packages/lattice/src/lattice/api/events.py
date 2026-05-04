"""HTTP endpoints for creating, listing, and fetching events."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from lattice.events import (
    DuplicateEventError,
    Event,
    count_events,
    create_event,
    get_event,
    list_events,
    store_event,
)
from lattice.identity import DeviceIdentity, get_identity
from pydantic import BaseModel, Field

router = APIRouter(prefix='/events', tags=['events'])


class CreateEventRequest(BaseModel):
    event_type: str = Field(
        description='Dotted namespace, e.g. "chat.message_sent".',
        examples=['test.echo'],
    )
    body: dict[str, Any] = Field(
        description='Event-type-specific content.',
        examples=[{'text': 'hello'}],
    )


class EventsListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    events: list[Event]


@router.post('', response_model=Event)
def create_event_endpoint(
    request: CreateEventRequest,
    identity: DeviceIdentity = Depends(get_identity),
) -> Event:
    event = create_event(
        identity=identity,
        event_type=request.event_type,
        body=request.body,
    )
    try:
        store_event(event)
    except DuplicateEventError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return event


@router.get('', response_model=EventsListResponse)
def list_events_endpoint(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> EventsListResponse:
    return EventsListResponse(
        total=count_events(),
        limit=limit,
        offset=offset,
        events=list_events(limit=limit, offset=offset),
    )


@router.get('/{event_id}', response_model=Event)
def get_event_endpoint(event_id: str) -> Event:
    event = get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f'event {event_id} not found')
    return event
