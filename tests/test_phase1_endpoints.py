"""
Unit tests for Phase 1 endpoints: /v1/healthz, /v1/metadata, /v1/context.
Verifies idempotent versioning, atomic updates, conflict handling, and error defense.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app import app
from store import store


@pytest.fixture(autouse=True)
def clean_store():
    store.clear()
    yield
    store.clear()


@pytest.mark.asyncio
async def test_healthz():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/healthz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "uptime_seconds" in data
        assert data["contexts_loaded"] == {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}


@pytest.mark.asyncio
async def test_metadata():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/metadata")
        assert resp.status_code == 200
        data = resp.json()
        assert "team_name" in data
        assert "version" in data
        assert "capabilities" in data


@pytest.mark.asyncio
async def test_context_push_and_idempotency():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Push version 1
        resp = await client.post(
            "/v1/context",
            json={
                "scope": "category",
                "context_id": "dentists",
                "version": 1,
                "payload": {"slug": "dentists", "title": "Dentists"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is True
        assert data["ack_id"] == "ack_dentists_v1"
        stored_at_1 = data["stored_at"]

        # Re-post same version 1 (idempotent no-op)
        resp2 = await client.post(
            "/v1/context",
            json={
                "scope": "category",
                "context_id": "dentists",
                "version": 1,
                "payload": {"slug": "dentists", "title": "Dentists"},
            },
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["accepted"] is True
        assert data2["stored_at"] == stored_at_1

        # Push higher version 2 (replaces atomically)
        resp3 = await client.post(
            "/v1/context",
            json={
                "scope": "category",
                "context_id": "dentists",
                "version": 2,
                "payload": {"slug": "dentists", "title": "Dentists Updated"},
            },
        )
        assert resp3.status_code == 200
        assert resp3.json()["accepted"] is True
        assert resp3.json()["ack_id"] == "ack_dentists_v2"
        assert store.get("category", "dentists")["title"] == "Dentists Updated"

        # Attempt to push lower version 1 (stale version -> 409 Conflict)
        resp4 = await client.post(
            "/v1/context",
            json={
                "scope": "category",
                "context_id": "dentists",
                "version": 1,
                "payload": {"slug": "dentists", "title": "Old"},
            },
        )
        assert resp4.status_code == 409
        data4 = resp4.json()
        assert data4["accepted"] is False
        assert data4["reason"] == "stale_version"
        assert data4["current_version"] == 2


@pytest.mark.asyncio
async def test_context_validation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid scope
        resp = await client.post(
            "/v1/context",
            json={
                "scope": "invalid_scope",
                "context_id": "test",
                "version": 1,
                "payload": {},
            },
        )
        assert resp.status_code == 400
        assert resp.json()["accepted"] is False
        assert resp.json()["reason"] == "invalid_scope"

        # Invalid version
        resp2 = await client.post(
            "/v1/context",
            json={
                "scope": "merchant",
                "context_id": "m_1",
                "version": -1,
                "payload": {},
            },
        )
        assert resp2.status_code == 400
        assert resp2.json()["accepted"] is False
