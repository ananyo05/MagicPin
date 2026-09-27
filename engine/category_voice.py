"""
Category voice rules and taboo scrubbing.
Ensures vertical-specific tone and eliminates forbidden claims/jargon.
"""

from typing import Any, Dict, List

DEFAULT_TABOOS = [
    "guaranteed",
    "100% safe",
    "completely cure",
    "miracle",
    "best in city",
    "doctor approved",
    "unbeatable",
]

INTERNAL_JARGON = [
    "triggercontext",
    "merchantcontext",
    "categorycontext",
    "customercontext",
    "payload",
    "placeholder",
    "category_slug",
    "merchant_id",
    "customer_id",
    "json",
    "llm",
]


def clean_text_and_check_taboos(text: str, category: Dict[str, Any]) -> str:
    """
    Scrubs forbidden claims or internal jargon from the composed text.
    """
    voice = category.get("voice", {})
    taboos = voice.get("vocab_taboo", []) + DEFAULT_TABOOS

    cleaned = text
    lower = cleaned.lower()

    for taboo in taboos:
        # If taboo phrase appears, replace with neutral wording
        t_clean = taboo.split("(")[0].strip().lower()
        if t_clean and t_clean in lower:
            # Replace case-insensitively
            idx = lower.find(t_clean)
            while idx != -1:
                cleaned = cleaned[:idx] + "effective" + cleaned[idx + len(t_clean) :]
                lower = cleaned.lower()
                idx = lower.find(t_clean)

    # Check and clean any accidental internal jargon
    for jargon in INTERNAL_JARGON:
        if jargon in lower:
            idx = lower.find(jargon)
            while idx != -1:
                cleaned = cleaned[:idx] + cleaned[idx + len(jargon) :]
                lower = cleaned.lower()
                idx = lower.find(jargon)

    return cleaned.strip()
