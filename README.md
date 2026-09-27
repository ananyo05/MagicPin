# Vera Message Engine — magicpin AI Challenge Submission

## What this is

A deterministic `compose(category, merchant, trigger, customer?)` message-composition engine for Vera, magicpin's AI assistant for merchant growth. Given structured context about a business category, a merchant, a trigger event, and (optionally) a customer, it returns a grounded, specific, single-CTA message — never generated freeform by an LLM at request time.

## Architecture

- **`app.py`** — FastAPI application exposing the five required endpoints: `GET /v1/healthz`, `GET /v1/metadata`, `POST /v1/context`, `POST /v1/tick`, `POST /v1/reply`.
- **`store.py`** — Thread-safe, versioned in-memory context store. Idempotent by `(scope, context_id, version)`; re-posting the same version is a no-op, a higher version replaces atomically, and a stale version returns `409 Conflict`.
- **`engine/compose.py`** — Core orchestrator. Routes each trigger to its composer based on trigger `kind` and whether a resolved `customer` object is present (not on the trigger's `scope` label — see "Bugs found and fixed" below).
- **`engine/templates.py`** — One composer function per trigger kind (23 total), each pulling its specifics — prices, dates, counts, quotes — directly from the merchant/trigger/customer JSON payloads it's given. No composer invents a figure that isn't present in its input.
- **`engine/grounding.py`** — Shared helpers: `get_active_offer`, `get_owner_name`, `get_customer_name`, `get_merchant_locality`, `is_hindi_preferred`, `get_digest_item`.
- **`engine/suppression.py`** — Consent and suppression-key enforcement; customer outreach is blocked outright if `consent` is missing, `opted_in` is `False`, or timestamps are absent.
- **`engine/signal_selector.py`** — Ranks competing triggers per merchant for `/v1/tick`'s single-action-per-merchant, 20-actions-per-tick constraints.
- **`conversation_state.py`** — Multi-turn state machine for `/v1/reply`: auto-reply-loop detection, intent-to-action-mode transition, hostile-message handling.

## Why deterministic templates over raw LLM completion

- **Latency**: sub-5ms per call, comfortably inside the 30s timeout at 10 req/s.
- **Zero fabrication by construction**: every number, date, and quote in a composed message is read from a payload field, not generated. When a composer has no real data to ground a claim (e.g. no pricing data on an `active_planning_intent` trigger), it says so honestly rather than inventing a figure — see "Bugs found and fixed."
- **100% reproducibility**: identical inputs always produce identical outputs.
- **No external LLM dependency at serving time**: no rate limits, downtime, or token cost during judging.

## Testing methodology and results

### Local heuristic pass (`LocalProvider`, no LLM)
42/42 automated pytest suite passing, 30/30 canonical test pairs, all four scenario checks (`warmup`, `auto_reply`, `intent`, `hostile`) passing. This gave an early **98% / 90%** on `phase2_short` / `full_evaluation` — but this scorer counts digits and keyword-matches; it does not evaluate grounding quality or fabrication. **Treat these numbers as a smoke test, not a quality signal.**

### Real LLM judge (Groq, `openai/gpt-oss-120b`)
Running `judge_simulator.py` with an actual LLM judge (`LLM_PROVIDER=groq`, `LLM_MODEL=openai/gpt-oss-120b`) surfaced real issues the heuristic scorer couldn't see, and gave a materially different, more trustworthy result:

| Stage | Avg Score | % |
|---|---|---|
| Initial Groq-judged baseline | 33/50 | 66% |
| After fixing scope-routing bug | 35/50 | 70% |
| After fixing 3 missing composers + fabricated-data removal (round 1) | 38/50 | 76% |
| After removing remaining fabricated pricing (round 2) | 38/50 | 76% (stable) |

**Final: 38/50 average (76%) across 14 scored compositions**, per-dimension breakdown:
- Specificity: 7/10
- Category Fit: 8/10
- Merchant Fit: 8/10
- Decision Quality: 8/10
- Engagement: 7/10

Scores show run-to-run variance of roughly ±1–2 points on identical input under the Groq judge (LLM-judge noise, not code changes) — treat single-point deltas between runs as noise, not signal.

## Bugs found and fixed during real-LLM testing

The local heuristic scorer's 90-98% masked three real defects, only surfaced once a real LLM judge was used:

1. **Scope-based routing bug** (`compose.py`): the customer-vs-merchant branch was routed on `trigger.scope == "customer"` rather than on whether an actual resolved `customer` object was present. Several merchant-facing trigger kinds (`winback_eligible`, `review_theme_emerged`, `supply_alert`) are labeled `scope: "customer"` in the dataset for targeting purposes but are merchant-facing messages — they were being misrouted into the customer branch and silently falling to the generic fallback template. Fixed by routing on `customer is not None` instead of the scope label.

2. **Three trigger kinds had no composer at all** (`wedding_package_followup`, `trial_followup`, `renewal_due`) and were silently producing generic fallback copy for every occurrence. Added dedicated composers for all three, grounded in their real payload fields (`days_to_wedding` / `next_step_window_open`, `next_session_options`, `days_remaining` / `plan` / `renewal_amount` respectively).

3. **Fabricated data in three composers**:
   - `compose_customer_lapsed_soft` (salons): hardcoded "₹199" and "Saturday at 4pm" with no basis in payload data. Now pulls the merchant's real active offer via `get_active_offer()` and only cites a specific slot when one is present in the trigger payload.
   - `compose_competitor_opened`: fell back to a hardcoded "4.4★" rating when `merchant.reputation.avg_rating` was absent. Now only cites a rating figure when real data is present.
   - `compose_ipl_match`: cited a "-12% Saturday covers" statistic with no source. Now only cites a shift percentage when the trigger payload actually provides one.
   - `compose_active_planning` (corporate thali / kids yoga programs): presented fully-priced package tiers (₹125/₹115/₹105 per thali, ₹1,999 for 8 yoga sessions) with **no basis whatsoever** in the trigger payload, which contains only `intent_topic` and the merchant's own last message. Rewritten to quote the merchant's actual stated interest and offer to *co-build* pricing rather than presenting invented figures as fact.
   - `compose_dormant_with_vera`: claimed a specific "searches trending up" statistic not present in payload. Rewritten to reference the real `last_topic` field instead.

## Known limitations

- **`get_customer_name()` on minor-linked accounts**: for `trial_followup` triggers involving a child customer record with a parent field (e.g. `c_012_karthik_jr_for_m008`), the current implementation produces "Hi Karthik (parent: Sumitra)!" rather than addressing the parent directly. Since these messages go to a parent's WhatsApp, the more natural framing would greet the parent by name. Not fixed in this submission — flagged for follow-up.
- **Trade-off between honesty and Specificity score**: removing fabricated pricing from `compose_active_planning` improved grounding integrity but *lowered* that composer's Specificity score (the rubric rewards concrete numbers regardless of whether they'd be real) — an inherent tension between the rubric's Specificity dimension and the "no fabrication" constraint. We chose honesty over score-maximization; see the case-study note in the commit history for the considered alternative (framing invented numbers explicitly as illustrative proposals) that was not adopted for this submission.
- **Single-action-per-merchant-per-tick** means `renewal_due` and `trial_followup` triggers for merchants that also have a higher-ranked competing trigger active in the same tick window (e.g. `perf_dip`, `active_planning_intent`) will not surface in that tick. Both composers are implemented and verified correct via direct single-trigger `/v1/tick` calls; they were not exercised in the full 25-trigger batch judge run for this reason.

## Deployment

```bash
uvicorn app:app --host 0.0.0.0 --port 8080
```

## Running the judge locally

```bash
LLM_PROVIDER=groq \
LLM_API_KEY=<your-groq-key> \
LLM_MODEL=openai/gpt-oss-120b \
TEST_SCENARIO=full_evaluation \
python3 judge_simulator.py
```

Note: `openai/gpt-oss-120b` is used rather than the script's hardcoded default (`llama-3.1-70b-versatile`, which does not correspond to a valid Groq model ID) — Groq deprecated the free/developer-tier `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` models in August 2026 in favor of the GPT-OSS family.

## Contact

vera-dev@magicpin.in