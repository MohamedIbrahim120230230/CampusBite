// ============================================================
// frontend/stock/StockDashboard.jsx
// Stock & Resilience — Member 4 (feature/stock-resilience)
// Covers: FR11, FR19, FR21, FR22, FR24, FR25, FR41, FR54
// UI: React + Bootstrap 5 CSS
// ============================================================

import React, { useState, useEffect, useCallback, useRef } from "react";

// ── Inject Bootstrap 5 + Bootstrap Icons ─────────────────────
if (typeof document !== "undefined") {
  if (!document.querySelector('link[href*="bootstrap@5"]')) {
    const bs = document.createElement("link");
    bs.rel  = "stylesheet";
    bs.href = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css";
    document.head.appendChild(bs);
  }
  if (!document.querySelector('link[href*="bootstrap-icons"]')) {
    const bi = document.createElement("link");
    bi.rel  = "stylesheet";
    bi.href = "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css";
    document.head.appendChild(bi);
  }
}

// ── Brand CSS variables (matches auth member's palette) ───────
const GLOBAL_CSS = `
  :root {
    --uc-primary:   #2563eb;
    --uc-success:   #16a34a;
    --uc-warning:   #d97706;
    --uc-danger:    #dc2626;
    --uc-muted:     #6b7280;
    --uc-surface:   #f8fafc;
    --uc-border:    #e2e8f0;
    --uc-radius:    12px;
    --uc-shadow:    0 1px 4px rgba(0,0,0,.08);
  }
  .uc-card {
    background: #fff;
    border: 1px solid var(--uc-border);
    border-radius: var(--uc-radius);
    box-shadow: var(--uc-shadow);
  }
  .uc-badge-available   { background: #dcfce7; color: #15803d; }
  .uc-badge-low         { background: #fef9c3; color: #854d0e; }
  .uc-badge-locked      { background: #dbeafe; color: #1d4ed8; }
  .uc-badge-outofstock  { background: #fee2e2; color: #b91c1c; }
  .uc-badge-flagged     { background: #fef3c7; color: #92400e; }
  .uc-stock-bar-track {
    height: 6px; border-radius: 99px;
    background: var(--uc-border); overflow: hidden;
  }
  .uc-stock-bar-fill {
    height: 100%; border-radius: 99px;
    transition: width .4s ease;
  }
  .uc-tab-btn {
    border: none; background: none; padding: .5rem 1rem;
    border-bottom: 2px solid transparent;
    color: var(--uc-muted); font-weight: 500; cursor: pointer;
    transition: .2s;
  }
  .uc-tab-btn.active {
    border-bottom-color: var(--uc-primary);
    color: var(--uc-primary);
  }
  .uc-pulse { animation: uc-pulse 2s infinite; }
  @keyframes uc-pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: .4; }
  }
  .uc-lock-chip {
    font-size: .72rem; padding: 2px 8px;
    border-radius: 99px; font-weight: 600;
    background: #dbeafe; color: #1e40af;
  }
  .uc-stat-card {
    border-radius: var(--uc-radius);
    padding: 1.25rem; border: 1px solid var(--uc-border);
    background: #fff;
  }
`;

// ── API helper ────────────────────────────────────────────────
const API_BASE = "/api/v1/stock";

async function apiFetch(path, options = {}) {
  const token = localStorage.getItem("jwt_token");
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  const text = await res.text();
  if (!text) throw { code: "EMPTY_RESPONSE", message: "Server returned no data." };
  let json;
  try { json = JSON.parse(text); }
  catch { throw { code: "INVALID_JSON", message: "Unexpected server response." }; }
  if (!res.ok) throw json.error ?? { code: "HTTP_ERROR", message: `HTTP ${res.status}` };
  return json.data;
}

// ── Stock colour logic ────────────────────────────────────────
function stockColor(available, total) {
  if (available <= 0)          return "#ef4444";
  if (available / total < 0.2) return "#f59e0b";
  return "#22c55e";
}

function stockLabel(available, total) {
  if (available <= 0)          return { label: "Out of Stock", cls: "uc-badge-outofstock" };
  if (available / total < 0.2) return { label: "Low Stock",   cls: "uc-badge-low" };
  return                                { label: "Available",  cls: "uc-badge-available" };
}

// ─────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────

// ── Toast notification ────────────────────────────────────────
function Toast({ toasts, dismiss }) {
  return (
    <div
      aria-live="polite"
      style={{ position: "fixed", bottom: 24, right: 24, zIndex: 9999, maxWidth: 360 }}
    >
      {toasts.map(t => (
        <div
          key={t.id}
          className={`alert alert-${t.type} alert-dismissible shadow-sm mb-2 d-flex align-items-center gap-2`}
          style={{ borderRadius: 10, fontSize: ".9rem" }}
        >
          <i className={`bi bi-${t.type === "success" ? "check-circle" : t.type === "warning" ? "exclamation-triangle" : "x-circle"}`} />
          <span>{t.message}</span>
          <button type="button" className="btn-close ms-auto" onClick={() => dismiss(t.id)} />
        </div>
      ))}
    </div>
  );
}

// ── Stock bar ─────────────────────────────────────────────────
function StockBar({ available, total, locked }) {
  const pct  = total > 0 ? Math.max(0, (available / total) * 100) : 0;
  const lpct = total > 0 ? Math.min(100, (locked / total) * 100)  : 0;
  return (
    <div>
      <div className="uc-stock-bar-track">
        <div
          className="uc-stock-bar-fill"
          style={{ width: `${pct}%`, background: stockColor(available, total) }}
        />
      </div>
      <div className="d-flex justify-content-between mt-1" style={{ fontSize: ".72rem", color: "#6b7280" }}>
        <span>{available} available</span>
        {locked > 0 && <span className="uc-lock-chip"><i className="bi bi-lock-fill me-1" />{locked} locked</span>}
        <span>{total} total</span>
      </div>
    </div>
  );
}

// ── Stat card ─────────────────────────────────────────────────
function StatCard({ icon, label, value, color = "#2563eb", sub }) {
  return (
    <div className="uc-stat-card">
      <div className="d-flex align-items-center gap-2 mb-1">
        <i className={`bi bi-${icon}`} style={{ color, fontSize: "1.2rem" }} />
        <span style={{ fontSize: ".8rem", color: "#6b7280", fontWeight: 500 }}>{label}</span>
      </div>
      <div style={{ fontSize: "1.7rem", fontWeight: 700, color }}>{value}</div>
      {sub && <div style={{ fontSize: ".75rem", color: "#9ca3af", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Main Dashboard
// ─────────────────────────────────────────────────────────────

export default function StockDashboard() {
  const [tab,         setTab]         = useState("overview");   // overview | locks | flagged | config | ledger
  const [items,       setItems]       = useState([]);
  const [activeLocks, setActiveLocks] = useState([]);
  const [flagged,     setFlagged]     = useState([]);
  const [config,      setConfig]      = useState([]);
  const [ledger,      setLedger]      = useState({ transactions: [], total: 0 });
  const [ledgerItem,  setLedgerItem]  = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [toasts,      setToasts]      = useState([]);
  const [search,      setSearch]      = useState("");
  const [restockModal, setRestockModal] = useState(null);  // menu_item row
  const [correctModal, setCorrectModal] = useState(null);
  const [restockQty,   setRestockQty]   = useState(1);
  const [restockNote,  setRestockNote]  = useState("");
  const [correctQty,   setCorrectQty]   = useState(0);
  const [correctNote,  setCorrectNote]  = useState("");
  const [configEdit,   setConfigEdit]   = useState({});     // key → value being edited
  const toastId = useRef(0);

  // ── Toast helpers ──────────────────────────────────────────
  const addToast = useCallback((message, type = "success") => {
    const id = ++toastId.current;
    setToasts(t => [...t, { id, message, type }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4000);
  }, []);
  const dismissToast = useCallback(id => setToasts(t => t.filter(x => x.id !== id)), []);

  // ── Data loaders ───────────────────────────────────────────
  const loadItems = useCallback(async () => {
    try {
      const data = await apiFetch("/availability");
      setItems(data);
    } catch (e) { addToast(e.message || "Failed to load stock.", "danger"); }
  }, [addToast]);

  const loadLocks = useCallback(async () => {
    try {
      const data = await apiFetch("/locks/active");
      setActiveLocks(data.active_locks || []);
    } catch (e) { addToast(e.message || "Failed to load locks.", "danger"); }
  }, [addToast]);

  const loadFlagged = useCallback(async () => {
    try {
      const data = await apiFetch("/flagged?status=PENDING");
      setFlagged(Array.isArray(data) ? data : []);
    } catch (e) { addToast(e.message || "Failed to load flagged orders.", "danger"); }
  }, [addToast]);

  const loadConfig = useCallback(async () => {
    try {
      const data = await apiFetch("/config");
      setConfig(Array.isArray(data) ? data : []);
    } catch (e) { addToast(e.message || "Failed to load config.", "danger"); }
  }, [addToast]);

  const loadLedger = useCallback(async (itemId) => {
    if (!itemId) return;
    try {
      const data = await apiFetch(`/transactions/${itemId}`);
      setLedger(data);
    } catch (e) { addToast(e.message || "Failed to load ledger.", "danger"); }
  }, [addToast]);

  // ── Initial load ───────────────────────────────────────────
  useEffect(() => {
    loadItems();
    // Auto-refresh every 30 seconds (FR36-style live update)
    const id = setInterval(loadItems, 30000);
    return () => clearInterval(id);
  }, [loadItems]);

  useEffect(() => {
    if (tab === "locks")   loadLocks();
    if (tab === "flagged") loadFlagged();
    if (tab === "config")  loadConfig();
    if (tab === "ledger" && ledgerItem) loadLedger(ledgerItem);
  }, [tab, loadLocks, loadFlagged, loadConfig, loadLedger, ledgerItem]);

  // ── Restock submit ─────────────────────────────────────────
  const handleRestock = async () => {
    if (!restockModal) return;
    setLoading(true);
    try {
      const data = await apiFetch(`/${restockModal.menu_item_id}/restock`, {
        method: "POST",
        body: JSON.stringify({ quantity: restockQty, note: restockNote || null }),
      });
      addToast(`Restocked "${restockModal.item_name}" — new total: ${data.new_stock_qty}`, "success");
      setRestockModal(null);
      setRestockQty(1);
      setRestockNote("");
      loadItems();
    } catch (e) {
      addToast(e.message || "Restock failed.", "danger");
    } finally { setLoading(false); }
  };

  // ── Correction submit ──────────────────────────────────────
  const handleCorrection = async () => {
    if (!correctModal) return;
    setLoading(true);
    try {
      const data = await apiFetch(`/${correctModal.menu_item_id}/correction`, {
        method: "POST",
        body: JSON.stringify({ new_quantity: correctQty, note: correctNote }),
      });
      addToast(
        `Stock corrected for "${correctModal.item_name}": ${data.old_qty} → ${data.new_qty}`,
        "warning",
      );
      setCorrectModal(null);
      setCorrectQty(0);
      setCorrectNote("");
      loadItems();
    } catch (e) {
      addToast(e.message || "Correction failed.", "danger");
    } finally { setLoading(false); }
  };

  // ── Flagged order review ───────────────────────────────────
  const handleReview = async (flaggedId, action, reason) => {
    setLoading(true);
    try {
      await apiFetch(`/flagged/${flaggedId}/review`, {
        method: "POST",
        body: JSON.stringify({ action, reason: reason || null }),
      });
      addToast(`Order ${action === "approve" ? "approved" : "rejected"} successfully.`, "success");
      loadFlagged();
    } catch (e) {
      addToast(e.message || "Review failed.", "danger");
    } finally { setLoading(false); }
  };

  // ── Config update ──────────────────────────────────────────
  const handleConfigSave = async (key) => {
    const value = configEdit[key];
    if (value === undefined) return;
    setLoading(true);
    try {
      await apiFetch(`/config/${key}`, {
        method: "PATCH",
        body: JSON.stringify({ value: String(value) }),
      });
      addToast(`Config "${key}" updated.`, "success");
      setConfigEdit(e => { const c = {...e}; delete c[key]; return c; });
      loadConfig();
    } catch (e) {
      addToast(e.message || "Config update failed.", "danger");
    } finally { setLoading(false); }
  };

  // ── Expire stale locks ─────────────────────────────────────
  const handleExpireLocks = async () => {
    setLoading(true);
    try {
      const data = await apiFetch("/locks/expire", { method: "POST" });
      addToast(`Expired ${data.locks_expired} lock(s). Auto-cancelled ${data.flagged_orders_cancelled} flagged order(s).`, "warning");
      loadLocks();
    } catch (e) {
      addToast(e.message || "Expire job failed.", "danger");
    } finally { setLoading(false); }
  };

  // ── Computed stats ─────────────────────────────────────────
  const totalItems    = items.length;
  const outOfStock    = items.filter(i => i.available_qty <= 0).length;
  const lowStock      = items.filter(i => i.available_qty > 0 && i.available_qty / (i.total_qty || 1) < 0.2).length;
  const totalLocked   = items.reduce((s, i) => s + (i.locked_qty || 0), 0);

  // ── Filtered items ─────────────────────────────────────────
  const filtered = items.filter(i =>
    i.item_name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <>
      <style>{GLOBAL_CSS}</style>

      {/* ── Header ─────────────────────────────────────────── */}
      <div className="px-3 px-md-4 pt-4 pb-2">
        <div className="d-flex align-items-center gap-3 mb-1">
          <div
            style={{
              width: 42, height: 42, borderRadius: 10,
              background: "linear-gradient(135deg,#2563eb,#1d4ed8)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >
            <i className="bi bi-boxes text-white" style={{ fontSize: "1.2rem" }} />
          </div>
          <div>
            <h5 className="mb-0 fw-bold" style={{ color: "#111827" }}>Stock & Resilience</h5>
            <small style={{ color: "#6b7280" }}>Member 4 — feature/stock-resilience</small>
          </div>
          <button
            className="btn btn-sm btn-outline-secondary ms-auto"
            onClick={loadItems}
            title="Refresh"
          >
            <i className="bi bi-arrow-clockwise" /> Refresh
          </button>
        </div>
      </div>

      {/* ── Stat Cards ─────────────────────────────────────── */}
      <div className="px-3 px-md-4 pb-3">
        <div className="row g-3">
          <div className="col-6 col-md-3">
            <StatCard icon="box-seam" label="Total Items" value={totalItems} color="#2563eb" />
          </div>
          <div className="col-6 col-md-3">
            <StatCard icon="x-circle" label="Out of Stock" value={outOfStock} color="#dc2626"
              sub={outOfStock > 0 ? "Action needed" : "All stocked"} />
          </div>
          <div className="col-6 col-md-3">
            <StatCard icon="exclamation-triangle" label="Low Stock" value={lowStock} color="#d97706"
              sub="< 20% remaining" />
          </div>
          <div className="col-6 col-md-3">
            <StatCard icon="lock" label="Locked Units" value={totalLocked} color="#7c3aed"
              sub="Active stock locks" />
          </div>
        </div>
      </div>

      {/* ── Tabs ───────────────────────────────────────────── */}
      <div className="px-3 px-md-4">
        <div className="d-flex gap-1 border-bottom mb-3" style={{ overflowX: "auto" }}>
          {[
            { key: "overview", icon: "grid",           label: "Stock Overview" },
            { key: "locks",    icon: "lock",            label: "Active Locks" },
            { key: "flagged",  icon: "flag",            label: "Flagged Orders", badge: flagged.length || null },
            { key: "ledger",   icon: "journal-text",    label: "Ledger" },
            { key: "config",   icon: "sliders",         label: "Config (FR54)" },
          ].map(t => (
            <button
              key={t.key}
              className={`uc-tab-btn ${tab === t.key ? "active" : ""}`}
              onClick={() => setTab(t.key)}
              style={{ whiteSpace: "nowrap" }}
            >
              <i className={`bi bi-${t.icon} me-1`} />
              {t.label}
              {t.badge ? (
                <span className="badge bg-danger ms-1 rounded-pill">{t.badge}</span>
              ) : null}
            </button>
          ))}
        </div>

        {/* ── Tab: Stock Overview ──────────────────────────── */}
        {tab === "overview" && (
          <div>
            <div className="mb-3">
              <div className="input-group" style={{ maxWidth: 320 }}>
                <span className="input-group-text bg-white border-end-0">
                  <i className="bi bi-search text-muted" />
                </span>
                <input
                  className="form-control border-start-0"
                  placeholder="Search items…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                />
              </div>
            </div>

            {filtered.length === 0 && (
              <div className="text-center py-5 text-muted">
                <i className="bi bi-box-seam" style={{ fontSize: "2rem" }} /><br />
                No items found.
              </div>
            )}

            <div className="row g-3">
              {filtered.map(item => {
                const sl = stockLabel(item.available_qty, item.total_qty);
                return (
                  <div key={item.menu_item_id} className="col-12 col-md-6 col-xl-4">
                    <div className="uc-card p-3 h-100">
                      {/* Header row */}
                      <div className="d-flex align-items-start justify-content-between mb-2">
                        <div>
                          <div className="fw-semibold" style={{ fontSize: ".95rem", color: "#111827" }}>
                            {item.item_name}
                          </div>
                          <div style={{ fontSize: ".78rem", color: "#6b7280" }}>
                            Max order: {item.max_order_qty} / item
                          </div>
                        </div>
                        <span className={`badge ${sl.cls} rounded-pill`}>{sl.label}</span>
                      </div>

                      {/* Stock bar */}
                      <StockBar
                        available={item.available_qty}
                        total={item.total_qty}
                        locked={item.locked_qty}
                      />

                      {/* Action buttons */}
                      <div className="d-flex gap-2 mt-3">
                        <button
                          className="btn btn-sm btn-outline-primary flex-fill"
                          onClick={() => {
                            setRestockModal(item);
                            setRestockQty(1);
                            setRestockNote("");
                          }}
                        >
                          <i className="bi bi-plus-circle me-1" />Restock
                        </button>
                        <button
                          className="btn btn-sm btn-outline-warning flex-fill"
                          onClick={() => {
                            setCorrectModal(item);
                            setCorrectQty(item.total_qty);
                            setCorrectNote("");
                          }}
                        >
                          <i className="bi bi-pencil-square me-1" />Correct
                        </button>
                        <button
                          className="btn btn-sm btn-outline-secondary"
                          onClick={() => { setLedgerItem(item.menu_item_id); setTab("ledger"); }}
                          title="View ledger"
                        >
                          <i className="bi bi-journal-text" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Tab: Active Locks ────────────────────────────── */}
        {tab === "locks" && (
          <div>
            <div className="d-flex align-items-center justify-content-between mb-3">
              <div>
                <span className="fw-semibold">Active Stock Locks</span>
                <span className="text-muted ms-2" style={{ fontSize: ".85rem" }}>
                  FR22 — Pessimistic locks (10-min TTL)
                </span>
              </div>
              <div className="d-flex gap-2">
                <button className="btn btn-sm btn-outline-secondary" onClick={loadLocks}>
                  <i className="bi bi-arrow-clockwise me-1" />Refresh
                </button>
                <button className="btn btn-sm btn-outline-danger" onClick={handleExpireLocks} disabled={loading}>
                  <i className="bi bi-clock-history me-1" />Expire Stale
                </button>
              </div>
            </div>

            {activeLocks.length === 0 ? (
              <div className="text-center py-5 text-muted uc-card p-4">
                <i className="bi bi-unlock" style={{ fontSize: "2rem" }} /><br />
                <div className="mt-2">No active stock locks.</div>
              </div>
            ) : (
              <div className="uc-card overflow-hidden">
                <div className="table-responsive">
                  <table className="table table-hover mb-0" style={{ fontSize: ".88rem" }}>
                    <thead className="table-light">
                      <tr>
                        <th>Item</th>
                        <th>Order ID</th>
                        <th className="text-end">Qty</th>
                        <th>Locked At</th>
                        <th>Expires</th>
                        <th className="text-end">Remaining</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activeLocks.map(lock => (
                        <tr key={lock.id}>
                          <td className="fw-medium">{lock.item_name}</td>
                          <td>
                            <code style={{ fontSize: ".75rem" }}>
                              {lock.order_id?.slice(0, 8)}…
                            </code>
                          </td>
                          <td className="text-end">{lock.quantity}</td>
                          <td>{new Date(lock.locked_at).toLocaleTimeString()}</td>
                          <td>{new Date(lock.expires_at).toLocaleTimeString()}</td>
                          <td className="text-end">
                            {lock.seconds_remaining > 0 ? (
                              <span className={`badge ${lock.seconds_remaining < 60 ? "bg-danger" : "bg-info text-dark"}`}>
                                {Math.floor(lock.seconds_remaining / 60)}m {lock.seconds_remaining % 60}s
                              </span>
                            ) : (
                              <span className="badge bg-secondary">Expiring…</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Tab: Flagged Orders ──────────────────────────── */}
        {tab === "flagged" && (
          <div>
            <div className="d-flex align-items-center justify-content-between mb-3">
              <div>
                <span className="fw-semibold">Flagged Orders</span>
                <span className="text-muted ms-2" style={{ fontSize: ".85rem" }}>
                  FR24 — Pending admin review
                </span>
              </div>
              <button className="btn btn-sm btn-outline-secondary" onClick={loadFlagged}>
                <i className="bi bi-arrow-clockwise me-1" />Refresh
              </button>
            </div>

            {flagged.length === 0 ? (
              <div className="text-center py-5 text-muted uc-card p-4">
                <i className="bi bi-check-circle" style={{ fontSize: "2rem", color: "#22c55e" }} /><br />
                <div className="mt-2">No pending flagged orders.</div>
              </div>
            ) : (
              <div className="d-flex flex-column gap-3">
                {flagged.map(f => (
                  <FlaggedOrderCard key={f.id} item={f} onReview={handleReview} loading={loading} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Tab: Stock Ledger ────────────────────────────── */}
        {tab === "ledger" && (
          <div>
            <div className="d-flex align-items-center gap-3 mb-3">
              <div>
                <span className="fw-semibold">Stock Transaction Ledger</span>
                <span className="text-muted ms-2" style={{ fontSize: ".85rem" }}>
                  FR41 — Immutable audit log
                </span>
              </div>
              <select
                className="form-select form-select-sm ms-auto"
                style={{ maxWidth: 220 }}
                value={ledgerItem || ""}
                onChange={e => {
                  const v = parseInt(e.target.value);
                  setLedgerItem(v || null);
                  if (v) loadLedger(v);
                }}
              >
                <option value="">— Select item —</option>
                {items.map(i => (
                  <option key={i.menu_item_id} value={i.menu_item_id}>{i.item_name}</option>
                ))}
              </select>
            </div>

            {!ledgerItem ? (
              <div className="text-center py-5 text-muted uc-card p-4">
                <i className="bi bi-journal-text" style={{ fontSize: "2rem" }} /><br />
                <div className="mt-2">Select an item to view its stock ledger.</div>
              </div>
            ) : (
              <div className="uc-card overflow-hidden">
                <div className="table-responsive">
                  <table className="table table-hover mb-0" style={{ fontSize: ".86rem" }}>
                    <thead className="table-light">
                      <tr>
                        <th>Type</th>
                        <th className="text-end">Delta</th>
                        <th className="text-end">Before</th>
                        <th className="text-end">After</th>
                        <th>Order</th>
                        <th>Note</th>
                        <th>Timestamp</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(ledger.transactions || []).map(txn => (
                        <tr key={txn.id}>
                          <td><TxnTypeBadge type={txn.txn_type} /></td>
                          <td className={`text-end fw-bold ${txn.quantity_delta < 0 ? "text-danger" : "text-success"}`}>
                            {txn.quantity_delta > 0 ? "+" : ""}{txn.quantity_delta}
                          </td>
                          <td className="text-end text-muted">{txn.quantity_before}</td>
                          <td className="text-end fw-medium">{txn.quantity_after}</td>
                          <td>
                            {txn.order_id ? (
                              <code style={{ fontSize: ".75rem" }}>{txn.order_id.slice(0, 8)}…</code>
                            ) : <span className="text-muted">—</span>}
                          </td>
                          <td style={{ maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {txn.note || <span className="text-muted">—</span>}
                          </td>
                          <td style={{ whiteSpace: "nowrap" }}>
                            {new Date(txn.created_at).toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="px-3 py-2 border-top text-muted" style={{ fontSize: ".8rem" }}>
                  {ledger.total} total transaction{ledger.total !== 1 ? "s" : ""}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Tab: Config ──────────────────────────────────── */}
        {tab === "config" && (
          <div>
            <div className="d-flex align-items-center justify-content-between mb-3">
              <div>
                <span className="fw-semibold">System Configuration</span>
                <span className="text-muted ms-2" style={{ fontSize: ".85rem" }}>
                  FR54 — Live reload ≤ 60 sec
                </span>
              </div>
              <button className="btn btn-sm btn-outline-secondary" onClick={loadConfig}>
                <i className="bi bi-arrow-clockwise me-1" />Refresh
              </button>
            </div>

            <div className="uc-card overflow-hidden">
              <table className="table mb-0" style={{ fontSize: ".88rem" }}>
                <thead className="table-light">
                  <tr>
                    <th>Parameter</th>
                    <th>Description</th>
                    <th style={{ width: 160 }}>Value</th>
                    <th style={{ width: 80 }} />
                  </tr>
                </thead>
                <tbody>
                  {config.map(c => (
                    <tr key={c.key}>
                      <td>
                        <code style={{ fontSize: ".8rem" }}>{c.key}</code>
                      </td>
                      <td className="text-muted" style={{ fontSize: ".82rem" }}>{c.description}</td>
                      <td>
                        <input
                          className="form-control form-control-sm"
                          value={configEdit[c.key] !== undefined ? configEdit[c.key] : c.value}
                          onChange={e => setConfigEdit(prev => ({ ...prev, [c.key]: e.target.value }))}
                        />
                      </td>
                      <td>
                        {configEdit[c.key] !== undefined && configEdit[c.key] !== c.value ? (
                          <button
                            className="btn btn-sm btn-primary"
                            onClick={() => handleConfigSave(c.key)}
                            disabled={loading}
                          >
                            Save
                          </button>
                        ) : (
                          <span className="text-muted" style={{ fontSize: ".8rem" }}>—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="alert alert-info mt-3 d-flex gap-2 align-items-center">
              <i className="bi bi-info-circle-fill" />
              <span style={{ fontSize: ".88rem" }}>
                Changes take effect within 60 seconds without system restart. All updates are audit-logged.
              </span>
            </div>
          </div>
        )}

        <div className="pb-5" />
      </div>

      {/* ── Restock Modal ───────────────────────────────────── */}
      {restockModal && (
        <Modal
          title={`Restock — ${restockModal.item_name}`}
          onClose={() => setRestockModal(null)}
          onConfirm={handleRestock}
          confirmLabel="Restock"
          confirmVariant="primary"
          loading={loading}
        >
          <div className="mb-3">
            <label className="form-label fw-medium">Quantity to add</label>
            <input
              type="number" min="1" className="form-control"
              value={restockQty}
              onChange={e => setRestockQty(Math.max(1, parseInt(e.target.value) || 1))}
            />
            <div className="form-text">
              Current stock: {restockModal.total_qty} | Locked: {restockModal.locked_qty}
            </div>
          </div>
          <div className="mb-3">
            <label className="form-label fw-medium">Note <span className="text-muted">(optional)</span></label>
            <input
              type="text" className="form-control" placeholder="e.g. Weekly delivery"
              value={restockNote}
              onChange={e => setRestockNote(e.target.value)}
            />
          </div>
        </Modal>
      )}

      {/* ── Correction Modal ────────────────────────────────── */}
      {correctModal && (
        <Modal
          title={`Correct Stock — ${correctModal.item_name}`}
          onClose={() => setCorrectModal(null)}
          onConfirm={handleCorrection}
          confirmLabel="Apply Correction"
          confirmVariant="warning"
          loading={loading}
          disableConfirm={correctNote.trim().length < 5}
        >
          <div className="alert alert-warning d-flex gap-2 align-items-center mb-3">
            <i className="bi bi-exclamation-triangle-fill" />
            <span style={{ fontSize: ".88rem" }}>
              FR41: Stock correction is logged permanently. Provide a mandatory reason.
            </span>
          </div>
          <div className="mb-3">
            <label className="form-label fw-medium">New exact quantity</label>
            <input
              type="number" min="0" className="form-control"
              value={correctQty}
              onChange={e => setCorrectQty(Math.max(0, parseInt(e.target.value) || 0))}
            />
            <div className="form-text">
              Current: {correctModal.total_qty} → Delta: {correctQty - correctModal.total_qty >= 0 ? "+" : ""}{correctQty - correctModal.total_qty}
            </div>
          </div>
          <div className="mb-3">
            <label className="form-label fw-medium">
              Reason <span className="text-danger">*</span>
            </label>
            <textarea
              className={`form-control ${correctNote.trim().length > 0 && correctNote.trim().length < 5 ? "is-invalid" : ""}`}
              rows={2}
              placeholder="e.g. Physical count revealed discrepancy due to spoilage"
              value={correctNote}
              onChange={e => setCorrectNote(e.target.value)}
            />
            {correctNote.trim().length < 5 && correctNote.length > 0 && (
              <div className="invalid-feedback">Reason must be at least 5 characters.</div>
            )}
          </div>
        </Modal>
      )}

      <Toast toasts={toasts} dismiss={dismissToast} />
    </>
  );
}

// ─────────────────────────────────────────────────────────────
// Flagged Order Card
// ─────────────────────────────────────────────────────────────
function FlaggedOrderCard({ item, onReview, loading }) {
  const [rejectReason, setRejectReason] = useState("");
  const [showReject,   setShowReject]   = useState(false);
  const timeLeft = Math.max(0, Math.ceil((new Date(item.auto_cancel_at) - Date.now()) / 60000));

  return (
    <div className="uc-card p-3">
      <div className="d-flex align-items-start justify-content-between mb-2">
        <div>
          <span className="badge uc-badge-flagged me-2">
            <i className="bi bi-flag-fill me-1" />Flagged
          </span>
          <code style={{ fontSize: ".78rem" }}>{item.order_id?.slice(0, 8)}…</code>
        </div>
        <div className="text-end">
          <div style={{ fontSize: ".78rem", color: "#9ca3af" }}>
            Auto-cancels in
          </div>
          <span className={`badge ${timeLeft < 15 ? "bg-danger" : "bg-warning text-dark"}`}>
            {timeLeft}m
          </span>
        </div>
      </div>

      <div className="mb-2" style={{ fontSize: ".88rem" }}>
        <strong>Reason:</strong> {item.flagged_reason}
      </div>

      {item.flag_details && (
        <div className="d-flex gap-2 mb-2 flex-wrap">
          {item.flag_details.max_qty_exceeded && (
            <span className="badge bg-light text-dark border">
              <i className="bi bi-cart-x me-1" />Qty threshold exceeded
            </span>
          )}
          {item.flag_details.total_exceeded && (
            <span className="badge bg-light text-dark border">
              <i className="bi bi-cash-coin me-1" />Total threshold exceeded
            </span>
          )}
        </div>
      )}

      {showReject && (
        <div className="mb-2">
          <input
            className="form-control form-control-sm"
            placeholder="Rejection reason (required)"
            value={rejectReason}
            onChange={e => setRejectReason(e.target.value)}
          />
        </div>
      )}

      <div className="d-flex gap-2">
        <button
          className="btn btn-sm btn-success"
          disabled={loading}
          onClick={() => onReview(item.id, "approve", null)}
        >
          <i className="bi bi-check-lg me-1" />Approve
        </button>
        {!showReject ? (
          <button
            className="btn btn-sm btn-outline-danger"
            onClick={() => setShowReject(true)}
          >
            <i className="bi bi-x-lg me-1" />Reject
          </button>
        ) : (
          <>
            <button
              className="btn btn-sm btn-danger"
              disabled={loading || !rejectReason.trim()}
              onClick={() => onReview(item.id, "reject", rejectReason)}
            >
              Confirm Reject
            </button>
            <button
              className="btn btn-sm btn-outline-secondary"
              onClick={() => { setShowReject(false); setRejectReason(""); }}
            >
              Cancel
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Transaction type badge
// ─────────────────────────────────────────────────────────────
function TxnTypeBadge({ type }) {
  const map = {
    RESERVE:    { cls: "bg-info text-dark",    icon: "lock"         },
    DEDUCT:     { cls: "bg-danger",             icon: "dash-circle"  },
    RELEASE:    { cls: "bg-success",            icon: "unlock"       },
    RESTOCK:    { cls: "bg-primary",            icon: "plus-circle"  },
    CORRECTION: { cls: "bg-warning text-dark",  icon: "pencil"       },
    ADMIN_DEDUCT: { cls: "bg-secondary",        icon: "trash"        },
  };
  const m = map[type] || { cls: "bg-light text-dark", icon: "question" };
  return (
    <span className={`badge ${m.cls}`}>
      <i className={`bi bi-${m.icon} me-1`} />{type}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────
// Generic modal
// ─────────────────────────────────────────────────────────────
function Modal({ title, onClose, onConfirm, confirmLabel, confirmVariant, loading, disableConfirm, children }) {
  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 1050,
        background: "rgba(0,0,0,.4)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: "1rem",
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="uc-card"
        style={{ width: "100%", maxWidth: 460, padding: "1.5rem" }}
      >
        <div className="d-flex align-items-center justify-content-between mb-3">
          <h6 className="mb-0 fw-bold">{title}</h6>
          <button className="btn-close" onClick={onClose} />
        </div>
        {children}
        <div className="d-flex gap-2 justify-content-end mt-3">
          <button className="btn btn-outline-secondary" onClick={onClose} disabled={loading}>
            Cancel
          </button>
          <button
            className={`btn btn-${confirmVariant}`}
            onClick={onConfirm}
            disabled={loading || disableConfirm}
          >
            {loading ? (
              <><span className="spinner-border spinner-border-sm me-2" />{confirmLabel}…</>
            ) : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
