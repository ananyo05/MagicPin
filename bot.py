"""
Main bot submission module for magicpin AI Challenge.
Exports:
- compose(category, merchant, trigger, customer) -> dict
- app (FastAPI ASGI application)
"""

from typing import Any, Dict, Optional

from app import app
from engine.compose import compose as _engine_compose


def compose(
    category: Dict[str, Any],
    merchant: Dict[str, Any],
    trigger: Dict[str, Any],
    customer: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Deterministic compose function:
    category, merchant, trigger, customer -> {body, cta, send_as, suppression_key, rationale}
    """
    return _engine_compose(category=category, merchant=merchant, trigger=trigger, customer=customer)


__all__ = ["compose", "app"]
