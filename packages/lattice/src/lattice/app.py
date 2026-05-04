"""FastAPI application factory and entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from lattice import __version__
from lattice.api.events import router as events_router
from lattice.api.identity import router as identity_router
from lattice.api.peers import router as peers_router
from lattice.db import init_db
from lattice.identity import get_identity
from lattice.peer_connection_service import initialize_peer_connection_service
from lattice.websocket import router as websocket_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    identity = get_identity()
    peer_connection_service = initialize_peer_connection_service(identity)
    await peer_connection_service.start_all()
    try:
        yield
    finally:
        await peer_connection_service.stop_all()


def create_app() -> FastAPI:
    app = FastAPI(
        title='Lattice',
        version=__version__,
        description='Self-hosted decentralized substrate.',
        lifespan=lifespan,
    )

    @app.get('/health')
    def health() -> dict[str, str]:
        return {'status': 'ok', 'version': __version__}

    app.include_router(websocket_router)
    app.include_router(identity_router)
    app.include_router(events_router)
    app.include_router(peers_router)

    return app


app = create_app()
