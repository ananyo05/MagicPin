"""
Test suite for all 30 canonical test pairs from dataset/test_pairs.json.
Validates:
- Valid schema (body, cta, send_as, suppression_key, rationale)
- Correct send_as ("vera" vs "merchant_on_behalf")
- No taboos or internal jargon leaked
- Proper vertical voice and grounding
"""

import json
from pathlib import Path
import pytest

from bot import compose

DATASET_DIR = Path(__file__).parent.parent / "dataset"


def load_dataset():
    test_pairs_path = DATASET_DIR / "test_pairs.json"
    with open(test_pairs_path) as fp:
        pairs = json.load(fp)["pairs"]

    categories = {}
    for f in (DATASET_DIR / "categories").glob("*.json"):
        d = json.load(open(f))
        categories[d.get("slug", f.stem)] = d

    merchants = {}
    for f in (DATASET_DIR / "merchants").glob("*.json"):
        d = json.load(open(f))
        merchants[d["merchant_id"]] = d

    customers = {}
    for f in (DATASET_DIR / "customers").glob("*.json"):
        d = json.load(open(f))
        customers[d["customer_id"]] = d

    triggers = {}
    for f in (DATASET_DIR / "triggers").glob("*.json"):
        d = json.load(open(f))
        triggers[d["id"]] = d

    return pairs, categories, merchants, customers, triggers


PAIRS, CATEGORIES, MERCHANTS, CUSTOMERS, TRIGGERS = load_dataset()


@pytest.mark.parametrize("pair", PAIRS, ids=[p["test_id"] for p in PAIRS])
def test_canonical_pair_composition(pair):
    test_id = pair["test_id"]
    trg_id = pair["trigger_id"]
    mid = pair["merchant_id"]
    cid = pair["customer_id"]

    trg = TRIGGERS[trg_id]
    merchant = MERCHANTS[mid]
    cat_slug = merchant["category_slug"]
    category = CATEGORIES[cat_slug]
    customer = CUSTOMERS.get(cid) if cid else None

    res = compose(category=category, merchant=merchant, trigger=trg, customer=customer)

    # 1. Output must be a dict with all 5 required fields
    assert isinstance(res, dict)
    for field in ["body", "cta", "send_as", "suppression_key", "rationale"]:
        assert field in res, f"Missing field '{field}' in {test_id}"

    # 2. Body must not be empty (these 30 pairs all have valid consent)
    assert len(res["body"].strip()) > 20, f"Body too short or empty for {test_id}: {res['body']}"

    # 3. CTA must be valid
    assert res["cta"] in {"open_ended", "binary", "none"}

    # 4. Correct attribution (send_as)
    if customer is not None or trg.get("scope") == "customer":
        assert res["send_as"] == "merchant_on_behalf", f"Expected customer send_as for {test_id}"
    else:
        assert res["send_as"] == "vera", f"Expected merchant send_as for {test_id}"

    # 5. Taboo and jargon checks
    body_lower = res["body"].lower()
    for taboo in ["guaranteed", "completely cure", "miracle", "best in city"]:
        assert taboo not in body_lower, f"Forbidden taboo '{taboo}' found in {test_id}"

    for jargon in ["triggercontext", "merchantcontext", "payload", "placeholder", "category_slug"]:
        assert jargon not in body_lower, f"Internal jargon '{jargon}' found in {test_id}"

    # 6. Specificity check: message should contain numbers, dates, prices, or names
    has_specifics = any(c.isdigit() for c in res["body"]) or any(
        kw in body_lower for kw in ["dr.", "jida", "dci", "diwali", "ipl", "swiggy", "google", "tomorrow"]
    )
    assert has_specifics, f"Message lacks verifiable specifics in {test_id}: {res['body']}"
