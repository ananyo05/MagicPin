"""
Grounding and fact-extraction engine.
Enforces that every claim, metric, price, and entity traces directly back to input JSON.
Prevents hallucinations and ensures strict factual consistency.
"""

from typing import Any, Dict, List, Optional, Tuple


def get_owner_name(merchant: Dict[str, Any], category_slug: str = "") -> str:
    """Extracts the appropriate owner/doctor name grounded in merchant data."""
    identity = merchant.get("identity", {})
    owner_first = identity.get("owner_first_name")
    m_name = identity.get("name", "there")

    if category_slug == "dentists":
        if owner_first:
            if owner_first.lower().startswith("dr.") or owner_first.lower().startswith("dr "):
                return owner_first
            return f"Dr. {owner_first}"
        elif m_name.lower().startswith("dr.") or m_name.lower().startswith("dr "):
            parts = m_name.split()
            return f"{parts[0]} {parts[1]}" if len(parts) > 1 else parts[0]
        return "Doctor"
    
    if owner_first:
        return owner_first
    return m_name.split()[0] if m_name else "there"


def get_merchant_locality(merchant: Dict[str, Any]) -> str:
    identity = merchant.get("identity", {})
    return identity.get("locality") or identity.get("city") or "your locality"


def get_active_offer(merchant: Dict[str, Any], category: Dict[str, Any], keyword: str = "") -> Optional[Dict[str, Any]]:
    """Returns an active offer from merchant catalog, falling back to category offer catalog."""
    # 1. Check merchant's active offers
    offers = merchant.get("offers", [])
    active_offers = [o for o in offers if o.get("status") == "active"]
    if keyword:
        for o in active_offers:
            if keyword.lower() in o.get("title", "").lower():
                return o
    if active_offers:
        return active_offers[0]

    # 2. Check category catalog as template fallback
    cat_catalog = category.get("offer_catalog", [])
    if keyword:
        for o in cat_catalog:
            if keyword.lower() in o.get("title", "").lower():
                return o
    if cat_catalog:
        return cat_catalog[0]

    return None


def get_digest_item(category: Dict[str, Any], item_id: str) -> Optional[Dict[str, Any]]:
    """Finds a digest item by ID in category digest."""
    if not item_id:
        return None
    for d in category.get("digest", []):
        if d.get("id") == item_id:
            return d
    return None


def get_customer_name(customer: Dict[str, Any]) -> str:
    """Returns the name to greet the customer contact by.

    Some minor-linked customer records encode a parent/guardian directly in
    the name field, e.g. "Karthik (parent: Sumitra)". These accounts are
    reached via whatsapp_via_parent, so we should greet the parent by name
    rather than surfacing the raw "(parent: X)" annotation to the child.
    """
    identity = customer.get("identity", {})
    name = identity.get("name") or "there"
    if "(parent:" in name:
        parent = name.split("(parent:", 1)[1].rstrip(")").strip()
        if parent:
            return parent
    return name


def get_customer_child_name(customer: Dict[str, Any]) -> Optional[str]:
    """Returns the child's first name when this customer record is a minor
    linked via a parent/guardian contact (see get_customer_name), else None.
    """
    identity = customer.get("identity", {})
    name = identity.get("name") or ""
    if "(parent:" in name:
        child = name.split("(parent:", 1)[0].strip()
        return child or None
    return None


def is_hindi_preferred(merchant: Dict[str, Any], customer: Optional[Dict[str, Any]] = None) -> bool:
    """Checks if Hindi or Hindi-English mix is preferred by merchant or customer."""
    if customer:
        lang_pref = str(customer.get("identity", {}).get("language_pref", "")).lower()
        if "hi" in lang_pref:
            return True

    languages = merchant.get("identity", {}).get("languages", [])
    if isinstance(languages, list):
        if any("hi" in str(l).lower() for l in languages):
            return True
    elif isinstance(languages, str) and "hi" in languages.lower():
        return True

    return False
