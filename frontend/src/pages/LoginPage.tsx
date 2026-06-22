import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";

const card: React.CSSProperties = { maxWidth: 400, margin: "80px auto", background: "#fff", borderRadius: 12, padding: 32, boxShadow: "0 4px 24px rgba(0,0,0,0.08)" };
const label: React.CSSProperties = { display: "block", marginBottom: 4, fontSize: 14, fontWeight: 500, color: "#374151" };
const input: React.CSSProperties = { width: "100%", padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14, marginBottom: 16 };
const btn: React.CSSProperties = { width: "100%", padding: "10px 0", background: "#1e3a5f", color: "#fff", border: "none", borderRadius: 6, fontSize: 15, fontWeight: 600, cursor: "pointer" };

export default function LoginPage() {
  const nav = useNavigate();
  const [role, setRole] = useState<"buyer" | "vendor">("buyer");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setErr("");
    try {
      const res = await api.login(email, password);
      if (res.user.role !== role) {
        setErr(`This account is registered as a ${res.user.role}, not a ${role}. Please select the correct portal.`);
        api.clearToken();
        return;
      }
      api.setToken(res.access_token);
      api.setUser(res.user);
      nav(res.user.role === "buyer" ? "/" : "/vendor");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={card}>
      <h2 style={{ marginBottom: 20, color: "#1e3a5f" }}>Sign In</h2>

      {/* Role toggle */}
      <div style={{ display: "flex", background: "#f1f5f9", borderRadius: 8, padding: 4, marginBottom: 24 }}>
        {(["buyer", "vendor"] as const).map(r => (
          <button key={r} onClick={() => { setRole(r); setErr(""); }}
            style={{
              flex: 1, padding: "8px 0", border: "none", borderRadius: 6, cursor: "pointer",
              fontWeight: 600, fontSize: 14, transition: "all 0.15s",
              background: role === r ? "#1e3a5f" : "transparent",
              color: role === r ? "#fff" : "#6b7280",
            }}>
            {r === "buyer" ? "🏢 Buyer Portal" : "🏭 Vendor Portal"}
          </button>
        ))}
      </div>

      {err && <div style={{ background: "#fee2e2", color: "#dc2626", padding: "8px 12px", borderRadius: 6, marginBottom: 16, fontSize: 14 }}>{err}</div>}
      <form onSubmit={submit}>
        <label style={label}>Email</label>
        <input style={input} type="email" value={email} onChange={e => setEmail(e.target.value)} required />
        <label style={label}>Password</label>
        <input style={input} type="password" value={password} onChange={e => setPassword(e.target.value)} required />
        <button style={btn} type="submit" disabled={loading}>
          {loading ? "Signing in…" : `Sign in as ${role === "buyer" ? "Buyer" : "Vendor"}`}
        </button>
      </form>
      <p style={{ marginTop: 16, textAlign: "center", fontSize: 14 }}>
        No account? <Link to="/register" style={{ color: "#1e3a5f" }}>Register</Link>
      </p>
    </div>
  );
}
