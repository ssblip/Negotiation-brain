import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api";
import BuyerDashboard from "./pages/BuyerDashboard";
import LoginPage from "./pages/LoginPage";
import NegotiationDetailPage from "./pages/NegotiationDetailPage";
import NewNegotiationPage from "./pages/NewNegotiationPage";
import RegisterPage from "./pages/RegisterPage";
import StrategyBuilderPage from "./pages/StrategyBuilderPage";
import VendorChatPage from "./pages/VendorChatPage";
import VendorDashboard from "./pages/VendorDashboard";

const S: React.CSSProperties = {
  display: "flex", alignItems: "center", justifyContent: "space-between",
  padding: "0 24px", height: 56, background: "#1e3a5f", color: "#fff",
};

function Nav() {
  const nav = useNavigate();
  const user = api.getUser();
  if (!user) return null;
  return (
    <nav style={S}>
      <span style={{ fontWeight: 700, fontSize: 18, cursor: "pointer" }}
        onClick={() => nav(user.role === "buyer" ? "/" : "/vendor")}>
        🧠 Negotiation Brain
      </span>
      <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
        {user.role === "buyer" && (
          <button style={{ background: "transparent", border: "none", color: "rgba(255,255,255,0.8)", cursor: "pointer", fontSize: 13, padding: 0 }}
            onClick={() => nav("/strategy")}>
            Strategy
          </button>
        )}
        <span style={{ fontSize: 14, opacity: 0.85 }}>{user.display_name} · {user.role}</span>
        <button style={{ background: "transparent", border: "1px solid rgba(255,255,255,0.4)", color: "#fff", padding: "4px 12px", borderRadius: 4, cursor: "pointer" }}
          onClick={() => { api.clearToken(); localStorage.removeItem("nb_user"); nav("/login"); }}>
          Logout
        </button>
      </div>
    </nav>
  );
}

function PrivateRoute({ children, role }: { children: React.ReactNode; role?: string }) {
  const user = api.getUser();
  const tok = localStorage.getItem("nb_token");
  if (!tok || !user) return <Navigate to="/login" replace />;
  if (role && user.role !== role) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Nav />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* Buyer routes */}
        <Route path="/" element={<PrivateRoute role="buyer"><BuyerDashboard /></PrivateRoute>} />
        <Route path="/negotiations/new" element={<PrivateRoute role="buyer"><NewNegotiationPage /></PrivateRoute>} />
        <Route path="/negotiations/:id" element={<PrivateRoute role="buyer"><NegotiationDetailPage /></PrivateRoute>} />
        <Route path="/strategy" element={<PrivateRoute role="buyer"><StrategyBuilderPage /></PrivateRoute>} />

        {/* Vendor routes */}
        <Route path="/vendor" element={<PrivateRoute role="vendor"><VendorDashboard /></PrivateRoute>} />
        <Route path="/vendor/negotiations/:vsid" element={<PrivateRoute role="vendor"><VendorChatPage /></PrivateRoute>} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
