"""
Adversarial and edge case test suite.
Validates:
1. Consent suppression (absent consent, opted out, missing timestamp, restricted scope)
2. Deduplication & suppression keys
3. /v1/tick constraints (20 actions hard cap, 1 action per merchant)
4. /v1/reply intent handling:
   - Auto-reply hell detection -> graceful exit (action: end)
   - Commitment / intent transition -> immediate ACTION mode without qualifying
   - Hostility / spam complaints -> graceful exit (action: end)
   - Off-topic requests -> polite on-mission redirection
5. Defensive input handling (malformed payloads never trigger 500)
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app import app
from bot import compose
from engine.suppression import suppression_engine
from store import store


@pytest.fixture(autouse=True)
def clean_state():
    store.clear()
    suppression_engine.reset()
    yield
    store.clear()
    suppression_engine.reset()


def test_customer_consent_hard_suppression():
    merchant = {
        "merchant_id": "m_test_dentist",
        "category_slug": "dentists",
        "identity": {"name": "Test Clinic", "owner_first_name": "Meera"},
    }
    category = {"slug": "dentists"}
    trigger = {"kind": "recall_due", "scope": "customer", "id": "trg_test_recall"}

    # Case A: Consent object missing completely
    cust_no_consent = {"customer_id": "c_1", "identity": {"name": "Rahul"}}
    res1 = compose(category=category, merchant=merchant, trigger=trigger, customer=cust_no_consent)
    assert res1["send_as"] == "suppressed"
    assert res1["body"] == ""
    assert "consent missing" in res1["rationale"].lower()

    # Case B: Explicitly opted out
    cust_opted_out = {
        "customer_id": "c_2",
        "identity": {"name": "Rahul"},
        "consent": {"opted_in": False, "opted_in_at": "2025-01-01"},
    }
    res2 = compose(category=category, merchant=merchant, trigger=trigger, customer=cust_opted_out)
    assert res2["send_as"] == "suppressed"
    assert "opted out" in res2["rationale"].lower()

    # Case C: Missing timestamp
    cust_no_timestamp = {
        "customer_id": "c_3",
        "identity": {"name": "Rahul"},
        "consent": {"opted_in": True, "opted_in_at": None},
    }
    res3 = compose(category=category, merchant=merchant, trigger=trigger, customer=cust_no_timestamp)
    assert res3["send_as"] == "suppressed"
    assert "timestamp missing" in res3["rationale"].lower()

    # Case D: Valid consent -> outreach allowed
    cust_valid = {
        "customer_id": "c_4",
        "identity": {"name": "Rahul"},
        "consent": {"opted_in_at": "2025-01-01", "scope": ["recall_reminders"]},
    }
    res4 = compose(category=category, merchant=merchant, trigger=trigger, customer=cust_valid)
    assert res4["send_as"] == "merchant_on_behalf"
    assert len(res4["body"]) > 10


def test_deduplication_suppression():
    merchant = {
        "merchant_id": "m_test_1",
        "category_slug": "dentists",
        "identity": {"name": "Test Clinic", "owner_first_name": "Meera"},
    }
    category = {"slug": "dentists"}
    trigger = {"kind": "cde_opportunity", "id": "trg_cde_1", "suppression_key": "cde:m_test_1:webinar_1"}

    res1 = compose(category=category, merchant=merchant, trigger=trigger)
    assert res1["send_as"] == "vera"

    # Record send
    suppression_engine.record_send(res1["suppression_key"])

    # Second send attempt with same suppression key should be suppressed
    res2 = compose(category=category, merchant=merchant, trigger=trigger)
    assert res2["send_as"] == "suppressed"
    assert "already sent" in res2["rationale"].lower()


@pytest.mark.asyncio
async def test_tick_action_cap_and_single_merchant_rule():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Preload 25 merchants and 30 triggers
        triggers = []
        for i in range(25):
            mid = f"m_test_{i}"
            store.push("merchant", mid, 1, {
                "merchant_id": mid,
                "category_slug": "dentists",
                "identity": {"name": f"Clinic {i}", "owner_first_name": f"Doctor {i}"},
            })

            # Create 2 triggers for each merchant to test single-action rule
            for t_idx in [1, 2]:
                tid = f"trg_{mid}_{t_idx}"
                store.push("trigger", tid, 1, {
                    "id": tid,
                    "kind": "curious_ask_due",
                    "merchant_id": mid,
                    "urgency": 3,
                })
                triggers.append(tid)

        # Preload category
        store.push("category", "dentists", 1, {"slug": "dentists"})

        # Call /v1/tick with 50 triggers across 25 merchants
        resp = await client.post("/v1/tick", json={"now": "2026-04-26T10:00:00Z", "available_triggers": triggers})
        assert resp.status_code == 200
        data = resp.json()
        actions = data.get("actions", [])

        # Hard constraint 1: Max 20 actions per tick
        assert len(actions) <= 20
        assert len(actions) == 20

        # Hard constraint 2: At most 1 action per merchant
        merchant_ids = [a["merchant_id"] for a in actions]
        assert len(merchant_ids) == len(set(merchant_ids))


@pytest.mark.asyncio
async def test_reply_auto_reply_hell():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        auto_msg = "Thank you for contacting us! Our team will respond shortly."

        # Turn 1: Bot receives canned reply
        resp = await client.post("/v1/reply", json={
            "conversation_id": "conv_auto_test",
            "merchant_id": "m_test",
            "from_role": "merchant",
            "message": auto_msg,
            "turn_number": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        # Bot should detect auto-reply pattern and end conversation immediately
        assert data["action"] == "end"
        assert "auto-reply" in data["rationale"].lower()


@pytest.mark.asyncio
async def test_reply_intent_transition_to_action_mode():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        commit_msg = "Ok lets do it. Whats next?"

        resp = await client.post("/v1/reply", json={
            "conversation_id": "conv_intent_test",
            "merchant_id": "m_test",
            "from_role": "merchant",
            "message": commit_msg,
            "turn_number": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "send"
        body = data.get("body", "").lower()

        # Check action mode keywords
        actioning = ["done", "sending", "draft", "here", "confirm", "proceed", "next"]
        assert any(w in body for w in actioning)

        # Check absence of qualifying questions
        qualifying = ["would you", "do you", "can you tell", "what if", "how about"]
        assert not any(w in body for w in qualifying)


@pytest.mark.asyncio
async def test_reply_hostile_handling():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        hostile_msg = "Stop messaging me. This is useless spam."

        resp = await client.post("/v1/reply", json={
            "conversation_id": "conv_hostile_test",
            "merchant_id": "m_test",
            "from_role": "merchant",
            "message": hostile_msg,
            "turn_number": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "end"


@pytest.mark.asyncio
async def test_reply_off_topic_redirection():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        off_topic_msg = "Can you help me file my GST taxes?"

        resp = await client.post("/v1/reply", json={
            "conversation_id": "conv_offtopic_test",
            "merchant_id": "m_test",
            "from_role": "merchant",
            "message": off_topic_msg,
            "turn_number": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "send"
        assert "google" in data["body"].lower() or "listing" in data["body"].lower()


@pytest.mark.asyncio
async def test_malformed_context_defense():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid version
        r1 = await client.post("/v1/context", json={
            "scope": "category", "context_id": "dentists", "version": "not_an_int", "payload": {}
        })
        assert r1.status_code == 400

        # Non-dict payload
        r2 = await client.post("/v1/context", json={
            "scope": "category", "context_id": "dentists", "version": 1, "payload": "string_not_dict"
        })
        assert r2.status_code == 400

        # Empty context_id
        r3 = await client.post("/v1/context", json={
            "scope": "category", "context_id": "", "version": 1, "payload": {}
        })
        assert r3.status_code == 400
