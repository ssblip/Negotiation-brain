"""
Negotiation AI Engine.

Wraps the Negotiation Brain document as Claude's system prompt.
Runs multi-turn vendor chat, extracts structured state from each reply,
and updates the VendorSession state machine.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

import anthropic
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    BuyerTargets,
    EscalationAlert,
    NegotiationMessage,
    VendorMemory,
    VendorSession,
)

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# ---------- Default negotiation brain doc (used when buyer hasn't uploaded one) ----------

# ---------- System prompt builder ----------
# Split into two blocks:
#   BLOCK 1 (cached) — fixed per session, prompt-cached after first turn
#   BLOCK 2 (dynamic) — round state + current offer; updated every turn

_STATIC_TEMPLATE = """\
You are a procurement negotiation bot acting for the buyer.

TONE — warm, human, genuinely collaborative. Like a colleague who really wants this deal to work, not a purchasing agent ticking boxes.
Think: "I really want this to work — help me help you."

Examples of the RIGHT warmth (vary your phrasing every turn — never repeat the same opener twice):
- Acknowledging a move: "That's helpful, thank you — genuinely appreciate you moving on price. We're close, just need a little more to get this locked in. Any flex left in that number?"
- Vendor holding firm: "Totally understand — not trying to squeeze you here. Before we close this out, is there one last thing we haven't tried on price?"
- Shifting dimensions: "Fair enough on price — let's set that aside for a moment. If you could stretch the warranty a bit, that'd really help us make the case internally. What can you do there?"
- Probing price: "Help me understand what's driving that number — if there's a story behind it, I can work with that. What's going on?"
- Encouraging progress: "Love the direction this is going — we're genuinely close. One more move and I think we can wrap this up today."
- Vendor struggling: "We're not here to push you somewhere that doesn't work for you — that's not what this is. Is there anything on our side we could adjust to make the numbers work better for you?"

NEVER use: cold transactional openers ("We need X to get this over the line"), repeated phrases across turns, or anything that sounds like a checklist.
2-3 sentences max. No corporate jargon. No filler. No threats.

ONE DIMENSION PER MESSAGE (HARD RULE):
Every message must contain exactly ONE focused ask. Never list multiple dimensions. You track all dimensions internally but push only one per turn.
- Wrong: "We need movement on price, delivery, and warranty."
- Right: "We need one more move on price — what's the best you can do?"
Shift to the next dimension only when the vendor holds firm on the current one.

DIMENSION ORDER BY STRATEGY:
- S1 (Spec Gap): spec compliance → price → warranty → delivery
- S2 (Value-Adjusted): price → warranty → delivery → payment
- S3 (Premium Justification): probe price justification → price → warranty → delivery
- S4 (Spec Surplus): model/scope → price → delivery → warranty
- S5 (Competitive): price → warranty → delivery → payment
- S6 (Requote): spec resubmit → (restart when compliant)
Follow this order. When the vendor holds firm on a dimension, acknowledge and move to the next one.

LOGROLLING (when state=logrolling):
Offer exactly ONE thing, ask for exactly ONE thing. Never list both sides as questions.

PAYMENT DIRECTION (critical — read carefully):
- Longer payment days = buyer pays later = GOOD FOR BUYER. Shorter = GOOD FOR VENDOR.
- Buyer's payment TARGET is the number of days the buyer wants to pay in (e.g. Net-60 = buyer wants to keep cash for 60 days).
- If the vendor's quoted payment days are LESS than the buyer's target (e.g. vendor quoted Net-45, target is Net-60): the buyer has NOT achieved its goal. ASK the vendor for longer terms — do not offer shorter ones.
- Only offer shorter payment terms (faster payment) as a logroll chip if the buyer has ALREADY achieved or exceeded its payment target on the current offer.
- NEVER offer Net-30 or shorter if the buyer's target is Net-60 — that moves further from the buyer's goal.

- Right (buyer already at Net-60, now logrolling): "If you can come down on price, we can move to Net-45 to get you paid a bit faster."
- Wrong: Offering Net-30 when buyer target is Net-60 and vendor quoted Net-45 — you'd be conceding something you haven't even won yet.
- Wrong: "What can you do on price and delivery and warranty?"

CONCESSIONS:
- Diminishing pattern — each concession smaller than the last.
- Always ask for something in return before conceding anything.
- When vendor claims they can't move: "Before we close this out, is there one thing we haven't tried?"

TACTIC RESPONSES (use exact style):
- High anchor: "That's higher than we were expecting — help us understand what's driving that number so we can work with you on it."
- Urgency / deadline: "Let me flag that with the team — what else can we do to move things along in the meantime?"
- Quality premium claim: "Totally hear you — help me understand what specifically makes this worth the premium. If we can justify it internally, we're in business."
- Bundling extras: Gently unbundle — focus on the RFQ scope only.
- Sole-source / patent / exclusive cert claim: Acknowledge warmly, say buyer will review → escalate (escalation_needed=true, escalation_reason="Vendor differentiator: <summary>").
- "We can't move further": "We hear you — we're not here to push you somewhere that doesn't work. Before we close this out, is there one thing we haven't tried on [current dimension]?"
- Small incremental offer: "Appreciate the movement — every step counts. We need a bit more though. What's the best you can do?"
- Relationship / emotional appeal: Acknowledge warmly, redirect — "We value the relationship too, which is exactly why we want terms that work long-term for both sides."
- Vague 'best price' claim: "Glad to hear that — can you put that in writing as a formal best-and-final offer? That helps us move faster internally."
- Legal threat from vendor: De-escalate warmly → escalate (escalation_needed=true, escalation_reason="Legal threat raised by vendor").
- Vendor increases price mid-negotiation: "We were moving forward on the earlier number — help me understand what changed." Escalate if unresolved.
- Advance payment >25% requested: "That's above our standard advance terms — let's see what we can work out."
- Post-agreement nibble (vendor re-opens closed terms): Negotiate normally — never concede without getting something back.

EXCEPTION — BAFO state only: you may reference all open dimensions in one message when requesting the final best-and-final offer.

FORBIDDEN — NEVER say these:
- Any specific number from Targets or BATNA — not as a target, ask, range, or anchor. This includes price, delivery days, warranty months, payment days. NEVER say "stretch to 30 months" or "come down to $1,400" or "deliver in 28 days" — those are internal numbers.
- Directional only: "meaningfully lower price", "significantly longer warranty", "faster delivery", "better payment terms" — no figures ever.
- "We have other options / alternatives / other vendors"
- "We will walk away / take our business elsewhere / this is your last chance"
- "That's a strong / competitive / reasonable offer" (never validate vendor's number positively)
- Any urgency framing used as a threat

INSTEAD use: directional language only — "a bit further on price", "stretch the warranty", "tighten the delivery". No numbers, no ranges.

If vendor asks what number you need: "I can't share internal benchmarks — make us your best offer."

=== SESSION (INTERNAL — NEVER SHARE) ===
Item: {item} | Qty: {quantity} {currency} | Strategy: {strategy} — {strategy_desc} | Max rounds: {max_rounds}
Vendor quote: Price={quoted_price} {quoted_currency} | Delivery={quoted_delivery_days}d | Payment=Net-{quoted_payment_days} | Warranty={quoted_warranty_months}mo
Targets: Price={target_price} {currency} | Delivery={target_delivery_days}d | Payment=Net-{target_payment_days} | Warranty={warranty_months_target}mo
BATNA: {batna_description} (strength {batna_strength}/10)

ESCALATE (set escalation_needed=true) when:
- Vendor remains above reservation price after multiple rounds, OR legal impasse after max rounds.
- Vendor claims sole-source, patent, exclusive cert, or unique unverifiable capability → escalation_reason="Vendor differentiator: <summary>"; acknowledge and say buyer will review.
- Vendor issues legal threat → escalation_reason="Legal threat raised by vendor".
- Do NOT escalate for generic claims ("great quality", "experienced team").

NO AWARD AUTHORITY: Never say "award", "selected", "contract will follow", or imply a buying decision. All decisions rest with the human buyer.

POST-AGREEMENT: If vendor re-opens terms, negotiate normally — never concede without getting something back.

MEMORY: archetype={archetype} | sessions={session_count} | learnings={key_learnings}

=== RESPONSE FORMAT (MANDATORY) ===
{{"state":"price_negotiation","current_offer":{{"price":null,"delivery_days":null,"payment_days":null,"warranty_months":null}},"escalation_needed":false,"escalation_reason":null,"agreement_reached":false,"concession_made":false}}
---
Your message to the vendor (plain text only, no JSON, no markdown).
States: greeting|spec_review|price_negotiation|logrolling|bafo|agreement|escalated|impasse|closed
"""

_DYNAMIC_TEMPLATE = """\
[TURN STATE] Round {round_count}/{max_rounds} | State: {current_state}
Current offer on table: {current_offer_str}
"""

_STRATEGY_DESCRIPTIONS = {
    "S1": "Spec Gap Redirect — address compliance gaps before price",
    "S2": "Value-Adjusted Price Negotiation — negotiate price relative to spec compliance",
    "S3": "Premium Justification Challenge — product is strong but price is too high",
    "S4": "Spec Surplus Trade — vendor over-specced, seek lower model or discount",
    "S5": "Competitive Normalisation — small gap, apply gentle competitive pressure",
    "S6": "Requote to Standard — product too far from requirements, request resubmission",
}


_HISTORY_KEEP_ROUNDS = 4  # keep last N round pairs in full; summarise older


def _build_system_blocks(vs: VendorSession, targets: BuyerTargets | None, memory: VendorMemory | None) -> list[dict]:
    """Return two Anthropic system blocks: [static-cached, dynamic-uncached]."""
    t = targets
    static_text = _STATIC_TEMPLATE.format(
        item=vs.negotiation.item,
        quantity=vs.negotiation.quantity,
        currency=vs.negotiation.currency,
        strategy=vs.strategy or "S2",
        strategy_desc=_STRATEGY_DESCRIPTIONS.get(vs.strategy or "S2", ""),
        max_rounds=settings.max_rounds,
        quoted_price=vs.quoted_price or "?",
        quoted_currency=vs.quoted_currency,
        quoted_delivery_days=vs.quoted_delivery_days or "?",
        quoted_payment_days=vs.quoted_payment_days or "?",
        quoted_warranty_months=vs.quoted_warranty_months or "?",
        target_price=t.target_price if t else "not set",
        target_delivery_days=t.target_delivery_days if t else "not set",
        target_payment_days=t.target_payment_days if t else "not set",
        warranty_months_target=t.warranty_months_target if t else "not set",
        batna_description=t.batna_description if t else "not configured",
        batna_strength=t.batna_strength if t else "?",
        archetype=memory.archetype if memory else "unknown",
        session_count=memory.session_count if memory else 0,
        key_learnings=(memory.key_learnings or "none")[:200] if memory else "none",
    )

    offer = vs.current_offer or {}
    offer_str = ", ".join(f"{k}={v}" for k, v in offer.items() if v is not None) or "none yet"
    dynamic_text = _DYNAMIC_TEMPLATE.format(
        round_count=vs.round_count,
        max_rounds=settings.max_rounds,
        current_state=vs.current_state,
        current_offer_str=offer_str,
    )

    return [
        {"type": "text", "text": static_text, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": dynamic_text},
    ]


def _build_messages(vs: VendorSession) -> list[dict]:
    """Return last N rounds of history; prepend a brief summary if older rounds exist."""
    all_msgs = vs.messages
    keep = _HISTORY_KEEP_ROUNDS * 2  # each round = 1 vendor + 1 bot message
    out = []

    if len(all_msgs) > keep:
        older = all_msgs[:-keep]
        # One-line summary of older rounds
        summary_lines = [f"[Earlier: {len(older)//2} rounds completed.]"]
        for m in older:
            if m.role == "vendor":
                summary_lines.append(f"Vendor: {m.content[:80]}…")
            else:
                summary_lines.append(f"Bot: {m.content[:80]}…")
        out.append({"role": "user", "content": "\n".join(summary_lines)})
        out.append({"role": "assistant", "content": "Understood. Continuing negotiation."})
        recent = all_msgs[-keep:]
    else:
        recent = all_msgs

    for m in recent:
        role = "user" if m.role == "vendor" else "assistant"
        out.append({"role": role, "content": m.content})
    return out


def _build_messages(vs: VendorSession) -> list[dict]:
    """Convert stored messages to Anthropic messages format."""
    out = []
    for m in vs.messages:
        role = "user" if m.role == "vendor" else "assistant"
        out.append({"role": role, "content": m.content})
    return out


def _parse_response(response_text: str) -> tuple[dict, str]:
    """
    Split bot response into (json_data, vendor_message).
    Handles cases where Claude wraps JSON in markdown fences.
    """
    # Try to find JSON before the --- separator
    parts = response_text.split("---", 1)
    json_str = parts[0].strip()
    vendor_msg = parts[1].strip() if len(parts) > 1 else response_text

    # Strip markdown fences if present
    json_str = re.sub(r"^```[a-z]*\n?", "", json_str).rstrip("```").strip()

    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        # Fallback: try to extract JSON from anywhere in the response
        match = re.search(r"\{.*?\}", response_text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
        if not parts[1:]:
            vendor_msg = response_text

    # Strip JSON/code blocks that leaked into the vendor message
    vendor_msg = re.sub(r"\n*```[\w]*\s*\{[\s\S]*?\}\s*```\s*$", "", vendor_msg).strip()
    vendor_msg = re.sub(r"\n*```[\w]*\s*[\s\S]*?```\s*$", "", vendor_msg).strip()
    # Strip raw JSON appended without fences (Claude occasionally puts it at the end)
    vendor_msg = re.sub(r'\n*\{"state"\s*:[\s\S]*$', "", vendor_msg).strip()
    # Strip any trailing incomplete JSON fragment starting with {
    vendor_msg = re.sub(r'\n*\{[^a-zA-Z]*"[a-z_]+"[\s\S]*$', "", vendor_msg).strip()

    return data, vendor_msg


def _with_retry(fn, retries=3):
    delays = [1.5, 4.0, 8.0]
    for attempt in range(retries):
        try:
            return fn()
        except anthropic.RateLimitError:
            if attempt == retries - 1:
                raise
            time.sleep(delays[attempt])
        except anthropic.APIStatusError as e:
            if e.status_code in (503, 529) and attempt < retries - 1:
                time.sleep(delays[attempt])
            else:
                raise


def run_negotiation_turn(
    db: Session,
    vs: VendorSession,
    vendor_message: str,
) -> tuple[str, str, dict | None, bool, bool]:
    """
    Process one vendor message through the negotiation AI.

    Returns: (reply_text, new_state, current_offer, escalation_needed, agreement_reached)
    """
    from app.models import BuyerTargets, VendorMemory

    targets = db.query(BuyerTargets).filter(BuyerTargets.negotiation_id == vs.negotiation_id).first()
    memory = db.query(VendorMemory).filter(VendorMemory.vendor_email == vs.vendor_email).first()

    system_blocks = _build_system_blocks(vs, targets, memory)
    history = _build_messages(vs)

    # Append the new vendor message
    history.append({"role": "user", "content": vendor_message})

    def _call():
        return _client.messages.create(
            model=settings.claude_model,
            max_tokens=1024,
            system=system_blocks,
            messages=history,
        )

    response = _with_retry(_call)
    raw_text = response.content[0].text

    json_data, reply_text = _parse_response(raw_text)

    new_state = json_data.get("state", vs.current_state)
    current_offer = json_data.get("current_offer")
    escalation_needed = bool(json_data.get("escalation_needed", False))
    escalation_reason = json_data.get("escalation_reason")
    agreement_reached = bool(json_data.get("agreement_reached", False))

    # --- Persist vendor message ---
    now = datetime.now(timezone.utc)
    vendor_msg_row = NegotiationMessage(
        vendor_session_id=vs.id,
        role="vendor",
        content=vendor_message,
        round_number=vs.round_count,
        state_at_time=vs.current_state,
        created_at=now,
    )
    db.add(vendor_msg_row)

    # --- Persist bot reply ---
    bot_msg_row = NegotiationMessage(
        vendor_session_id=vs.id,
        role="assistant",
        content=reply_text,
        round_number=vs.round_count + 1,
        state_at_time=new_state,
        created_at=now,
    )
    db.add(bot_msg_row)

    # --- Update VendorSession ---
    vs.round_count += 1
    vs.current_state = new_state
    if current_offer:
        merged = dict(vs.current_offer or {})
        for k, v in current_offer.items():
            if v is not None:
                merged[k] = v
        vs.current_offer = merged

    if vs.first_response_at is None:
        vs.first_response_at = now

    if agreement_reached:
        # Record latest agreed terms but keep chat open — buyer must close explicitly
        vs.status = "agreed"
        vs.current_state = "agreement"
        offer = vs.current_offer or {}
        vs.final_price = offer.get("price")
        vs.final_delivery_days = offer.get("delivery_days")
        vs.final_payment_days = offer.get("payment_days")
    elif vs.status != "agreed":
        # Only reset to chatting if not already in an agreed state
        vs.status = "chatting"

    if escalation_needed and escalation_reason:
        vs.status = "escalated"
        alert = EscalationAlert(
            vendor_session_id=vs.id,
            negotiation_id=vs.negotiation_id,
            reason=escalation_reason,
            context_summary=f"Round {vs.round_count}. Vendor last said: {vendor_message[:300]}",
        )
        db.add(alert)

    # Max rounds → force BAFO or impasse
    if vs.round_count >= settings.max_rounds and new_state not in ("agreement", "closed", "escalated"):
        vs.current_state = "bafo"

    db.commit()
    db.refresh(vs)

    return reply_text, vs.current_state, vs.current_offer, escalation_needed, agreement_reached


def generate_opening_message(db: Session, vs: VendorSession) -> str:
    """Generate the bot's first greeting message when vendor opens the chat."""
    from app.models import BuyerTargets, VendorMemory

    targets = db.query(BuyerTargets).filter(BuyerTargets.negotiation_id == vs.negotiation_id).first()
    memory = db.query(VendorMemory).filter(VendorMemory.vendor_email == vs.vendor_email).first()

    system_blocks = _build_system_blocks(vs, targets, memory)

    # Strategy-specific opening focus: one dimension to lead with, not a scatter-shot list
    _OPENING_FOCUS = {
        "S1": (
            "spec_review",
            "1. Acknowledge receipt of their quote (name the price). Warmly note that before we can move to commercial terms, we need to discuss spec compliance.\n"
            "2. Ask one specific question about how their product meets the technical requirements."
        ),
        "S2": (
            "price_negotiation",
            "1. Acknowledge their quote (name the price). Say it's a good starting point but the price needs to come down meaningfully to make this work.\n"
            "2. Ask what they can do on price — just price, one focused ask."
        ),
        "S3": (
            "price_negotiation",
            "1. Acknowledge their quote (name the price). Say their product looks strong but the price needs justification at this level.\n"
            "2. Ask them to walk you through what's driving the price — one question."
        ),
        "S4": (
            "price_negotiation",
            "1. Acknowledge their quote (name the price). Note that their spec appears above the RFQ requirement and ask if there's a more standard configuration.\n"
            "2. Ask what that would mean for price — one focused ask."
        ),
        "S5": (
            "price_negotiation",
            "1. Acknowledge their quote (name the price). Say it's close but you need a small move on price to finalize.\n"
            "2. Ask what their best price is — one direct ask."
        ),
        "S6": (
            "spec_review",
            "1. Acknowledge their quote (name the price). Warmly explain that the product doesn't fully meet the spec requirements as submitted.\n"
            "2. Ask if they can resubmit with a configuration that meets the requirements — one clear ask."
        ),
    }
    strategy = vs.strategy or "S2"
    focus_state, focus_instruction = _OPENING_FOCUS.get(strategy, _OPENING_FOCUS["S2"])

    opening_instruction = (
        f"Generate the opening message. Strategy: {strategy} — {_STRATEGY_DESCRIPTIONS.get(strategy, '')}.\n"
        f"Vendor quoted: Price={vs.quoted_price} {vs.quoted_currency} | Delivery={vs.quoted_delivery_days}d | Payment=Net-{vs.quoted_payment_days} | Warranty={vs.quoted_warranty_months}mo\n"
        f"Output JSON (state={focus_state}) then --- then exactly 2 sentences:\n"
        f"{focus_instruction}\n"
        "Conversational and friendly tone. No internal target numbers. No filler. No escalation. Do NOT ask about multiple dimensions — one focused ask only."
    )

    def _call():
        return _client.messages.create(
            model=settings.claude_model,
            max_tokens=512,
            system=system_blocks,
            messages=[{"role": "user", "content": opening_instruction}],
        )

    response = _with_retry(_call)
    raw_text = response.content[0].text

    _, reply_text = _parse_response(raw_text)

    now = datetime.now(timezone.utc)
    bot_msg = NegotiationMessage(
        vendor_session_id=vs.id,
        role="assistant",
        content=reply_text,
        round_number=0,
        state_at_time="greeting",
        created_at=now,
    )
    db.add(bot_msg)
    vs.current_state = "greeting"
    vs.status = "chatting"
    db.commit()

    return reply_text


def update_vendor_memory(db: Session, vs: VendorSession) -> None:
    """Called after a session closes — updates persistent vendor memory."""
    memory = db.query(VendorMemory).filter(VendorMemory.vendor_email == vs.vendor_email).first()
    if not memory:
        memory = VendorMemory(vendor_email=vs.vendor_email, vendor_company=vs.vendor_company)
        db.add(memory)

    memory.session_count = (memory.session_count or 0) + 1
    memory.updated_at = datetime.now(timezone.utc)

    # Compute average concession
    if vs.quoted_price and vs.final_price:
        concession = (vs.quoted_price - vs.final_price) / vs.quoted_price * 100
        prev_avg = memory.avg_concession_pct or concession
        memory.avg_concession_pct = round((prev_avg + concession) / 2, 2)

    # Simple archetype heuristic
    if vs.round_count <= 2 and vs.status == "agreed":
        memory.archetype = "responsive"
    elif vs.round_count >= settings.max_rounds and vs.status != "agreed":
        memory.archetype = "reluctant_conceder"
    else:
        memory.archetype = memory.archetype or "unknown"

    db.commit()
