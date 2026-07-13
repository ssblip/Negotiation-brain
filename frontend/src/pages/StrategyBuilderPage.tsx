import { useEffect, useState } from "react";
import { api } from "../api";

const SECTIONS = [
  {
    key: "Core Principles",
    description: "Tone, style, and ground rules the bot applies in every conversation.",
  },
  {
    key: "Price & Concession Rules",
    description: "How to handle price anchors, guesses, counter-offers, and concession sequencing.",
  },
  {
    key: "Behavioral Scenarios",
    description: "How the bot responds to specific vendor tactics (anchoring, urgency, bundling, sole-source claims, etc.).",
  },
  {
    key: "Company-Specific Rules",
    description: "Free-form rules unique to your organisation — payment terms, currencies, ESG requirements, approval thresholds.",
  },
];

export default function StrategyBuilderPage() {
  const [sections, setSections] = useState<Record<string, string>>({});
  const [isCustomised, setIsCustomised] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState("");
  const [expanded, setExpanded] = useState<string | null>(SECTIONS[0].key);

  useEffect(() => {
    api.getStrategySections()
      .then(res => {
        setSections(res.sections);
        setIsCustomised(res.is_customised);
      })
      .catch(() => setErr("Failed to load strategy."))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    setSaving(true); setSaved(false); setErr("");
    try {
      await api.saveStrategySections(sections);
      setIsCustomised(true);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    if (!confirm("Reset all sections to default values? Your customisations will be lost.")) return;
    api.saveStrategySections({}).then(() => {
      setLoading(true);
      api.getStrategySections().then(res => {
        setSections(res.sections);
        setIsCustomised(false);
        setLoading(false);
      });
    });
  }

  if (loading) return (
    <div style={{ maxWidth: 800, margin: "80px auto", textAlign: "center", color: "#6b7280" }}>
      Loading strategy…
    </div>
  );

  return (
    <div style={{ maxWidth: 800, margin: "0 auto", padding: "32px 16px" }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: "#1e3a5f", margin: 0 }}>
              Strategy Builder
            </h1>
            <p style={{ fontSize: 13, color: "#6b7280", marginTop: 6 }}>
              Define exactly how the AI bot negotiates on your behalf. These rules apply to all your negotiations.
            </p>
          </div>
          <span style={{
            fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 99,
            background: isCustomised ? "#d1fae5" : "#fef3c7",
            color: isCustomised ? "#065f46" : "#92400e",
          }}>
            {isCustomised ? "Custom strategy active" : "Using defaults"}
          </span>
        </div>

        <div style={{ marginTop: 12, padding: "10px 14px", background: "#f0f9ff", border: "1px solid #bae6fd", borderRadius: 8, fontSize: 13, color: "#0369a1" }}>
          <strong>How this works:</strong> Each section below becomes part of the AI bot's instructions. Edit the text to match your company's procurement policy — be specific. The bot reads this verbatim before every negotiation.
        </div>
      </div>

      {err && (
        <div style={{ background: "#fee2e2", color: "#dc2626", padding: "8px 12px", borderRadius: 6, marginBottom: 16, fontSize: 13 }}>{err}</div>
      )}

      {/* Sections */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 24 }}>
        {SECTIONS.map(s => {
          const isOpen = expanded === s.key;
          return (
            <div key={s.key} style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden" }}>
              <button
                onClick={() => setExpanded(isOpen ? null : s.key)}
                style={{
                  width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "14px 18px", background: isOpen ? "#f8fafc" : "#fff",
                  border: "none", cursor: "pointer", textAlign: "left",
                  borderBottom: isOpen ? "1px solid #e5e7eb" : "none",
                }}
              >
                <div>
                  <div style={{ fontWeight: 700, fontSize: 14, color: "#1e3a5f" }}>{s.key}</div>
                  <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>{s.description}</div>
                </div>
                <span style={{ fontSize: 18, color: "#9ca3af", flexShrink: 0, marginLeft: 12 }}>
                  {isOpen ? "▲" : "▼"}
                </span>
              </button>

              {isOpen && (
                <div style={{ padding: "14px 18px" }}>
                  <textarea
                    value={sections[s.key] || ""}
                    onChange={e => setSections(prev => ({ ...prev, [s.key]: e.target.value }))}
                    rows={8}
                    style={{
                      width: "100%", padding: "10px 12px", border: "1px solid #d1d5db",
                      borderRadius: 6, fontSize: 13, lineHeight: 1.6, resize: "vertical",
                      fontFamily: "inherit", boxSizing: "border-box", color: "#374151",
                    }}
                  />
                  <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 4 }}>
                    {(sections[s.key] || "").split("\n").filter(Boolean).length} lines
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <button
          onClick={handleSave}
          disabled={saving}
          style={{ padding: "10px 24px", background: "#1e3a5f", color: "#fff", border: "none", borderRadius: 6, fontWeight: 700, cursor: "pointer", fontSize: 14 }}
        >
          {saving ? "Saving…" : "Save Strategy"}
        </button>
        <button
          onClick={handleReset}
          style={{ padding: "10px 18px", background: "transparent", color: "#6b7280", border: "1px solid #d1d5db", borderRadius: 6, fontWeight: 500, cursor: "pointer", fontSize: 14 }}
        >
          Reset to Defaults
        </button>
        {saved && (
          <span style={{ fontSize: 13, color: "#059669", fontWeight: 600 }}>✓ Strategy saved — active on all new negotiations</span>
        )}
      </div>
    </div>
  );
}
