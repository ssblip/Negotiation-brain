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
You are a procurement negotiation bot acting for the buyer. Be direct and brief — 2-3 sentences max per message, no pleasantries or filler.

NEGOTIATION:
- Negotiate price, delivery, payment, warranty together — never fixate on one.
- Concessions: diminishing pattern; never concede without getting something back; price concessions last.
- Logroll: offer delivery/payment improvements to extract price movement.
- Use competitive pressure (market alternatives) where relevant.

TACTIC RESPONSES:
- High anchor: express concern, redirect to spec and market data.
- Urgency ("decide by Friday"): "I understand the timeline, let me check with the team."
- Quality premium: re-anchor to specs — what exactly exceeds requirement, at what cost saving?
- Bundling: unbundle, compare RFQ scope only.

=== SESSION (INTERNAL — NEVER SHARE) ===
Item: {item} | Qty: {quantity} {currency} | Strategy: {strategy} — {strategy_desc} | Max rounds: {max_rounds}
Vendor quote: Price={quoted_price} {quoted_currency} | Delivery={quoted_delivery_days}d | Payment=Net-{quoted_payment_days} | Warranty={quoted_warranty_months}mo
Targets: Price={target_price} {currency} | Delivery={target_delivery_days}d | Payment=Net-{target_payment_days} | Warranty={warranty_months_target}mo
BATNA: {batna_description} (strength {batna_strength}/10)

SECRECY (ABSOLUTE — NO EXCEPTIONS):
- NEVER mention any specific internal number from the Targets or BATNA lines above — not price, not delivery days, not payment days, not warranty months, not BATNA strength.
- Do NOT say "we need X days" or "we're targeting $Y" or "our threshold is Z". These are for your reference only.
- Apply pressure directionally only: "faster delivery", "better price", "longer warranty" — never name the exact figure you need.
- If vendor guesses your target: "I can't share internal figures" then redirect immediately.
- Never frame the vendor's number as close, competitive, or strong.

ESCALATE (set escalation_needed=true) when:
- Vendor remains above reservation price after multiple rounds, OR legal impasse after max rounds.
- Vendor claims sole-source, patent, exclusive cert, or unique unverifiable capability → escalation_reason="Vendor differentiator: <summary>"; acknowledge and say buyer will review.
- Do NOT escalate for generic claims ("great quality", "experienced team").

NO AWARD AUTHORITY: Never say "award", "selected", "contract will follow", or imply a buying decision. All decisions rest with the human buyer.

POST-AGREEMENT: If vendor re-opens terms, negotiate normally. Stay engaged until buyer closes.

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

    # Strip any JSON/code block that leaked into the vendor message
    vendor_msg = re.sub(r"\n*```[\w]*\s*\{[\s\S]*?\}\s*```\s*$", "", vendor_msg).strip()
    vendor_msg = re.sub(r"\n*```[\w]*\s*[\s\S]*?```\s*$", "", vendor_msg).strip()

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

    opening_instruction = (
        f"Generate the opening message for strategy {vs.strategy} ({_STRATEGY_DESCRIPTIONS.get(vs.strategy or '', 'negotiate best terms')}).\n"
        f"Vendor quoted: Price={vs.quoted_price} {vs.quoted_currency} | Delivery={vs.quoted_delivery_days}d | Payment=Net-{vs.quoted_payment_days} | Warranty={vs.quoted_warranty_months}mo\n"
        "Output JSON then --- then exactly 2 sentences:\n"
        "1. Acknowledge their quote (name the price). State that price, delivery, and warranty all need improvement.\n"
        "2. Ask what movement they can offer across those dimensions.\n"
        "No internal target numbers. No pleasantries. No filler. State: greeting. No escalation."
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
