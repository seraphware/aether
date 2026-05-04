"""Peers: persistence model and repository functions for peer relationships."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import String, select
from sqlalchemy.orm import Mapped, mapped_column

from lattice.db import Base, UTCDateTime, get_session

logger = structlog.get_logger(__name__)


class Peer(Base):
    __tablename__ = 'peers'

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


def register_peer(device_id: str, label: str, url: str) -> None:
    if not device_id:
        raise ValueError("device_id cannot be empty")
    with get_session() as session:
        existing = session.get(Peer, device_id)
        if existing is not None:
            existing.label = label
            existing.url = url
            logger.info('peer.updated', device_id=device_id)
        else:
            row = Peer(
                device_id=device_id,
                label=label,
                url=url,
                created_at=datetime.now(UTC),
            )
            session.add(row)
            logger.info('peer.registered', device_id=device_id)


def get_peer(device_id: str) -> Peer | None:
    with get_session() as session:
        row = session.get(Peer, device_id)
        return row


def list_peers(*, limit: int = 100, offset: int = 0) -> list[Peer]:
    if limit < 1 or limit > 1000:
        raise ValueError(f'limit must be between 1 and 1000, got {limit}')
    if offset < 0:
        raise ValueError(f'offset must be non-negative, got {offset}')

    with get_session() as session:
        result = session.execute(select(Peer).order_by(Peer.created_at).offset(offset).limit(limit))
        return list(result.scalars())


def count_peers() -> int:
    with get_session() as session:
        return session.query(Peer).count()


def mark_peer_seen(device_id: str) -> None:
    with get_session() as session:
        peer = session.get(Peer, device_id)
        if peer is None:
            logger.warning('peer.mark_seen.not_found', device_id=device_id)
            return
        peer.last_seen_at = datetime.now(UTC)
