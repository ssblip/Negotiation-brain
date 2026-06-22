"""
Scoring engine — implements the Negotiation Brain scoring framework.

Spec Score  : how well the vendor's product meets the buyer's spec requirements (0–100)
CVS         : Composite Vendor Score across all commercial dimensions (0–100)
Strategy    : auto-selects S1–S6 per the document's decision tree
"""
from __future__ import annotations

import math
from typing import Any


# ---------- Spec Score ----------

def _score_num(vendor_val: float | None, required_val: float | None) -> float:
    if vendor_val is None or required_val is None:
        return 50.0
    if required_val == 0:
        return 100.0
    ratio = vendor_val / required_val
    return max(0.0, min(100.0, ratio * 100))


def _score_bool(vendor_val: Any, required_val: Any) -> float:
    return 100.0 if str(vendor_val).lower() == str(required_val).lower() else 0.0


def _score_cat(vendor_val: Any, required_val: Any) -> float:
    return 100.0 if str(vendor_val).strip().lower() == str(required_val).strip().lower() else 0.0


def _score_multi(vendor_val: Any, required_val: Any) -> float:
    if not required_val:
        return 100.0
    req_set = {str(v).lower() for v in (required_val if isinstance(required_val, list) else [required_val])}
    ven_set = {str(v).lower() for v in (vendor_val if isinstance(vendor_val, list) else [vendor_val])}
    if not req_set:
        return 100.0
    overlap = len(req_set & ven_set) / len(req_set)
    return overlap * 100


def _score_pctnum(vendor_val: float | None, required_val: float | None) -> float:
    return _score_num(vendor_val, required_val)


def _score_single_spec(field_type: str, vendor_val: Any, required_val: Any) -> float:
    ft = field_type.upper()
    if ft == "NUM":
        return _score_num(
            float(vendor_val) if vendor_val is not None else None,
            float(required_val) if required_val is not None else None,
        )
    if ft == "BOOL":
        return _score_bool(vendor_val, required_val)
    if ft in ("CAT", "SCORE", "TEXT", "DATE", "RANGE", "TIER"):
        return _score_cat(vendor_val, required_val)
    if ft == "MULTI":
        return _score_multi(vendor_val, required_val)
    if ft == "PCTNUM":
        return _score_pctnum(
            float(vendor_val) if vendor_val is not None else None,
            float(required_val) if required_val is not None else None,
        )
    return 50.0


def compute_spec_score(custom_specs: list[dict], custom_spec_values: dict[str, Any] | None) -> float:
    """
    custom_specs: buyer's spec requirements [{name, field_type, required_value, weight}]
    custom_spec_values: vendor's provided values {name: value}
    Returns 0–100.
    """
    if not custom_specs:
        return 100.0

    total_weight = sum(s.get("weight", 1.0) for s in custom_specs)
    if total_weight == 0:
        return 100.0

    weighted_sum = 0.0
    vendor_vals = custom_spec_values or {}

    for spec in custom_specs:
        name = spec["name"]
        field_type = spec.get("field_type", "TEXT")
        required_val = spec.get("required_value")
        weight = spec.get("weight", 1.0)
        vendor_val = vendor_vals.get(name)
        score = _score_single_spec(field_type, vendor_val, required_val)
        weighted_sum += score * weight

    return round(weighted_sum / total_weight, 2)


# ---------- Dimension Scores (formulas from Negotiation Brain v3, Section 8.2) ----------

def _price_dim_score(quoted: float | None, target: float | None, reservation: float | None) -> float | None:
    """
    Tier 1: quoted ≤ target                          → 100
    Tier 2: target < quoted ≤ target×1.10            → 100 − ((quoted−target)/target × 100 × 4)
    Tier 3: target×1.10 < quoted ≤ reservation       → 60 − ((quoted−target×1.10)/target × 100 × 3)
    Tier 4: quoted > reservation                     → max(0, 30 − ((quoted−rp)/rp × 100 × 5))
    """
    if quoted is None or target is None:
        return None
    if quoted <= target:
        return 100.0
    t110 = target * 1.10
    if quoted <= t110:
        return max(0.0, 100.0 - ((quoted - target) / target * 100 * 4))
    if reservation is None or quoted <= reservation:
        score = 60.0 - ((quoted - t110) / target * 100 * 3)
        return max(0.0, score)
    # above reservation
    return max(0.0, 30.0 - ((quoted - reservation) / reservation * 100 * 5))


def _delivery_dim_score(quoted_days: int | None, target_days: int | None, max_days: int | None) -> float | None:
    """
    gap = quoted − target
    gap ≤ 0                              → 100
    0 < gap ≤ slack                      → 100 − (gap × 4)
    slack < gap ≤ slack+14               → max(30, 80 − (gap × 5))
    gap > slack+14                       → max(0, 30 − (gap × 3))
    slack = max(max_days − target_days, 0) if both present, else 7
    """
    if quoted_days is None or target_days is None:
        return None
    gap = quoted_days - target_days
    if gap <= 0:
        return 100.0
    slack = max(max_days - target_days, 0) if max_days is not None else 7
    if gap <= slack:
        return max(0.0, 100.0 - gap * 4)
    if gap <= slack + 14:
        return max(30.0, 80.0 - gap * 5)
    return max(0.0, 30.0 - gap * 3)


def _payment_dim_score(quoted_days: int | None, target_days: int | None, min_days: int | None,
                        advance_pct: float = 0.0) -> float | None:
    """
    quoted ≥ target                      → 100
    min ≤ quoted < target                → 70 + (quoted−min)/(target−min) × 30
    quoted < min                         → max(0, quoted/min × 50)
    advance_pct > 50                     → 0
    advance_pct > 25                     → score × 0.5
    """
    if quoted_days is None or target_days is None:
        return None
    if quoted_days >= target_days:
        score = 100.0
    elif min_days is not None and min_days < target_days and quoted_days >= min_days:
        score = 70.0 + (quoted_days - min_days) / (target_days - min_days) * 30.0
    elif min_days is not None and quoted_days < min_days:
        score = max(0.0, quoted_days / min_days * 50.0)
    else:
        gap = (target_days - quoted_days) / max(target_days, 1)
        score = max(0.0, 100.0 - gap * 100)

    if advance_pct > 50:
        return 0.0
    if advance_pct > 25:
        score *= 0.5
    return round(score, 2)


def _warranty_dim_score(quoted_months: int | None, target_months: int | None, min_months: int | None) -> float | None:
    """
    base = min(100, quoted/target × 100)
    min_months check: if quoted < min → 0
    """
    if quoted_months is None or target_months is None:
        return None
    if min_months is not None and quoted_months < min_months:
        return 0.0
    return round(min(100.0, quoted_months / max(target_months, 1) * 100.0), 2)


def compute_cvs(
    spec_score: float,
    quoted_price: float | None,
    target_price: float | None,
    reservation_price: float | None,
    quoted_delivery: int | None,
    target_delivery: int | None,
    max_delivery: int | None,
    quoted_payment: int | None,
    target_payment: int | None,
    min_payment: int | None,
    quoted_warranty: int | None,
    target_warranty: int | None,
    min_warranty: int | None,
) -> float:
    """CVS per doc Section 8.1: price 35%, delivery 20%, payment 15%, spec 18%, warranty 7%, risk/compliance 5%."""
    # None means target not configured — use 50 (neutral) so CVS still computes
    price_score    = _price_dim_score(quoted_price, target_price, reservation_price) or 50.0
    delivery_score = _delivery_dim_score(quoted_delivery, target_delivery, max_delivery) or 50.0
    payment_score  = _payment_dim_score(quoted_payment, target_payment, min_payment) or 50.0
    warranty_score = _warranty_dim_score(quoted_warranty, target_warranty, min_warranty) or 50.0

    cvs = (
        price_score    * 0.35
        + delivery_score * 0.20
        + payment_score  * 0.15
        + spec_score     * 0.18
        + warranty_score * 0.07
        # risk/compliance (5%) omitted — no risk score field currently
    )
    return round(cvs, 2)


# ---------- Strategy Selection (S1–S6) ----------

def select_strategy(spec_score: float, quoted_price: float | None, target_price: float | None) -> str:
    """
    Implements the strategy decision tree from the Negotiation Brain document.
    Returns one of: S1 | S2 | S3 | S4 | S5 | S6
    """
    price_gap_pct = 0.0
    if quoted_price and target_price and target_price > 0:
        price_gap_pct = ((quoted_price - target_price) / target_price) * 100

    if spec_score < 50:
        return "S6"  # Requote to Standard
    if 50 <= spec_score < 70:
        return "S1"  # Spec Gap Redirect
    if spec_score >= 110:  # significantly over-specced (vendor_val >> required)
        return "S4"  # Spec Surplus Trade
    if 70 <= spec_score < 90:
        if price_gap_pct <= 5:
            return "S5"  # Competitive Normalisation
        return "S2"  # Value-Adjusted Price Negotiation
    # spec_score >= 90
    if price_gap_pct > 20:
        return "S3"  # Premium Justification Challenge
    return "S5"  # Competitive Normalisation


def compute_initial_concession_budget(
    quoted_price: float | None,
    target_price: float | None,
    reservation_price: float | None,
) -> dict:
    """
    Compute per-dimension concession budget for the bot.
    Price budget = gap between target and what bot can offer.
    """
    price_budget_pct = 0.0
    if quoted_price and target_price and reservation_price:
        # Bot starts from target and can concede up to reservation
        total_gap = quoted_price - target_price
        bot_room = reservation_price - target_price
        price_budget_pct = max(0.0, min(bot_room / max(quoted_price, 1) * 100, 20.0))

    return {
        "price_pct_remaining": round(price_budget_pct, 2),
        "delivery_days_remaining": 5,
        "payment_days_remaining": 15,
        "warranty_months_remaining": 6,
        "concessions_made": [],
    }
