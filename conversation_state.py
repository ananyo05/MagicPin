"""
Conversation state machine and intent handler for /v1/reply.
Handles:
1. Auto-reply detection and graceful exit / wait.
2. Immediate transition from pitch mode to ACTION mode upon commitment (zero qualification).
3. Hostile / unsubscribe handling and polite exit.
4. Merchant question answering and off-topic redirection.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

AUTO_REPLY_PATTERNS = [
    r"thank you for contacting",
    r"will respond shortly",
    r"will get back to you",
    r"automated assistant",
    r"canned response",
    r"hamari team tak pahuncha",
    r"auto-generated",
    r"currently away",
    r"outside business hours",
    r"this is an automated",
]

COMMITMENT_PATTERNS = [
    r"\blets do it\b",
    r"\blet's do it\b",
    r"\bwhats next\b",
    r"\bwhat's next\b",
    r"\bproceed\b",
    r"\bi want to join\b",
    r"\bstart now\b",
    r"\bgo ahead\b",
    r"\byes please\b",
    r"\bconfirm\b",
    r"\bok do it\b",
    r"\byes do it\b",
    r"\bpublish it\b",
    r"\bsend it\b",
    r"\bactivate\b",
]

HOSTILE_PATTERNS = [
    r"\bstop messaging\b",
    r"\buseless spam\b",
    r"\bspam\b",
    r"\bstop\b",
    r"\bunsubscribe\b",
    r"\bdont message\b",
    r"\bdon't message\b",
    r"\bnot interested\b",
    r"\bleave me alone\b",
    r"\bfuck off\b",
    r"\bhate this\b",
]

OFF_TOPIC_PATTERNS = [
    r"\bgst\b",
    r"\btax\b",
    r"\bloan\b",
    r"\baccounting\b",
    r"\bweather\b",
    r"\bcricket score\b",
]


class ConversationStateMachine:
    def __init__(self):
        # conv_id -> list of turn dicts: [{"from": role, "msg": text, "ts": ...}]
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}

    def record_turn(self, conv_id: str, from_role: str, message: str, turn_number: int = 1):
        if conv_id not in self.conversations:
            self.conversations[conv_id] = []
        self.conversations[conv_id].append({
            "from": from_role,
            "message": message,
            "turn_number": turn_number,
        })

    def handle_reply(
        self,
        conv_id: str,
        merchant_id: Optional[str],
        customer_id: Optional[str],
        from_role: str,
        message: str,
        turn_number: int,
        merchant: Optional[Dict[str, Any]] = None,
        category: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Processes inbound message and returns {action, body?, cta?, wait_seconds?, rationale}.
        Action can be 'send', 'wait', or 'end'.
        """
        history = self.conversations.get(conv_id, [])
        self.record_turn(conv_id, from_role, message, turn_number)

        msg_lower = message.strip().lower()

        # 1. Check for Auto-reply pattern
        # Either pattern match or same message sent repeatedly
        is_canned = any(re.search(pat, msg_lower) for pat in AUTO_REPLY_PATTERNS)
        prior_messages = [t["message"].strip().lower() for t in history if t["from"] == from_role]
        repeated_message = prior_messages.count(msg_lower) >= 1

        if is_canned or repeated_message:
            # If auto-reply detected, exit gracefully to avoid burning turns
            return {
                "action": "end",
                "rationale": "Auto-reply detected from merchant's automated WhatsApp system; ending conversation to avoid spamming.",
            }

        # 2. Check Hostile / Unsubscribe / Not interested
        if any(re.search(pat, msg_lower) for pat in HOSTILE_PATTERNS):
            return {
                "action": "end",
                "rationale": "Merchant requested stop or signaled disinterest; gracefully exiting conversation immediately.",
            }

        # 3. Check for Commitment / Action Intent
        # MUST switch immediately to ACTION mode with actioning words and ZERO qualifying questions
        if any(re.search(pat, msg_lower) for pat in COMMITMENT_PATTERNS):
            return {
                "action": "send",
                "body": (
                    "Done! Proceeding with this right away. I have prepared the draft and next steps here for your confirmation. "
                    "Sending the confirmation now so your update goes live immediately."
                ),
                "cta": "none",
                "rationale": "Merchant signaled explicit commitment; switched immediately to ACTION mode with zero qualification.",
            }

        # 4. Check for Off-topic
        if any(re.search(pat, msg_lower) for pat in OFF_TOPIC_PATTERNS):
            return {
                "action": "send",
                "body": (
                    "Samajh gayi! Hamara focus aapke Google Business Profile aur local customers badhane par hai. "
                    "Aapke listing ya offers ke related koi bhi update karna ho toh batayein, hum turant live kar denge."
                ),
                "cta": "open_ended",
                "rationale": "Politely acknowledged off-topic query and redirected back to core merchant growth mission.",
            }

        # 5. Default engaging response / advance conversation
        return {
            "action": "send",
            "body": (
                "Done! Noted your response. I will coordinate the next steps and share the final preview here shortly."
            ),
            "cta": "open_ended",
            "rationale": "Acknowledged merchant input and advanced conversation to next operational step.",
        }

    def clear(self):
        self.conversations.clear()


conversation_sm = ConversationStateMachine()
