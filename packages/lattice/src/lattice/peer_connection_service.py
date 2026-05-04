"""Service for managing peer connections.
"""
import asyncio

from lattice.identity import DeviceIdentity
from lattice.peer_connections import maintain_peer_connection
from lattice.peers import Peer, list_peers


class PeerConnectionService:
    def __init__(self, identity):
        self.identity = identity
        self.tasks: dict[str, asyncio.Task] = {}

    async def start_all(self) -> None:
        for peer in list_peers():
            self.add_peer(peer)

    async def stop_all(self) -> None:
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()

    def add_peer(self, peer: Peer) -> None:
        self.remove_peer(peer.device_id)
        task = asyncio.create_task(maintain_peer_connection(peer, self.identity))
        self.tasks[peer.device_id] = task

    def remove_peer(self, device_id: str) -> None:
        task = self.tasks.pop(device_id, None)
        if task is not None:
            task.cancel()

_peer_connection_service: PeerConnectionService | None = None


def get_peer_connection_service() -> PeerConnectionService:
    if _peer_connection_service is None:
        raise RuntimeError("peer connection service not initialized")
    return _peer_connection_service


def initialize_peer_connection_service(identity: DeviceIdentity) -> PeerConnectionService:
    """Create the singleton service instance. Called from lifespan."""
    global _peer_connection_service
    _peer_connection_service = PeerConnectionService(identity)
    return _peer_connection_service
