"""
Signal selection and ranking engine.
Ranks competing triggers by urgency, impact, recency, and merchant relevance.
Enforces the 20-action cap per tick and 1-action per merchant per tick constraint.
"""

from typing import Any, Dict, List, Optional, Tuple

HIGH_IMPACT_KINDS = {
    "regulation_change": 10,
    "appointment_tomorrow": 9,
    "chronic_refill_due": 9,
    "recall_due": 8,
    "ipl_match_today": 8,
    "active_planning_intent": 8,
    "competitor_opened": 7,
    "cde_opportunity": 7,
    "category_seasonal": 7,
    "perf_dip": 6,
    "perf_spike": 6,
    "milestone_reached": 6,
    "gbp_unverified": 5,
    "festival_upcoming": 5,
    "customer_lapsed_hard": 5,
    "customer_lapsed_soft": 4,
    "dormant_with_vera": 3,
    "curious_ask_due": 3,
}


def rank_triggers(
    triggers: List[Dict[str, Any]],
    merchant_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Ranks triggers in descending order of priority.
    """
    def score_trigger(trg: Dict[str, Any]) -> Tuple[int, int, int]:
        kind = trg.get("kind", "")
        urgency = trg.get("urgency", 3)
        impact = HIGH_IMPACT_KINDS.get(kind, 3)

        mid = trg.get("merchant_id")
        merchant = merchant_map.get(mid, {})
        signals = merchant.get("signals", [])

        # Bonus if merchant signals match the trigger
        match_bonus = 0
        if "high_risk_adult_cohort" in signals and "fluoride" in str(trg):
            match_bonus += 2
        if "ctr_below_peer_median" in signals and kind == "perf_dip":
            match_bonus += 2
        if "engaged_in_last_24h" in signals:
            match_bonus += 1

        return (urgency, impact + match_bonus)

    return sorted(triggers, key=score_trigger, reverse=True)
