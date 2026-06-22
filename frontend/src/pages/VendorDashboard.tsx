import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, VendorSession } from "../api";

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  invited:   { bg: "#eff6ff", text: "#2563eb" },
  chatting:  { bg: "#ecfdf5", text: "#059669" },
  agreed:    { bg: "#f0fdf4", text: "#16a34a" },
  escalated: { bg: "#fff7ed", text: "#ea580c" },
  rejected:  { bg: "#fef2f2", text: "#dc2626" },
};

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: 10, fontWeight: 600, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</span>
      <span style={{ fontSize: 13, color: "#1e293b", fontWeight: 500 }}>{value}</span>
    </div>
  );
}

export default function VendorDashboard() {
  const nav = useNavigate();
  const [sessions, setSessions] = useState<VendorSession[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listVendorNegotiations().then(setSessions).finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 16px" }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, color: "#1e3a5f", marginBottom: 4 }}>My Negotiations</h1>
      <p style={{ color: "#6b7280", fontSize: 14, marginBottom: 28 }}>All negotiations you've been invited to.</p>

      {loading ? <p style={{ color: "#6b7280" }}>Loading…</p> : sessions.length === 0 ? (
        <div style={{ textAlign: "center", padding: "80px 0", color: "#6b7280" }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>📨</div>
          <p style={{ fontSize: 16, fontWeight: 500 }}>No invitations yet</p>
          <p style={{ fontSize: 13, marginTop: 4 }}>Buyers will invite you to negotiations — check back here once invited.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {sessions.map(vs => {
            const c = STATUS_COLORS[vs.status] || { bg: "#f3f4f6", text: "#374151" };
            const cur = vs.current_offer?.price;
            const currency = vs.negotiation_currency || vs.quoted_currency;
            const specs = vs.custom_spec_values ? Object.entries(vs.custom_spec_values).filter(([, v]) => v != null && v !== "") : [];

            return (
              <div key={vs.id} style={{ background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb", overflow: "hidden", boxShadow: "0 1px 4px rgba(0,0,0,0.05)" }}>
                {/* Header */}
                <div style={{ padding: "16px 24px", borderBottom: "1px solid #f3f4f6", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontSize: 17, fontWeight: 700, color: "#1e293b" }}>{vs.negotiation_item || vs.negotiation_title || "Negotiation"}</span>
                      <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 99, background: c.bg, color: c.text }}>{vs.status.toUpperCase()}</span>
                    </div>
                    <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 3 }}>
                      {vs.negotiation_title && vs.negotiation_item && vs.negotiation_title !== vs.negotiation_item && (
                        <span>{vs.negotiation_title} · </span>
                      )}
                      {vs.buyer_company && <span>Buyer: {vs.buyer_company} · </span>}
                      Qty: {vs.negotiation_quantity?.toLocaleString() ?? "—"} · {vs.round_count} round{vs.round_count !== 1 ? "s" : ""} completed
                    </div>
                  </div>
                  {(vs.status === "invited" || vs.status === "chatting") && (
                    <button
                      onClick={() => nav(`/vendor/negotiations/${vs.id}`)}
                      style={{ padding: "8px 20px", background: "#1e3a5f", color: "#fff", border: "none", borderRadius: 8, fontWeight: 600, cursor: "pointer", fontSize: 13, whiteSpace: "nowrap" }}>
                      {vs.status === "invited" ? "Start Chat →" : "Continue Chat →"}
                    </button>
                  )}
                  {vs.status === "agreed" && (
                    <span style={{ fontSize: 13, color: "#059669", fontWeight: 700 }}>✓ Agreed at {currency} {vs.final_price?.toFixed(2)}</span>
                  )}
                </div>

                {/* Quote submission details */}
                <div style={{ padding: "16px 24px" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 12 }}>Your Submitted Quote</div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 16 }}>
                    <Field label="Unit Price" value={vs.quoted_price != null ? `${currency} ${vs.quoted_price.toFixed(2)}` : null} />
                    <Field label="Delivery" value={vs.quoted_delivery_days != null ? `${vs.quoted_delivery_days} days` : null} />
                    <Field label="Payment Terms" value={vs.quoted_payment_days != null ? `Net-${vs.quoted_payment_days}` : null} />
                    <Field label="Warranty" value={vs.quoted_warranty_months != null ? `${vs.quoted_warranty_months} months` : null} />
                    {specs.map(([key, val]) => (
                      <Field key={key} label={key.replace(/_/g, " ")} value={String(val)} />
                    ))}
                  </div>

                  {/* Current negotiated offer if active */}
                  {cur != null && cur !== vs.quoted_price && (
                    <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid #f3f4f6" }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: "#059669", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10 }}>Current Negotiated Offer</div>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 16 }}>
                        <Field label="Price" value={`${currency} ${Number(cur).toFixed(2)}`} />
                        {vs.current_offer?.delivery_days != null && <Field label="Delivery" value={`${vs.current_offer.delivery_days} days`} />}
                        {vs.current_offer?.payment_days != null && <Field label="Payment" value={`Net-${vs.current_offer.payment_days}`} />}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
