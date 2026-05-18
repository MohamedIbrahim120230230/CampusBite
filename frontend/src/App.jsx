import { BrowserRouter, Routes, Route, NavLink, Outlet, useNavigate } from "react-router-dom";
import Login from "./features/auth/auth_components";
import MenuPage from "./features/menu-cart/MenuPage";
import AdminPanel from "./features/menu-cart/AdminPanel";

function CafeteriaLayout() {
  return (
    <div>
      <nav className="navbar navbar-dark bg-dark px-4">
        <span className="navbar-brand">🍴 Cafeteria System</span>
        <div>
          <NavLink 
            to="/menu" 
            className={({ isActive }) => `btn me-2 ${isActive ? 'btn-light' : 'btn-outline-light'}`}
          >
            Menu
          </NavLink>
          <NavLink 
            to="/admin" 
            className={({ isActive }) => `btn ${isActive ? 'btn-light' : 'btn-outline-light'}`}
          >
            Admin
          </NavLink>
        </div>
      </nav>
      <div className="p-4">
        <Outlet />
      </div>
    </div>
  );
}

// Separate wrapper so we can call useNavigate (hooks need to be inside BrowserRouter)
function LoginPage() {
  const navigate = useNavigate();
  return (
    <Login
      navigate={navigate}
      onLoginSuccess={(data) => {
        // Optional: store user info if needed elsewhere
        localStorage.setItem("user", JSON.stringify(data.user));
      }}
    />
  );
}

function ProtectedRoute({ children }) {
  const token = localStorage.getItem("jwt_token");
  if (!token) { window.location.href = "/"; return null; }
  return children;
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
        <Route path="/" element={<LoginPage />} />

        <Route element={<CafeteriaLayout />}>
          <Route path="/menu" element={<MenuPage />} />
          <Route path="/admin" element={<AdminPanel />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
