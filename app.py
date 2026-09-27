"""
FastAPI application for Vera Message Engine.
Provides HTTP API according to magicpin AI Challenge specifications.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from conversation_state import conversation_sm
from engine.compose import compose
from engine.signal_selector import rank_triggers
from store import store

START_TIME = time.time()
DATASET_DIR = Path(__file__).parent / "dataset"

app = FastAPI(
    title="Vera Message Engine",
    description="Deterministic message-composition engine for magicpin AI Challenge",
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={
            "accepted": False,
            "reason": "malformed_request",
            "details": str(exc),
        },
    )


class ContextRequest(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: Optional[str] = None


class TickRequest(BaseModel):
    now: Optional[str] = None
    available_triggers: List[str] = Field(default_factory=list)


class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str
    received_at: Optional[str] = None
    turn_number: int = 1


def _resolve_context(scope: str, context_id: str) -> Optional[Dict[str, Any]]:
    """Resolves context from store, falling back to disk if available."""
    val = store.get(scope, context_id)
    if val:
        return val

    # Fallback to local files if pushed during dataset generation
    try:
        if scope == "category":
            p = DATASET_DIR / "categories" / f"{context_id}.json"
            if p.exists():
                return json.load(open(p))
        elif scope == "merchant":
            p = DATASET_DIR / "merchants" / f"{context_id}.json"
            if p.exists():
                return json.load(open(p))
        elif scope == "customer":
            p = DATASET_DIR / "customers" / f"{context_id}.json"
            if p.exists():
                return json.load(open(p))
        elif scope == "trigger":
            p = DATASET_DIR / "triggers" / f"{context_id}.json"
            if p.exists():
                return json.load(open(p))
    except Exception:
        pass
    return None


@app.get("/v1/healthz")
async def healthz():
    uptime = int(time.time() - START_TIME)
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "contexts_loaded": store.counts(),
    }


@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": "Vera Deterministic Engine",
        "team_members": ["Vera Engineering Team"],
        "model": "deterministic-rules-engine-v1",
        "approach": "deterministic parametrized template engine with strict grounding and zero hallucination risk",
        "contact_email": "vera-dev@magicpin.in",
        "version": "1.0.0",
        "capabilities": [
            "multi_turn",
            "auto_reply_detection",
            "intent_transition",
            "consent_suppression",
            "grounding_enforcement",
        ],
        "submitted_at": "2026-09-26T23:30:00Z",
    }


@app.post("/v1/context")
async def post_context(req: ContextRequest):
    try:
        accepted, resp_data, status_code = store.push(
            scope=req.scope,
            context_id=req.context_id,
            version=req.version,
            payload=req.payload,
            delivered_at=req.delivered_at,
        )
        return JSONResponse(status_code=status_code, content=resp_data)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"accepted": False, "reason": "processing_error", "details": str(exc)},
        )


@app.post("/v1/tick")
async def tick(req: TickRequest):
    available_triggers = req.available_triggers or []
    trigger_objs = []
    merchant_map = {}

    for trg_id in available_triggers:
        trg = _resolve_context("trigger", trg_id)
        if trg:
            # Ensure trigger id is present
            if "id" not in trg:
                trg["id"] = trg_id
            trigger_objs.append(trg)
            mid = trg.get("merchant_id") or trg.get("payload", {}).get("merchant_id")
            if mid and mid not in merchant_map:
                m = _resolve_context("merchant", mid)
                if m:
                    merchant_map[mid] = m

    ranked = rank_triggers(trigger_objs, merchant_map)

    actions = []
    seen_merchants = set()

    for trg in ranked:
        if len(actions) >= 20:  # Hard cap: 20 actions per tick
            break

        mid = trg.get("merchant_id") or trg.get("payload", {}).get("merchant_id")
        cid = trg.get("customer_id") or trg.get("payload", {}).get("customer_id")

        if not mid:
            continue

        # Single action per merchant per tick
        if mid in seen_merchants:
            continue

        merchant = merchant_map.get(mid) or _resolve_context("merchant", mid)
        if not merchant:
            continue

        cat_slug = merchant.get("category_slug")
        category = _resolve_context("category", cat_slug) or {}

        customer = _resolve_context("customer", cid) if cid else None

        composed = compose(category=category, merchant=merchant, trigger=trg, customer=customer)

        # Do not emit if message was suppressed or empty
        body_text = composed.get("body", "").strip()
        if not body_text:
            continue

        seen_merchants.add(mid)
        trg_id = trg.get("id", "trg_unknown")

        actions.append({
            "conversation_id": f"conv_{mid}_{trg_id}",
            "merchant_id": mid,
            "customer_id": cid,
            "send_as": composed.get("send_as", "vera"),
            "trigger_id": trg_id,
            "template_name": f"vera_{trg.get('kind', 'generic')}_v1",
            "template_params": [merchant.get("identity", {}).get("name", "")],
            "body": body_text,
            "cta": composed.get("cta", "open_ended"),
            "suppression_key": composed.get("suppression_key", ""),
            "rationale": composed.get("rationale", ""),
        })

    return {"actions": actions}


@app.post("/v1/reply")
async def reply(req: ReplyRequest):
    merchant = _resolve_context("merchant", req.merchant_id) if req.merchant_id else None
    category = None
    if merchant and merchant.get("category_slug"):
        category = _resolve_context("category", merchant["category_slug"])

    resp = conversation_sm.handle_reply(
        conv_id=req.conversation_id,
        merchant_id=req.merchant_id,
        customer_id=req.customer_id,
        from_role=req.from_role,
        message=req.message,
        turn_number=req.turn_number,
        merchant=merchant,
        category=category,
    )
    return resp


@app.post("/v1/teardown")
async def teardown():
    store.clear()
    conversation_sm.clear()
    return {"status": "ok", "message": "Context store and conversation state cleared"}
