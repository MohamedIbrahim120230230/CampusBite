// ============================================================
// App.jsx — Root router with role-based guards
// ============================================================

import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import Login from "./features/auth/auth_components";
import MenuPage from "./features/menu-cart/MenuPage";
import AdminPanel from "./features/menu-cart/AdminPanel";
import StockDashboard from "./features/stock/StockDashboard";
// import KitchenPage from "./features/kitchen/KitchenPage"; // uncomment when ready

// ── Login wrapper (needs useNavigate, must be inside BrowserRouter) ──
function LoginPage() {
  const navigate = useNavigate();
  return (
    <Login
      navigate={navigate}
      onLoginSuccess={(data) => {
        localStorage.setItem("user", JSON.stringify(data.user));
      }}
    />
  );
}

// ── Role guard ────────────────────────────────────────────────
// Redirects to "/" if not logged in, or to "/menu" if wrong role
function RequireRole({ allowed, children }) {
  const user = JSON.parse(localStorage.getItem("user") || "null");
  if (!user) return <Navigate to="/" replace />;
  if (!allowed.includes(user.role)) return <Navigate to="/menu" replace />;
  return children;
}

// ── App ───────────────────────────────────────────────────────
function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public: login */}
        <Route path="/" element={<LoginPage />} />

        {/* Students + admins can view the menu */}
        <Route
          path="/menu"
          element={
            <RequireRole allowed={["student", "admin"]}>
              <MenuPage />
            </RequireRole>
          }
        />

        {/* Admins only */}
        <Route
          path="/admin"
          element={
            <RequireRole allowed={["admin"]}>
              <AdminPanel />
            </RequireRole>
          }
        />

        {/* Admins only */}
        <Route 
          path="/stock" 
          element={
            <RequireRole allowed={["admin"]}>
              <StockDashboard />
            </RequireRole>
          } 
        />
        
        {/* Staff only */}
        <Route 
          path="/kitchen" 
          element={
            <RequireRole allowed={["staff"]}>
              <div style={{ color: "white", padding: 20 }}>Kitchen panel coming soon</div>
              {/* <KitchenPage /> */}
            </RequireRole>
          } 
        />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;