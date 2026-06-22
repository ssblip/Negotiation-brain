"""Email sender for vendor invitations, escalation alerts, and award notifications."""
from __future__ import annotations

import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings
from app.models import Negotiation, User, VendorSession


def _send_smtp(to: str, subject: str, html: str) -> None:
    if not settings.smtp_user:
        print(f"[EMAIL STUB] To: {to} | Subject: {subject}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
        s.starttls()
        s.login(settings.smtp_user, settings.smtp_pass)
        s.sendmail(settings.smtp_user, [to], msg.as_string())


def send_vendor_invitation(
    vs: VendorSession,
    negotiation: Negotiation,
    buyer: User,
) -> None:
    chat_url = f"{settings.frontend_url}/negotiate/{vs.magic_link_token}"
    vendor_login_url = f"{settings.frontend_url}/login"

    vendor_name = vs.vendor_name or vs.vendor_company or "there"
    price_line = f"${vs.quoted_price:,.2f} per unit" if vs.quoted_price else "as submitted"

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
  <h2 style="color: #1a56db;">Negotiation Invitation</h2>
  <p>Hi {vendor_name},</p>
  <p>
    <strong>{buyer.company or buyer.display_name}</strong> has reviewed your quote for
    <strong>{negotiation.item}</strong> (Qty: {negotiation.quantity:,}) and would like to
    discuss the terms further.
  </p>
  <p>Your current quote: <strong>{price_line}</strong></p>

  <h3>How to respond</h3>
  <p>You can join the negotiation in two ways:</p>

  <p>
    <strong>Option 1 — Quick access (no login needed):</strong><br/>
    <a href="{chat_url}" style="background:#1a56db;color:white;padding:10px 20px;
       border-radius:5px;text-decoration:none;display:inline-block;margin-top:8px;">
      Open Negotiation Chat →
    </a>
  </p>

  <p>
    <strong>Option 2 — Create an account to track all your bids:</strong><br/>
    <a href="{vendor_login_url}">Register / Login</a> with this email address
    ({vs.vendor_email}) and all invitations will appear in your dashboard.
  </p>

  <p style="color:#666;font-size:12px;margin-top:30px;">
    This invitation is valid for 7 days. Reference: Negotiation #{negotiation.id}
  </p>
</body>
</html>
"""
    _send_smtp(
        to=vs.vendor_email,
        subject=f"Negotiation Invitation: {negotiation.item} — {buyer.company or buyer.display_name}",
        html=html,
    )


def send_escalation_alert(
    buyer_email: str,
    buyer_name: str,
    vendor_company: str,
    reason: str,
    review_url: str,
) -> None:
    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
  <h2 style="color: #e02424;">⚠ Negotiation Escalation — Action Required</h2>
  <p>Hi {buyer_name},</p>
  <p>
    The negotiation bot has escalated a session with <strong>{vendor_company}</strong>
    and requires your decision.
  </p>
  <p><strong>Reason:</strong> {reason}</p>
  <p>
    <a href="{review_url}" style="background:#e02424;color:white;padding:10px 20px;
       border-radius:5px;text-decoration:none;display:inline-block;margin-top:8px;">
      Review &amp; Decide →
    </a>
  </p>
</body>
</html>
"""
    _send_smtp(
        to=buyer_email,
        subject=f"Action Required: Negotiation Escalated — {vendor_company}",
        html=html,
    )


def send_award_notification(
    vs: VendorSession,
    neg: Negotiation,
    buyer: User,
    explanation: str,
) -> None:
    vendor_name = vs.vendor_name or vs.vendor_company or "there"
    offer = vs.current_offer or {}
    price    = vs.final_price        if vs.final_price        is not None else (offer.get("price")           if offer.get("price")           is not None else vs.quoted_price)
    delivery = vs.final_delivery_days if vs.final_delivery_days is not None else (offer.get("delivery_days")   if offer.get("delivery_days")   is not None else vs.quoted_delivery_days)
    payment  = vs.final_payment_days  if vs.final_payment_days  is not None else (offer.get("payment_days")    if offer.get("payment_days")    is not None else vs.quoted_payment_days)
    warranty = offer.get("warranty_months") if offer.get("warranty_months") is not None else vs.quoted_warranty_months

    price_str    = f"{vs.quoted_currency} {price:,.2f}" if price    else "As per quote"
    delivery_str = f"{delivery} days"                   if delivery else "As per quote"
    payment_str  = f"Net-{payment}"                     if payment  else "As per quote"
    warranty_str = f"{warranty} months"                 if warranty else "As per quote"
    buyer_name   = buyer.company or buyer.display_name

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #1e293b;">
  <div style="background: #f0fdf4; border: 1px solid #86efac; border-radius: 10px; padding: 20px 24px; margin-bottom: 24px;">
    <h2 style="color: #15803d; margin: 0 0 4px;">Tender Awarded — Congratulations!</h2>
    <p style="margin: 0; color: #166534; font-size: 14px;">Your bid for <strong>{neg.item}</strong> has been selected.</p>
  </div>

  <p>Dear {vendor_name},</p>
  <p>
    We are pleased to inform you that <strong>{buyer_name}</strong> has awarded the tender for
    <strong>{neg.item}</strong> (Qty: {neg.quantity:,}) to your company.
  </p>

  <h3 style="color: #1e3a5f; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px;">Finalised Terms</h3>
  <table style="width: 100%; border-collapse: collapse; font-size: 14px; margin-bottom: 20px;">
    <tr style="background: #f8fafc;">
      <td style="padding: 10px 14px; font-weight: 600; border: 1px solid #e2e8f0; width: 40%;">Item</td>
      <td style="padding: 10px 14px; border: 1px solid #e2e8f0;">{neg.item}</td>
    </tr>
    <tr>
      <td style="padding: 10px 14px; font-weight: 600; border: 1px solid #e2e8f0;">Quantity</td>
      <td style="padding: 10px 14px; border: 1px solid #e2e8f0;">{neg.quantity:,}</td>
    </tr>
    <tr style="background: #f8fafc;">
      <td style="padding: 10px 14px; font-weight: 600; border: 1px solid #e2e8f0;">Agreed Price</td>
      <td style="padding: 10px 14px; border: 1px solid #e2e8f0; font-weight: 700; color: #15803d;">{price_str}</td>
    </tr>
    <tr>
      <td style="padding: 10px 14px; font-weight: 600; border: 1px solid #e2e8f0;">Delivery</td>
      <td style="padding: 10px 14px; border: 1px solid #e2e8f0;">{delivery_str}</td>
    </tr>
    <tr style="background: #f8fafc;">
      <td style="padding: 10px 14px; font-weight: 600; border: 1px solid #e2e8f0;">Payment Terms</td>
      <td style="padding: 10px 14px; border: 1px solid #e2e8f0;">{payment_str}</td>
    </tr>
    <tr>
      <td style="padding: 10px 14px; font-weight: 600; border: 1px solid #e2e8f0;">Warranty</td>
      <td style="padding: 10px 14px; border: 1px solid #e2e8f0;">{warranty_str}</td>
    </tr>
  </table>

  <div style="background: #eff6ff; border-left: 4px solid #3b82f6; padding: 12px 16px; margin-bottom: 20px;">
    <p style="margin: 0; font-size: 14px;"><strong>Note from {buyer_name}:</strong><br/>{explanation}</p>
  </div>

  <p style="font-size: 14px;">Our procurement team will be in touch shortly with the formal purchase order and next steps. Please do not proceed with production until you receive the official PO.</p>

  <p style="color: #6b7280; font-size: 12px; margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 12px;">
    Reference: Tender #{neg.id} &nbsp;|&nbsp; {buyer_name}
  </p>
</body>
</html>
"""
    _send_smtp(
        to=vs.vendor_email,
        subject=f"Tender Awarded: {neg.item} — You have been selected",
        html=html,
    )


def send_rejection_notification(
    vs: VendorSession,
    neg: Negotiation,
    buyer: User,
    explanation: str | None,
) -> None:
    vendor_name = vs.vendor_name or vs.vendor_company or "there"
    buyer_name  = buyer.company or buyer.display_name
    explanation_block = (
        f'<div style="background:#fff7ed;border-left:4px solid #f59e0b;padding:12px 16px;margin-bottom:20px;">'
        f'<p style="margin:0;font-size:14px;"><strong>Note from {buyer_name}:</strong><br/>{explanation}</p>'
        f'</div>'
    ) if explanation else ""

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #1e293b;">
  <h2 style="color: #1e3a5f;">Tender Outcome: {neg.item}</h2>

  <p>Dear {vendor_name},</p>
  <p>
    Thank you for participating in the tender process for <strong>{neg.item}</strong>
    (Qty: {neg.quantity:,}) conducted by <strong>{buyer_name}</strong>.
  </p>
  <p>
    After careful evaluation of all submissions, we regret to inform you that your bid
    was not selected for this tender. We appreciate the time and effort you invested in
    preparing your proposal.
  </p>

  {explanation_block}

  <p style="font-size: 14px;">
    We value your participation and hope to work with you in future procurement opportunities.
    If you have any questions, please do not hesitate to reach out to us.
  </p>

  <p style="color: #6b7280; font-size: 12px; margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 12px;">
    Reference: Tender #{neg.id} &nbsp;|&nbsp; {buyer_name}
  </p>
</body>
</html>
"""
    _send_smtp(
        to=vs.vendor_email,
        subject=f"Tender Update: {neg.item} — Outcome Notification",
        html=html,
    )


def send_agreement_notification(
    buyer_email: str,
    buyer_name: str,
    vendor_company: str,
    final_price: float | None,
    currency: str,
    review_url: str,
) -> None:
    price_str = f"{currency} {final_price:,.2f}" if final_price else "terms agreed"
    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
  <h2 style="color: #057a55;">✓ Tentative Agreement Reached</h2>
  <p>Hi {buyer_name},</p>
  <p>
    The negotiation bot has reached a tentative agreement with
    <strong>{vendor_company}</strong> at <strong>{price_str}</strong>.
  </p>
  <p>Please review the full terms and approve or reject.</p>
  <p>
    <a href="{review_url}" style="background:#057a55;color:white;padding:10px 20px;
       border-radius:5px;text-decoration:none;display:inline-block;margin-top:8px;">
      Review Agreement →
    </a>
  </p>
</body>
</html>
"""
    _send_smtp(
        to=buyer_email,
        subject=f"Agreement Reached: {vendor_company} — Awaiting Your Approval",
        html=html,
    )
