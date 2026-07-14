import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import * as XLSX from "xlsx";
import { api, Escalation, Message, VendorSession } from "../api";

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  invited:               { bg: "#eff6ff", text: "#2563eb" },
  chatting:              { bg: "#ecfdf5", text: "#059669" },
  agreed:                { bg: "#f0fdf4", text: "#16a34a" },
  escalated:             { bg: "#fff7ed", text: "#ea580c" },
  rejected:              { bg: "#fef2f2", text: "#dc2626" },
  expired:               { bg: "#f9fafb", text: "#6b7280" },
  awarded:               { bg: "#fef9c3", text: "#854d0e" },
  closed:                { bg: "#f1f5f9", text: "#64748b" },
  pending_qualification: { bg: "#fff1f2", text: "#be123c" },
};

const STRATEGY_LABELS: Record<string, string> = {
  S1: "S1 Spec Gap Redirect",
  S2: "S2 Value-Adjusted",
  S3: "S3 Premium Challenge",
  S4: "S4 Spec Surplus",
  S5: "S5 Competitive",
  S6: "S6 Requote",
};

const STATUS_LABELS: Record<string, string> = {
  pending_qualification: "PENDING",
};

function Badge({ status }: { status: string }) {
  const c = STATUS_COLORS[status] || { bg: "#f3f4f6", text: "#374151" };
  return (
    <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 99, background: c.bg, color: c.text }}>
      {STATUS_LABELS[status] ?? status.toUpperCase()}
    </span>
  );
}

function savingsPct(original: number | null, current: number | null | undefined): string {
  if (!original || !current) return "—";
  const pct = ((original - current) / original) * 100;
  return pct > 0 ? `${pct.toFixed(1)}%` : "—";
}

type DimKey = "price" | "spec" | "delivery" | "payment" | "warranty";
const DIMS: { key: DimKey; label: string }[] = [
  { key: "price",    label: "Price"    },
  { key: "spec",     label: "Spec"     },
  { key: "delivery", label: "Delivery" },
  { key: "payment",  label: "Payment"  },
  { key: "warranty", label: "Warranty" },
];
const DIM_WEIGHTS: Record<string, number> = { P1: 3, P2: 2, P3: 1 };
const P_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  P1: { bg: "#fef3c7", text: "#92400e", border: "#fcd34d" },
  P2: { bg: "#ede9fe", text: "#5b21b6", border: "#c4b5fd" },
  P3: { bg: "#f1f5f9", text: "#475569", border: "#cbd5e1" },
};

function dimScore(vs: VendorSession, key: DimKey): number {
  const map: Record<DimKey, number | null> = {
    price:    vs.price_score,
    spec:     vs.spec_score,
    delivery: vs.delivery_score,
    payment:  vs.payment_score,
    warranty: vs.warranty_score,
  };
  return map[key] ?? 50;
}

export default function NegotiationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const nid = Number(id);

  const [vendors, setVendors] = useState<VendorSession[]>([]);
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [priorityDim, setPriorityDim] = useState<Partial<Record<"P1" | "P2" | "P3", DimKey>>>({});
  const [selectedVs, setSelectedVs] = useState<VendorSession | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval>>();

  // Award modal state
  const [showAward, setShowAward] = useState(false);
  const [awardVsId, setAwardVsId] = useState<number | null>(null);
  const [awardExplanation, setAwardExplanation] = useState("");
  const [shareExplanation, setShareExplanation] = useState(true);
  const [awarding, setAwarding] = useState(false);
  const [awardErr, setAwardErr] = useState("");
  const [awardedTo, setAwardedTo] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [vs, esc] = await Promise.all([api.listVendors(nid), api.listEscalations(nid)]);
    setVendors(vs);
    setEscalations(esc);
    if (selectedVs) {
      const updated = vs.find(v => v.id === selectedVs.id);
      if (updated) setSelectedVs(updated);
    }
  }, [nid, selectedVs]);

  useEffect(() => {
    refresh();
    pollRef.current = setInterval(refresh, 5000);
    return () => clearInterval(pollRef.current);
  }, [refresh]);

  async function openChat(vs: VendorSession) {
    setSelectedVs(vs);
    setLoadingMsgs(true);
    try {
      const msgs = await api.getChatHistoryBuyer(nid, vs.id);
      setMessages(msgs);
    } finally { setLoadingMsgs(false); }
  }

  async function resolveEscalation(eid: number, decision: string) {
    await api.resolveEscalation(eid, decision);
    refresh();
  }

  // Weighted sort score: P1×3 + P2×2 + P3×1, normalized
  function sortScore(vs: VendorSession): number {
    const slots: ["P1", "P2", "P3"] = ["P1", "P2", "P3"];
    let weightedSum = 0, totalWeight = 0;
    for (const slot of slots) {
      const dim = priorityDim[slot];
      if (!dim) continue;
      const w = DIM_WEIGHTS[slot];
      weightedSum += dimScore(vs, dim) * w;
      totalWeight += w;
    }
    return totalWeight > 0 ? weightedSum / totalWeight : 0;
  }

  const hasSort = Object.values(priorityDim).some(Boolean);
  const activeVendors = vendors.filter(v => v.status !== "rejected");
  const sortedVendors = hasSort
    ? [...activeVendors].sort((a, b) => sortScore(b) - sortScore(a))
    : activeVendors;

  function exportExcel() {
    const rows = vendors.map(v => ({
      Vendor: v.vendor_company || v.vendor_email,
      Email: v.vendor_email,
      Status: v.status,
      Strategy: v.strategy || "",
      "Spec Score": v.spec_score != null ? `${v.spec_score.toFixed(1)}%` : "",
      "Price Score": v.price_score != null ? `${v.price_score.toFixed(1)}%` : "",
      "Delivery Score": v.delivery_score != null ? `${v.delivery_score.toFixed(1)}%` : "",
      "Payment Score": v.payment_score != null ? `${v.payment_score.toFixed(1)}%` : "",
      "Warranty Score": v.warranty_score != null ? `${v.warranty_score.toFixed(1)}%` : "",
      "Original Price": v.quoted_price,
      "Current Offer": v.current_offer?.price ?? "",
      "Savings %": v.quoted_price && v.current_offer?.price ? savingsPct(v.quoted_price, v.current_offer.price) : "",
      "Delivery (days)": v.current_offer?.delivery_days ?? v.quoted_delivery_days ?? "",
      "Payment (Net-X)": v.current_offer?.payment_days ?? v.quoted_payment_days ?? "",
      Rounds: v.round_count,
      "Final Price": v.final_price ?? "",
    }));
    const ws = XLSX.utils.json_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Negotiations");
    XLSX.writeFile(wb, `negotiation-${nid}.xlsx`);
  }

  async function submitAward() {
    if (!awardVsId) return setAwardErr("Please select a vendor to award.");
    if (!awardExplanation.trim()) return setAwardErr("Please provide an award explanation.");
    setAwarding(true); setAwardErr("");
    try {
      const res = await api.awardTender(nid, { vendor_session_id: awardVsId, explanation: awardExplanation, share_explanation: shareExplanation });
      setAwardedTo(res.awarded_to);
      setShowAward(false);
      setAwardExplanation("");
      setAwardVsId(null);
      await refresh();
    } catch (e: unknown) {
      setAwardErr(e instanceof Error ? e.message : "Award failed");
    } finally {
      setAwarding(false);
    }
  }

  const isCompleted = vendors.some(v => v.status === "awarded");
  const pendingEscalations = escalations.filter(e => e.status === "pending");

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "28px 16px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <button onClick={() => nav("/")} style={{ background: "none", border: "none", color: "#6b7280", cursor: "pointer", fontSize: 13, marginBottom: 4 }}>
            ← Back to Dashboard
          </button>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "#1e3a5f" }}>Live Negotiation Monitor</h1>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <button onClick={exportExcel} style={{ padding: "8px 16px", background: "#059669", color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, cursor: "pointer", fontSize: 13 }}>
            ↓ Export Excel
          </button>
          {!isCompleted && vendors.length > 0 && (
            <button onClick={() => setShowAward(true)} style={{ padding: "8px 16px", background: "#1e3a5f", color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, cursor: "pointer", fontSize: 13 }}>
              Close &amp; Award Tender →
            </button>
          )}
        </div>
      </div>

      {awardedTo && (
        <div style={{ background: "#fef9c3", border: "1px solid #fde047", borderRadius: 8, padding: "12px 20px", marginBottom: 20, fontWeight: 600, color: "#854d0e", fontSize: 14 }}>
          Tender awarded to <strong>{awardedTo}</strong>. Emails have been sent to all vendors.
        </div>
      )}

      {/* Escalation alerts */}
      {pendingEscalations.length > 0 && (
        <div style={{ background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 8, padding: 16, marginBottom: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#ea580c", marginBottom: 10 }}>⚠ Action Required — {pendingEscalations.length} Escalation{pendingEscalations.length > 1 ? "s" : ""}</h3>
          {pendingEscalations.map(e => {
            const isDifferentiator = e.reason?.startsWith("Vendor differentiator:");
            return (
              <div key={e.id} style={{
                background: "#fff",
                border: `1px solid ${isDifferentiator ? "#c4b5fd" : "#fed7aa"}`,
                borderRadius: 6, padding: 12, marginBottom: 8,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  {isDifferentiator && (
                    <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 99, background: "#ede9fe", color: "#7c3aed", border: "1px solid #c4b5fd" }}>
                      DIFFERENTIATOR CLAIM
                    </span>
                  )}
                  <span style={{ fontSize: 13, fontWeight: 500 }}>{e.reason}</span>
                </div>
                {isDifferentiator && (
                  <div style={{ fontSize: 12, color: "#7c3aed", background: "#f5f3ff", borderRadius: 4, padding: "6px 10px", marginBottom: 8 }}>
                    Vendor is asserting a unique advantage the bot cannot verify. Review and decide whether it justifies accepting their terms or excluding them.
                  </div>
                )}
                <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8 }}>{e.context_summary}</div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={() => resolveEscalation(e.id, "proceed")} style={{ padding: "4px 12px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: 12 }}>
                    {isDifferentiator ? "Proceed Anyway" : "Continue Negotiation"}
                  </button>
                  <button onClick={() => resolveEscalation(e.id, "accept")} style={{ padding: "4px 12px", background: "#059669", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: 12 }}>Accept Current Terms</button>
                  <button onClick={() => resolveEscalation(e.id, "reject")} style={{ padding: "4px 12px", background: "#dc2626", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: 12 }}>Reject</button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Live table */}
      <div style={{ background: "#fff", borderRadius: 10, border: "1px solid #e5e7eb", overflow: "hidden", marginBottom: 24 }}>
        <div style={{ padding: "14px 20px", borderBottom: "1px solid #f3f4f6" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <span style={{ fontWeight: 600, fontSize: 14, color: "#374151" }}>Vendor Negotiations</span>
            <span style={{ fontSize: 12, color: "#9ca3af" }}>Auto-refreshes every 5s</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span style={{ fontSize: 12, color: "#6b7280", fontWeight: 500 }}>Sort by:</span>
            {(["P1", "P2", "P3"] as const).map(slot => {
              const c = P_COLORS[slot];
              const selected = priorityDim[slot] ?? "";
              return (
                <div key={slot} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 7px", borderRadius: 99, background: c.bg, color: c.text, border: `1px solid ${c.border}` }}>{slot}</span>
                  <select
                    value={selected}
                    onChange={e => {
                      const dim = e.target.value as DimKey | "";
                      setPriorityDim(prev => {
                        const next = { ...prev };
                        // remove this dim from any other slot
                        for (const s of ["P1", "P2", "P3"] as const) {
                          if (next[s] === dim && s !== slot) delete next[s];
                        }
                        if (dim) next[slot] = dim;
                        else delete next[slot];
                        return next;
                      });
                    }}
                    style={{ fontSize: 12, border: "1px solid #e5e7eb", borderRadius: 6, padding: "3px 6px", background: "#fff", cursor: "pointer", color: selected ? "#1e293b" : "#9ca3af" }}
                  >
                    <option value="">— none</option>
                    {DIMS.map(d => <option key={d.key} value={d.key}>{d.label}</option>)}
                  </select>
                </div>
              );
            })}
            {hasSort && (
              <button onClick={() => setPriorityDim({})} style={{ fontSize: 11, color: "#6b7280", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>
                clear
              </button>
            )}
          </div>
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#f8fafc", fontSize: 12, color: "#6b7280", fontWeight: 600 }}>
              {["Vendor", "Status", "Strategy", "Spec", "Price", "Delivery", "Payment", "Warranty", "Original", "Current Offer", "Savings", "Rounds", "Action"].map(h => (
                <th key={h} style={{ padding: "10px 14px", textAlign: "left", borderBottom: "1px solid #f3f4f6", whiteSpace: "nowrap" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedVendors.length === 0 ? (
              <tr><td colSpan={13} style={{ padding: "32px 0", textAlign: "center", color: "#9ca3af", fontSize: 14 }}>No vendors yet</td></tr>
            ) : sortedVendors.map((vs, rank) => (
              <tr key={vs.id} style={{ borderBottom: "1px solid #f8fafc", fontSize: 13 }}>
                <td style={{ padding: "12px 14px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    {hasSort && (
                      <span style={{ fontSize: 10, fontWeight: 700, background: "#1e3a5f", color: "#fff", borderRadius: 99, padding: "1px 6px", minWidth: 18, textAlign: "center" }}>#{rank + 1}</span>
                    )}
                    <span style={{ fontWeight: 600, color: "#1e293b" }}>{vs.vendor_company || "—"}</span>
                  </div>
                  <div style={{ fontSize: 11, color: "#9ca3af" }}>{vs.vendor_email}</div>
                  {vs.has_pending_escalation && <div style={{ fontSize: 10, color: "#ea580c", fontWeight: 700 }}>⚠ ESCALATED</div>}
                </td>
                <td style={{ padding: "12px 14px" }}><Badge status={vs.status} /></td>
                <td style={{ padding: "12px 14px", fontSize: 11, color: "#6b7280" }}>{STRATEGY_LABELS[vs.strategy || ""] || "—"}</td>
                <td style={{ padding: "12px 14px" }}>
                  {vs.spec_score != null ? (
                    <span style={{ color: vs.spec_score >= 90 ? "#059669" : vs.spec_score >= 70 ? "#d97706" : "#dc2626", fontWeight: 600 }}>
                      {vs.spec_score.toFixed(0)}%
                    </span>
                  ) : "—"}
                </td>
                {([
                  {
                    key: "price_score" as const,
                    val: () => { const v = vs.current_offer?.["price"] ?? vs.quoted_price; return v != null ? Number(v).toLocaleString() : null; },
                  },
                  {
                    key: "delivery_score" as const,
                    val: () => { const v = vs.current_offer?.["delivery_days"] ?? vs.quoted_delivery_days; return v != null ? `${v}d` : null; },
                  },
                  {
                    key: "payment_score" as const,
                    val: () => { const v = vs.current_offer?.["payment_days"] ?? vs.quoted_payment_days; return v != null ? `Net-${v}` : null; },
                  },
                  {
                    key: "warranty_score" as const,
                    val: () => { const v = vs.current_offer?.["warranty_months"] ?? vs.quoted_warranty_months; return v != null ? `${v}mo` : null; },
                  },
                ]).map(({ key, val }) => {
                  const score = vs[key];
                  const numVal = val();
                  return (
                    <td key={key} style={{ padding: "12px 14px" }}>
                      {score != null ? (
                        <div>
                          <div style={{ color: score >= 80 ? "#059669" : score >= 50 ? "#d97706" : "#dc2626", fontWeight: 700, fontSize: 13 }}>
                            {score.toFixed(0)}%
                          </div>
                          {numVal && <div style={{ fontSize: 11, color: "#6b7280", marginTop: 1 }}>{numVal}</div>}
                        </div>
                      ) : "—"}
                    </td>
                  );
                })}
                <td style={{ padding: "12px 14px", color: "#6b7280" }}>
                  {vs.quoted_price != null ? `${vs.quoted_currency} ${vs.quoted_price.toFixed(2)}` : "—"}
                </td>
                <td style={{ padding: "12px 14px", fontWeight: 600, color: "#1e293b" }}>
                  {vs.current_offer?.price != null ? `${vs.quoted_currency} ${Number(vs.current_offer.price).toFixed(2)}` : "—"}
                </td>
                <td style={{ padding: "12px 14px", color: "#059669", fontWeight: 600 }}>
                  {savingsPct(vs.quoted_price, vs.current_offer?.price)}
                </td>
                <td style={{ padding: "12px 14px", color: "#6b7280" }}>{vs.round_count}</td>
                <td style={{ padding: "12px 14px" }}>
                  <button onClick={() => openChat(vs)}
                    style={{ fontSize: 12, padding: "4px 10px", background: "#eff6ff", color: "#2563eb", border: "none", borderRadius: 4, cursor: "pointer", fontWeight: 500 }}>
                    View Chat
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Award modal */}
      {showAward && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
          <div style={{ background: "#fff", borderRadius: 12, width: "100%", maxWidth: 620, maxHeight: "90vh", overflowY: "auto", boxShadow: "0 20px 60px rgba(0,0,0,0.25)" }}>
            <div style={{ padding: "20px 24px", borderBottom: "1px solid #e5e7eb", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <h2 style={{ fontSize: 17, fontWeight: 700, color: "#1e3a5f", margin: 0 }}>Close &amp; Award Tender</h2>
                <p style={{ fontSize: 13, color: "#6b7280", margin: "4px 0 0" }}>Select the winning vendor and provide a decision explanation.</p>
              </div>
              <button onClick={() => { setShowAward(false); setAwardErr(""); }} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "#6b7280" }}>✕</button>
            </div>

            <div style={{ padding: "20px 24px" }}>
              <p style={{ fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 10 }}>Select winning vendor:</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
                {vendors.filter(v => v.status !== "rejected" && v.status !== "pending_qualification").map(v => {
                  const offer = v.current_offer || {};
                  const price = offer["price"] ?? v.quoted_price;
                  const isSelected = awardVsId === v.id;
                  return (
                    <label key={v.id} style={{
                      display: "flex", alignItems: "center", gap: 12, padding: "12px 14px",
                      border: `2px solid ${isSelected ? "#1e3a5f" : "#e5e7eb"}`,
                      borderRadius: 8, cursor: "pointer",
                      background: isSelected ? "#eff6ff" : "#fafafa",
                    }}>
                      <input type="radio" name="award_vendor" value={v.id} checked={isSelected} onChange={() => setAwardVsId(v.id)} style={{ accentColor: "#1e3a5f" }} />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, color: "#1e293b", fontSize: 14 }}>{v.vendor_company || v.vendor_email}</div>
                        <div style={{ fontSize: 12, color: "#6b7280" }}>{v.vendor_email}</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>
                          {price != null ? `${v.quoted_currency} ${Number(price).toLocaleString()}` : "—"}
                        </div>
                        <div style={{ marginTop: 2 }}><Badge status={v.status} /></div>
                      </div>
                      {v.price_score != null && (
                        <div style={{ textAlign: "center", minWidth: 44 }}>
                          <div style={{ fontSize: 13, fontWeight: 700, color: v.price_score >= 80 ? "#059669" : v.price_score >= 50 ? "#d97706" : "#dc2626" }}>
                            {v.price_score.toFixed(0)}%
                          </div>
                          <div style={{ fontSize: 10, color: "#9ca3af" }}>score</div>
                        </div>
                      )}
                    </label>
                  );
                })}
              </div>

              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 }}>
                Award decision &amp; explanation <span style={{ color: "#dc2626" }}>*</span>
              </label>
              <textarea
                value={awardExplanation}
                onChange={e => setAwardExplanation(e.target.value)}
                placeholder="e.g. Selected based on competitive pricing, strong delivery commitment, and ISO 9001 certification. This vendor demonstrated the best overall value for our requirements."
                style={{ width: "100%", minHeight: 100, padding: "8px 10px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 13, resize: "vertical", boxSizing: "border-box", marginBottom: 12 }}
              />

              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#374151", cursor: "pointer", marginBottom: 16 }}>
                <input type="checkbox" checked={shareExplanation} onChange={e => setShareExplanation(e.target.checked)} style={{ accentColor: "#1e3a5f" }} />
                Share this explanation with unsuccessful vendors in their notification email
              </label>

              {awardErr && (
                <div style={{ background: "#fee2e2", color: "#dc2626", padding: "8px 12px", borderRadius: 6, fontSize: 13, marginBottom: 12 }}>
                  {awardErr}
                </div>
              )}

              <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
                <button onClick={() => { setShowAward(false); setAwardErr(""); }} style={{ padding: "8px 18px", background: "transparent", color: "#6b7280", border: "1px solid #d1d5db", borderRadius: 6, cursor: "pointer", fontWeight: 500, fontSize: 14 }}>
                  Cancel
                </button>
                <button onClick={submitAward} disabled={awarding} style={{ padding: "8px 20px", background: "#1e3a5f", color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, cursor: "pointer", fontSize: 14 }}>
                  {awarding ? "Awarding…" : "Award Tender & Send Emails →"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Chat drawer */}
      {selectedVs && (
        <div style={{ background: "#fff", borderRadius: 10, border: "1px solid #e5e7eb", overflow: "hidden" }}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid #f3f4f6", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>
              Chat: {selectedVs.vendor_company || selectedVs.vendor_email}
              <span style={{ marginLeft: 8 }}><Badge status={selectedVs.status} /></span>
            </span>
            <button onClick={() => setSelectedVs(null)} style={{ background: "none", border: "none", fontSize: 18, cursor: "pointer", color: "#6b7280" }}>✕</button>
          </div>
          <div style={{ maxHeight: 480, overflowY: "auto", padding: 20 }}>
            {loadingMsgs ? <p style={{ color: "#6b7280" }}>Loading…</p> : messages.length === 0 ? (
              <p style={{ color: "#9ca3af", fontSize: 13 }}>No messages yet. The chat will begin when the vendor opens their invitation link.</p>
            ) : messages.map(m => (
              <div key={m.id} style={{ marginBottom: 16, display: "flex", justifyContent: m.role === "assistant" ? "flex-start" : "flex-end" }}>
                <div style={{
                  maxWidth: "75%", padding: "10px 14px", borderRadius: 10, fontSize: 13, lineHeight: 1.55,
                  background: m.role === "assistant" ? "#f0f9ff" : "#1e3a5f",
                  color: m.role === "assistant" ? "#1e293b" : "#fff",
                  borderBottomLeftRadius: m.role === "assistant" ? 2 : 10,
                  borderBottomRightRadius: m.role === "vendor" ? 2 : 10,
                }}>
                  <div style={{ fontSize: 10, marginBottom: 4, opacity: 0.6, fontWeight: 600 }}>
                    {m.role === "assistant" ? "🤖 BOT" : "🏢 VENDOR"} · Round {m.round_number}
                  </div>
                  {m.content}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
