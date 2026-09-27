"""
Suppression and consent enforcement engine.
Ensures hard compliance rules:
1. Missing or false customer consent suppresses outreach.
2. Suppression key generation for deduplication.
3. Cooldown / deduplication tracking.
"""

from typing import Any, Dict, Optional, Set, Tuple


class SuppressionEngine:
    def __init__(self):
        self._sent_suppression_keys: Set[str] = set()

    def check_suppression(
        self,
        trigger: Dict[str, Any],
        merchant: Dict[str, Any],
        customer: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str, str]:
        """
        Evaluates whether a message must be suppressed.
        Returns: (is_suppressed, suppression_key, reason)
        """
        suppression_key = self.generate_suppression_key(trigger, merchant, customer)

        # Rule 1: Customer consent check
        if customer is not None:
            consent = customer.get("consent")
            if not consent:
                return True, suppression_key, "Customer consent missing or absent"
            
            # Explicit opt-in boolean check if present
            if consent.get("opted_in") is False:
                return True, suppression_key, "Customer explicitly opted out"

            # Check timestamp of opt-in
            if not consent.get("opted_in_at"):
                return True, suppression_key, "Customer consent timestamp missing"

            # Check consent scope
            scope = consent.get("scope", [])
            trigger_kind = trigger.get("kind", "")
            
            # If scope is empty or doesn't permit this outreach type
            if isinstance(scope, list):
                if not scope:
                    return True, suppression_key, "Customer consent scope is empty"
                
                # If trigger is promotional / winback / churn but customer only consented to transactional/reminders
                is_promo = trigger_kind in {"customer_lapsed_hard", "customer_lapsed_soft", "promotional", "festival_upcoming"}
                is_reminder = trigger_kind in {"recall_due", "appointment_tomorrow", "chronic_refill_due"}
                
                allowed_reminders = any("reminder" in s or "recall" in s for s in scope)
                allowed_promo = any("promo" in s or "offer" in s or "marketing" in s for s in scope)

                if is_reminder and not (allowed_reminders or allowed_promo):
                    return True, suppression_key, f"Outreach type '{trigger_kind}' not permitted by customer consent scope"

        # Rule 2: Deduplication by suppression key if already sent
        if suppression_key in self._sent_suppression_keys:
            return True, suppression_key, f"Suppression key '{suppression_key}' already sent in this test session"

        return False, suppression_key, ""

    def record_send(self, suppression_key: str):
        if suppression_key:
            self._sent_suppression_keys.add(suppression_key)

    def generate_suppression_key(
        self,
        trigger: Dict[str, Any],
        merchant: Dict[str, Any],
        customer: Optional[Dict[str, Any]] = None,
    ) -> str:
        # Use existing suppression_key if trigger provided it
        if trigger.get("suppression_key"):
            return trigger["suppression_key"]

        t_kind = trigger.get("kind", "trigger")
        m_id = merchant.get("merchant_id", "m_unknown")

        if customer:
            c_id = customer.get("customer_id", "c_unknown")
            return f"{t_kind}:{m_id}:{c_id}"
        
        t_id = trigger.get("id", "t_unknown")
        return f"{t_kind}:{m_id}:{t_id}"

    def reset(self):
        self._sent_suppression_keys.clear()


suppression_engine = SuppressionEngine()
