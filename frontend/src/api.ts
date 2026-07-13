const BASE = (import.meta.env.VITE_API_BASE as string) || "http://localhost:8000/api";

function token(): string | null {
  return localStorage.getItem("nb_token");
}

function authHeaders(): Record<string, string> {
  const t = token();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    ...opts,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(opts.headers || {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json() as Promise<T>;
}

async function upload<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Upload failed");
  }
  return res.json() as Promise<T>;
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface User { id: number; email: string; display_name: string; company: string | null; role: string; }
export interface TokenOut { access_token: string; user: User; }
export interface Negotiation { id: number; title: string; item: string; quantity: number; currency: string; status: string; created_at: string; vendor_count: number; active_count: number; agreed_count: number; }
export interface BuyerTargets { id: number; negotiation_id: number; target_price: number | null; reservation_price: number | null; target_delivery_days: number | null; max_delivery_days: number | null; target_payment_days: number | null; min_payment_days: number | null; warranty_months_target: number | null; warranty_months_min: number | null; batna_description: string | null; batna_strength: number | null; custom_specs: CustomSpec[]; }
export interface CustomSpec { name: string; field_type: string; required_value: unknown; weight: number; unit: string | null; mandatory: boolean; }
export interface VendorQuote { vendor_email: string; vendor_company: string | null; vendor_name: string | null; quoted_price: number | null; quoted_delivery_days: number | null; quoted_payment_days: number | null; quoted_warranty_months: number | null; quoted_currency: string; custom_spec_values: Record<string, unknown> | null; }
export interface VendorSession { id: number; negotiation_id: number; negotiation_title: string | null; negotiation_item: string | null; negotiation_quantity: number | null; negotiation_currency: string | null; buyer_company: string | null; vendor_email: string; vendor_company: string | null; vendor_name: string | null; quoted_price: number | null; quoted_delivery_days: number | null; quoted_payment_days: number | null; quoted_warranty_months: number | null; quoted_currency: string; custom_spec_values: Record<string, unknown> | null; priority: "P1" | "P2" | "P3" | null; spec_score: number | null; cvs_score: number | null; price_score: number | null; delivery_score: number | null; payment_score: number | null; warranty_score: number | null; strategy: string | null; current_state: string; round_count: number; current_offer: Record<string, number | null> | null; final_price: number | null; final_delivery_days: number | null; final_payment_days: number | null; status: string; invited_at: string; first_response_at: string | null; closed_at: string | null; has_pending_escalation: boolean; mandatory_failures: string[] | null; buyer_override: boolean; }
export interface Message { id: number; role: string; content: string; round_number: number; created_at: string; }
export interface Escalation { id: number; vendor_session_id: number; negotiation_id: number; reason: string; context_summary: string | null; status: string; buyer_decision: string | null; created_at: string; }
export interface VendorContext { vendor_session_id: number; negotiation_id: number; item: string; quantity: number; currency: string; buyer_company: string | null; vendor_company: string | null; vendor_name: string | null; quoted_price: number | null; quoted_delivery_days: number | null; quoted_payment_days: number | null; status: string; current_state: string; round_count: number; current_offer: Record<string, number | null> | null; }
export interface ChatOut { reply: string; state: string; round_count: number; current_offer: Record<string, number | null> | null; escalation_needed: boolean; agreement_reached: boolean; }
export interface ParsedVendors { vendors: VendorQuote[]; raw_text: string; }

// ── Auth ──────────────────────────────────────────────────────────────────

export const api = {
  setToken: (t: string) => localStorage.setItem("nb_token", t),
  clearToken: () => localStorage.removeItem("nb_token"),
  getUser: (): User | null => {
    const raw = localStorage.getItem("nb_user");
    return raw ? JSON.parse(raw) : null;
  },
  setUser: (u: User) => localStorage.setItem("nb_user", JSON.stringify(u)),

  register: (body: { email: string; password: string; display_name: string; company?: string; role: string }) =>
    req<TokenOut>("/auth/register", { method: "POST", body: JSON.stringify(body) }),

  login: (email: string, password: string) =>
    req<TokenOut>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  // Negotiations
  listNegotiations: () => req<Negotiation[]>("/negotiations"),
  getNegotiation: (nid: number) => req<Negotiation>(`/negotiations/${nid}`),
  createNegotiation: (body: { title: string; item: string; quantity: number; currency: string }) =>
    req<Negotiation>("/negotiations", { method: "POST", body: JSON.stringify(body) }),
  updateNegotiation: (nid: number, body: { title: string; item: string; quantity: number; currency: string }) =>
    req<Negotiation>(`/negotiations/${nid}`, { method: "PATCH", body: JSON.stringify(body) }),

  uploadGlobalStrategyDoc: (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return upload<{ ok: boolean; chars: number }>("/me/strategy-doc", fd);
  },

  getStrategyDocStatus: () => req<{ uploaded: boolean; chars: number }>("/me/strategy-doc-status"),

  parseQuotes: (nid: number, files: File[]) => {
    const fd = new FormData();
    files.forEach(f => fd.append("files", f));
    return upload<ParsedVendors>(`/negotiations/${nid}/parse-quotes`, fd);
  },

  setTargets: (nid: number, body: Partial<BuyerTargets>) =>
    req<BuyerTargets>(`/negotiations/${nid}/targets`, { method: "POST", body: JSON.stringify(body) }),

  getTargets: (nid: number) => req<BuyerTargets | null>(`/negotiations/${nid}/targets`),

  addVendors: (nid: number, vendors: VendorQuote[]) =>
    req<VendorSession[]>(`/negotiations/${nid}/vendors`, { method: "POST", body: JSON.stringify(vendors) }),

  listVendors: (nid: number) => req<VendorSession[]>(`/negotiations/${nid}/vendors`),

  setVendorPriority: (nid: number, vsid: number, priority: "P1" | "P2" | "P3" | null) =>
    req<VendorSession>(`/negotiations/${nid}/vendors/${vsid}/priority`, { method: "PATCH", body: JSON.stringify({ priority }) }),

  overrideVendorQualification: (nid: number, vsid: number, override: boolean) =>
    req<VendorSession>(`/negotiations/${nid}/vendors/${vsid}/override`, { method: "PATCH", body: JSON.stringify({ override }) }),

  sendInvitations: (nid: number) =>
    req<{ sent: number; total: number }>(`/negotiations/${nid}/send-invitations`, { method: "POST" }),

  getChatHistoryBuyer: (nid: number, vsid: number) =>
    req<Message[]>(`/negotiations/${nid}/vendors/${vsid}/messages`),

  listEscalations: (nid: number) => req<Escalation[]>(`/negotiations/${nid}/escalations`),

  awardTender: (nid: number, body: { vendor_session_id: number; explanation: string; share_explanation: boolean }) =>
    req<{ ok: boolean; awarded_to: string }>(`/negotiations/${nid}/award`, { method: "POST", body: JSON.stringify(body) }),

  resolveEscalation: (eid: number, decision: string, instruction?: string) =>
    req<Escalation>(`/escalations/${eid}/resolve`, { method: "POST", body: JSON.stringify({ decision, instruction }) }),

  // Vendor (magic link)
  getVendorContext: (token: string) => req<VendorContext>(`/negotiate/${token}`),
  startNegotiationChat: (token: string) => req<Message>(`/negotiate/${token}/start`, { method: "POST" }),
  vendorChat: (token: string, message: string) =>
    req<ChatOut>(`/negotiate/${token}/chat`, { method: "POST", body: JSON.stringify({ message }) }),
  getVendorMessages: (token: string) => req<Message[]>(`/negotiate/${token}/messages`),

  // Vendor (account)
  listVendorNegotiations: () => req<VendorSession[]>("/vendor/negotiations"),
  vendorAccountStart: (vsid: number) => req<Message>(`/vendor/negotiations/${vsid}/start`, { method: "POST" }),
  vendorAccountChat: (vsid: number, message: string) =>
    req<ChatOut>(`/vendor/negotiations/${vsid}/chat`, { method: "POST", body: JSON.stringify({ message }) }),
  vendorAccountMessages: (vsid: number) => req<Message[]>(`/vendor/negotiations/${vsid}/messages`),
};
