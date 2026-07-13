from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Annotated

import anthropic
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import schemas
from app.auth import (
    create_token,
    get_current_user,
    hash_password,
    require_buyer,
    require_vendor,
    verify_password,
)
from app.config import settings
from app.database import Base, engine, get_db
from app.emailer import (
    send_agreement_notification,
    send_award_notification,
    send_escalation_alert,
    send_rejection_notification,
    send_vendor_invitation,
)
from app.models import (
    BuyerTargets,
    EscalationAlert,
    Negotiation,
    NegotiationMessage,
    User,
    VendorMemory,
    VendorSession,
)
from app.negotiation import (
    generate_opening_message,
    run_negotiation_turn,
    update_vendor_memory,
)
from app.parser import extract_text_from_file, parse_vendors_from_text, condense_strategy_doc
from app.scorer import (
    compute_cvs,
    compute_initial_concession_budget,
    compute_spec_score,
    get_mandatory_failures,
    select_strategy,
    _price_dim_score,
    _delivery_dim_score,
    _payment_dim_score,
    _warranty_dim_score,
)

Base.metadata.create_all(bind=engine)

# Runtime migrations — each statement gets its own connection so a PostgreSQL
# aborted-transaction state from one statement doesn't block the rest.
from sqlalchemy import text as _sql_text
_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS strategy_doc TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS strategy_doc_condensed TEXT",
    "ALTER TABLE vendor_sessions ADD COLUMN IF NOT EXISTS priority TEXT",
    "ALTER TABLE negotiations ADD COLUMN IF NOT EXISTS strategy_doc_condensed TEXT",
    "ALTER TABLE vendor_sessions ADD COLUMN IF NOT EXISTS mandatory_failures JSON",
    "ALTER TABLE vendor_sessions ADD COLUMN IF NOT EXISTS buyer_override BOOLEAN DEFAULT FALSE",
]
for _stmt in _MIGRATIONS:
    try:
        with engine.connect() as _conn:
            _conn.execute(_sql_text(_stmt))
            _conn.commit()
    except Exception:
        pass

import traceback as _tb
from fastapi.responses import JSONResponse
from starlette.requests import Request

app = FastAPI(title="Negotiation Brain API", debug=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    err = _tb.format_exc()
    print("GLOBAL ERROR:\n", err)
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {str(exc)}", "trace": err})


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"ok": True}


# ── Auth ─────────────────────────────────────────────────────────────────────

@app.post("/api/auth/register", response_model=schemas.TokenOut)
def register(body: schemas.RegisterIn, db: Annotated[Session, Depends(get_db)]):
    import traceback
    try:
        if db.query(User).filter(User.email == body.email).first():
            raise HTTPException(400, "Email already registered")
        user = User(
            email=body.email,
            password_hash=hash_password(body.password),
            display_name=body.display_name,
            company=body.company,
            role=body.role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        if user.role == "vendor":
            _link_vendor_sessions(db, user)
        return schemas.TokenOut(access_token=create_token(user.id), user=schemas.UserOut.model_validate(user))
    except HTTPException:
        raise
    except Exception as e:
        err = traceback.format_exc()
        print("REGISTER ERROR:\n", err)
        raise HTTPException(500, detail=f"{type(e).__name__}: {str(e)}")


@app.post("/api/auth/login", response_model=schemas.TokenOut)
def login(body: schemas.LoginIn, db: Annotated[Session, Depends(get_db)]):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if user.role == "vendor":
        _link_vendor_sessions(db, user)
    return schemas.TokenOut(access_token=create_token(user.id), user=schemas.UserOut.model_validate(user))


@app.get("/api/auth/me", response_model=schemas.UserOut)
def me(user: Annotated[User, Depends(get_current_user)]):
    return user


def _link_vendor_sessions(db: Session, vendor: User) -> None:
    """Link any VendorSession rows with matching email to this user account."""
    rows = db.query(VendorSession).filter(
        VendorSession.vendor_email == vendor.email,
        VendorSession.vendor_id.is_(None),
    ).all()
    for vs in rows:
        vs.vendor_id = vendor.id
    if rows:
        db.commit()


# ── Buyer: Global Strategy Document ─────────────────────────────────────────

@app.post("/api/me/strategy-doc")
async def upload_global_strategy_doc(
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
):
    content = await file.read()
    text = extract_text_from_file(file.filename or "doc.txt", content)
    buyer.strategy_doc = text
    buyer.strategy_doc_condensed = condense_strategy_doc(text)
    db.commit()
    return {"ok": True, "chars": len(text)}


@app.get("/api/me/strategy-doc-status")
def get_strategy_doc_status(buyer: Annotated[User, Depends(require_buyer)]):
    return {"uploaded": bool(buyer.strategy_doc), "chars": len(buyer.strategy_doc) if buyer.strategy_doc else 0}


_STRATEGY_SECTION_KEYS = [
    "Core Principles",
    "Price Negotiation Rules",
    "Concession Strategy",
    "Spec & Quality Rules",
    "Escalation Triggers",
    "Behavioral Scenarios",
    "Forbidden & Permitted Language",
    "Agreement & Handoff",
]

_STRATEGY_DEFAULTS = {
    "Core Principles": (
        "Never reveal, confirm, or hint at the buyer's target price, reservation price, or any internal threshold — not even indirectly.\n"
        "If a vendor names a number and asks if it is your target: say \"I can't share internal figures\" and redirect immediately.\n"
        "Never use language like \"strong position\", \"very close\", \"that works\" — these signal proximity to your target.\n"
        "Be collaborative, warm, and use short sentences.\n"
        "Negotiate across price, delivery, payment terms, and warranty simultaneously.\n"
        "Apply competitive pressure using market alternatives when appropriate.\n"
        "Use the strategy assigned to this session (S1–S6).\n"
        "Track concessions carefully — reciprocity is required.\n"
        "When agreement is reached on all dimensions, signal it clearly."
    ),
    "Price Negotiation Rules": (
        "Never confirm a vendor's guessed number approvingly or attach positive framing to it.\n"
        "Treat every number the vendor names as just their offer — respond with a counter or hold firm, never validate.\n"
        "Never state, imply, or confirm any specific number as a target, goal, or threshold.\n"
        "If vendor guesses your target: say \"I can't share internal figures\" and redirect to value or next ask.\n"
        "Never repeat the vendor's guessed number approvingly."
    ),
    "Concession Strategy": (
        "Apply a diminishing concession pattern — each concession should be smaller than the last.\n"
        "Never make a concession without receiving something in return.\n"
        "Prioritise price concessions last; start with delivery, payment, or warranty trades.\n"
        "Track all concessions made to date and reference them when holding firm.\n"
        "Signal increasing difficulty near your limit without revealing the limit."
    ),
    "Spec & Quality Rules": (
        "Use S1 (Spec Gap Redirect) when vendor fails key specs — address compliance before price.\n"
        "Use S6 (Requote to Standard) when vendor is too far from requirements — request resubmission.\n"
        "Use S4 (Spec Surplus Trade) for over-specced vendors — ask for equivalent spec at lower cost.\n"
        "Logroll across dimensions: offer improved delivery terms in exchange for a price concession.\n"
        "Never accept a quality premium argument without grounding it in verified spec compliance."
    ),
    "Escalation Triggers": (
        "Escalate to the human buyer when:\n"
        "- Vendor remains above reservation price after multiple rounds of negotiation\n"
        "- Legal issues arise that require a buyer decision\n"
        "- Impasse is reached after maximum rounds\n"
        "- Vendor asserts a differentiator you cannot verify or counter: sole-source claim, proprietary technology, exclusive certification, or unique capability — set reason as \"Vendor differentiator: <one-line summary>\"\n"
        "Do NOT escalate for standard sales claims (\"we have great quality\", \"our team is experienced\")."
    ),
    "Behavioral Scenarios": (
        "Anchoring (vendor opens very high): Express concern, redirect to spec compliance and market competitiveness.\n"
        "Urgency tactics (\"we need a decision by Friday\"): Acknowledge but do not rush — \"I understand the timeline, let me check with the team\".\n"
        "Quality deflection (\"our product justifies the premium\"): Re-anchor to spec requirements — what specifically exceeds the requirement, and at what cost savings?\n"
        "Bundling (vendor adds extras to justify price): Unbundle — compare only what was quoted in the RFQ scope.\n"
        "Sole-source or proprietary claims: Escalate to buyer immediately — do not attempt to dismiss or negotiate around it."
    ),
    "Forbidden & Permitted Language": (
        "FORBIDDEN phrases:\n"
        "- \"strong position\", \"very close\", \"that works\", \"almost there\", \"you're competitive\"\n"
        "- \"award\", \"selected\", \"you've won\", \"contract will follow\", \"procurement team will be in touch\"\n"
        "- Any phrase implying a purchasing decision has been made\n"
        "- Approving or repeating vendor-named numbers positively\n\n"
        "PERMITTED phrases:\n"
        "- \"I can't share internal figures\"\n"
        "- \"Let me take that back to the team\"\n"
        "- \"We're still evaluating all options\"\n"
        "- \"That's noted — what else can you offer on [dimension]?\"\n"
        "- \"We need to see more movement on [dimension] before we can move forward\""
    ),
    "Agreement & Handoff": (
        "When agreement is reached on all dimensions, signal it clearly in the JSON state field.\n"
        "Never say \"award\", \"you've been selected\", or imply a contract will follow.\n"
        "All final decisions rest with the human buyer — the bot cannot close or formalise anything.\n"
        "The negotiation stays open until the buyer explicitly closes it from the dashboard.\n"
        "If a vendor offers updated terms after a prior agreement, treat it as a new live offer and negotiate normally."
    ),
}


def _parse_strategy_sections(text: str) -> dict[str, str]:
    """Parse ## Section\ncontent format into a dict."""
    sections: dict[str, str] = {}
    current_key: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_key is not None:
                sections[current_key] = "\n".join(lines).strip()
            current_key = line[3:].strip()
            lines = []
        else:
            if current_key is not None:
                lines.append(line)
    if current_key is not None:
        sections[current_key] = "\n".join(lines).strip()
    return sections


def _assemble_strategy_sections(sections: dict[str, str]) -> str:
    parts = []
    for key in _STRATEGY_SECTION_KEYS:
        content = sections.get(key, _STRATEGY_DEFAULTS.get(key, ""))
        parts.append(f"## {key}\n{content}")
    return "\n\n".join(parts)


@app.get("/api/me/strategy-sections")
def get_strategy_sections(buyer: Annotated[User, Depends(require_buyer)]):
    condensed = buyer.strategy_doc_condensed or ""
    if "## " in condensed:
        sections = _parse_strategy_sections(condensed)
    else:
        sections = {}
    # Fill missing keys with defaults
    for key in _STRATEGY_SECTION_KEYS:
        if key not in sections:
            sections[key] = _STRATEGY_DEFAULTS[key]
    return {"sections": sections, "is_customised": bool(buyer.strategy_doc_condensed and "## " in buyer.strategy_doc_condensed)}


@app.post("/api/me/strategy-sections")
def save_strategy_sections(
    body: dict,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    sections = body.get("sections", {})
    assembled = _assemble_strategy_sections(sections)
    buyer.strategy_doc_condensed = assembled
    db.commit()
    return {"ok": True, "chars": len(assembled)}


# ── Buyer: Negotiations ───────────────────────────────────────────────────────

@app.get("/api/negotiations", response_model=list[schemas.NegotiationOut])
def list_negotiations(
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    rows = db.query(Negotiation).filter(Negotiation.buyer_id == buyer.id).order_by(Negotiation.id.desc()).all()
    return [_neg_out(n) for n in rows]


@app.post("/api/negotiations", response_model=schemas.NegotiationOut)
def create_negotiation(
    body: schemas.NegotiationCreateIn,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    neg = Negotiation(
        buyer_id=buyer.id,
        title=body.title,
        item=body.item,
        quantity=body.quantity,
        currency=body.currency,
    )
    db.add(neg)
    db.commit()
    db.refresh(neg)
    return _neg_out(neg)


@app.get("/api/negotiations/{nid}", response_model=schemas.NegotiationOut)
def get_negotiation(
    nid: int,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    neg = _get_neg(nid, buyer.id, db)
    return _neg_out(neg)


@app.patch("/api/negotiations/{nid}", response_model=schemas.NegotiationOut)
def update_negotiation(
    nid: int,
    body: schemas.NegotiationCreateIn,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    neg = _get_neg(nid, buyer.id, db)
    neg.title = body.title
    neg.item = body.item
    neg.quantity = body.quantity
    neg.currency = body.currency
    db.commit()
    db.refresh(neg)
    return _neg_out(neg)


@app.post("/api/negotiations/{nid}/strategy-doc")
async def upload_strategy_doc(
    nid: int,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
):
    """Upload the negotiation brain / strategy document for this negotiation."""
    neg = _get_neg(nid, buyer.id, db)
    content = await file.read()
    text = extract_text_from_file(file.filename or "doc.txt", content)
    neg.strategy_doc = text
    neg.strategy_doc_condensed = condense_strategy_doc(text)
    db.commit()
    return {"ok": True, "chars": len(text)}


@app.post("/api/negotiations/{nid}/parse-quotes", response_model=schemas.ParsedVendorsOut)
async def parse_quote_document(
    nid: int,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
    files: list[UploadFile] = File(...),
):
    """Upload one or more vendor quote documents. Returns parsed vendor list for buyer review."""
    _get_neg(nid, buyer.id, db)
    parts: list[str] = []
    for f in files:
        content = await f.read()
        text = extract_text_from_file(f.filename or "quotes.pdf", content)
        parts.append(f"--- [{f.filename}] ---\n{text}")
    raw_text = "\n\n".join(parts)
    targets = db.query(BuyerTargets).filter(BuyerTargets.negotiation_id == nid).first()
    custom_specs = targets.custom_specs if targets and targets.custom_specs else []
    vendors = parse_vendors_from_text(raw_text, custom_specs=custom_specs)
    return schemas.ParsedVendorsOut(vendors=vendors, raw_text=raw_text[:2000])


@app.post("/api/negotiations/{nid}/targets", response_model=schemas.BuyerTargetsOut)
def set_targets(
    nid: int,
    body: schemas.BuyerTargetsIn,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    neg = _get_neg(nid, buyer.id, db)
    existing = db.query(BuyerTargets).filter(BuyerTargets.negotiation_id == nid).first()
    data = body.model_dump()
    if existing:
        for k, v in data.items():
            # Preserve existing custom_specs if the update sends an empty list
            if k == "custom_specs" and not v and existing.custom_specs:
                continue
            setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return schemas.BuyerTargetsOut.model_validate(existing)

    t = BuyerTargets(negotiation_id=nid, **data)
    db.add(t)
    db.commit()
    db.refresh(t)
    return schemas.BuyerTargetsOut.model_validate(t)


@app.get("/api/negotiations/{nid}/targets", response_model=schemas.BuyerTargetsOut | None)
def get_targets(
    nid: int,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    _get_neg(nid, buyer.id, db)
    t = db.query(BuyerTargets).filter(BuyerTargets.negotiation_id == nid).first()
    if not t:
        return None
    return schemas.BuyerTargetsOut.model_validate(t)


@app.post("/api/negotiations/{nid}/vendors", response_model=list[schemas.VendorSessionOut])
def add_vendors(
    nid: int,
    vendors: list[schemas.VendorQuoteIn],
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    """Add (or upsert) vendor sessions with their parsed quote data and compute scores."""
    neg = _get_neg(nid, buyer.id, db)
    targets = db.query(BuyerTargets).filter(BuyerTargets.negotiation_id == nid).first()
    results = []

    for v in vendors:
        existing = db.query(VendorSession).filter(
            VendorSession.negotiation_id == nid,
            VendorSession.vendor_email == v.vendor_email,
        ).first()

        if existing:
            vs = existing
        else:
            vs = VendorSession(negotiation_id=nid, vendor_email=v.vendor_email)
            db.add(vs)

        vs.vendor_company = v.vendor_company
        vs.vendor_name = v.vendor_name
        vs.quoted_price = v.quoted_price
        vs.quoted_delivery_days = v.quoted_delivery_days
        vs.quoted_payment_days = v.quoted_payment_days
        vs.quoted_warranty_months = v.quoted_warranty_months
        vs.quoted_currency = v.quoted_currency or neg.currency
        vs.custom_spec_values = v.custom_spec_values

        # Compute scores
        custom_specs = targets.custom_specs if targets else []
        failures = get_mandatory_failures(custom_specs or [], v.custom_spec_values)
        spec_score = compute_spec_score(custom_specs or [], v.custom_spec_values)
        cvs = compute_cvs(
            spec_score,
            v.quoted_price, targets.target_price if targets else None, targets.reservation_price if targets else None,
            v.quoted_delivery_days, targets.target_delivery_days if targets else None, targets.max_delivery_days if targets else None,
            v.quoted_payment_days, targets.target_payment_days if targets else None, targets.min_payment_days if targets else None,
            v.quoted_warranty_months, targets.warranty_months_target if targets else None, targets.warranty_months_min if targets else None,
        )
        strategy = select_strategy(spec_score, v.quoted_price, targets.target_price if targets else None)
        budget = compute_initial_concession_budget(v.quoted_price, targets.target_price if targets else None, targets.reservation_price if targets else None)

        vs.mandatory_failures = failures or None
        vs.spec_score = spec_score
        vs.cvs_score = cvs
        vs.strategy = strategy
        vs.concession_budget = budget
        if failures and not vs.buyer_override:
            vs.status = "pending_qualification"
        vs.current_offer = {
            "price": v.quoted_price,
            "delivery_days": v.quoted_delivery_days,
            "payment_days": v.quoted_payment_days,
            "warranty_months": v.quoted_warranty_months,
        }

        # Link to registered vendor account if exists
        vendor_user = db.query(User).filter(User.email == v.vendor_email, User.role == "vendor").first()
        if vendor_user:
            vs.vendor_id = vendor_user.id

        db.commit()
        db.refresh(vs)
        results.append(_vs_out(vs, db))

    return results


@app.get("/api/negotiations/{nid}/vendors", response_model=list[schemas.VendorSessionOut])
def list_vendors(
    nid: int,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    _get_neg(nid, buyer.id, db)
    rows = db.query(VendorSession).filter(VendorSession.negotiation_id == nid).all()
    targets = db.query(BuyerTargets).filter(BuyerTargets.negotiation_id == nid).first()
    custom_specs = targets.custom_specs if targets else []
    if custom_specs:
        changed = False
        for vs in rows:
            failures = get_mandatory_failures(custom_specs, vs.custom_spec_values) or None
            if vs.mandatory_failures != failures:
                vs.mandatory_failures = failures
                if failures and not vs.buyer_override and vs.status not in ("rejected", "closed", "awarded"):
                    vs.status = "pending_qualification"
                elif not failures and vs.status == "pending_qualification":
                    vs.status = "invited"
                changed = True
        if changed:
            db.commit()
    return [_vs_out(vs, db) for vs in rows]


@app.patch("/api/negotiations/{nid}/vendors/{vsid}/priority", response_model=schemas.VendorSessionOut)
def set_vendor_priority(
    nid: int,
    vsid: int,
    body: dict,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    _get_neg(nid, buyer.id, db)
    vs = db.query(VendorSession).filter(VendorSession.id == vsid, VendorSession.negotiation_id == nid).first()
    if not vs:
        raise HTTPException(status_code=404, detail="Vendor session not found")
    priority = body.get("priority")
    if priority not in (None, "P1", "P2", "P3"):
        raise HTTPException(status_code=400, detail="priority must be P1, P2, P3, or null")
    vs.priority = priority
    db.commit()
    db.refresh(vs)
    return _vs_out(vs, db)


@app.patch("/api/negotiations/{nid}/vendors/{vsid}/override", response_model=schemas.VendorSessionOut)
def override_vendor_qualification(
    nid: int,
    vsid: int,
    body: dict,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    """Buyer overrides the bot's qualification recommendation for a vendor."""
    _get_neg(nid, buyer.id, db)
    vs = db.query(VendorSession).filter(VendorSession.id == vsid, VendorSession.negotiation_id == nid).first()
    if not vs:
        raise HTTPException(status_code=404, detail="Vendor session not found")
    override = bool(body.get("override", False))
    vs.buyer_override = override
    if override and vs.status == "pending_qualification":
        vs.status = "invited"
    elif not override and vs.mandatory_failures:
        vs.status = "pending_qualification"
    db.commit()
    db.refresh(vs)
    return _vs_out(vs, db)


@app.post("/api/negotiations/{nid}/send-invitations")
def send_invitations(
    nid: int,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    """Mark negotiation as active — vendors log in to see their negotiations."""
    neg = _get_neg(nid, buyer.id, db)
    vendors = db.query(VendorSession).filter(VendorSession.negotiation_id == nid).all()
    if not vendors:
        raise HTTPException(400, "No vendors added yet")

    neg.status = "active"
    db.commit()
    return {"sent": len(vendors), "total": len(vendors)}


@app.get("/api/negotiations/{nid}/vendors/{vsid}/messages", response_model=list[schemas.MessageOut])
def get_chat_history_buyer(
    nid: int,
    vsid: int,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    _get_neg(nid, buyer.id, db)
    vs = _get_vs(vsid, db)
    return [schemas.MessageOut.model_validate(m) for m in vs.messages]


@app.get("/api/negotiations/{nid}/escalations", response_model=list[schemas.EscalationOut])
def list_escalations(
    nid: int,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    _get_neg(nid, buyer.id, db)
    rows = db.query(EscalationAlert).filter(EscalationAlert.negotiation_id == nid).all()
    return [schemas.EscalationOut.model_validate(e) for e in rows]


@app.post("/api/escalations/{eid}/resolve", response_model=schemas.EscalationOut)
def resolve_escalation(
    eid: int,
    body: schemas.EscalationResolveIn,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    alert = db.get(EscalationAlert, eid)
    if not alert:
        raise HTTPException(404)
    neg = db.get(Negotiation, alert.negotiation_id)
    if not neg or neg.buyer_id != buyer.id:
        raise HTTPException(403)

    alert.status = "resolved"
    alert.buyer_decision = body.decision
    alert.buyer_instruction = body.instruction

    vs = db.get(VendorSession, alert.vendor_session_id)
    if vs:
        if body.decision == "accept":
            vs.status = "agreed"
            vs.current_state = "agreement"
        elif body.decision == "reject":
            vs.status = "rejected"
            vs.current_state = "closed"
        else:
            vs.status = "chatting"
            vs.current_state = "price_negotiation"

    db.commit()
    db.refresh(alert)
    return schemas.EscalationOut.model_validate(alert)


@app.post("/api/negotiations/{nid}/award")
def award_tender(
    nid: int,
    body: schemas.AwardIn,
    buyer: Annotated[User, Depends(require_buyer)],
    db: Annotated[Session, Depends(get_db)],
):
    """Buyer closes the tender: awards one vendor, closes all others, sends emails."""
    neg = _get_neg(nid, buyer.id, db)

    winner = db.query(VendorSession).filter(
        VendorSession.id == body.vendor_session_id,
        VendorSession.negotiation_id == nid,
    ).first()
    if not winner:
        raise HTTPException(404, "Vendor session not found")

    now = datetime.now(timezone.utc)
    winner.status = "awarded"
    winner.closed_at = now

    all_vendors = db.query(VendorSession).filter(VendorSession.negotiation_id == nid).all()
    losers = [v for v in all_vendors if v.id != winner.id]
    for loser in losers:
        loser.status = "closed"
        loser.closed_at = now

    neg.status = "completed"
    db.commit()

    try:
        send_award_notification(winner, neg, buyer, body.explanation)
    except Exception as e:
        print(f"Award email error: {e}")

    for loser in losers:
        try:
            send_rejection_notification(loser, neg, buyer, body.explanation if body.share_explanation else None)
        except Exception as e:
            print(f"Rejection email error: {e}")

    return {"ok": True, "awarded_to": winner.vendor_company or winner.vendor_email}


# ── Vendor: magic-link access ─────────────────────────────────────────────────

@app.get("/api/negotiate/{token}", response_model=schemas.VendorContextOut)
def get_vendor_context(token: str, db: Annotated[Session, Depends(get_db)]):
    vs = _get_vs_by_token(token, db)
    neg = vs.negotiation
    buyer = db.get(User, neg.buyer_id)
    return schemas.VendorContextOut(
        vendor_session_id=vs.id,
        negotiation_id=neg.id,
        item=neg.item,
        quantity=neg.quantity,
        currency=neg.currency,
        buyer_company=buyer.company if buyer else None,
        vendor_company=vs.vendor_company,
        vendor_name=vs.vendor_name,
        quoted_price=vs.quoted_price,
        quoted_delivery_days=vs.quoted_delivery_days,
        quoted_payment_days=vs.quoted_payment_days,
        status=vs.status,
        current_state=vs.current_state,
        round_count=vs.round_count,
        current_offer=vs.current_offer,
    )


@app.post("/api/negotiate/{token}/start", response_model=schemas.MessageOut)
def start_negotiation_chat(token: str, db: Annotated[Session, Depends(get_db)]):
    """Called when vendor opens the chat for the first time. Generates bot opening message."""
    vs = _get_vs_by_token(token, db)
    if vs.current_state not in ("not_started",):
        # Already started — return last bot message
        last = next((m for m in reversed(vs.messages) if m.role == "assistant"), None)
        if last:
            return schemas.MessageOut.model_validate(last)

    try:
        reply = generate_opening_message(db, vs)
    except anthropic.AuthenticationError:
        raise HTTPException(502, "Anthropic API key invalid")
    except anthropic.RateLimitError:
        raise HTTPException(429, "Rate limit hit. Try again shortly.")

    db.refresh(vs)
    last_msg = vs.messages[-1]
    return schemas.MessageOut.model_validate(last_msg)


@app.post("/api/negotiate/{token}/chat", response_model=schemas.VendorChatOut)
def vendor_chat(token: str, body: schemas.VendorChatIn, db: Annotated[Session, Depends(get_db)]):
    vs = _get_vs_by_token(token, db)

    if vs.status in ("rejected", "closed", "pending_qualification"):
        raise HTTPException(400, f"This negotiation is already {vs.status}.")

    try:
        reply, state, offer, escalation, agreement = run_negotiation_turn(db, vs, body.message)
    except anthropic.AuthenticationError:
        raise HTTPException(502, "Anthropic API key invalid")
    except anthropic.RateLimitError:
        raise HTTPException(429, "Rate limit hit. Try again shortly.")

    # Notify buyer on escalation or agreement
    if escalation or agreement:
        neg = vs.negotiation
        buyer = db.get(User, neg.buyer_id)
        review_url = f"{settings.frontend_url}/negotiations/{neg.id}"
        if escalation and buyer:
            try:
                send_escalation_alert(buyer.email, buyer.display_name, vs.vendor_company or vs.vendor_email, "Bot escalated — review needed", review_url)
            except Exception:
                pass
        if agreement and buyer:
            try:
                send_agreement_notification(buyer.email, buyer.display_name, vs.vendor_company or vs.vendor_email, offer.get("price") if offer else None, neg.currency, review_url)
                update_vendor_memory(db, vs)
            except Exception:
                pass

    return schemas.VendorChatOut(
        reply=reply,
        state=state,
        round_count=vs.round_count,
        current_offer=offer,
        escalation_needed=escalation,
        agreement_reached=agreement,
    )


@app.get("/api/negotiate/{token}/messages", response_model=list[schemas.MessageOut])
def get_vendor_chat_history(token: str, db: Annotated[Session, Depends(get_db)]):
    vs = _get_vs_by_token(token, db)
    return [schemas.MessageOut.model_validate(m) for m in vs.messages]


# ── Vendor: account-based access ──────────────────────────────────────────────

@app.get("/api/vendor/negotiations", response_model=list[schemas.VendorSessionOut])
def vendor_negotiations(
    vendor: Annotated[User, Depends(require_vendor)],
    db: Annotated[Session, Depends(get_db)],
):
    rows = db.query(VendorSession).filter(VendorSession.vendor_id == vendor.id).order_by(VendorSession.id.desc()).all()
    return [_vs_out(vs, db) for vs in rows]


@app.get("/api/vendor/negotiations/{vsid}/messages", response_model=list[schemas.MessageOut])
def vendor_get_messages(
    vsid: int,
    vendor: Annotated[User, Depends(require_vendor)],
    db: Annotated[Session, Depends(get_db)],
):
    vs = _get_vs(vsid, db)
    if vs.vendor_id != vendor.id:
        raise HTTPException(403)
    return [schemas.MessageOut.model_validate(m) for m in vs.messages]


@app.post("/api/vendor/negotiations/{vsid}/chat", response_model=schemas.VendorChatOut)
def vendor_account_chat(
    vsid: int,
    body: schemas.VendorChatIn,
    vendor: Annotated[User, Depends(require_vendor)],
    db: Annotated[Session, Depends(get_db)],
):
    vs = _get_vs(vsid, db)
    if vs.vendor_id != vendor.id:
        raise HTTPException(403)
    if vs.status in ("rejected", "closed", "pending_qualification"):
        raise HTTPException(400, f"This negotiation is already {vs.status}.")

    if vs.current_state == "not_started":
        generate_opening_message(db, vs)
        db.refresh(vs)

    try:
        reply, state, offer, escalation, agreement = run_negotiation_turn(db, vs, body.message)
    except anthropic.AuthenticationError:
        raise HTTPException(502, "Anthropic API key invalid")
    except anthropic.RateLimitError:
        raise HTTPException(429, "Rate limit hit. Try again shortly.")

    if escalation or agreement:
        neg = vs.negotiation
        buyer = db.get(User, neg.buyer_id)
        review_url = f"{settings.frontend_url}/negotiations/{neg.id}"
        if escalation and buyer:
            try:
                send_escalation_alert(buyer.email, buyer.display_name, vs.vendor_company or vs.vendor_email, "Bot escalated — review needed", review_url)
            except Exception:
                pass
        if agreement and buyer:
            try:
                send_agreement_notification(buyer.email, buyer.display_name, vs.vendor_company or vs.vendor_email, offer.get("price") if offer else None, neg.currency, review_url)
                update_vendor_memory(db, vs)
            except Exception:
                pass

    return schemas.VendorChatOut(
        reply=reply,
        state=state,
        round_count=vs.round_count,
        current_offer=offer,
        escalation_needed=escalation,
        agreement_reached=agreement,
    )


@app.post("/api/vendor/negotiations/{vsid}/start", response_model=schemas.MessageOut)
def vendor_account_start(
    vsid: int,
    vendor: Annotated[User, Depends(require_vendor)],
    db: Annotated[Session, Depends(get_db)],
):
    vs = _get_vs(vsid, db)
    if vs.vendor_id != vendor.id:
        raise HTTPException(403)
    if vs.current_state != "not_started":
        last = next((m for m in reversed(vs.messages) if m.role == "assistant"), None)
        if last:
            return schemas.MessageOut.model_validate(last)

    generate_opening_message(db, vs)
    db.refresh(vs)
    return schemas.MessageOut.model_validate(vs.messages[-1])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_neg(nid: int, buyer_id: int, db: Session) -> Negotiation:
    neg = db.get(Negotiation, nid)
    if not neg or neg.buyer_id != buyer_id:
        raise HTTPException(404, "Negotiation not found")
    return neg


def _get_vs(vsid: int, db: Session) -> VendorSession:
    vs = db.get(VendorSession, vsid)
    if not vs:
        raise HTTPException(404, "Vendor session not found")
    return vs


def _get_vs_by_token(token: str, db: Session) -> VendorSession:
    vs = db.query(VendorSession).filter(VendorSession.magic_link_token == token).first()
    if not vs:
        raise HTTPException(404, "Invalid or expired link")
    if vs.token_expires_at and vs.token_expires_at < datetime.now(timezone.utc):
        raise HTTPException(410, "This invitation link has expired")
    return vs


def _neg_out(neg: Negotiation) -> schemas.NegotiationOut:
    sessions = neg.vendor_sessions
    return schemas.NegotiationOut(
        id=neg.id,
        title=neg.title,
        item=neg.item,
        quantity=neg.quantity,
        currency=neg.currency,
        status=neg.status,
        created_at=neg.created_at,
        vendor_count=len(sessions),
        active_count=sum(1 for vs in sessions if vs.status == "chatting"),
        agreed_count=sum(1 for vs in sessions if vs.status == "agreed"),
    )


def _vs_out(vs: VendorSession, db: Session) -> schemas.VendorSessionOut:
    has_pending = db.query(EscalationAlert).filter(
        EscalationAlert.vendor_session_id == vs.id,
        EscalationAlert.status == "pending",
    ).count() > 0
    out = schemas.VendorSessionOut.model_validate(vs)
    out.has_pending_escalation = has_pending
    neg = vs.negotiation
    if neg:
        out.negotiation_title    = neg.title
        out.negotiation_item     = neg.item
        out.negotiation_quantity = neg.quantity
        out.negotiation_currency = neg.currency
        out.buyer_company        = neg.buyer.company if neg.buyer else None

    targets = db.query(BuyerTargets).filter(BuyerTargets.negotiation_id == vs.negotiation_id).first()
    if targets:
        def _r(v): return round(v, 1) if v is not None else None
        # Use current negotiated offer values when available, fall back to original quote
        cur = vs.current_offer or {}
        eff_price    = cur.get("price")           if cur.get("price")           is not None else vs.quoted_price
        eff_delivery = cur.get("delivery_days")   if cur.get("delivery_days")   is not None else vs.quoted_delivery_days
        eff_payment  = cur.get("payment_days")    if cur.get("payment_days")    is not None else vs.quoted_payment_days
        eff_warranty = cur.get("warranty_months") if cur.get("warranty_months") is not None else vs.quoted_warranty_months
        out.price_score    = _r(_price_dim_score(eff_price,    targets.target_price,          targets.reservation_price))
        out.delivery_score = _r(_delivery_dim_score(eff_delivery, targets.target_delivery_days, targets.max_delivery_days))
        out.payment_score  = _r(_payment_dim_score(eff_payment,  targets.target_payment_days,  targets.min_payment_days))
        out.warranty_score = _r(_warranty_dim_score(eff_warranty, targets.warranty_months_target, targets.warranty_months_min))

    return out
