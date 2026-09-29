"""Error responses must carry CORS headers.

Without them the browser drops the response and the web app can only say
"We couldn't reach Atlas", hiding the real reason (file too large, a
server error with its reference, ...).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from atlas.config import get_settings

ORIGIN = "https://atlasmatch.co.uk"


@pytest.fixture
def client(monkeypatch):
    for key, value in {
        "DATABASE_URL": "postgresql://unused@localhost/unused",
        "CLERK_ISSUER": "https://clerk.example",
        "STORAGE_BUCKET": "unused",
        "STORAGE_ACCESS_KEY_ID": "unused",
        "STORAGE_SECRET_ACCESS_KEY": "unused",
        "WEB_ORIGINS": ORIGIN,
        "MAX_UPLOAD_MB": "1",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    from atlas.api.main import create_app

    app = create_app()

    @app.get("/test-crash")
    def crash():
        raise RuntimeError("boom")

    yield TestClient(app, raise_server_exceptions=False)
    get_settings.cache_clear()


def test_unexpected_error_keeps_cors_headers(client):
    response = client.get("/test-crash", headers={"Origin": ORIGIN})
    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == ORIGIN
    body = response.json()["error"]
    assert body["code"] == "internal_error"
    assert body["reference"] in body["message"]


def test_oversized_upload_keeps_cors_headers(client):
    size = 3 * 1024 * 1024
    response = client.post("/v1/datasets", headers={"Origin": ORIGIN, "Content-Length": str(size)}, content=b"x" * size)
    assert response.status_code == 413
    assert response.headers.get("access-control-allow-origin") == ORIGIN
    assert response.json()["error"]["code"] == "file_too_large"


def test_other_origins_still_get_no_cors_headers(client):
    response = client.get("/test-crash", headers={"Origin": "https://evil.example"})
    assert response.status_code == 500
    assert "access-control-allow-origin" not in response.headers
