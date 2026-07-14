import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, VendorQuote, VendorSession } from "../api";

const card: React.CSSProperties = { background: "#fff", borderRadius: 10, padding: 28, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", border: "1px solid #e5e7eb", marginBottom: 20 };
const label: React.CSSProperties = { display: "block", marginBottom: 4, fontSize: 13, fontWeight: 500, color: "#374151" };
const input: React.CSSProperties = { width: "100%", padding: "7px 10px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14, marginBottom: 12 };
const h3: React.CSSProperties = { fontSize: 15, fontWeight: 700, color: "#1e3a5f", marginBottom: 16 };
const btn: React.CSSProperties = { padding: "8px 18px", background: "#1e3a5f", color: "#fff", border: "none", borderRadius: 6, fontWeight: 600, cursor: "pointer", fontSize: 14 };
const btnGhost: React.CSSProperties = { ...btn, background: "transparent", color: "#1e3a5f", border: "1px solid #1e3a5f" };
const btnBack: React.CSSProperties = { padding: "8px 14px", background: "transparent", color: "#6b7280", border: "1px solid #d1d5db", borderRadius: 6, fontWeight: 500, cursor: "pointer", fontSize: 14 };

type Step = "basics" | "targets" | "quotes" | "review";
const STEPS: Step[] = ["basics", "targets", "quotes", "review"];
const STEP_LABELS = ["Basics", "Set Targets", "Upload Quotes", "Qualify & Send"];

export default function NewNegotiationPage() {
  const nav = useNavigate();
  const [searchParams] = useSearchParams();
  const resumeId = searchParams.get("resume");

  const [step, setStep] = useState<Step>("basics");
  const [negId, setNegId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [resumeLoading, setResumeLoading] = useState(!!resumeId);
  const [err, setErr] = useState("");
  const [activeVendorTab, setActiveVendorTab] = useState(0);
  const [vendorSessions, setVendorSessions] = useState<VendorSession[]>([]);
  const [overridingVsid, setOverridingVsid] = useState<number | null>(null);

  // Step 1 — Basics
  const [basics, setBasics] = useState({ title: "", item: "", quantity: 1, currency: "USD" });

  // Step 3 — Quote files + parsed vendors
  const [quoteFiles, setQuoteFiles] = useState<File[]>([]);
  const [vendors, setVendors] = useState<VendorQuote[]>([]);
  const [parsing, setParsing] = useState(false);

  // Step 3 — Targets
  const [targets, setTargets] = useState({
    target_price: "", target_delivery_days: "",
    target_payment_days: "", warranty_months_target: "",
  });

  type CustomSpec = { name: string; field_type: string; required_value: string; weight: string; unit: string; mandatory: boolean };
  const BLANK_SPEC: CustomSpec = { name: "", field_type: "NUM", required_value: "", weight: "1", unit: "", mandatory: false };
  const [customSpecs, setCustomSpecs] = useState<CustomSpec[]>([]);

  function setT(k: string) { return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setTargets(t => ({ ...t, [k]: e.target.value })); }
  function setSpec(idx: number, k: keyof CustomSpec, v: string | boolean) {
    setCustomSpecs(ss => ss.map((s, i) => i === idx ? { ...s, [k]: v } : s));
  }

  // On mount, if resuming an existing draft, load its data and jump to right step
  useEffect(() => {
    if (!resumeId) return;
    const id = Number(resumeId);
    if (isNaN(id)) return;

    (async () => {
      setResumeLoading(true);
      try {
        const neg = await api.getNegotiation(id);
        setNegId(neg.id);
        setBasics({ title: neg.title, item: neg.item, quantity: neg.quantity, currency: neg.currency });

        const [existingVendors, existingTargets] = await Promise.all([
          api.listVendors(id).catch(() => []),
          api.getTargets(id).catch(() => null),
        ]);

        if (existingVendors.length > 0) {
          setVendorSessions(existingVendors);
          setVendors(existingVendors.map(vs => ({
            vendor_email: vs.vendor_email,
            vendor_company: vs.vendor_company,
            vendor_name: vs.vendor_name,
            quoted_price: vs.quoted_price,
            quoted_delivery_days: vs.quoted_delivery_days,
            quoted_payment_days: vs.quoted_payment_days,
            quoted_warranty_months: vs.quoted_warranty_months,
            quoted_currency: vs.quoted_currency,
            custom_spec_values: null,
          })));
        }

        if (existingTargets) {
          setTargets({
            target_price: existingTargets.target_price?.toString() ?? "",
            target_delivery_days: existingTargets.target_delivery_days?.toString() ?? "",
            target_payment_days: existingTargets.target_payment_days?.toString() ?? "",
            warranty_months_target: existingTargets.warranty_months_target?.toString() ?? "",
          });
          if (existingTargets.custom_specs?.length) {
            setCustomSpecs(existingTargets.custom_specs.map((s: { name: string; field_type: string; required_value: unknown; weight: number; unit: string | null; mandatory?: boolean }) => ({
              name: s.name,
              field_type: s.field_type,
              required_value: String(s.required_value ?? ""),
              weight: String(s.weight ?? 1),
              unit: s.unit ?? "",
              mandatory: s.mandatory ?? false,
            })));
          }
          setStep("review");
        } else if (existingTargets) {
          setStep("quotes");
        } else {
          setStep("targets");
        }
      } catch {
        setErr("Could not load draft negotiation.");
      } finally {
        setResumeLoading(false);
      }
    })();
  }, [resumeId]);

  const stepIdx = STEPS.indexOf(step);

  function goBack() {
    setErr("");
    const prev = STEPS[stepIdx - 1];
    if (prev) setStep(prev);
  }

  async function handleBasics() {
    if (!basics.title || !basics.item) return setErr("Title and item are required");
    setLoading(true); setErr("");
    try {
      let id = negId;
      if (id) {
        await api.updateNegotiation(id, { ...basics, quantity: Number(basics.quantity) });
      } else {
        const neg = await api.createNegotiation({ ...basics, quantity: Number(basics.quantity) });
        id = neg.id;
        setNegId(id);
      }
      setStep("targets");
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }

  async function handleParseQuotes() {
    if (quoteFiles.length === 0 || !negId) return setErr("Please select at least one file");
    setParsing(true); setErr("");
    try {
      const result = await api.parseQuotes(negId, quoteFiles);
      console.log("Parsed vendors:", JSON.stringify(result.vendors, null, 2));
      setVendors(result.vendors.map(v => ({ ...v, vendor_email: v.vendor_email || "" })));
      setParsing(false);
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Parse failed"); setParsing(false); }
  }

  function updateVendor(idx: number, field: keyof VendorQuote, value: string | number | null) {
    setVendors(vs => vs.map((v, i) => i === idx ? { ...v, [field]: value } : v));
  }

  function updateVendorSpec(idx: number, key: string, value: string) {
    setVendors(vs => vs.map((v, i) => i === idx
      ? { ...v, custom_spec_values: { ...(v.custom_spec_values || {}), [key]: value } }
      : v));
  }

  function getSpec(v: VendorQuote, key: string): string {
    return (v.custom_spec_values as Record<string, string> | null)?.[key] ?? "";
  }

  async function handleQuotesDone() {
    if (!negId || vendors.length === 0) return setErr("Add at least one vendor");
    setLoading(true); setErr("");
    try {
      await api.addVendors(negId, vendors);
      const sessions = await api.listVendors(negId);
      setVendorSessions(sessions);
      setStep("review");
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }

  async function handleQualificationOverride(vsid: number, include: boolean) {
    if (!negId || overridingVsid !== null) return;
    const snapshot = vendorSessions.find(s => s.id === vsid);

    // Optimistic update — instant UI response
    setVendorSessions(ss => ss.map(s => {
      if (s.id !== vsid) return s;
      return {
        ...s,
        buyer_override: include,
        status: include ? "invited" : (s.mandatory_failures?.length ? "rejected" : s.status),
      };
    }));
    setOverridingVsid(vsid);

    try {
      const updated = await api.overrideVendorQualification(negId, vsid, include);
      setVendorSessions(ss => ss.map(s => s.id === vsid ? updated : s));
    } catch (e: unknown) {
      if (snapshot) setVendorSessions(ss => ss.map(s => s.id === vsid ? snapshot : s));
      setErr(e instanceof Error ? e.message : "Error");
    } finally {
      setOverridingVsid(null);
    }
  }

  async function handleTargets() {
    if (!negId) return;
    setLoading(true); setErr("");
    try {
      const num = (v: string) => v ? Number(v) : null;
      await api.setTargets(negId, {
        target_price: num(targets.target_price),
        target_delivery_days: num(targets.target_delivery_days),
        target_payment_days: num(targets.target_payment_days),
        warranty_months_target: num(targets.warranty_months_target),
        custom_specs: customSpecs
          .filter(s => s.name.trim())
          .map(s => ({
            name: s.name.trim(),
            field_type: s.field_type,
            required_value: s.field_type === "NUM" || s.field_type === "PCTNUM"
              ? Number(s.required_value)
              : s.field_type === "BOOL"
              ? s.required_value.toLowerCase() === "true"
              : s.required_value,
            weight: Number(s.weight) || 1,
            unit: s.unit || null,
            mandatory: s.mandatory,
          })),
      });
      setStep("quotes");
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }

  async function handleSend() {
    if (!negId) return;
    setLoading(true); setErr("");
    try {
      const res = await api.sendInvitations(negId);
      alert(`✓ Invitations sent to ${res.sent} vendors!`);
      nav(`/negotiations/${negId}`);
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }

  if (resumeLoading) {
    return (
      <div style={{ maxWidth: 760, margin: "0 auto", padding: "80px 16px", textAlign: "center", color: "#6b7280" }}>
        Loading draft…
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: "32px 16px" }}>
      <div style={{ marginBottom: 24, display: "flex", alignItems: "center", gap: 12 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "#1e3a5f" }}>
          {resumeId ? "Continue Negotiation Setup" : "New Negotiation"}
        </h1>
        {resumeId && (
          <span style={{ fontSize: 12, background: "#fef3c7", color: "#92400e", padding: "2px 8px", borderRadius: 99, fontWeight: 600 }}>
            DRAFT
          </span>
        )}
      </div>

      {/* Step indicator */}
      <div style={{ display: "flex", gap: 0, marginBottom: 32 }}>
        {STEP_LABELS.map((l, i) => (
          <div key={l} style={{ flex: 1, textAlign: "center" }}>
            <div style={{ height: 4, background: i <= stepIdx ? "#1e3a5f" : "#e5e7eb", marginBottom: 6, borderRadius: 2 }} />
            <span style={{ fontSize: 11, color: i <= stepIdx ? "#1e3a5f" : "#9ca3af", fontWeight: i === stepIdx ? 700 : 400 }}>{l}</span>
          </div>
        ))}
      </div>

      {err && <div style={{ background: "#fee2e2", color: "#dc2626", padding: "8px 12px", borderRadius: 6, marginBottom: 16, fontSize: 14 }}>{err}</div>}

      {/* Step 1: Basics */}
      {step === "basics" && (
        <div style={card}>
          <h3 style={h3}>Negotiation Basics</h3>
          <label style={label}>Negotiation Title</label>
          <input style={input} value={basics.title} onChange={e => setBasics(b => ({ ...b, title: e.target.value }))} placeholder="e.g. Steel Bolts Q3 2025" />
          <label style={label}>Item / Product</label>
          <input style={input} value={basics.item} onChange={e => setBasics(b => ({ ...b, item: e.target.value }))} placeholder="e.g. M8 Stainless Steel Bolts" />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={label}>Quantity</label>
              <input style={input} type="number" min={1} value={basics.quantity} onChange={e => setBasics(b => ({ ...b, quantity: Number(e.target.value) }))} />
            </div>
            <div>
              <label style={label}>Currency</label>
              <input style={input} value={basics.currency} onChange={e => setBasics(b => ({ ...b, currency: e.target.value }))} placeholder="USD" />
            </div>
          </div>
          <button style={{ ...btn, marginTop: 8 }} onClick={handleBasics} disabled={loading}>
            {loading ? "Saving…" : negId ? "Update & Continue →" : "Next →"}
          </button>
        </div>
      )}

      {/* Step 3: Upload RFQ responses */}
      {step === "quotes" && (
        <div style={card}>
          <h3 style={h3}>Upload Vendor Quote Documents</h3>
          <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 16 }}>
            Upload one file per vendor, or a single document containing all quotes. AI will extract each vendor's data automatically.
          </p>
          <input
            type="file"
            accept=".pdf,.docx,.xlsx,.txt"
            multiple
            onChange={e => setQuoteFiles(Array.from(e.target.files || []))}
            style={{ marginBottom: 8 }}
          />
          {quoteFiles.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
              {quoteFiles.map((f, i) => (
                <span key={i} style={{ fontSize: 11, background: "#eff6ff", color: "#1d4ed8", border: "1px solid #bfdbfe", borderRadius: 99, padding: "2px 10px" }}>
                  {f.name}
                </span>
              ))}
            </div>
          )}
          <button style={{ ...btnGhost, marginBottom: 20 }} onClick={handleParseQuotes} disabled={parsing || quoteFiles.length === 0}>
            {parsing ? "Parsing with AI…" : `Parse ${quoteFiles.length > 1 ? `${quoteFiles.length} Documents` : "Document"}`}
          </button>

          {vendors.length > 0 && (
            <>
              <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: "#374151" }}>
                Found {vendors.length} vendor{vendors.length > 1 ? "s" : ""} — review details:
              </h4>

              {/* Vendor tabs */}
              <div style={{ display: "flex", gap: 0, borderBottom: "2px solid #e5e7eb", marginBottom: 0, flexWrap: "wrap" }}>
                {vendors.map((v, i) => (
                  <button key={i} onClick={() => setActiveVendorTab(i)} style={{
                    padding: "8px 16px", border: "none", background: "none", cursor: "pointer",
                    fontSize: 13, fontWeight: activeVendorTab === i ? 700 : 400,
                    color: activeVendorTab === i ? "#1e3a5f" : "#6b7280",
                    borderBottom: activeVendorTab === i ? "2px solid #1e3a5f" : "2px solid transparent",
                    marginBottom: -2, whiteSpace: "nowrap",
                  }}>
                    {v.vendor_company || `Vendor ${i + 1}`}
                  </button>
                ))}
                <button onClick={() => {
                  setVendors(vs => [...vs, { vendor_email: "", vendor_company: "", vendor_name: "", quoted_price: null, quoted_delivery_days: null, quoted_payment_days: null, quoted_warranty_months: null, quoted_currency: "USD", custom_spec_values: null }]);
                  setActiveVendorTab(vendors.length);
                }} style={{ padding: "8px 14px", border: "none", background: "none", cursor: "pointer", fontSize: 13, color: "#2563eb", marginBottom: -2 }}>
                  + Add Vendor
                </button>
              </div>

              {/* Active vendor panel */}
              {vendors.map((v, i) => {
                if (i !== activeVendorTab) return null;
                const sec: React.CSSProperties = { fontSize: 11, fontWeight: 700, color: "#1e3a5f", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10, marginTop: 20, paddingBottom: 6, borderBottom: "1px solid #e5e7eb" };
                return (
                  <div key={i} style={{ border: "1px solid #e5e7eb", borderTop: "none", borderRadius: "0 0 8px 8px", padding: 20, marginBottom: 16 }}>

                    {/* Identity */}
                    <div style={sec}>Identity</div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                      <div>
                        <label style={label}>Company Name</label>
                        <input style={input} value={v.vendor_company || ""} onChange={e => updateVendor(i, "vendor_company", e.target.value)} placeholder="e.g. Apex Tech Systems" />
                      </div>
                      <div>
                        <label style={{ ...label, color: "#dc2626" }}>Email Address *</label>
                        <input style={input} type="email" value={v.vendor_email} onChange={e => updateVendor(i, "vendor_email", e.target.value)} placeholder="vendor@company.com" />
                      </div>
                      <div style={{ gridColumn: "1 / -1" }}>
                        <label style={label}>Contact Name</label>
                        <input style={input} value={v.vendor_name || ""} onChange={e => updateVendor(i, "vendor_name", e.target.value)} placeholder="e.g. James Whitfield" />
                      </div>
                    </div>

                    {/* Price */}
                    <div style={sec}>Price</div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                      <div>
                        <label style={label}>Quoted Unit Price</label>
                        <input style={input} type="number" step="0.01" value={v.quoted_price ?? ""} onChange={e => updateVendor(i, "quoted_price", e.target.value ? Number(e.target.value) : null)} placeholder="e.g. 1480.00" />
                      </div>
                      <div>
                        <label style={label}>Currency</label>
                        <input style={input} value={v.quoted_currency} onChange={e => updateVendor(i, "quoted_currency", e.target.value)} placeholder="USD" />
                      </div>
                    </div>

                    {/* Delivery */}
                    <div style={sec}>Delivery</div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                      <div>
                        <label style={label}>Lead Time (days from PO)</label>
                        <input style={input} type="number" value={v.quoted_delivery_days ?? ""} onChange={e => updateVendor(i, "quoted_delivery_days", e.target.value ? Number(e.target.value) : null)} placeholder="e.g. 35" />
                      </div>
                      <div>
                        <label style={label}>Lead Time Variability</label>
                        <input style={input} value={getSpec(v, "lead_time_risk")} onChange={e => updateVendorSpec(i, "lead_time_risk", e.target.value)} placeholder="e.g. Subject to freight delays" />
                      </div>
                    </div>

                    {/* Payment Terms */}
                    <div style={sec}>Payment Terms</div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                      <div>
                        <label style={label}>Payment Terms (Net-X days)</label>
                        <input style={input} type="number" value={v.quoted_payment_days ?? ""} onChange={e => updateVendor(i, "quoted_payment_days", e.target.value ? Number(e.target.value) : null)} placeholder="e.g. 45" />
                      </div>
                      <div>
                        <label style={label}>Advance Payment Required</label>
                        <input style={input} value={getSpec(v, "advance_payment")} onChange={e => updateVendorSpec(i, "advance_payment", e.target.value)} placeholder="e.g. 30% upfront" />
                      </div>
                    </div>

                    {/* Warranty & SLA */}
                    <div style={sec}>Warranty & SLA</div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                      <div>
                        <label style={label}>Warranty Period (months)</label>
                        <input style={input} type="number" value={v.quoted_warranty_months ?? ""} onChange={e => updateVendor(i, "quoted_warranty_months", e.target.value ? Number(e.target.value) : null)} placeholder="e.g. 24" />
                      </div>
                    </div>

                    {/* Quality Deflection */}
                    <div style={sec}>Quality Deflection</div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                      <div>
                        <label style={label}>Certifications</label>
                        <input style={input} value={getSpec(v, "certifications")} onChange={e => updateVendorSpec(i, "certifications", e.target.value)} placeholder="e.g. ISO 9001, MIL-STD-810H, IP65" />
                      </div>
                      <div>
                        <label style={label}>Defect Rate (%)</label>
                        <input style={input} type="number" step="0.01" min="0" max="100" value={getSpec(v, "defect_rate")} onChange={e => updateVendorSpec(i, "defect_rate", e.target.value)} placeholder="e.g. 0.5" />
                      </div>
                      <div>
                        <label style={label}>Quality Standard</label>
                        <input style={input} value={getSpec(v, "quality_standard")} onChange={e => updateVendorSpec(i, "quality_standard", e.target.value)} placeholder="e.g. Six Sigma, AQL 1.0" />
                      </div>
                      <div>
                        <label style={label}>Inspection / Acceptance</label>
                        <input style={input} value={getSpec(v, "inspection_terms")} onChange={e => updateVendorSpec(i, "inspection_terms", e.target.value)} placeholder="e.g. Third-party QC accepted" />
                      </div>
                      <div style={{ gridColumn: "1 / -1" }}>
                        <label style={label}>Quality Deflection Notes</label>
                        <textarea style={{ ...input, height: 64, resize: "vertical" } as React.CSSProperties} value={getSpec(v, "quality_notes")} onChange={e => updateVendorSpec(i, "quality_notes", e.target.value)} placeholder="Known quality objections or deflection tactics observed in the quote…" />
                      </div>
                    </div>

                    {/* Buyer-defined custom specs */}
                    {customSpecs.length > 0 && (
                      <>
                        <div style={sec}>Buyer-Defined Specs</div>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                          {customSpecs.map(s => {
                            const val = getSpec(v, s.name);
                            const autoExtracted = val !== "" && val !== null && val !== undefined;
                            return (
                              <div key={s.name} style={s.field_type === "TEXT" ? { gridColumn: "1 / -1" } : {}}>
                                <label style={label}>
                                  {s.name}{s.unit ? ` (${s.unit})` : ""}
                                  {autoExtracted && (
                                    <span style={{ marginLeft: 6, fontSize: 10, color: "#059669", background: "#d1fae5", borderRadius: 4, padding: "1px 5px", fontWeight: 600 }}>auto</span>
                                  )}
                                </label>
                                {s.field_type === "BOOL" ? (
                                  <select style={input} value={String(val)} onChange={e => updateVendorSpec(i, s.name, e.target.value)}>
                                    <option value="">— not specified —</option>
                                    <option value="true">Yes</option>
                                    <option value="false">No</option>
                                  </select>
                                ) : s.field_type === "NUM" || s.field_type === "PCTNUM" ? (
                                  <input style={input} type="number" step={s.field_type === "PCTNUM" ? "0.01" : "1"} value={val ?? ""} onChange={e => updateVendorSpec(i, s.name, e.target.value)} placeholder={s.required_value ? `Target: ${s.required_value}` : ""} />
                                ) : (
                                  <input style={input} value={val ?? ""} onChange={e => updateVendorSpec(i, s.name, e.target.value)} placeholder={s.required_value ? `Target: ${s.required_value}` : `e.g. ${s.name}`} />
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </>
                    )}

                    {/* Other Details */}
                    <div style={sec}>Other Details</div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                      <div>
                        <label style={label}>Volume Discount</label>
                        <input style={input} value={getSpec(v, "volume_discount")} onChange={e => updateVendorSpec(i, "volume_discount", e.target.value)} placeholder="e.g. 3% above 250 units" />
                      </div>
                      <div>
                        <label style={label}>Country of Origin</label>
                        <input style={input} value={getSpec(v, "origin_country")} onChange={e => updateVendorSpec(i, "origin_country", e.target.value)} placeholder="e.g. India, USA" />
                      </div>
                      <div style={{ gridColumn: "1 / -1" }}>
                        <label style={label}>Additional Notes</label>
                        <textarea style={{ ...input, height: 64, resize: "vertical" } as React.CSSProperties} value={getSpec(v, "notes")} onChange={e => updateVendorSpec(i, "notes", e.target.value)} placeholder="Any other relevant information from the quote…" />
                      </div>
                    </div>

                    <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid #f3f4f6" }}>
                      <button onClick={() => {
                        setVendors(vs => vs.filter((_, j) => j !== i));
                        setActiveVendorTab(Math.max(0, i - 1));
                      }} style={{ fontSize: 12, color: "#dc2626", background: "none", border: "none", cursor: "pointer" }}>
                        Remove this vendor
                      </button>
                    </div>
                  </div>
                );
              })}

              <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
                <button style={btnBack} onClick={goBack}>← Back</button>
                <button style={btn} onClick={handleQuotesDone} disabled={loading}>{loading ? "Saving…" : "Save Vendors & Continue →"}</button>
              </div>
            </>
          )}

          {vendors.length === 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 12 }}>
                Parse a document above, or{" "}
                <button style={{ background: "none", border: "none", color: "#2563eb", cursor: "pointer", textDecoration: "underline", fontSize: 13 }}
                  onClick={() => setVendors([{ vendor_email: "", vendor_company: "", vendor_name: "", quoted_price: null, quoted_delivery_days: null, quoted_payment_days: null, quoted_warranty_months: null, quoted_currency: "USD", custom_spec_values: null }])}>
                  add vendor manually
                </button>.
              </div>
              <button style={btnBack} onClick={goBack}>← Back</button>
            </div>
          )}
        </div>
      )}

      {/* Step 2: Targets */}
      {step === "targets" && (
        <div style={card}>
          <h3 style={h3}>Set Negotiation Targets</h3>
          <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 16 }}>
            These are INTERNAL — the AI bot will never reveal them to vendors. Set these before sending your RFQ.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={label}>Target Price (per unit)</label>
              <input style={input} type="number" step="0.01" value={targets.target_price} onChange={setT("target_price")} placeholder="e.g. 1400" />
            </div>
            <div>
              <label style={label}>Target Delivery (days)</label>
              <input style={input} type="number" value={targets.target_delivery_days} onChange={setT("target_delivery_days")} placeholder="e.g. 30" />
            </div>
            <div>
              <label style={label}>Target Payment Terms (Net-X days)</label>
              <input style={input} type="number" value={targets.target_payment_days} onChange={setT("target_payment_days")} placeholder="e.g. 45" />
            </div>
            <div>
              <label style={label}>Warranty Target (months)</label>
              <input style={input} type="number" value={targets.warranty_months_target} onChange={setT("warranty_months_target")} placeholder="e.g. 24" />
            </div>
          </div>

          {/* Required Specifications — defined here before RFQ goes out */}
          <div style={{ marginTop: 20, borderTop: "1px solid #e5e7eb", paddingTop: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: "#1e3a5f" }}>Required Specifications</div>
                <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
                  Define before sending the RFQ — the AI will extract each vendor's values when parsing their responses.
                </div>
              </div>
              <button onClick={() => setCustomSpecs(ss => [...ss, { ...BLANK_SPEC }])}
                style={{ padding: "5px 12px", background: "#f0f9ff", color: "#1e3a5f", border: "1px solid #bae6fd", borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" }}>
                + Add Spec
              </button>
            </div>

            {customSpecs.length === 0 && (
              <div style={{ fontSize: 13, color: "#9ca3af", fontStyle: "italic", padding: "8px 0 12px" }}>
                No specs yet — e.g. IP Rating, MIL-STD-810H, ISO 9001, Defect Rate…
              </div>
            )}

            {customSpecs.map((s, si) => (
              <div key={si} style={{ background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 8, padding: 12, marginBottom: 8 }}>
                <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1.5fr 0.5fr 0.5fr auto", gap: 8, alignItems: "end" }}>
                  <div>
                    <label style={{ ...label, marginBottom: 2 }}>Spec Name</label>
                    <input style={{ ...input, marginBottom: 0 }} value={s.name} onChange={e => setSpec(si, "name", e.target.value)} placeholder="e.g. IP Rating" />
                  </div>
                  <div>
                    <label style={{ ...label, marginBottom: 2 }}>Type</label>
                    <select style={{ ...input, marginBottom: 0 }} value={s.field_type} onChange={e => setSpec(si, "field_type", e.target.value)}>
                      <option value="NUM">Number</option>
                      <option value="BOOL">Yes/No</option>
                      <option value="CAT">Category</option>
                      <option value="MULTI">Multi-select</option>
                      <option value="PCTNUM">Percentage</option>
                      <option value="TIER">Tier</option>
                      <option value="TEXT">Text</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ ...label, marginBottom: 2 }}>Required Value</label>
                    {s.field_type === "BOOL" ? (
                      <select style={{ ...input, marginBottom: 0 }} value={s.required_value} onChange={e => setSpec(si, "required_value", e.target.value)}>
                        <option value="true">Yes / True</option>
                        <option value="false">No / False</option>
                      </select>
                    ) : (
                      <input style={{ ...input, marginBottom: 0 }} value={s.required_value} onChange={e => setSpec(si, "required_value", e.target.value)} placeholder={s.field_type === "NUM" ? "e.g. 65" : "e.g. IP65"} />
                    )}
                  </div>
                  <div>
                    <label style={{ ...label, marginBottom: 2 }}>Unit</label>
                    <input style={{ ...input, marginBottom: 0 }} value={s.unit} onChange={e => setSpec(si, "unit", e.target.value)} placeholder="opt." />
                  </div>
                  <div>
                    <label style={{ ...label, marginBottom: 2 }}>Weight</label>
                    <input style={{ ...input, marginBottom: 0 }} type="number" min="0.1" step="0.1" value={s.weight} onChange={e => setSpec(si, "weight", e.target.value)} />
                  </div>
                  <button onClick={() => setCustomSpecs(ss => ss.filter((_, j) => j !== si))}
                    style={{ background: "none", border: "none", color: "#dc2626", cursor: "pointer", fontSize: 20, paddingBottom: 2 }}>×</button>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
                  <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>Importance:</span>
                  <button
                    type="button"
                    onClick={() => setSpec(si, "mandatory", !s.mandatory)}
                    style={{
                      padding: "3px 14px", borderRadius: 99, border: "1.5px solid", fontSize: 12, fontWeight: 700, cursor: "pointer",
                      background: s.mandatory ? "#fef2f2" : "#f0fdf4",
                      color: s.mandatory ? "#dc2626" : "#059669",
                      borderColor: s.mandatory ? "#fca5a5" : "#86efac",
                    }}
                  >
                    {s.mandatory ? "Must Have" : "Good to Have"}
                  </button>
                  {s.mandatory && (
                    <span style={{ fontSize: 11, color: "#9a3412", fontStyle: "italic" }}>Vendor will require qualification review if they don't meet this</span>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button style={btnBack} onClick={goBack}>← Back</button>
            <button style={btn} onClick={handleTargets} disabled={loading}>{loading ? "Saving…" : "Save & Prepare RFQ →"}</button>
          </div>
        </div>
      )}

      {/* Step 4: Qualify & Send invitations */}
      {step === "review" && (() => {
        const hasFailed = (vs: typeof vendorSessions[0]) => (vs.mandatory_failures ?? []).length > 0;
        const flagged = vendorSessions.filter(vs => hasFailed(vs) && !vs.buyer_override && vs.status === "pending_qualification");
        const overriddenVendors = vendorSessions.filter(vs => hasFailed(vs) && vs.buyer_override);
        const excludedVendors = vendorSessions.filter(vs => hasFailed(vs) && !vs.buyer_override && vs.status === "rejected");
        const clean = vendorSessions.filter(vs => !hasFailed(vs));
        const totalIncluded = clean.length + overriddenVendors.length;
        return (
          <div style={card}>
            <h3 style={h3}>Qualify & Send Invitations</h3>

            {/* Qualification review — only shown when bot has flagged vendors */}
            {flagged.length > 0 && (
              <div style={{ background: "#fffbeb", border: "1px solid #fcd34d", borderRadius: 8, padding: 16, marginBottom: 20 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#92400e", marginBottom: 10 }}>
                  Bot Qualification Review — {flagged.length} vendor{flagged.length > 1 ? "s" : ""} flagged
                </div>
                <div style={{ fontSize: 12, color: "#78350f", marginBottom: 14 }}>
                  These vendors don't meet your Must Have specs. Bot recommends excluding them. You have the final say.
                </div>
                {flagged.map(vs => (
                  <div key={vs.id} style={{ background: "#fff", border: "1.5px solid #fca5a5", borderRadius: 8, padding: 14, marginBottom: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 14, color: "#111827" }}>
                          {vs.vendor_company || vs.vendor_email}
                        </div>
                        <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>{vs.vendor_email}</div>
                        <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 5 }}>
                          {(vs.mandatory_failures || []).map(f => (
                            <span key={f} style={{ fontSize: 11, background: "#fee2e2", color: "#dc2626", border: "1px solid #fca5a5", borderRadius: 99, padding: "2px 8px", fontWeight: 600 }}>
                              {f}
                            </span>
                          ))}
                        </div>
                        <div style={{ marginTop: 8, fontSize: 12, color: "#7c3aed", fontStyle: "italic" }}>
                          Bot: Vendor does not meet {(vs.mandatory_failures || []).join(", ")} — recommend excluding from negotiation.
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                        <button
                          onClick={() => handleQualificationOverride(vs.id, true)}
                          disabled={overridingVsid !== null}
                          style={{ padding: "6px 14px", borderRadius: 6, border: "1.5px solid #059669", background: "#f0fdf4", color: "#059669", fontSize: 12, fontWeight: 700, cursor: overridingVsid !== null ? "default" : "pointer", opacity: overridingVsid === vs.id ? 0.6 : 1 }}
                        >
                          {overridingVsid === vs.id ? "…" : "Include"}
                        </button>
                        <button
                          onClick={() => handleQualificationOverride(vs.id, false)}
                          disabled={overridingVsid !== null}
                          style={{ padding: "6px 14px", borderRadius: 6, border: "1.5px solid #dc2626", background: "#fef2f2", color: "#dc2626", fontSize: 12, fontWeight: 700, cursor: overridingVsid !== null ? "default" : "pointer", opacity: overridingVsid === vs.id ? 0.6 : 1 }}
                        >
                          {overridingVsid === vs.id ? "…" : "Exclude"}
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Overridden vendors (buyer chose to include despite failures) */}
            {overriddenVendors.map(vs => (
              <div key={vs.id} style={{ background: "#f0fdf4", border: "1px solid #86efac", borderRadius: 8, padding: 12, marginBottom: 8, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13, color: "#111827" }}>{vs.vendor_company || vs.vendor_email}</div>
                  <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>{vs.vendor_email}</div>
                  <div style={{ marginTop: 5, display: "flex", gap: 5, flexWrap: "wrap" }}>
                    {(vs.mandatory_failures || []).map(f => (
                      <span key={f} style={{ fontSize: 10, background: "#fee2e2", color: "#dc2626", borderRadius: 99, padding: "1px 7px", fontWeight: 600 }}>{f}</span>
                    ))}
                    <span style={{ fontSize: 10, background: "#d1fae5", color: "#059669", borderRadius: 99, padding: "1px 7px", fontWeight: 700 }}>Buyer included</span>
                  </div>
                </div>
                <button
                  onClick={() => handleQualificationOverride(vs.id, false)}
                  disabled={overridingVsid !== null}
                  style={{ fontSize: 11, color: "#6b7280", background: "none", border: "1px solid #d1d5db", borderRadius: 5, padding: "4px 10px", cursor: overridingVsid !== null ? "default" : "pointer", opacity: overridingVsid === vs.id ? 0.6 : 1 }}
                >
                  {overridingVsid === vs.id ? "…" : "Undo — Exclude"}
                </button>
              </div>
            ))}

            {/* Excluded vendors (buyer confirmed exclusion) */}
            {excludedVendors.map(vs => (
              <div key={vs.id} style={{ background: "#fafafa", border: "1px solid #e5e7eb", borderRadius: 8, padding: 12, marginBottom: 8, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, opacity: 0.7 }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13, color: "#374151" }}>{vs.vendor_company || vs.vendor_email}</div>
                  <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>{vs.vendor_email}</div>
                  <div style={{ marginTop: 5, display: "flex", gap: 5, flexWrap: "wrap" }}>
                    {(vs.mandatory_failures || []).map(f => (
                      <span key={f} style={{ fontSize: 10, background: "#fee2e2", color: "#dc2626", borderRadius: 99, padding: "1px 7px", fontWeight: 600 }}>{f}</span>
                    ))}
                    <span style={{ fontSize: 10, background: "#f3f4f6", color: "#6b7280", borderRadius: 99, padding: "1px 7px", fontWeight: 700 }}>Excluded</span>
                  </div>
                </div>
                <button
                  onClick={() => handleQualificationOverride(vs.id, true)}
                  disabled={overridingVsid !== null}
                  style={{ fontSize: 11, color: "#059669", background: "none", border: "1px solid #86efac", borderRadius: 5, padding: "4px 10px", cursor: overridingVsid !== null ? "default" : "pointer", opacity: overridingVsid === vs.id ? 0.6 : 1 }}
                >
                  {overridingVsid === vs.id ? "…" : "Undo — Include"}
                </button>
              </div>
            ))}

            {/* Clean vendors */}
            {clean.map(vs => (
              <div key={vs.id} style={{ background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 8, padding: 12, marginBottom: 8, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13, color: "#111827" }}>{vs.vendor_company || vs.vendor_email}</div>
                  <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>{vs.vendor_email}</div>
                </div>
                <span style={{ fontSize: 11, background: "#d1fae5", color: "#059669", borderRadius: 99, padding: "3px 10px", fontWeight: 700 }}>Ready</span>
              </div>
            ))}

            <div style={{ background: "#f0f9ff", border: "1px solid #bae6fd", borderRadius: 8, padding: 14, margin: "20px 0 20px", fontSize: 13 }}>
              <strong>{totalIncluded} vendor{totalIncluded !== 1 ? "s" : ""} will be invited.</strong>
              {" "}When they open their link the AI bot starts negotiating automatically. You can monitor all conversations live and will be alerted for escalations.
            </div>

            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <button style={btnBack} onClick={goBack}>← Back</button>
              {flagged.length === 0 ? (
                <button style={{ ...btn, padding: "12px 28px", fontSize: 15 }} onClick={handleSend} disabled={loading || totalIncluded === 0}>
                  {loading ? "Sending…" : `Send Invitations to ${totalIncluded} Vendor${totalIncluded !== 1 ? "s" : ""}`}
                </button>
              ) : (
                <span style={{ fontSize: 13, color: "#b45309", fontWeight: 500 }}>
                  Review all flagged vendors before sending.
                </span>
              )}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
