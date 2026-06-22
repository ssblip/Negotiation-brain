import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";

const card: React.CSSProperties = { maxWidth: 420, margin: "60px auto", background: "#fff", borderRadius: 12, padding: 32, boxShadow: "0 4px 24px rgba(0,0,0,0.08)" };
const label: React.CSSProperties = { display: "block", marginBottom: 4, fontSize: 14, fontWeight: 500, color: "#374151" };
const input: React.CSSProperties = { width: "100%", padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14, marginBottom: 14 };
const btn: React.CSSProperties = { width: "100%", padding: "10px 0", background: "#1e3a5f", color: "#fff", border: "none", borderRadius: 6, fontSize: 15, fontWeight: 600, cursor: "pointer" };

export default function RegisterPage() {
  const nav = useNavigate();
  const [form, setForm] = useState({ email: "", password: "", display_name: "", company: "", role: "buyer" });
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setErr("");
    try {
      const res = await api.register(form);
      api.setToken(res.access_token);
      api.setUser(res.user);
      nav(res.user.role === "buyer" ? "/" : "/vendor");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={card}>
      <h2 style={{ marginBottom: 24, color: "#1e3a5f" }}>Create Account</h2>
      {err && <div style={{ background: "#fee2e2", color: "#dc2626", padding: "8px 12px", borderRadius: 6, marginBottom: 14, fontSize: 14 }}>{err}</div>}
      <form onSubmit={submit}>
        <label style={label}>Role</label>
        <select style={{ ...input, background: "#fff" }} value={form.role} onChange={set("role")}>
          <option value="buyer">Buyer</option>
          <option value="vendor">Vendor</option>
        </select>
        <label style={label}>Full Name</label>
        <input style={input} value={form.display_name} onChange={set("display_name")} required />
        <label style={label}>Company</label>
        <input style={input} value={form.company} onChange={set("company")} />
        <label style={label}>Email</label>
        <input style={input} type="email" value={form.email} onChange={set("email")} required />
        <label style={label}>Password</label>
        <input style={input} type="password" value={form.password} onChange={set("password")} required minLength={6} />
        <button style={btn} type="submit" disabled={loading}>{loading ? "Creating…" : "Create Account"}</button>
      </form>
      <p style={{ marginTop: 16, textAlign: "center", fontSize: 14 }}>
        Have an account? <Link to="/login" style={{ color: "#1e3a5f" }}>Sign in</Link>
      </p>
    </div>
  );
}
