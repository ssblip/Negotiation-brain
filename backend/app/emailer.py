"""Email sender for vendor invitations and escalation alerts."""
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
