from fastapi.testclient import TestClient
from lattice.app import create_app


def test_health_returns_ok() -> None:
    with TestClient(create_app()) as client:
        response = client.get('/health')
        assert response.status_code == 200
        assert response.json()['status'] == 'ok'


def test_health_includes_version() -> None:
    with TestClient(create_app()) as client:
        response = client.get('/health')
        assert 'version' in response.json()
