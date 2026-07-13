from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    display_name: Mapped[str] = mapped_column(String)
    company: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String)  # buyer | vendor
    strategy_doc: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategy_doc_condensed: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    negotiations: Mapped[list[Negotiation]] = relationship(back_populates="buyer")
    vendor_sessions: Mapped[list[VendorSession]] = relationship(back_populates="vendor_user")


class Negotiation(Base):
    """One negotiation event created by a buyer (covers all vendors for one RFP)."""
    __tablename__ = "negotiations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String)
    item: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    currency: Mapped[str] = mapped_column(String, default="USD")
    status: Mapped[str] = mapped_column(String, default="draft")  # draft|active|completed|cancelled
    strategy_doc: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategy_doc_condensed: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    buyer: Mapped[User] = relationship(back_populates="negotiations")
    targets: Mapped[BuyerTargets | None] = relationship(back_populates="negotiation", uselist=False)
    vendor_sessions: Mapped[list[VendorSession]] = relationship(back_populates="negotiation")


class BuyerTargets(Base):
    """Buyer's negotiation targets and session configuration."""
    __tablename__ = "buyer_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    negotiation_id: Mapped[int] = mapped_column(ForeignKey("negotiations.id"), unique=True)

    # Price
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    reservation_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # NEVER revealed to vendor

    # Delivery
    target_delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Payment (days, e.g. 30 = Net-30)
    target_payment_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_payment_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Warranty
    warranty_months_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warranty_months_min: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # BATNA
    batna_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    batna_strength: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1–10

    # Custom spec fields: [{name, field_type, required_value, weight, unit}]
    custom_specs: Mapped[list | None] = mapped_column(JSON, nullable=True)

    negotiation: Mapped[Negotiation] = relationship(back_populates="targets")


class VendorSession(Base):
    """One vendor's participation in a negotiation — holds their quote, scores, state, and chat."""
    __tablename__ = "vendor_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    negotiation_id: Mapped[int] = mapped_column(ForeignKey("negotiations.id"))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # set after vendor registers
    vendor_email: Mapped[str] = mapped_column(String, index=True)
    vendor_company: Mapped[str | None] = mapped_column(String, nullable=True)
    vendor_name: Mapped[str | None] = mapped_column(String, nullable=True)

    # Magic link auth
    magic_link_token: Mapped[str] = mapped_column(String, unique=True, default=_token)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Original parsed quote
    quoted_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quoted_delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quoted_payment_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quoted_warranty_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quoted_currency: Mapped[str] = mapped_column(String, default="USD")
    custom_spec_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {field_name: value}
    raw_quote_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Computed scores (filled after parsing)
    spec_score: Mapped[float | None] = mapped_column(Float, nullable=True)   # 0–100
    cvs_score: Mapped[float | None] = mapped_column(Float, nullable=True)    # 0–100
    strategy: Mapped[str | None] = mapped_column(String, nullable=True)       # S1–S6

    # State machine
    current_state: Mapped[str] = mapped_column(String, default="not_started")
    # not_started|greeting|spec_review|price_negotiation|logrolling|bafo|agreement|escalated|impasse|closed
    round_count: Mapped[int] = mapped_column(Integer, default=0)
    concession_budget: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Latest offer tracking (updated each round)
    current_offer: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {price, delivery_days, payment_days, warranty_months}

    # Final agreed terms
    final_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_payment_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    priority: Mapped[str | None] = mapped_column(String, nullable=True)  # P1 | P2 | P3 | None

    mandatory_failures: Mapped[list | None] = mapped_column(JSON, nullable=True)  # spec names that failed Must Have gate
    buyer_override: Mapped[bool] = mapped_column(Boolean, default=False)  # buyer chose to include despite failures

    status: Mapped[str] = mapped_column(String, default="invited")
    # invited|chatting|agreed|escalated|rejected|expired|pending_qualification

    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    negotiation: Mapped[Negotiation] = relationship(back_populates="vendor_sessions")
    vendor_user: Mapped[User | None] = relationship(back_populates="vendor_sessions")
    messages: Mapped[list[NegotiationMessage]] = relationship(back_populates="vendor_session", order_by="NegotiationMessage.id")
    escalations: Mapped[list[EscalationAlert]] = relationship(back_populates="vendor_session")


class NegotiationMessage(Base):
    __tablename__ = "negotiation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor_session_id: Mapped[int] = mapped_column(ForeignKey("vendor_sessions.id"))
    role: Mapped[str] = mapped_column(String)  # assistant | vendor
    content: Mapped[str] = mapped_column(Text)
    round_number: Mapped[int] = mapped_column(Integer, default=0)
    state_at_time: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    vendor_session: Mapped[VendorSession] = relationship(back_populates="messages")


class VendorMemory(Base):
    """Persistent vendor profile — survives across multiple negotiations."""
    __tablename__ = "vendor_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor_email: Mapped[str] = mapped_column(String, unique=True, index=True)
    vendor_company: Mapped[str | None] = mapped_column(String, nullable=True)
    archetype: Mapped[str | None] = mapped_column(String, nullable=True)
    # reluctant_conceder|responsive|aggressive|quality_deflector|logroller|unknown
    session_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_concession_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    tactics_used: Mapped[list | None] = mapped_column(JSON, nullable=True)
    key_learnings: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EscalationAlert(Base):
    """Created when the bot needs human buyer input."""
    __tablename__ = "escalation_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor_session_id: Mapped[int] = mapped_column(ForeignKey("vendor_sessions.id"))
    negotiation_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String)
    context_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|resolved
    buyer_decision: Mapped[str | None] = mapped_column(String, nullable=True)  # proceed|accept|reject
    buyer_instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    vendor_session: Mapped[VendorSession] = relationship(back_populates="escalations")
