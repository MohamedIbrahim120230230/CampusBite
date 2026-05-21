// ============================================================
// frontend/src/features/menu-cart/AdminPanel.jsx
// ============================================================

import React, { useState, useEffect, useCallback } from "react";
import { apiFetch, apiLogout } from "../../shared/api";
import { useNavigate } from "react-router-dom";

if (typeof document !== "undefined") {
  if (!document.querySelector('link[href*="Sora"]')) {
    const f = document.createElement("link");
    f.rel  = "stylesheet";
    f.href = "https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&family=Inter:wght@400;500;600;700&display=swap";
    document.head.appendChild(f);
  }
  if (!document.querySelector('link[href*="bootstrap-icons"]')) {
    const i = document.createElement("link");
    i.rel  = "stylesheet";
    i.href = "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css";
    document.head.appendChild(i);
  }
}

const CATEGORIES = ["meals", "beverages", "snacks"];

const EMPTY_FORM = {
  name: "", category: "meals", price: "",
  stock_qty: "", max_order_qty: 10, active: true,
  description: "", image_url: "",
};

const EMPTY_VOUCHER = {
  code: "", discount_type: "flat", discount_value: "",
  min_order: "", max_uses: "1", expires_at: "",
};

function UniversityLogo({ size = 36 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="48" stroke="#b48e32" strokeWidth="2" fill="none"/>
      <circle cx="50" cy="28" r="10" fill="#dc2626"/>
      <path d="M50 42 L50 75" stroke="#1e3a5f" strokeWidth="4" strokeLinecap="round"/>
      <path d="M35 55 C35 55 50 45 65 55" stroke="#1e3a5f" strokeWidth="4" strokeLinecap="round" fill="none"/>
      <path d="M30 68 C30 68 50 55 70 68" stroke="#1e3a5f" strokeWidth="4" strokeLinecap="round" fill="none"/>
      <path d="M25 80 C25 80 50 65 75 80" stroke="#1e3a5f" strokeWidth="4" strokeLinecap="round" fill="none"/>
    </svg>
  );
}

function Toast({ toasts, removeToast }) {
  return (
    <div style={{ position:"fixed", bottom:24, right:24, zIndex:9999, display:"flex", flexDirection:"column", gap:8 }}>
      {toasts.map(t => (
        <div key={t.id} className={`uc-toast uc-toast--${t.type}`}>
          <i className={`bi ${t.type==="success" ? "bi-check-circle-fill" : t.type==="warn" ? "bi-exclamation-triangle-fill" : "bi-x-circle-fill"}`} />
          <span>{t.message}</span>
          <button onClick={() => removeToast(t.id)} className="uc-toast-close"><i className="bi bi-x" /></button>
        </div>
      ))}
    </div>
  );
}

function useToast() {
  const [toasts, setToasts] = useState([]);
  const add    = useCallback((message, type="success") => {
    const id = Date.now();
    setToasts(p => [...p, { id, message, type }]);
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 3500);
  }, []);
  const remove = useCallback(id => setToasts(p => p.filter(t => t.id !== id)), []);
  return { toasts, addToast: add, removeToast: remove };
}

function ConfirmModal({ message, onConfirm, onCancel }) {
  return (
    <>
      <div className="ap-modal-backdrop" onClick={onCancel} />
      <div className="ap-modal" role="dialog" aria-modal="true">
        <div className="ap-modal-inner">
          <div className="ap-modal-icon"><i className="bi bi-exclamation-triangle-fill" /></div>
          <h3 className="ap-modal-title">Confirm Action</h3>
          <p className="ap-modal-msg">{message}</p>
          <div className="ap-modal-actions">
            <button className="ap-cancel-btn" onClick={onCancel}>Cancel</button>
            <button className="ap-danger-btn" onClick={onConfirm}>Confirm</button>
          </div>
        </div>
      </div>
    </>
  );
}

export default function AdminPanel() {
  const navigate = useNavigate();
  const { toasts, addToast, removeToast } = useToast();
  const [activeTab,  setActiveTab]  = useState("menu");

  // Update CSS custom property for nav height (admin always has mobile tabs)
  useEffect(() => {
    const root = document.documentElement;
    const update = () => {
      const isMobile = window.innerWidth < 768;
      root.style.setProperty("--nav-total-h", isMobile ? "104px" : "68px");
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const [items,      setItems]      = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [saving,     setSaving]     = useState(false);
  const [form,       setForm]       = useState(EMPTY_FORM);
  const [editingId,  setEditingId]  = useState(null);
  const [errors,     setErrors]     = useState({});
  const [filterCat,  setFilterCat]  = useState("");
  const [search,     setSearch]     = useState("");
  const [confirm,    setConfirm]    = useState(null);
  const [showForm,   setShowForm]   = useState(false);

  const [vouchers,   setVouchers]   = useState([]);
  const [vLoading,   setVLoading]   = useState(false);
  const [vSaving,    setVSaving]    = useState(false);
  const [vForm,      setVForm]      = useState(EMPTY_VOUCHER);
  const [vErrors,    setVErrors]    = useState({});
  const [showVForm,  setShowVForm]  = useState(false);
  const [vConfirm,   setVConfirm]   = useState(null);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch("/menu/items");
      setItems(data.items || data || []);
    } catch {
      addToast("Failed to load menu items.", "error");
    } finally {
      setLoading(false);
    }
  }, []); // eslint-disable-line

  useEffect(() => { fetchItems(); }, []);

  const fetchVouchers = useCallback(async () => {
    setVLoading(true);
    try {
      const data = await apiFetch("/admin/vouchers");
      setVouchers(data.vouchers || []);
    } catch {
      addToast("Failed to load vouchers.", "error");
    } finally {
      setVLoading(false);
    }
  }, []); // eslint-disable-line

  useEffect(() => { if (activeTab === "vouchers") fetchVouchers(); }, [activeTab]); // eslint-disable-line

  const handleVChange = e => {
    const { name, value } = e.target;
    setVForm(p => ({ ...p, [name]: value }));
    if (vErrors[name]) setVErrors(p => ({ ...p, [name]: "" }));
  };

  const validateVoucher = () => {
    const e = {};
    if (!vForm.code.trim()) e.code = "Code is required.";
    else if (!/^[A-Z0-9_-]{2,20}$/.test(vForm.code.trim().toUpperCase())) e.code = "2-20 chars, letters/numbers/dash/underscore only.";
    if (vForm.discount_type !== "free_delivery") {
      if (!vForm.discount_value || isNaN(vForm.discount_value) || parseFloat(vForm.discount_value) <= 0) e.discount_value = "Enter a value > 0.";
      if (vForm.discount_type === "percent" && parseFloat(vForm.discount_value) > 100) e.discount_value = "Percentage cannot exceed 100.";
    }
    if (vForm.min_order && (isNaN(vForm.min_order) || parseFloat(vForm.min_order) < 0)) e.min_order = "Must be >= 0.";
    if (!vForm.max_uses || isNaN(vForm.max_uses) || parseInt(vForm.max_uses) < 1) e.max_uses = "Must be >= 1.";
    if (!vForm.expires_at) e.expires_at = "Expiry date is required.";
    return e;
  };

  const handleVSubmit = async () => {
    const errs = validateVoucher();
    if (Object.keys(errs).length) { setVErrors(errs); return; }
    setVSaving(true);
    try {
      await apiFetch("/admin/vouchers", {
        method: "POST",
        body: JSON.stringify({
          code:           vForm.code.trim().toUpperCase(),
          discount_type:  vForm.discount_type,
          discount_value: vForm.discount_type === "free_delivery" ? 0 : parseFloat(vForm.discount_value),
          min_order:      parseFloat(vForm.min_order || 0),
          max_uses:       parseInt(vForm.max_uses, 10),
          expires_at:     new Date(vForm.expires_at).toISOString(),
        }),
      });
      addToast(`Voucher ${vForm.code.toUpperCase()} created.`, "success");
      setVForm(EMPTY_VOUCHER); setVErrors({}); setShowVForm(false);
      fetchVouchers();
    } catch (err) {
      addToast(err?.message || "Failed to create voucher.", "error");
    } finally { setVSaving(false); }
  };

  const confirmDeactivateVoucher = async () => {
    const { code } = vConfirm;
    setVConfirm(null);
    try {
      await apiFetch(`/admin/vouchers/${code}`, { method: "DELETE" });
      addToast(`Voucher ${code} deactivated.`, "warn");
      fetchVouchers();
    } catch (err) {
      addToast(err?.message || "Failed to deactivate voucher.", "error");
    }
  };

  const handleChange = e => {
    const { name, type, value, checked } = e.target;
    setForm(prev => ({ ...prev, [name]: type === "checkbox" ? checked : value }));
    if (errors[name]) setErrors(prev => ({ ...prev, [name]: "" }));
  };

  const validate = () => {
    const e = {};
    if (!form.name.trim()) e.name = "Item name is required.";
    if (!form.price || isNaN(form.price) || parseFloat(form.price) <= 0) e.price = "Enter a valid price > 0.";
    if (!form.stock_qty || isNaN(form.stock_qty) || parseInt(form.stock_qty) < 0) e.stock_qty = "Stock quantity must be >= 0.";
    if (!form.max_order_qty || isNaN(form.max_order_qty) || parseInt(form.max_order_qty) < 1) e.max_order_qty = "Max order qty must be >= 1.";
    return e;
  };

  const handleSubmit = async () => {
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setSaving(true);
    try {
      const payload = {
        ...form,
        name: form.name.trim(), description: form.description.trim(), image_url: form.image_url.trim(),
        price: parseFloat(form.price), stock_qty: parseInt(form.stock_qty, 10), max_order_qty: parseInt(form.max_order_qty, 10),
      };
      if (editingId) {
        await apiFetch(`/admin/menu/${editingId}`, { method: "PUT", body: JSON.stringify(payload) });
        addToast(`"${payload.name}" updated successfully.`, "success");
      } else {
        await apiFetch("/admin/menu", { method: "POST", body: JSON.stringify(payload) });
        addToast(`"${payload.name}" published to menu.`, "success");
      }
      setForm(EMPTY_FORM); setEditingId(null); setErrors({}); setShowForm(false);
      fetchItems();
    } catch (err) {
      addToast(err?.message || "Failed to save item.", "error");
    } finally { setSaving(false); }
  };

  const handleEdit = (item) => {
    setForm({ name:item.name, category:item.category, price:item.price, stock_qty:item.stock_qty, max_order_qty:item.max_order_qty, active:item.active, description:item.description||"", image_url:item.image_url||"" });
    setEditingId(item.id); setErrors({}); setShowForm(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleCancelEdit = () => { setForm(EMPTY_FORM); setEditingId(null); setErrors({}); setShowForm(false); };

  const confirmDeactivate = async () => {
    const { id, name } = confirm;
    setConfirm(null);
    try {
      await apiFetch(`/admin/menu/${id}`, { method: "DELETE" });
      addToast(`"${name}" deactivated.`, "warn");
      fetchItems();
    } catch (err) { addToast(err?.message || "Failed to deactivate item.", "error"); }
  };

  const handleLogout = async () => { await apiLogout(); navigate("/"); };

  const filtered = items.filter(item => {
    const matchCat    = !filterCat || item.category === filterCat;
    const matchSearch = !search || item.name.toLowerCase().includes(search.toLowerCase());
    return matchCat && matchSearch;
  });

  const stats = {
    total:    items.length,
    active:   items.filter(i => i.active).length,
    inactive: items.filter(i => !i.active).length,
    oos:      items.filter(i => i.stock_qty === 0).length,
  };

  return (
    <>
      <style>{ADMIN_CSS}</style>
      <div className="ap-page">
        <div className="uc-mesh"  aria-hidden="true" />
        <div className="uc-grid"  aria-hidden="true" />

        {/* ── Navbar ── */}
        <nav className="mp-nav">
          <div className="mp-nav-brand">
            <div className="mp-nav-logo"><UniversityLogo size={32} /></div>
            <div className="mp-nav-brand-text">
              <span className="mp-nav-name">CampusBite</span>
              <span className="mp-nav-uni">E-JUST University</span>
            </div>
            <span className="ap-admin-tag">Admin</span>
          </div>

          {/* Desktop nav tabs — hidden on mobile (mp-mobile-tabs handles it) */}
          <div className="mp-nav-tabs">
            <button className="mp-nav-tab" onClick={() => navigate("/menu")}><i className="bi bi-storefront" /><span>Menu</span></button>
            <button className="mp-nav-tab mp-nav-tab--active"><i className="bi bi-gear-fill" /><span>Admin</span></button>
            <button className="mp-nav-tab" onClick={() => navigate("/stock")}><i className="bi bi-boxes" /><span>Stock</span></button>
            <button className="mp-nav-tab" onClick={() => navigate("/lifecycle")}><i className="bi bi-arrow-repeat" /><span>Lifecycle</span></button>
          </div>

          <div className="mp-nav-actions">
            <button className="mp-logout-btn" onClick={handleLogout} title="Sign out">
              <i className="bi bi-box-arrow-right" />
            </button>
          </div>
        </nav>

        {/* ── Mobile tabs bar — same pattern as MenuPage ── */}
        <div className="mp-mobile-tabs">
          <button className="mp-mobile-tab" onClick={() => navigate("/menu")}><i className="bi bi-storefront" /><span>Menu</span></button>
          <button className="mp-mobile-tab mp-mobile-tab--active"><i className="bi bi-gear-fill" /><span>Admin</span></button>
          <button className="mp-mobile-tab" onClick={() => navigate("/stock")}><i className="bi bi-boxes" /><span>Stock</span></button>
          <button className="mp-mobile-tab" onClick={() => navigate("/lifecycle")}><i className="bi bi-arrow-repeat" /><span>Lifecycle</span></button>
        </div>

        <div className="ap-body">

          {/* ── Section tabs ── */}
          <div className="ap-section-tabs">
            <button className={"ap-section-tab" + (activeTab==="menu" ? " ap-section-tab--active" : "")} onClick={() => setActiveTab("menu")}>
              <i className="bi bi-grid-3x3-gap-fill" /> Menu Items
            </button>
            <button className={"ap-section-tab" + (activeTab==="vouchers" ? " ap-section-tab--active" : "")} onClick={() => setActiveTab("vouchers")}>
              <i className="bi bi-ticket-perforated-fill" /> Vouchers
            </button>
          </div>

          {/* ══════════ VOUCHERS TAB ══════════ */}
          {activeTab === "vouchers" && (
            <>
              <div className="ap-stats">
                {[
                  { label:"Total",    value: vouchers.length, icon:"bi-ticket-perforated-fill", color:"var(--uc-gold)"   },
                  { label:"Active",   value: vouchers.filter(v => v.is_active && new Date(v.expires_at) > new Date()).length, icon:"bi-check-circle-fill", color:"var(--uc-acc2)"  },
                  { label:"Expired",  value: vouchers.filter(v => new Date(v.expires_at) <= new Date()).length, icon:"bi-clock-history", color:"var(--uc-warn)"  },
                  { label:"Inactive", value: vouchers.filter(v => !v.is_active).length, icon:"bi-x-circle-fill", color:"var(--uc-danger)" },
                ].map(s => (
                  <div key={s.label} className="ap-stat">
                    <i className={"bi " + s.icon} style={{ color:s.color }} />
                    <div>
                      <div className="ap-stat-val" style={{ color:s.color }}>{s.value}</div>
                      <div className="ap-stat-label">{s.label}</div>
                    </div>
                  </div>
                ))}
              </div>

              {showVForm && (
                <div className="ap-form-card">
                  <div className="ap-form-hd">
                    <h2 className="ap-form-title"><i className="bi bi-plus-circle-fill" /> New Voucher</h2>
                    <button className="mp-cart-close" onClick={() => { setShowVForm(false); setVForm(EMPTY_VOUCHER); setVErrors({}); }} aria-label="Close"><i className="bi bi-x-lg" /></button>
                  </div>
                  <div className="ap-form-grid">
                    <div className="ap-field">
                      <label className="ap-label">Voucher Code *</label>
                      <input name="code" className={"ap-input" + (vErrors.code ? " ap-input--err" : "")} placeholder="e.g. SUMMER25"
                        value={vForm.code} onChange={e => { setVForm(p => ({ ...p, code: e.target.value.toUpperCase() })); if (vErrors.code) setVErrors(p => ({...p, code:""})); }} />
                      {vErrors.code && <span className="ap-field-err">{vErrors.code}</span>}
                    </div>
                    <div className="ap-field">
                      <label className="ap-label">Discount Type *</label>
                      <select name="discount_type" className="ap-input" value={vForm.discount_type} onChange={handleVChange}>
                        <option value="flat">Flat (EGP off)</option>
                        <option value="percent">Percentage (% off)</option>
                        <option value="free_delivery">Free Delivery</option>
                      </select>
                    </div>
                    {vForm.discount_type !== "free_delivery" && (
                      <div className="ap-field">
                        <label className="ap-label">{vForm.discount_type === "percent" ? "Discount % *" : "Discount Amount (EGP) *"}</label>
                        <div className="ap-input-prefix-wrap">
                          <span className="ap-input-prefix">{vForm.discount_type === "percent" ? "%" : "EGP"}</span>
                          <input name="discount_value" type="number" min="0" step="0.01"
                            className={"ap-input ap-input--prefixed" + (vErrors.discount_value ? " ap-input--err" : "")}
                            placeholder={vForm.discount_type === "percent" ? "50" : "20.00"}
                            value={vForm.discount_value} onChange={handleVChange} />
                        </div>
                        {vErrors.discount_value && <span className="ap-field-err">{vErrors.discount_value}</span>}
                      </div>
                    )}
                    <div className="ap-field">
                      <label className="ap-label">Min Order (EGP)</label>
                      <div className="ap-input-prefix-wrap">
                        <span className="ap-input-prefix">EGP</span>
                        <input name="min_order" type="number" min="0" step="0.01"
                          className={"ap-input ap-input--prefixed" + (vErrors.min_order ? " ap-input--err" : "")}
                          placeholder="0.00" value={vForm.min_order} onChange={handleVChange} />
                      </div>
                      {vErrors.min_order ? <span className="ap-field-err">{vErrors.min_order}</span> : <span className="ap-field-hint">Leave 0 for no minimum</span>}
                    </div>
                    <div className="ap-field">
                      <label className="ap-label">Max Uses *</label>
                      <input name="max_uses" type="number" min="1"
                        className={"ap-input" + (vErrors.max_uses ? " ap-input--err" : "")}
                        placeholder="100" value={vForm.max_uses} onChange={handleVChange} />
                      {vErrors.max_uses && <span className="ap-field-err">{vErrors.max_uses}</span>}
                    </div>
                    <div className="ap-field">
                      <label className="ap-label">Expiry Date *</label>
                      <input name="expires_at" type="datetime-local"
                        className={"ap-input" + (vErrors.expires_at ? " ap-input--err" : "")}
                        value={vForm.expires_at} onChange={handleVChange}
                        min={new Date().toISOString().slice(0,16)} />
                      {vErrors.expires_at && <span className="ap-field-err">{vErrors.expires_at}</span>}
                    </div>
                  </div>
                  <div className="ap-form-actions">
                    <button className="ap-cancel-btn" onClick={() => { setShowVForm(false); setVForm(EMPTY_VOUCHER); setVErrors({}); }}>Cancel</button>
                    <button className="ap-submit-btn" onClick={handleVSubmit} disabled={vSaving}>
                      {vSaving ? <><span className="mp-spinner-sm" /> Creating…</> : <><i className="bi bi-plus-circle-fill" /> Create Voucher</>}
                    </button>
                  </div>
                </div>
              )}

              <div className="ap-table-card">
                <div className="ap-table-hd">
                  <div className="ap-table-hd-left">
                    <h2 className="ap-form-title"><i className="bi bi-ticket-perforated-fill" /> Vouchers</h2>
                    <span className="ap-count">{vouchers.length} total</span>
                  </div>
                  <div className="ap-table-hd-right">
                    {!showVForm && <button className="ap-add-new-btn" onClick={() => setShowVForm(true)}><i className="bi bi-plus-lg" /> New Voucher</button>}
                  </div>
                </div>

                {vLoading ? (
                  <div className="mp-loading"><div className="mp-spinner" /><span>Loading vouchers…</span></div>
                ) : vouchers.length === 0 ? (
                  <div className="mp-empty"><span style={{ fontSize:40 }}>🎟️</span><p>No vouchers yet. Create one above.</p></div>
                ) : (
                  <>
                    {/* Desktop voucher table */}
                    <div className="ap-table-wrap ap-desktop-only">
                      <table className="ap-table">
                        <thead>
                          <tr><th>Code</th><th>Type</th><th>Value</th><th>Min Order</th><th>Uses</th><th>Expires</th><th>Status</th><th>Actions</th></tr>
                        </thead>
                        <tbody>
                          {vouchers.map(v => {
                            const expired = new Date(v.expires_at) <= new Date();
                            const active  = v.is_active && !expired;
                            return (
                              <tr key={v.id} className={!active ? "ap-row--inactive" : ""}>
                                <td><span className="ap-item-name" style={{ fontFamily:"monospace", letterSpacing:".05em" }}>{v.code}</span></td>
                                <td><span className="ap-cat-badge">{v.discount_type === "flat" ? "Flat" : v.discount_type === "percent" ? "Percent" : "Free Delivery"}</span></td>
                                <td className="ap-price">{v.discount_type === "flat" ? Number(v.discount_value).toFixed(2)+" EGP" : v.discount_type === "percent" ? Number(v.discount_value).toFixed(0)+"%" : "—"}</td>
                                <td style={{ fontSize:12.5, color:"var(--uc-muted)" }}>{Number(v.min_order)>0 ? Number(v.min_order).toFixed(0)+" EGP" : "None"}</td>
                                <td style={{ fontSize:12.5 }}>{v.used_count} / {v.max_uses}</td>
                                <td style={{ fontSize:11.5, color: expired ? "var(--uc-danger)" : "var(--uc-muted)" }}>
                                  {new Date(v.expires_at).toLocaleDateString("en-GB",{day:"2-digit",month:"short",year:"numeric"})}{expired && " (expired)"}
                                </td>
                                <td><span className={"ap-status " + (active ? "ap-status--active" : "ap-status--inactive")}><span className="ap-status-dot" />{active ? "Active" : expired ? "Expired" : "Inactive"}</span></td>
                                <td>{v.is_active && <button className="ap-deactivate-btn" title="Deactivate" onClick={() => setVConfirm({ code: v.code })}><i className="bi bi-x-circle-fill" /></button>}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>

                    {/* Mobile voucher cards */}
                    <div className="ap-card-list ap-mobile-only">
                      {vouchers.map(v => {
                        const expired = new Date(v.expires_at) <= new Date();
                        const active  = v.is_active && !expired;
                        return (
                          <div key={v.id} className={"ap-mobile-card" + (!active ? " ap-mobile-card--inactive" : "")}>
                            <div className="ap-mc-row">
                              <span className="ap-mc-code">{v.code}</span>
                              <span className={"ap-status " + (active ? "ap-status--active" : "ap-status--inactive")}><span className="ap-status-dot" />{active ? "Active" : expired ? "Expired" : "Inactive"}</span>
                            </div>
                            <div className="ap-mc-row ap-mc-row--muted">
                              <span><span className="ap-cat-badge">{v.discount_type === "flat" ? "Flat" : v.discount_type === "percent" ? "%" : "Free Delivery"}</span></span>
                              <span className="ap-price" style={{ fontSize:14 }}>{v.discount_type === "flat" ? Number(v.discount_value).toFixed(2)+" EGP" : v.discount_type === "percent" ? Number(v.discount_value).toFixed(0)+"%" : "—"}</span>
                            </div>
                            <div className="ap-mc-row ap-mc-row--muted">
                              <span style={{ fontSize:11.5 }}>Uses: {v.used_count}/{v.max_uses}</span>
                              <span style={{ fontSize:11.5, color: expired ? "var(--uc-danger)" : "var(--uc-muted)" }}>Exp: {new Date(v.expires_at).toLocaleDateString("en-GB",{day:"2-digit",month:"short",year:"numeric"})}</span>
                            </div>
                            {v.is_active && (
                              <button className="ap-mc-deactivate" onClick={() => setVConfirm({ code: v.code })}>
                                <i className="bi bi-x-circle-fill" /> Deactivate
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>

              {vConfirm && (
                <ConfirmModal
                  message={"Deactivate voucher " + vConfirm.code + "? Students will no longer be able to use it."}
                  onConfirm={confirmDeactivateVoucher}
                  onCancel={() => setVConfirm(null)}
                />
              )}
            </>
          )}

          {/* ══════════ MENU ITEMS TAB ══════════ */}
          {activeTab === "menu" && (
            <>
              <div className="ap-stats">
                {[
                  { label:"Total Items",  value:stats.total,    icon:"bi-grid-3x3-gap-fill",      color:"var(--uc-gold)"   },
                  { label:"Active",       value:stats.active,   icon:"bi-check-circle-fill",       color:"var(--uc-acc2)"  },
                  { label:"Inactive",     value:stats.inactive, icon:"bi-x-circle-fill",           color:"var(--uc-danger)"},
                  { label:"Out of Stock", value:stats.oos,      icon:"bi-exclamation-circle-fill", color:"var(--uc-warn)"  },
                ].map(s => (
                  <div key={s.label} className="ap-stat">
                    <i className={`bi ${s.icon}`} style={{ color:s.color }} />
                    <div>
                      <div className="ap-stat-val" style={{ color:s.color }}>{s.value}</div>
                      <div className="ap-stat-label">{s.label}</div>
                    </div>
                  </div>
                ))}
              </div>

              {showForm && (
                <div className="ap-form-card">
                  <div className="ap-form-hd">
                    <h2 className="ap-form-title">
                      <i className={`bi ${editingId ? "bi-pencil-square" : "bi-plus-circle-fill"}`} />
                      {editingId ? "Edit Menu Item" : "Add New Item"}
                    </h2>
                    <button className="mp-cart-close" onClick={handleCancelEdit} aria-label="Close form"><i className="bi bi-x-lg" /></button>
                  </div>

                  <div className="ap-form-grid">
                    <div className="ap-field ap-field--wide">
                      <label className="ap-label">Item Name *</label>
                      <input name="name" className={`ap-input${errors.name ? " ap-input--err" : ""}`} placeholder="e.g. Grilled Chicken Bowl" value={form.name} onChange={handleChange} />
                      {errors.name && <span className="ap-field-err">{errors.name}</span>}
                    </div>
                    <div className="ap-field ap-field--wide">
                      <label className="ap-label">Description</label>
                      <input name="description" className="ap-input" placeholder="Short description (optional)" value={form.description} onChange={handleChange} />
                    </div>
                    <div className="ap-field ap-field--wide">
                      <label className="ap-label">Image URL <span className="ap-label-hint">(paste any image link)</span></label>
                      <div style={{ display:"flex", gap:10, alignItems:"flex-start" }}>
                        <input name="image_url" className="ap-input" placeholder="https://..." value={form.image_url} onChange={handleChange} />
                        {form.image_url && (
                          <div style={{ flexShrink:0, width:56, height:56, borderRadius:8, overflow:"hidden", border:"1px solid var(--uc-brd)" }}>
                            <img src={form.image_url} alt="preview" style={{ width:"100%", height:"100%", objectFit:"cover" }} onError={e => e.target.style.display="none"} />
                          </div>
                        )}
                      </div>
                      <span className="ap-field-hint">Paste a direct image URL. Preview appears on the right.</span>
                    </div>
                    <div className="ap-field">
                      <label className="ap-label">Category *</label>
                      <select name="category" className="ap-input" value={form.category} onChange={handleChange}>
                        {CATEGORIES.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase()+c.slice(1)}</option>)}
                      </select>
                    </div>
                    <div className="ap-field">
                      <label className="ap-label">Price (EGP) *</label>
                      <div className="ap-input-prefix-wrap">
                        <span className="ap-input-prefix">EGP</span>
                        <input name="price" type="number" min="0" step="0.01"
                          className={`ap-input ap-input--prefixed${errors.price ? " ap-input--err" : ""}`}
                          placeholder="0.00" value={form.price} onChange={handleChange} />
                      </div>
                      {errors.price && <span className="ap-field-err">{errors.price}</span>}
                    </div>
                    <div className="ap-field">
                      <label className="ap-label">Stock Quantity *</label>
                      <input name="stock_qty" type="number" min="0"
                        className={`ap-input${errors.stock_qty ? " ap-input--err" : ""}`}
                        placeholder="0" value={form.stock_qty} onChange={handleChange} />
                      {errors.stock_qty && <span className="ap-field-err">{errors.stock_qty}</span>}
                    </div>
                    <div className="ap-field">
                      <label className="ap-label">Max Order Qty * <span className="ap-label-hint">(per-item cap)</span></label>
                      <input name="max_order_qty" type="number" min="1"
                        className={`ap-input${errors.max_order_qty ? " ap-input--err" : ""}`}
                        placeholder="10" value={form.max_order_qty} onChange={handleChange} />
                      {errors.max_order_qty
                        ? <span className="ap-field-err">{errors.max_order_qty}</span>
                        : <span className="ap-field-hint">Students can&apos;t order more than this per transaction</span>}
                    </div>
                    <div className="ap-field ap-field--toggle">
                      <label className="ap-toggle-label">
                        <span className="ap-label">Visible to students</span>
                        <span className="ap-label-hint">Inactive items are hidden from the menu</span>
                      </label>
                      <button type="button" className={`ap-toggle ${form.active ? "ap-toggle--on" : ""}`}
                        onClick={() => setForm(p => ({ ...p, active: !p.active }))}
                        aria-pressed={form.active} aria-label="Toggle item visibility">
                        <span className="ap-toggle-thumb" />
                      </button>
                    </div>
                  </div>

                  <div className="ap-form-actions">
                    <button className="ap-cancel-btn" onClick={handleCancelEdit} disabled={saving}>Cancel</button>
                    <button className="ap-submit-btn" onClick={handleSubmit} disabled={saving}>
                      {saving ? <><span className="mp-spinner-sm" /> Saving…</> : editingId ? <><i className="bi bi-check-lg" /> Save Changes</> : <><i className="bi bi-plus-circle-fill" /> Publish Item</>}
                    </button>
                  </div>
                </div>
              )}

              {/* Table + controls */}
              <div className="ap-table-card">
                <div className="ap-table-hd">
                  <div className="ap-table-hd-left">
                    <h2 className="ap-form-title"><i className="bi bi-list-ul" /> Menu Items</h2>
                    <span className="ap-count">{filtered.length} item{filtered.length!==1?"s":""}</span>
                  </div>
                  <div className="ap-table-hd-right">
                    <div style={{ position:"relative" }}>
                      <i className="bi bi-search" style={{ position:"absolute", left:11, top:"50%", transform:"translateY(-50%)", color:"var(--uc-muted)", fontSize:13, pointerEvents:"none" }} />
                      <input className="ap-input ap-search" placeholder="Search items…" value={search} onChange={e => setSearch(e.target.value)} style={{ paddingLeft:32 }} />
                    </div>
                    <select className="ap-input ap-filter-select" value={filterCat} onChange={e => setFilterCat(e.target.value)}>
                      <option value="">All categories</option>
                      {CATEGORIES.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase()+c.slice(1)}</option>)}
                    </select>
                    {!showForm && (
                      <button className="ap-add-new-btn" onClick={() => { handleCancelEdit(); setShowForm(true); }}>
                        <i className="bi bi-plus-lg" /> Add Item
                      </button>
                    )}
                  </div>
                </div>

                {loading ? (
                  <div className="mp-loading"><div className="mp-spinner" /><span>Loading items…</span></div>
                ) : filtered.length === 0 ? (
                  <div className="mp-empty"><span style={{ fontSize:40 }}>📋</span><p>No items found.</p></div>
                ) : (
                  <>
                    {/* ── Desktop table ── */}
                    <div className="ap-table-wrap ap-desktop-only">
                      <table className="ap-table">
                        <thead>
                          <tr><th>Image</th><th>Name</th><th>Category</th><th>Price</th><th>Stock</th><th>Max Qty</th><th>Status</th><th>Actions</th></tr>
                        </thead>
                        <tbody>
                          {filtered.map(item => (
                            <tr key={item.id} className={!item.active ? "ap-row--inactive" : ""}>
                              <td>
                                {item.image_url
                                  ? <img src={item.image_url} alt={item.name} style={{ width:44, height:44, borderRadius:8, objectFit:"cover", border:"1px solid var(--uc-brd)" }} onError={e => e.target.style.display="none"} />
                                  : <div style={{ width:44, height:44, borderRadius:8, background:"var(--uc-inp)", border:"1px solid var(--uc-brd)", display:"flex", alignItems:"center", justifyContent:"center", fontSize:20 }}>🍴</div>}
                              </td>
                              <td>
                                <span className="ap-item-name">{item.name}</span>
                                {item.description && <span className="ap-item-desc">{item.description}</span>}
                              </td>
                              <td><span className="ap-cat-badge">{item.category}</span></td>
                              <td className="ap-price">{Number(item.price).toFixed(2)} <small>EGP</small></td>
                              <td><span className={`ap-stock ${item.stock_qty===0?"ap-stock--oos":item.stock_qty<=5?"ap-stock--low":""}`}>{item.stock_qty===0?"Out of stock":item.stock_qty}</span></td>
                              <td className="ap-max-qty"><span className="ap-max-badge">{item.max_order_qty}</span></td>
                              <td><span className={`ap-status ${item.active?"ap-status--active":"ap-status--inactive"}`}><span className="ap-status-dot" />{item.active?"Active":"Inactive"}</span></td>
                              <td>
                                <div className="ap-row-actions">
                                  <button className="ap-edit-btn" onClick={() => handleEdit(item)} title="Edit item"><i className="bi bi-pencil-fill" /></button>
                                  {item.active && <button className="ap-deactivate-btn" onClick={() => setConfirm({ id:item.id, name:item.name })} title="Deactivate"><i className="bi bi-eye-slash-fill" /></button>}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* ── Mobile card list — no horizontal scroll ── */}
                    <div className="ap-card-list ap-mobile-only">
                      {filtered.map(item => (
                        <div key={item.id} className={"ap-mobile-card" + (!item.active ? " ap-mobile-card--inactive" : "")}>
                          <div className="ap-mc-row">
                            <div className="ap-mc-img-name">
                              {item.image_url
                                ? <img src={item.image_url} alt={item.name} className="ap-mc-img" onError={e => e.target.style.display="none"} />
                                : <div className="ap-mc-img ap-mc-img--placeholder">🍴</div>}
                              <div>
                                <span className="ap-item-name" style={{ fontSize:14 }}>{item.name}</span>
                                {item.description && <span className="ap-item-desc">{item.description}</span>}
                              </div>
                            </div>
                            <div className="ap-mc-actions">
                              <button className="ap-edit-btn" onClick={() => handleEdit(item)} title="Edit"><i className="bi bi-pencil-fill" /></button>
                              {item.active && <button className="ap-deactivate-btn" onClick={() => setConfirm({ id:item.id, name:item.name })} title="Deactivate"><i className="bi bi-eye-slash-fill" /></button>}
                            </div>
                          </div>
                          <div className="ap-mc-row ap-mc-row--muted">
                            <span className="ap-cat-badge">{item.category}</span>
                            <span className={`ap-status ${item.active?"ap-status--active":"ap-status--inactive"}`}><span className="ap-status-dot" />{item.active?"Active":"Inactive"}</span>
                          </div>
                          <div className="ap-mc-row ap-mc-row--muted">
                            <span className="ap-price" style={{ fontSize:15 }}>{Number(item.price).toFixed(2)} <small>EGP</small></span>
                            <div style={{ display:"flex", gap:12, fontSize:12, color:"var(--uc-muted)" }}>
                              <span>Stock: <strong style={{ color: item.stock_qty===0?"var(--uc-danger)":item.stock_qty<=5?"var(--uc-warn)":"var(--uc-text)" }}>{item.stock_qty===0?"OOS":item.stock_qty}</strong></span>
                              <span>Max: <strong style={{ color:"var(--uc-text)" }}>{item.max_order_qty}</strong></span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </>
          )}

        </div>

        {confirm && (
          <ConfirmModal
            message={`Deactivate "${confirm.name}"? It will be hidden from students immediately.`}
            onConfirm={confirmDeactivate}
            onCancel={() => setConfirm(null)}
          />
        )}
        <Toast toasts={toasts} removeToast={removeToast} />
      </div>
    </>
  );
}

const ADMIN_CSS = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --uc-bg:#0f172a; --uc-card:rgba(30,58,95,0.4);
    --uc-brd:rgba(180,142,50,0.15); --uc-brd-hi:rgba(180,142,50,0.5);
    --uc-acc:#b48e32; --uc-acc2:#22c993; --uc-gold:#b48e32;
    --uc-text:#f1f5f9; --uc-muted:#94a3b8;
    --uc-danger:#f56565; --uc-warn:#f6ad55;
    --uc-inp:rgba(255,255,255,0.05);
    --uc-r:16px; --uc-rs:10px;
    --fd:'Sora',sans-serif; --fb:'Inter',sans-serif;
    --glass-bg:rgba(30,58,95,0.6);
    --glass-border:rgba(180,142,50,0.2);
    --nav-total-h: 68px;
  }
  .ap-page { min-height:100vh; background:var(--uc-bg); color:var(--uc-text); font-family:var(--fb); position:relative; overflow-x:hidden; }
  .uc-mesh { position:fixed; inset:0; z-index:0; pointer-events:none; overflow:hidden; }
  .uc-mesh::before { content:''; position:absolute; inset:-40%;
    background: radial-gradient(ellipse 65% 55% at 15% 25%,rgba(180,142,50,.08) 0%,transparent 60%),
                radial-gradient(ellipse 45% 55% at 85% 75%,rgba(180,142,50,.05) 0%,transparent 55%),
                radial-gradient(ellipse 45% 55% at 55% 5%, rgba(220,38,38,.03) 0%,transparent 50%);
    animation:meshMove 18s ease-in-out infinite alternate; }
  @keyframes meshMove{from{transform:translate(0,0) rotate(0)}to{transform:translate(2%,1.5%) rotate(2deg)}}
  .uc-grid { position:fixed; inset:0; z-index:0; pointer-events:none;
    background-image:linear-gradient(rgba(180,142,50,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(180,142,50,.03) 1px,transparent 1px);
    background-size:52px 52px; }

  /* ── Navbar ── */
  .mp-nav {
    position:sticky; top:0; z-index:200;
    display:flex; align-items:center; justify-content:space-between;
    padding:0 clamp(12px,3vw,32px); height:60px; gap:8px;
    background:rgba(15,23,42,.98); backdrop-filter:blur(20px); border-bottom:1px solid var(--uc-brd);
  }
  .mp-nav-brand { display:flex; align-items:center; gap:10px; flex-shrink:0; flex-wrap:nowrap; }
  .mp-nav-logo { width:36px; height:36px; border-radius:10px; background:rgba(180,142,50,0.1); border:1px solid var(--uc-brd); display:flex; align-items:center; justify-content:center; flex-shrink:0; }
  .mp-nav-brand-text { display:flex; flex-direction:column; gap:1px; }
  .mp-nav-name { font-family:var(--fd); font-size:15px; font-weight:700; letter-spacing:-.02em; color:var(--uc-gold); line-height:1; }
  .mp-nav-uni { font-size:9px; color:var(--uc-muted); letter-spacing:.02em; }
  .ap-admin-tag { font-size:10px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; background:rgba(180,142,50,.15); color:var(--uc-gold); border:1px solid rgba(180,142,50,.3); border-radius:100px; padding:3px 9px; white-space:nowrap; }

  /* Desktop tabs — hidden below 768px; mp-mobile-tabs takes over */
  .mp-nav-tabs { display:none; }
  @media(min-width:768px) {
    .mp-nav-tabs { display:flex; gap:4px; background:var(--uc-inp); border:1px solid var(--uc-brd); border-radius:var(--uc-rs); padding:3px; }
  }
  .mp-nav-tab { display:flex; align-items:center; gap:5px; background:none; border:none; border-radius:8px; color:var(--uc-muted); font-family:var(--fb); font-size:12px; font-weight:600; padding:6px 12px; cursor:pointer; transition:all .2s; white-space:nowrap; }
  .mp-nav-tab span { display:none; }
  @media(min-width:900px) { .mp-nav-tab span { display:inline; } }
  .mp-nav-tab:hover { color:var(--uc-text); background:rgba(180,142,50,.08); }
  .mp-nav-tab--active { background:rgba(180,142,50,.15); color:var(--uc-gold); box-shadow:0 1px 4px rgba(0,0,0,.35); }

  /* ── Mobile tabs bar — same as MenuPage ── */
  .mp-mobile-tabs {
    position:sticky; top:60px; z-index:190;
    display:flex; align-items:center; gap:6px;
    padding:6px clamp(12px,3vw,24px); height:44px;
    background:rgba(15,23,42,.98); backdrop-filter:blur(16px);
    border-bottom:1px solid var(--uc-brd);
    overflow-x:auto; -webkit-overflow-scrolling:touch; scrollbar-width:none;
  }
  .mp-mobile-tabs::-webkit-scrollbar { display:none; }
  @media(min-width:768px) { .mp-mobile-tabs { display:none; } }
  .mp-mobile-tab { display:flex; align-items:center; gap:6px; flex-shrink:0; background:var(--uc-inp); border:1px solid var(--uc-brd); border-radius:100px; color:var(--uc-muted); font-family:var(--fb); font-size:12px; font-weight:600; padding:6px 14px; cursor:pointer; transition:all .2s; white-space:nowrap; }
  .mp-mobile-tab:hover { border-color:var(--uc-gold); color:var(--uc-text); }
  .mp-mobile-tab--active { background:rgba(180,142,50,.15); border-color:var(--uc-gold); color:var(--uc-gold); }

  .mp-nav-actions { display:flex; align-items:center; gap:6px; flex-shrink:0; }
  .mp-logout-btn { width:36px; height:36px; display:flex; align-items:center; justify-content:center; background:none; border:1px solid var(--uc-brd); border-radius:var(--uc-rs); color:var(--uc-muted); cursor:pointer; font-size:15px; transition:all .2s; }
  .mp-logout-btn:hover { border-color:var(--uc-danger); color:var(--uc-danger); }

  /* ── Body ── */
  .ap-body { position:relative; z-index:1; padding:clamp(14px,3vw,28px); display:flex; flex-direction:column; gap:18px; }

  /* ── Stats ── */
  .ap-stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; }
  .ap-stat { display:flex; align-items:center; gap:12px; background:var(--glass-bg); backdrop-filter:blur(12px); border:1px solid var(--glass-border); border-radius:var(--uc-r); padding:16px; transition:border-color .25s,transform .2s; }
  .ap-stat:hover { border-color:var(--uc-brd-hi); transform:translateY(-2px); }
  .ap-stat i { font-size:22px; flex-shrink:0; }
  .ap-stat-val { font-family:var(--fd); font-size:22px; font-weight:700; line-height:1; }
  .ap-stat-label { font-size:10px; color:var(--uc-muted); margin-top:3px; }

  /* ── Form card ── */
  .ap-form-card { background:var(--glass-bg); backdrop-filter:blur(16px); border:1px solid var(--uc-brd-hi); border-radius:var(--uc-r); padding:clamp(16px,3vw,24px); animation:fadeUp .3s ease both; box-shadow:0 8px 32px rgba(0,0,0,.3); }
  @keyframes fadeUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
  .ap-form-hd { display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; }
  .ap-form-title { font-family:var(--fd); font-size:16px; font-weight:700; display:flex; align-items:center; gap:8px; color:var(--uc-gold); }
  .mp-cart-close { width:32px; height:32px; display:flex; align-items:center; justify-content:center; background:none; border:1px solid var(--uc-brd); border-radius:var(--uc-rs); color:var(--uc-muted); cursor:pointer; font-size:13px; transition:all .2s; }
  .mp-cart-close:hover { border-color:var(--uc-danger); color:var(--uc-danger); }
  .ap-form-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:14px; margin-bottom:18px; }
  .ap-field { display:flex; flex-direction:column; gap:5px; }
  .ap-field--wide { grid-column:1/-1; }
  .ap-field--toggle { flex-direction:row; align-items:center; justify-content:space-between; grid-column:1/-1; }
  .ap-label { font-size:11px; font-weight:600; letter-spacing:.07em; text-transform:uppercase; color:var(--uc-muted); }
  .ap-label-hint { font-size:10px; letter-spacing:0; text-transform:none; color:var(--uc-muted); opacity:.7; margin-left:4px; }
  .ap-toggle-label { display:flex; flex-direction:column; gap:3px; }
  .ap-input { background:rgba(255,255,255,.05); border:1px solid var(--uc-brd); border-radius:var(--uc-rs); color:var(--uc-text); font-family:var(--fb); font-size:13.5px; padding:10px 13px; outline:none; transition:border-color .2s,box-shadow .2s; width:100%; -webkit-appearance:none; }
  .ap-input::placeholder { color:rgba(148,163,184,.5); }
  .ap-input:focus { border-color:var(--uc-gold); box-shadow:0 0 0 3px rgba(180,142,50,.15); }
  .ap-input--err { border-color:var(--uc-danger) !important; }
  .ap-input-prefix-wrap { position:relative; display:flex; align-items:center; }
  .ap-input-prefix { position:absolute; left:12px; font-size:11px; font-weight:700; color:var(--uc-gold); pointer-events:none; letter-spacing:.04em; }
  .ap-input--prefixed { padding-left:44px; }
  .ap-field-err { font-size:11px; color:var(--uc-danger); }
  .ap-field-hint { font-size:11px; color:var(--uc-muted); opacity:.75; }
  .ap-toggle { width:46px; height:26px; border-radius:13px; position:relative; flex-shrink:0; background:var(--uc-inp); border:1px solid var(--uc-brd); cursor:pointer; transition:background .2s,border-color .2s; }
  .ap-toggle--on { background:rgba(180,142,50,.25); border-color:var(--uc-gold); }
  .ap-toggle-thumb { position:absolute; top:3px; left:3px; width:18px; height:18px; border-radius:50%; background:var(--uc-muted); transition:transform .2s,background .2s; }
  .ap-toggle--on .ap-toggle-thumb { transform:translateX(20px); background:var(--uc-gold); }
  .ap-form-actions { display:flex; justify-content:flex-end; gap:10px; flex-wrap:wrap; }
  .ap-cancel-btn { background:rgba(255,255,255,.05); border:1px solid var(--uc-brd); border-radius:var(--uc-rs); color:var(--uc-muted); font-family:var(--fb); font-size:13px; font-weight:600; padding:10px 20px; cursor:pointer; transition:all .2s; }
  .ap-cancel-btn:hover { border-color:var(--uc-gold); color:var(--uc-text); }
  .ap-submit-btn { display:flex; align-items:center; gap:7px; background:linear-gradient(135deg,var(--uc-gold),#8b6914); border:none; border-radius:var(--uc-rs); color:#0f172a; font-family:var(--fb); font-size:13px; font-weight:700; padding:10px 22px; cursor:pointer; box-shadow:0 4px 18px rgba(180,142,50,.3); transition:transform .15s,opacity .2s; }
  .ap-submit-btn:hover:not(:disabled) { transform:translateY(-1px); }
  .ap-submit-btn:disabled { opacity:.45; cursor:not-allowed; transform:none; }

  /* ── Table card ── */
  .ap-table-card { background:var(--glass-bg); backdrop-filter:blur(12px); border:1px solid var(--glass-border); border-radius:var(--uc-r); overflow:hidden; }
  .ap-table-hd { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px; padding:16px 18px; border-bottom:1px solid var(--uc-brd); }
  .ap-table-hd-left { display:flex; align-items:center; gap:8px; }
  .ap-count { font-size:11px; color:var(--uc-muted); background:rgba(255,255,255,.05); border:1px solid var(--uc-brd); border-radius:100px; padding:3px 10px; }
  .ap-table-hd-right { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
  .ap-search { width:160px; padding:8px 12px; font-size:12.5px; }
  .ap-filter-select { width:130px; padding:8px 12px; font-size:12.5px; }
  @media(max-width:480px) { .ap-search { width:120px; } .ap-filter-select { width:110px; } }
  .ap-add-new-btn { display:flex; align-items:center; gap:6px; background:linear-gradient(135deg,var(--uc-gold),#8b6914); border:none; border-radius:var(--uc-rs); color:#0f172a; font-family:var(--fb); font-size:12.5px; font-weight:700; padding:8px 16px; cursor:pointer; white-space:nowrap; box-shadow:0 3px 14px rgba(180,142,50,.28); transition:opacity .2s; touch-action:manipulation; }
  .ap-add-new-btn:hover { opacity:.88; }

  /* ── Responsive layout switching ── */
  /*
   * FIX: Both ap-desktop-only and ap-mobile-only use !important on their
   * media-query overrides to prevent CSS specificity conflicts from causing
   * both the table and card list to render simultaneously.
   */
  .ap-desktop-only { display:none !important; }
  @media(min-width:768px) { .ap-desktop-only { display:block !important; } }

  .ap-mobile-only { display:block !important; }
  @media(min-width:768px) { .ap-mobile-only { display:none !important; } }

  /* ── Desktop table ── */
  .ap-table-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
  .ap-table { width:100%; border-collapse:collapse; }
  .ap-table th { background:rgba(180,142,50,.05); padding:11px 15px; font-size:10px; font-weight:700; letter-spacing:.07em; text-transform:uppercase; color:var(--uc-gold); text-align:left; white-space:nowrap; border-bottom:1px solid var(--uc-brd); }
  .ap-table td { padding:13px 15px; border-bottom:1px solid rgba(255,255,255,.04); font-size:13px; vertical-align:middle; }
  .ap-table tr:last-child td { border-bottom:none; }
  .ap-table tr:hover td { background:rgba(180,142,50,.03); }
  .ap-row--inactive td { opacity:.55; }

  /* ── Mobile card list ── */
  .ap-card-list { display:flex; flex-direction:column; gap:0; }
  .ap-mobile-card { padding:14px 16px; border-bottom:1px solid rgba(255,255,255,.05); display:flex; flex-direction:column; gap:9px; transition:background .15s; }
  .ap-mobile-card:last-child { border-bottom:none; }
  .ap-mobile-card:hover { background:rgba(180,142,50,.03); }
  .ap-mobile-card--inactive { opacity:.55; }
  .ap-mc-row { display:flex; align-items:center; justify-content:space-between; gap:8px; }
  .ap-mc-row--muted { color:var(--uc-muted); font-size:12px; }
  .ap-mc-img-name { display:flex; align-items:center; gap:10px; flex:1; min-width:0; }
  .ap-mc-img { width:40px; height:40px; border-radius:8px; object-fit:cover; border:1px solid var(--uc-brd); flex-shrink:0; }
  .ap-mc-img--placeholder { display:flex; align-items:center; justify-content:center; background:var(--uc-inp); font-size:18px; }
  .ap-mc-actions { display:flex; gap:6px; flex-shrink:0; }
  .ap-mc-code { font-family:monospace; letter-spacing:.06em; font-weight:700; font-size:14px; color:var(--uc-text); }
  .ap-mc-deactivate { width:100%; display:flex; align-items:center; justify-content:center; gap:6px; background:rgba(246,173,85,.08); border:1px solid rgba(246,173,85,.2); border-radius:var(--uc-rs); color:var(--uc-warn); font-family:var(--fb); font-size:12px; font-weight:600; padding:8px; cursor:pointer; transition:all .2s; touch-action:manipulation; }
  .ap-mc-deactivate:hover { background:rgba(246,173,85,.16); }

  /* ── Shared item/status elements ── */
  .ap-item-name { display:block; font-weight:600; font-size:13px; margin-bottom:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ap-item-desc { display:block; font-size:11px; color:var(--uc-muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ap-cat-badge { font-size:10px; font-weight:600; padding:3px 9px; border-radius:100px; background:rgba(180,142,50,.12); color:var(--uc-gold); border:1px solid rgba(180,142,50,.25); text-transform:capitalize; white-space:nowrap; }
  .ap-price { font-family:var(--fd); font-size:14px; font-weight:700; color:var(--uc-gold); }
  .ap-price small { font-size:10px; font-weight:500; opacity:.6; }
  .ap-stock { font-size:12.5px; font-weight:600; }
  .ap-stock--oos { color:var(--uc-danger); }
  .ap-stock--low { color:var(--uc-warn); }
  .ap-max-badge { display:inline-flex; align-items:center; justify-content:center; width:30px; height:30px; border-radius:var(--uc-rs); background:rgba(255,255,255,.05); border:1px solid var(--uc-brd); font-size:12px; font-weight:700; }
  .ap-status { display:inline-flex; align-items:center; gap:5px; font-size:12px; font-weight:600; white-space:nowrap; }
  .ap-status-dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
  .ap-status--active .ap-status-dot  { background:var(--uc-acc2); box-shadow:0 0 6px var(--uc-acc2); }
  .ap-status--inactive .ap-status-dot { background:var(--uc-muted); }
  .ap-status--active  { color:var(--uc-acc2); }
  .ap-status--inactive { color:var(--uc-muted); }
  .ap-row-actions { display:flex; gap:6px; }
  .ap-edit-btn, .ap-deactivate-btn { width:32px; height:32px; display:flex; align-items:center; justify-content:center; background:none; border:1px solid var(--uc-brd); border-radius:var(--uc-rs); cursor:pointer; font-size:13px; transition:all .2s; touch-action:manipulation; }
  .ap-edit-btn { color:var(--uc-gold); }
  .ap-edit-btn:hover { background:rgba(180,142,50,.12); border-color:var(--uc-gold); }
  .ap-deactivate-btn { color:var(--uc-warn); }
  .ap-deactivate-btn:hover { background:rgba(246,173,85,.1); border-color:var(--uc-warn); }

  /* ── Section tabs ── */
  .ap-section-tabs { display:flex; gap:4px; background:rgba(255,255,255,.03); border:1px solid var(--uc-brd); border-radius:var(--uc-r); padding:5px; align-self:flex-start; overflow-x:auto; -webkit-overflow-scrolling:touch; scrollbar-width:none; }
  .ap-section-tabs::-webkit-scrollbar { display:none; }
  .ap-section-tab { display:flex; align-items:center; gap:7px; background:none; border:none; border-radius:12px; color:var(--uc-muted); font-family:var(--fb); font-size:13px; font-weight:600; padding:9px 18px; cursor:pointer; transition:all .2s; white-space:nowrap; }
  .ap-section-tab:hover { color:var(--uc-text); background:rgba(180,142,50,.08); }
  .ap-section-tab--active { background:rgba(180,142,50,.15); color:var(--uc-gold); box-shadow:0 1px 6px rgba(0,0,0,.4); }

  /* ── Modal ── */
  .ap-danger-btn { background:linear-gradient(135deg,var(--uc-danger),#c53030); border:none; border-radius:var(--uc-rs); color:#fff; font-family:var(--fb); font-size:13.5px; font-weight:700; padding:11px 24px; cursor:pointer; transition:opacity .2s; }
  .ap-danger-btn:hover { opacity:.88; }
  .ap-modal-backdrop { position:fixed; inset:0; background:rgba(0,0,0,.7); z-index:500; }
  .ap-modal { position:fixed; inset:0; z-index:501; display:flex; align-items:center; justify-content:center; padding:20px; }
  .ap-modal-inner { background:var(--glass-bg); backdrop-filter:blur(20px); border:1px solid var(--glass-border); border-radius:var(--uc-r); padding:28px; max-width:380px; width:100%; text-align:center; box-shadow:0 24px 56px rgba(0,0,0,.6); animation:fadeUp .25s ease both; }
  .ap-modal-icon { font-size:34px; color:var(--uc-warn); margin-bottom:12px; }
  .ap-modal-title { font-family:var(--fd); font-size:17px; font-weight:700; margin-bottom:8px; color:var(--uc-gold); }
  .ap-modal-msg { font-size:13px; color:var(--uc-muted); line-height:1.5; margin-bottom:22px; }
  .ap-modal-actions { display:flex; gap:10px; justify-content:center; }

  /* ── Misc ── */
  .mp-loading { display:flex; flex-direction:column; align-items:center; gap:14px; padding:60px 20px; color:var(--uc-muted); }
  .mp-spinner { width:32px; height:32px; border:3px solid var(--uc-brd); border-top-color:var(--uc-gold); border-radius:50%; animation:spin .7s linear infinite; }
  .mp-spinner-sm { display:inline-block; width:14px; height:14px; border:2px solid rgba(255,255,255,.3); border-top-color:#fff; border-radius:50%; animation:spin .7s linear infinite; }
  @keyframes spin{to{transform:rotate(360deg)}}
  .mp-empty { display:flex; flex-direction:column; align-items:center; gap:12px; padding:60px 20px; color:var(--uc-muted); }
  .uc-toast { display:flex; align-items:center; gap:10px; padding:12px 18px; border-radius:var(--uc-rs); font-size:13px; font-weight:500; min-width:240px; max-width:340px; box-shadow:0 8px 28px rgba(0,0,0,.5); animation:fadeUp .3s ease both; backdrop-filter:blur(12px); }
  .uc-toast--success { background:rgba(180,142,50,.15); border:1px solid rgba(180,142,50,.3); color:var(--uc-gold); }
  .uc-toast--warn    { background:#2b1f0a; border:1px solid rgba(246,173,85,.3);  color:var(--uc-warn); }
  .uc-toast--error   { background:#2b0e0e; border:1px solid rgba(245,101,101,.3); color:var(--uc-danger); }
  .uc-toast-close { margin-left:auto; background:none; border:none; cursor:pointer; color:inherit; opacity:.7; font-size:16px; padding:0; }
`;