import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ChatOut, Message, VendorSession } from "../api";

export default function VendorChatPage() {
  const { vsid } = useParams<{ vsid: string }>();
  const nav = useNavigate();

  const [session, setSession] = useState<VendorSession | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [currentOffer, setCurrentOffer] = useState<Record<string, number | null> | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    async function init() {
      try {
        const sessions = await api.listVendorNegotiations();
        const vs = sessions.find(s => s.id === Number(vsid));
        if (!vs) { setErr("Negotiation not found"); setLoading(false); return; }
        setSession(vs);
        setCurrentOffer(vs.current_offer);
        if (vs.current_state === "not_started") {
          const openMsg = await api.vendorAccountStart(Number(vsid));
          setMessages([openMsg]);
        } else {
          const msgs = await api.vendorAccountMessages(Number(vsid));
          setMessages(msgs);
        }
      } catch (e: unknown) {
        setErr(e instanceof Error ? e.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    }
    init();
  }, [vsid]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput("");
    setSending(true);
    setErr("");

    const userMsg: Message = { id: Date.now(), role: "vendor", content: text, round_number: 0, created_at: new Date().toISOString() };
    setMessages(m => [...m, userMsg]);

    try {
      const result: ChatOut = await api.vendorAccountChat(Number(vsid), text);
      const botMsg: Message = { id: Date.now() + 1, role: "assistant", content: result.reply, round_number: result.round_count, created_at: new Date().toISOString() };
      setMessages(m => [...m, botMsg]);
      if (result.current_offer) setCurrentOffer(result.current_offer);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Error sending message");
    } finally {
      setSending(false);
    }
  }

  const isClosed = session?.status === "closed";

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "80vh", color: "#6b7280" }}>
      Loading negotiation…
    </div>
  );

  if (err && !session) return (
    <div style={{ maxWidth: 500, margin: "80px auto", textAlign: "center" }}>
      <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
      <h2 style={{ color: "#dc2626", marginBottom: 8 }}>Not Found</h2>
      <p style={{ color: "#6b7280", marginBottom: 20 }}>{err}</p>
      <button onClick={() => nav("/vendor")} style={{ padding: "8px 20px", background: "#1e3a5f", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}>← Back to Dashboard</button>
    </div>
  );

  return (
    <div style={{ display: "flex", height: "calc(100vh - 56px)", overflow: "hidden" }}>
      {/* Sidebar */}
      <div style={{ width: 280, background: "#1e3a5f", color: "#fff", padding: 24, flexShrink: 0, overflowY: "auto" }}>
        <button onClick={() => nav("/vendor")} style={{ background: "none", border: "none", color: "rgba(255,255,255,0.6)", cursor: "pointer", fontSize: 13, marginBottom: 20, padding: 0 }}>
          ← My Negotiations
        </button>

        <div style={{ fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.5)", marginBottom: 8, letterSpacing: 1 }}>NEGOTIATION</div>
        {session && (
          <>
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>{session.vendor_company || "Negotiation"}</div>
              <div style={{ marginTop: 6, display: "inline-block", padding: "2px 10px", borderRadius: 99, fontSize: 11, fontWeight: 700, background: "rgba(255,255,255,0.1)" }}>
                {session.status.toUpperCase()}
              </div>
            </div>

            <div style={{ fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.5)", marginBottom: 8, letterSpacing: 1 }}>YOUR QUOTE</div>
            <div style={{ marginBottom: 20, fontSize: 13 }}>
              <Row label="Price" value={session.quoted_price != null ? `${session.quoted_currency} ${Number(session.quoted_price).toFixed(2)}` : "—"} />
              <Row label="Delivery" value={`${session.quoted_delivery_days ?? "—"} days`} />
              <Row label="Payment" value={`Net-${session.quoted_payment_days ?? "—"}`} />
              <Row label="Warranty" value={session.quoted_warranty_months ? `${session.quoted_warranty_months} mo` : "—"} />
            </div>

            {currentOffer && Object.values(currentOffer).some(v => v != null) && (
              <>
                <div style={{ fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.5)", marginBottom: 8, letterSpacing: 1 }}>CURRENT OFFER</div>
                <div style={{ fontSize: 13 }}>
                  {currentOffer.price != null && <Row label="Price" value={`${session.quoted_currency} ${Number(currentOffer.price).toFixed(2)}`} highlight />}
                  {currentOffer.delivery_days != null && <Row label="Delivery" value={`${currentOffer.delivery_days} days`} />}
                  {currentOffer.payment_days != null && <Row label="Payment" value={`Net-${currentOffer.payment_days}`} />}
                </div>
              </>
            )}

            <div style={{ marginTop: 24, fontSize: 12, opacity: 0.5 }}>
              {session.round_count} round{session.round_count !== 1 ? "s" : ""} completed
            </div>
          </>
        )}
      </div>

      {/* Chat area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>
          {messages.map(m => (
            <div key={m.id} style={{ display: "flex", justifyContent: m.role === "assistant" ? "flex-start" : "flex-end" }}>
              <div style={{
                maxWidth: "70%", padding: "12px 16px", borderRadius: 12, fontSize: 14, lineHeight: 1.6,
                background: m.role === "assistant" ? "#fff" : "#1e3a5f",
                color: m.role === "assistant" ? "#1e293b" : "#fff",
                boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
                borderBottomLeftRadius: m.role === "assistant" ? 2 : 12,
                borderBottomRightRadius: m.role === "vendor" ? 2 : 12,
              }}>
                <div style={{ fontSize: 10, fontWeight: 700, marginBottom: 6, opacity: 0.55 }}>
                  {m.role === "assistant" ? "🤖 NEGOTIATION BOT" : "YOU"} · {new Date(m.created_at).toLocaleTimeString()}
                </div>
                <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
              </div>
            </div>
          ))}

          {err && <div style={{ background: "#fee2e2", color: "#dc2626", padding: "8px 12px", borderRadius: 6, fontSize: 13 }}>{err}</div>}
          <div ref={bottomRef} />
        </div>

        {!isClosed ? (
          <div style={{ padding: "16px 24px", background: "#fff", borderTop: "1px solid #e5e7eb", display: "flex", gap: 12 }}>
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), send())}
              placeholder="Type your response…"
              disabled={sending}
              style={{ flex: 1, padding: "10px 14px", border: "1px solid #d1d5db", borderRadius: 8, fontSize: 14, outline: "none" }}
            />
            <button onClick={send} disabled={sending || !input.trim()}
              style={{ padding: "10px 20px", background: sending ? "#9ca3af" : "#1e3a5f", color: "#fff", border: "none", borderRadius: 8, fontWeight: 600, cursor: sending ? "not-allowed" : "pointer", fontSize: 14 }}>
              {sending ? "…" : "Send"}
            </button>
          </div>
        ) : (
          <div style={{ padding: "16px 24px", background: "#f9fafb", borderTop: "1px solid #e5e7eb", textAlign: "center", fontSize: 13, color: "#6b7280" }}>
            This negotiation is closed. The buyer will be in touch with the final decision.
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
      <span style={{ opacity: 0.6 }}>{label}</span>
      <span style={{ fontWeight: highlight ? 700 : 500, color: highlight ? "#4ade80" : undefined }}>{value}</span>
    </div>
  );
}
