import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Negotiation } from "../api";

const STATUS_COLOR: Record<string, string> = {
  draft: "#6b7280", active: "#2563eb", completed: "#059669", cancelled: "#dc2626",
};

function badge(status: string) {
  return (
    <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 99, background: STATUS_COLOR[status] + "22", color: STATUS_COLOR[status] }}>
      {status.toUpperCase()}
    </span>
  );
}

export default function BuyerDashboard() {
  const nav = useNavigate();
  const [negotiations, setNegotiations] = useState<Negotiation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listNegotiations().then(setNegotiations).finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 16px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: "#1e3a5f" }}>My Negotiations</h1>
          <p style={{ color: "#6b7280", marginTop: 4, fontSize: 14 }}>Manage and monitor all your vendor negotiations</p>
        </div>
        <button
          onClick={() => nav("/negotiations/new")}
          style={{ background: "#1e3a5f", color: "#fff", border: "none", padding: "10px 20px", borderRadius: 8, fontWeight: 600, cursor: "pointer", fontSize: 14 }}>
          + New Negotiation
        </button>
      </div>

      {loading ? (
        <p style={{ color: "#6b7280" }}>Loading…</p>
      ) : negotiations.length === 0 ? (
        <div style={{ textAlign: "center", padding: "80px 0", color: "#6b7280" }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>📋</div>
          <p style={{ fontSize: 18, fontWeight: 500, marginBottom: 8 }}>No negotiations yet</p>
          <p style={{ fontSize: 14 }}>Create your first negotiation to get started</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {negotiations.map(n => (
            <div key={n.id}
              onClick={() => n.status === "draft" ? nav(`/negotiations/new?resume=${n.id}`) : nav(`/negotiations/${n.id}`)}
              style={{ background: "#fff", borderRadius: 10, padding: "20px 24px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)", cursor: "pointer", border: n.status === "draft" ? "1px dashed #d1d5db" : "1px solid #e5e7eb", transition: "box-shadow 0.15s" }}
              onMouseEnter={e => (e.currentTarget.style.boxShadow = "0 4px 16px rgba(0,0,0,0.12)")}
              onMouseLeave={e => (e.currentTarget.style.boxShadow = "0 1px 4px rgba(0,0,0,0.07)")}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                    <span style={{ fontSize: 17, fontWeight: 600, color: "#1e293b" }}>{n.title}</span>
                    {badge(n.status)}
                  </div>
                  <div style={{ fontSize: 13, color: "#6b7280" }}>
                    {n.item} · Qty {n.quantity.toLocaleString()} · {n.currency}
                  </div>
                </div>
                {n.status === "draft" ? (
                  <button
                    onClick={e => { e.stopPropagation(); nav(`/negotiations/new?resume=${n.id}`); }}
                    style={{ padding: "7px 14px", background: "#f59e0b", color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, cursor: "pointer", fontSize: 13, whiteSpace: "nowrap" }}>
                    Continue Setup →
                  </button>
                ) : (
                  <div style={{ display: "flex", gap: 20, textAlign: "center" }}>
                    <div>
                      <div style={{ fontSize: 22, fontWeight: 700, color: "#1e3a5f" }}>{n.vendor_count}</div>
                      <div style={{ fontSize: 11, color: "#6b7280" }}>Vendors</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 22, fontWeight: 700, color: "#2563eb" }}>{n.active_count}</div>
                      <div style={{ fontSize: 11, color: "#6b7280" }}>Chatting</div>
                    </div>
                  </div>
                )}
              </div>
              <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 10 }}>
                Created {new Date(n.created_at).toLocaleDateString()}
                {n.status === "draft" && <span style={{ marginLeft: 8, color: "#f59e0b", fontWeight: 500 }}>· Setup incomplete</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
