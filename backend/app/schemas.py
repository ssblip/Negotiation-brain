from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


# ---------- Auth ----------

class RegisterIn(BaseModel):
    email: str
    password: str
    display_name: str
    company: str | None = None
    role: str = "buyer"  # buyer | vendor


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    company: str | None
    role: str

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    user: UserOut


# ---------- Negotiation ----------

class NegotiationCreateIn(BaseModel):
    title: str
    item: str
    quantity: int = 1
    currency: str = "USD"


class NegotiationOut(BaseModel):
    id: int
    title: str
    item: str
    quantity: int
    currency: str
    status: str
    created_at: datetime
    vendor_count: int = 0
    active_count: int = 0
    agreed_count: int = 0

    model_config = {"from_attributes": True}


# ---------- Buyer Targets ----------

class CustomSpec(BaseModel):
    name: str
    field_type: str  # NUM | BOOL | CAT | DATE | TIER | PCTNUM | SCORE | MULTI | RANGE | TEXT
    required_value: Any
    weight: float = 1.0
    unit: str | None = None


class BuyerTargetsIn(BaseModel):
    target_price: float | None = None
    reservation_price: float | None = None
    target_delivery_days: int | None = None
    max_delivery_days: int | None = None
    target_payment_days: int | None = None
    min_payment_days: int | None = None
    warranty_months_target: int | None = None
    warranty_months_min: int | None = None
    batna_description: str | None = None
    batna_strength: int | None = None
    custom_specs: list[CustomSpec] = []


class BuyerTargetsOut(BuyerTargetsIn):
    id: int
    negotiation_id: int

    model_config = {"from_attributes": True}


# ---------- Vendor Session ----------

class VendorQuoteIn(BaseModel):
    vendor_email: str
    vendor_company: str | None = None
    vendor_name: str | None = None
    quoted_price: float | None = None
    quoted_delivery_days: int | None = None
    quoted_payment_days: int | None = None
    quoted_warranty_months: int | None = None
    quoted_currency: str = "USD"
    custom_spec_values: dict[str, Any] | None = None


class VendorSessionOut(BaseModel):
    id: int
    negotiation_id: int
    negotiation_title: str | None = None
    negotiation_item: str | None = None
    negotiation_quantity: int | None = None
    negotiation_currency: str | None = None
    buyer_company: str | None = None
    vendor_email: str
    vendor_company: str | None
    vendor_name: str | None
    quoted_price: float | None
    quoted_delivery_days: int | None
    quoted_payment_days: int | None
    quoted_warranty_months: int | None
    quoted_currency: str
    custom_spec_values: dict | None = None
    priority: str | None = None
    spec_score: float | None
    cvs_score: float | None
    price_score: float | None = None
    delivery_score: float | None = None
    payment_score: float | None = None
    warranty_score: float | None = None
    strategy: str | None
    current_state: str
    round_count: int
    current_offer: dict | None
    final_price: float | None
    final_delivery_days: int | None
    final_payment_days: int | None
    status: str
    invited_at: datetime
    first_response_at: datetime | None
    closed_at: datetime | None
    has_pending_escalation: bool = False

    model_config = {"from_attributes": True}


class ParsedVendorsOut(BaseModel):
    vendors: list[VendorQuoteIn]
    raw_text: str


# ---------- Chat ----------

class VendorChatIn(BaseModel):
    message: str


class VendorChatOut(BaseModel):
    reply: str
    state: str
    round_count: int
    current_offer: dict | None
    escalation_needed: bool
    agreement_reached: bool


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    round_number: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Escalation ----------

class EscalationOut(BaseModel):
    id: int
    vendor_session_id: int
    negotiation_id: int
    reason: str
    context_summary: str | None
    status: str
    buyer_decision: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EscalationResolveIn(BaseModel):
    decision: str  # proceed | accept | reject
    instruction: str | None = None


class AwardIn(BaseModel):
    vendor_session_id: int
    explanation: str
    share_explanation: bool = True


# ---------- Vendor magic-link context ----------

class VendorContextOut(BaseModel):
    vendor_session_id: int
    negotiation_id: int
    item: str
    quantity: int
    currency: str
    buyer_company: str | None
    vendor_company: str | None
    vendor_name: str | None
    quoted_price: float | None
    quoted_delivery_days: int | None
    quoted_payment_days: int | None
    status: str
    current_state: str
    round_count: int
    current_offer: dict | None
