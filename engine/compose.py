"""
Core compose orchestrator for Vera Message Engine.
Signature: compose(category, merchant, trigger, customer?) -> dict
Returns: {body, cta, send_as, suppression_key, rationale}
"""

from typing import Any, Dict, Optional

from engine.category_voice import clean_text_and_check_taboos
from engine.suppression import suppression_engine
from engine.templates import (
    compose_active_planning,
    compose_appointment_tomorrow,
    compose_bridal_followup,
    compose_category_seasonal,
    compose_cde_opportunity,
    compose_chronic_refill_due,
    compose_competitor_opened,
    compose_curious_ask,
    compose_customer_lapsed_hard,
    compose_customer_lapsed_soft,
    compose_dormant_with_vera,
    compose_fallback,
    compose_festival_upcoming,
    compose_gbp_unverified,
    compose_ipl_match,
    compose_milestone_reached,
    compose_perf_dip,
    compose_perf_spike,
    compose_recall_due,
    compose_regulation_change,
    compose_renewal_due,
    compose_research_digest,
    compose_review_theme_emerged,
    compose_supply_alert,
    compose_trial_followup,
    compose_winback_eligible,
)


def compose(
    category: Dict[str, Any],
    merchant: Dict[str, Any],
    trigger: Dict[str, Any],
    customer: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Deterministic compose() function.
    Given category, merchant, trigger, and optional customer context,
    produces a fully grounded message adhering to the magicpin AI Challenge rubric.
    """
    # Defensive fallbacks for empty / malformed context
    category = category if isinstance(category, dict) else {}
    merchant = merchant if isinstance(merchant, dict) else {}
    trigger = trigger if isinstance(trigger, dict) else {}
    customer = customer if isinstance(customer, dict) else None

    # Step 1: Suppression & consent check
    is_suppressed, supp_key, supp_reason = suppression_engine.check_suppression(
        trigger=trigger, merchant=merchant, customer=customer
    )
    if is_suppressed:
        return {
            "body": "",
            "cta": "none",
            "send_as": "suppressed",
            "suppression_key": supp_key,
            "rationale": f"Suppressed: {supp_reason}",
        }

    # Step 2: Route by trigger kind
    t_kind = trigger.get("kind", "")

    # Customer-facing triggers — route on whether we actually have a resolved
    # customer object to personalize with, not on the trigger's scope label.
    # (A trigger can be labeled scope="customer" for targeting purposes while
    # still being a merchant-facing message — e.g. winback_eligible,
    # review_theme_emerged, supply_alert — so scope alone is not a reliable
    # signal for which composer branch to use.)
    if customer is not None:
        cust = customer
        if t_kind == "recall_due":
            res = compose_recall_due(category, merchant, trigger, cust)
        elif t_kind == "chronic_refill_due":
            res = compose_chronic_refill_due(category, merchant, trigger, cust)
        elif t_kind == "appointment_tomorrow":
            res = compose_appointment_tomorrow(category, merchant, trigger, cust)
        elif t_kind == "wedding_package_followup":
            res = compose_bridal_followup(category, merchant, trigger, cust)
        elif t_kind == "trial_followup":
            res = compose_trial_followup(category, merchant, trigger, cust)
        elif t_kind == "customer_lapsed_soft":
            res = compose_customer_lapsed_soft(category, merchant, trigger, cust)
        elif t_kind == "customer_lapsed_hard":
            res = compose_customer_lapsed_hard(category, merchant, trigger, cust)
        else:
            res = compose_fallback(category, merchant, trigger, cust)
    else:
        # Merchant-facing triggers
        if t_kind in {"research_digest", "category_research_digest_release"}:
            res = compose_research_digest(category, merchant, trigger)
        elif t_kind in {"regulation_change", "compliance_alert"}:
            res = compose_regulation_change(category, merchant, trigger)
        elif t_kind == "cde_opportunity":
            res = compose_cde_opportunity(category, merchant, trigger)
        elif t_kind == "competitor_opened":
            res = compose_competitor_opened(category, merchant, trigger)
        elif t_kind in {"active_planning_intent", "active_planning"}:
            res = compose_active_planning(category, merchant, trigger)
        elif t_kind == "curious_ask_due":
            res = compose_curious_ask(category, merchant, trigger)
        elif t_kind == "ipl_match_today":
            res = compose_ipl_match(category, merchant, trigger)
        elif t_kind in {"category_seasonal", "seasonal_perf_dip"}:
            res = compose_category_seasonal(category, merchant, trigger)
        elif t_kind == "gbp_unverified":
            res = compose_gbp_unverified(category, merchant, trigger)
        elif t_kind == "milestone_reached":
            res = compose_milestone_reached(category, merchant, trigger)
        elif t_kind == "perf_dip":
            res = compose_perf_dip(category, merchant, trigger)
        elif t_kind == "perf_spike":
            res = compose_perf_spike(category, merchant, trigger)
        elif t_kind == "winback_eligible":
            res = compose_winback_eligible(category, merchant, trigger)
        elif t_kind == "review_theme_emerged":
            res = compose_review_theme_emerged(category, merchant, trigger)
        elif t_kind == "supply_alert":
            res = compose_supply_alert(category, merchant, trigger)
        elif t_kind == "renewal_due":
            res = compose_renewal_due(category, merchant, trigger)
        elif t_kind == "dormant_with_vera":
            res = compose_dormant_with_vera(category, merchant, trigger)
        elif t_kind == "festival_upcoming":
            res = compose_festival_upcoming(category, merchant, trigger)
        else:
            res = compose_fallback(category, merchant, trigger, None)

    # Step 3: Taboo scrubbing and voice cleanup
    res["body"] = clean_text_and_check_taboos(res.get("body", ""), category)

    return res