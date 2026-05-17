// OrderPaymentApp.jsx
// Full Order & Payment flow: Cart → Place Order → Payment → Tracking
// React + Bootstrap 5 · Covers FR4-FR17, FR24, FR26-FR31

import { useState, useEffect, useRef } from "react";

// ─── MOCK API (works standalone without backend) ──────────────────────────────
const MOCK_MENU = [
  { id:"m1", name:"Beef Burger",     price:45, category:"Main",   image_url:"🍔", is_available:true,  available_stock:50 },
  { id:"m2", name:"Veggie Burger",   price:38, category:"Main",   image_url:"🥦", is_available:true,  available_stock:30 },
  { id:"m3", name:"Salad Bowl",      price:25, category:"Salads", image_url:"🥗", is_available:true,  available_stock:40 },
  { id:"m4", name:"Salad Wrap",      price:30, category:"Salads", image_url:"🌯", is_available:true,  available_stock:35 },
  { id:"m5", name:"Orange Juice",    price:20, category:"Drinks", image_url:"🍊", is_available:true,  available_stock:60 },
  { id:"m6", name:"Water Bottle",    price:5,  category:"Drinks", image_url:"💧", is_available:true,  available_stock:200},
  { id:"m7", name:"Fish Sandwich",   price:40, category:"Main",   image_url:"🐟", is_available:false, available_stock:0  },
  { id:"m8", name:"Grilled Chicken", price:50, category:"Main",   image_url:"🍗", is_available:true,  available_stock:25 },
];
const MOCK_VOUCHERS = {
  SAVE20:   { code:"SAVE20",   discount_type:"flat",    discount_value:20, min_order:50 },
  HALF50:   { code:"HALF50",   discount_type:"percent", discount_value:50, min_order:100},
  FREESHIP: { code:"FREESHIP", discount_type:"free_delivery", discount_value:0, min_order:0 },
  EXPIRED:  null,
};

function computeDiscount(voucher, subtotal) {
  if (!voucher) return 0;
  if (voucher.discount_type === "flat")    return Math.min(voucher.discount_value, subtotal);
  if (voucher.discount_type === "percent") return Math.round(subtotal * voucher.discount_value / 100 * 100)/100;
  return 0;
}

// ─── CONSTANTS ────────────────────────────────────────────────────────────────
const STEPS = ["cart", "checkout", "payment", "tracking"];
const STATUS_COLORS = {
  pending_payment:"warning", confirmed:"info", preparing:"primary",
  ready_for_pickup:"success", delivered:"success", cancelled:"danger", payment_timeout:"secondary"
};
const STATUS_LABELS = {
  pending_payment:"Pending Payment", confirmed:"Confirmed", preparing:"Preparing",
  ready_for_pickup:"Ready for Pickup", delivered:"Delivered", cancelled:"Cancelled",
  payment_timeout:"Payment Timeout"
};
const MAX_QTY = 20;
const PAYMENT_TIMEOUT_SECS = 600;

// ─── MAIN APP ─────────────────────────────────────────────────────────────────
export default function OrderPaymentApp() {
  const userId = "user-demo-001";
  const [step,        setStep]       = useState("cart");
  const [menu,        setMenu]       = useState(MOCK_MENU);
  const [cart,        setCart]       = useState([]);
  const [search,      setSearch]     = useState("");
  const [category,    setCategory]   = useState("All");
  const [voucherCode, setVoucherCode]= useState("");
  const [appliedVoucher, setAppliedVoucher] = useState(null);
  const [voucherMsg,  setVoucherMsg] = useState(null);
  const [order,       setOrder]      = useState(null);
  const [payMethod,   setPayMethod]  = useState("online");
  const [payState,    setPayState]   = useState("idle"); // idle|processing|success|failed|timeout
  const [payError,    setPayError]   = useState(null);
  const [cancelModal, setCancelModal]= useState(false);
  const [partialModal,setPartialModal]=useState(false);
  const [toast,       setToast]      = useState(null);
  const [timeLeft,    setTimeLeft]   = useState(null);
  const timerRef = useRef(null);

  const categories = ["All", ...new Set(MOCK_MENU.map(i => i.category))];

  const showToast = (msg, type="success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  // ── CART LOGIC ──────────────────────────────────────────────
  const addToCart = (item) => {
    if (!item.is_available || item.available_stock < 1) return;
    setCart(prev => {
      const existing = prev.find(c => c.id === item.id);
      if (existing) {
        if (existing.qty + 1 > MAX_QTY) {
          showToast(`Maximum ${MAX_QTY} units per item`, "danger"); return prev;
        }
        return prev.map(c => c.id === item.id ? {...c, qty: c.qty+1} : c);
      }
      return [...prev, { ...item, qty: 1 }];
    });
    showToast(`${item.name} added to cart`);
  };

  const updateQty = (id, delta) => {
    setCart(prev => prev.map(c => {
      if (c.id !== id) return c;
      const newQty = c.qty + delta;
      if (newQty < 1)      return null;
      if (newQty > MAX_QTY){ showToast(`Max ${MAX_QTY} units`, "warning"); return c; }
      return { ...c, qty: newQty };
    }).filter(Boolean));
  };

  const removeItem = (id) => setCart(prev => prev.filter(c => c.id !== id));

  const subtotal  = cart.reduce((s, c) => s + c.price * c.qty, 0);
  const discount  = appliedVoucher ? computeDiscount(appliedVoucher, subtotal) : 0;
  const total     = Math.max(0, subtotal - discount);
  const cartCount = cart.reduce((s, c) => s + c.qty, 0);

  // FR6, FR7 – Voucher
  const applyVoucher = () => {
    const code = voucherCode.trim().toUpperCase();
    if (!code) return;
    if (code in MOCK_VOUCHERS) {
      const v = MOCK_VOUCHERS[code];
      if (!v) { setVoucherMsg({ type:"danger", msg:"This voucher has expired" }); return; }
      if (subtotal < v.min_order) { setVoucherMsg({ type:"danger", msg:`Minimum order of ${v.min_order} EGP required` }); return; }
      setAppliedVoucher(v);
      setVoucherMsg({ type:"success", msg:`Voucher applied! You save ${computeDiscount(v,subtotal)} EGP` });
    } else {
      setVoucherMsg({ type:"danger", msg:"Invalid voucher code" });
    }
  };
  const removeVoucher = () => { setAppliedVoucher(null); setVoucherCode(""); setVoucherMsg(null); };

  // FR8, FR9, FR31 – Place Order
  const placeOrder = () => {
    const unavailable = cart.filter(c => !c.is_available);
    if (unavailable.length) {
      showToast(`Unavailable items: ${unavailable.map(i=>i.name).join(", ")}`, "danger"); return;
    }
    const newOrder = {
      id:             `ORD-${Date.now()}`,
      idempotency_key:`IDP-${Date.now()}`,
      user_id:        userId,
      status:         "pending_payment",
      items:          cart.map(c => ({ ...c, unit_price:c.price, subtotal:c.price*c.qty })),
      subtotal, discount, total,
      voucher_code:   appliedVoucher?.code || null,
      created_at:     new Date().toISOString(),
      confirmed_at:   null,
    };
    setOrder(newOrder);
    setStep("checkout");
  };

  // FR10 – Select payment method & FR24 – start timer
  const startPayment = () => {
    setPayState("processing");
    setTimeLeft(PAYMENT_TIMEOUT_SECS);
    setStep("payment");
    setPayError(null);
    if (payMethod !== "online") {
      // Cash/Wallet/Meal plan confirm immediately
      setTimeout(() => confirmOrder(), 800);
    }
  };

  // FR24 – Payment timeout countdown
  useEffect(() => {
    if (step !== "payment" || payState !== "processing" || payMethod !== "online") return;
    timerRef.current = setInterval(() => {
      setTimeLeft(t => {
        if (t <= 1) {
          clearInterval(timerRef.current);
          setPayState("timeout");
          setOrder(o => o ? {...o, status:"payment_timeout"} : o);
          return 0;
        }
        return t - 1;
      });
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, [step, payState, payMethod]);

  const confirmOrder = () => {
    clearInterval(timerRef.current);
    setPayState("success");
    setOrder(o => o ? {
      ...o,
      status:       "confirmed",
      confirmed_at: new Date().toISOString(),
    } : o);
  };

  // FR12 – simulate failure
  const simulateFailure = (reason) => {
    clearInterval(timerRef.current);
    setPayState("failed");
    const msgs = {
      insufficient_funds: "Payment declined: Insufficient funds",
      card_expired:       "Payment declined: Card expired",
      gateway_error:      "Payment service unavailable. Please try again",
    };
    setPayError(msgs[reason] || "Payment declined");
  };

  const retryPayment = () => {
    setPayState("processing");
    setPayError(null);
    setTimeLeft(PAYMENT_TIMEOUT_SECS);
    if (payMethod !== "online") setTimeout(() => confirmOrder(), 800);
  };

  const proceedToTracking = () => setStep("tracking");

  // FR14, FR26 – Cancel order
  const handleCancel = () => {
    const status = order?.status;
    if (status === "pending_payment") {
      setOrder(o => ({...o, status:"cancelled", cancelled_at: new Date().toISOString()}));
      setCancelModal(false); showToast("Order cancelled successfully");
      setTimeout(() => { setStep("cart"); setCart([]); setOrder(null); setPayState("idle"); }, 1500);
    } else if (status === "confirmed") {
      const confirmedAt = new Date(order.confirmed_at);
      const windowEnd   = new Date(confirmedAt.getTime() + 15*60*1000);
      if (new Date() <= windowEnd) {
        setOrder(o => ({...o, status:"cancelled"}));
        setCancelModal(false);
        showToast("Order cancelled. Refund initiated.");
        setTimeout(() => { setStep("cart"); setCart([]); setOrder(null); setPayState("idle"); }, 1500);
      } else {
        setCancelModal(false);
        setPartialModal(true);
      }
    }
  };

  const confirmPartialRefund = () => {
    const refundAmount = ((order?.total || 0) * 0.5).toFixed(2);
    setOrder(o => ({...o, status:"cancelled"}));
    setPartialModal(false);
    showToast(`Order cancelled. 50% refund (${refundAmount} EGP) initiated.`, "info");
    setTimeout(() => { setStep("cart"); setCart([]); setOrder(null); setPayState("idle"); }, 2000);
  };

  // FR16 – Staff status simulation
  const simulateStatusUpdate = (newStatus) => {
    setOrder(o => o ? {...o, status: newStatus} : o);
    showToast(`Order status updated to: ${STATUS_LABELS[newStatus]}`);
  };

  // ── FILTERED MENU ────────────────────────────────────────────
  const filteredMenu = menu.filter(item => {
    const matchCat = category === "All" || item.category === category;
    const matchQ   = item.name.toLowerCase().includes(search.toLowerCase());
    return matchCat && matchQ;
  });

  const fmtTime = (s) => `${String(Math.floor(s/60)).padStart(2,"0")}:${String(s%60).padStart(2,"0")}`;

  // ── RENDER ───────────────────────────────────────────────────
  return (
    <div style={{fontFamily:"'DM Sans', sans-serif", background:"#f0f4f8", minHeight:"100vh"}}>
      {/* Google Font */}
      <style>{`
        @import url('https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css');
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Space+Grotesk:wght@600;700&display=swap');
        :root {
          --brand:    #1a56db;
          --brand-dk: #1347c5;
          --accent:   #ff6b35;
          --success:  #0ea770;
          --danger:   #e53e3e;
          --warning:  #d97706;
          --surface:  #ffffff;
          --muted:    #6b7280;
          --border:   #e2e8f0;
        }
        .step-indicator { display:flex; align-items:center; gap:0; }
        .step-dot { width:32px; height:32px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:13px; font-weight:600; }
        .step-line { flex:1; height:3px; background:var(--border); }
        .step-line.done { background:var(--brand); }
        .menu-card { transition: transform .15s, box-shadow .15s; cursor:pointer; }
        .menu-card:hover { transform:translateY(-3px); box-shadow:0 8px 24px rgba(26,86,219,.12)!important; }
        .cart-item { border-left:3px solid var(--brand); }
        .qty-btn { width:30px; height:30px; border-radius:50%; border:1.5px solid var(--border); background:#fff; display:flex; align-items:center; justify-content:center; cursor:pointer; font-size:16px; transition:all .12s; }
        .qty-btn:hover { background:var(--brand); color:#fff; border-color:var(--brand); }
        .pay-method { border:2px solid var(--border); border-radius:12px; padding:14px 18px; cursor:pointer; transition:all .15s; }
        .pay-method.selected { border-color:var(--brand); background:#eff4ff; }
        .pay-method:hover:not(.selected) { border-color:#93c5fd; }
        .status-timeline { position:relative; }
        .timeline-item { display:flex; gap:12px; padding-bottom:20px; }
        .timeline-item:last-child { padding-bottom:0; }
        .timeline-dot { width:14px; height:14px; border-radius:50%; margin-top:3px; flex-shrink:0; }
        .timeline-line { position:absolute; left:6px; top:14px; bottom:0; width:2px; background:var(--border); }
        .badge-status { padding:5px 12px; border-radius:20px; font-size:12px; font-weight:600; }
        .toast-container { position:fixed; top:20px; right:20px; z-index:9999; }
        .progress-bar-animated { animation: progress-anim 1s linear infinite; }
        @keyframes progress-anim { from{background-position:40px 0} to{background-position:0 0} }
        .timer-ring { font-variant-numeric:tabular-nums; font-family:'Space Grotesk',sans-serif; }
        .section-title { font-family:'Space Grotesk',sans-serif; font-size:22px; font-weight:700; color:#1e293b; }
        .brand-text { font-family:'Space Grotesk',sans-serif; font-weight:700; }
      `}</style>

      {/* Toast */}
      {toast && (
        <div className="toast-container">
          <div className={`toast show align-items-center text-bg-${toast.type === "success" ? "success" : toast.type === "danger" ? "danger" : toast.type === "info" ? "primary" : "warning"} border-0`} style={{minWidth:280}}>
            <div className="d-flex">
              <div className="toast-body fw-500">{toast.msg}</div>
              <button type="button" className="btn-close btn-close-white me-2 m-auto" onClick={()=>setToast(null)}/>
            </div>
          </div>
        </div>
      )}

      {/* Navbar */}
      <nav style={{background:"var(--brand)", padding:"14px 0", boxShadow:"0 2px 12px rgba(26,86,219,.3)"}}>
        <div className="container d-flex justify-content-between align-items-center">
          <span className="brand-text text-white" style={{fontSize:20}}>🎓 UniCafé</span>
          <div className="d-flex align-items-center gap-3">
            <span className="text-white opacity-75" style={{fontSize:13}}>Welcome, Ahmed</span>
            <button className="btn btn-light btn-sm position-relative" onClick={()=>setStep("cart")}>
              🛒 Cart
              {cartCount > 0 && <span className="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger" style={{fontSize:10}}>{cartCount}</span>}
            </button>
          </div>
        </div>
      </nav>

      {/* Step Indicator */}
      <div style={{background:"#fff", borderBottom:"1px solid var(--border)", padding:"14px 0"}}>
        <div className="container" style={{maxWidth:600}}>
          <div className="step-indicator">
            {STEPS.map((s, i) => {
              const idx = STEPS.indexOf(step);
              const done = i < idx, active = i === idx;
              return (
                <div key={s} style={{display:"contents"}}>
                  <div className="d-flex flex-column align-items-center gap-1">
                    <div className="step-dot" style={{
                      background: done ? "var(--brand)" : active ? "var(--brand)" : "#e2e8f0",
                      color: done||active ? "#fff" : "#94a3b8"
                    }}>
                      {done ? "✓" : i+1}
                    </div>
                    <span style={{fontSize:11, color: active ? "var(--brand)" : "#94a3b8", fontWeight: active?600:400}}>
                      {s.charAt(0).toUpperCase()+s.slice(1)}
                    </span>
                  </div>
                  {i < STEPS.length-1 && <div className={`step-line${i < idx ? " done" : ""}`}/>}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="container py-4" style={{maxWidth:1100}}>

        {/* ════════════════ STEP: CART ════════════════ */}
        {step === "cart" && (
          <div className="row g-4">
            {/* Menu */}
            <div className="col-lg-7">
              <div className="section-title mb-3">Menu</div>
              {/* Search + Category */}
              <div className="d-flex gap-2 mb-3 flex-wrap">
                <input className="form-control" placeholder="🔍 Search menu..." value={search} onChange={e=>setSearch(e.target.value)} style={{maxWidth:220, fontSize:14}}/>
                <div className="d-flex gap-1 flex-wrap">
                  {categories.map(c=>(
                    <button key={c} className={`btn btn-sm ${category===c?"btn-primary":"btn-outline-secondary"}`} onClick={()=>setCategory(c)} style={{fontSize:12}}>{c}</button>
                  ))}
                </div>
              </div>
              {/* Menu Grid */}
              <div className="row g-3">
                {filteredMenu.length === 0 && (
                  <div className="col-12 text-center text-muted py-4">No items found for "{search}"</div>
                )}
                {filteredMenu.map(item => {
                  const inCart = cart.find(c=>c.id===item.id);
                  return (
                    <div key={item.id} className="col-sm-6">
                      <div className="card menu-card h-100 border-0 shadow-sm" style={{borderRadius:14, opacity: item.is_available?1:0.6}}>
                        <div className="card-body p-3">
                          <div className="d-flex justify-content-between align-items-start mb-2">
                            <span style={{fontSize:36}}>{item.image_url}</span>
                            <span className={`badge ${item.is_available?"bg-success":"bg-secondary"}`} style={{fontSize:10}}>
                              {item.is_available ? `${item.available_stock} left` : "Out of Stock"}
                            </span>
                          </div>
                          <div className="fw-600 mb-1" style={{fontSize:15}}>{item.name}</div>
                          <div style={{fontSize:13, color:"var(--muted)"}} className="mb-2">{item.category}</div>
                          <div className="d-flex justify-content-between align-items-center">
                            <span className="fw-700" style={{color:"var(--brand)", fontSize:16}}>{item.price} EGP</span>
                            {item.is_available ? (
                              inCart ? (
                                <div className="d-flex align-items-center gap-2">
                                  <button className="qty-btn" onClick={()=>updateQty(item.id,-1)}>−</button>
                                  <span className="fw-600">{inCart.qty}</span>
                                  <button className="qty-btn" onClick={()=>addToCart(item)}>+</button>
                                </div>
                              ) : (
                                <button className="btn btn-primary btn-sm" onClick={()=>addToCart(item)} style={{fontSize:12,borderRadius:8}}>Add +</button>
                              )
                            ) : (
                              <span className="text-muted" style={{fontSize:12}}>Unavailable</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Cart */}
            <div className="col-lg-5">
              <div className="card border-0 shadow-sm sticky-top" style={{borderRadius:16, top:20}}>
                <div className="card-body p-4">
                  <div className="section-title mb-3">🛒 Your Cart</div>

                  {cart.length === 0 ? (
                    <div className="text-center py-4">
                      <div style={{fontSize:48}}>🛒</div>
                      <div className="text-muted mt-2">Your cart is empty</div>
                      <div className="text-muted" style={{fontSize:13}}>Add items from the menu</div>
                    </div>
                  ) : (
                    <>
                      <div className="d-flex flex-column gap-2 mb-3">
                        {cart.map(item => (
                          <div key={item.id} className="cart-item p-3 rounded-3" style={{background:"#f8fafc"}}>
                            <div className="d-flex justify-content-between align-items-center">
                              <div>
                                <div className="fw-600" style={{fontSize:14}}>{item.image_url} {item.name}</div>
                                <div className="text-muted" style={{fontSize:12}}>{item.price} EGP × {item.qty}</div>
                              </div>
                              <div className="d-flex align-items-center gap-2">
                                <span className="fw-700" style={{fontSize:14, color:"var(--brand)"}}>{(item.price*item.qty).toFixed(0)} EGP</span>
                                <button className="qty-btn" onClick={()=>removeItem(item.id)} style={{fontSize:12}}>✕</button>
                              </div>
                            </div>
                            <div className="d-flex align-items-center gap-2 mt-2">
                              <button className="qty-btn" onClick={()=>updateQty(item.id,-1)}>−</button>
                              <span className="fw-600" style={{fontSize:13}}>{item.qty}</span>
                              <button className="qty-btn" onClick={()=>updateQty(item.id,1)}>+</button>
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Voucher */}
                      <div className="mb-3">
                        <div style={{fontSize:13, fontWeight:600, marginBottom:6}}>🏷️ Voucher Code</div>
                        {appliedVoucher ? (
                          <div className="d-flex align-items-center justify-content-between p-2 rounded-3" style={{background:"#f0fdf4", border:"1.5px solid #bbf7d0"}}>
                            <span style={{fontSize:13, color:"var(--success)", fontWeight:600}}>✓ {appliedVoucher.code} applied</span>
                            <button className="btn btn-sm btn-outline-danger" style={{fontSize:11}} onClick={removeVoucher}>Remove</button>
                          </div>
                        ) : (
                          <div className="d-flex gap-2">
                            <input className="form-control form-control-sm" placeholder="Enter code" value={voucherCode} onChange={e=>setVoucherCode(e.target.value.toUpperCase())} style={{letterSpacing:1}}/>
                            <button className="btn btn-outline-primary btn-sm" onClick={applyVoucher}>Apply</button>
                          </div>
                        )}
                        {voucherMsg && <div className={`mt-2 small text-${voucherMsg.type==="success"?"success":"danger"}`}>{voucherMsg.msg}</div>}
                      </div>

                      {/* Totals */}
                      <div className="border-top pt-3">
                        <div className="d-flex justify-content-between mb-1">
                          <span className="text-muted" style={{fontSize:13}}>Subtotal</span>
                          <span style={{fontSize:13}}>{subtotal.toFixed(2)} EGP</span>
                        </div>
                        {discount > 0 && (
                          <div className="d-flex justify-content-between mb-1">
                            <span style={{fontSize:13, color:"var(--success)"}}>Discount</span>
                            <span style={{fontSize:13, color:"var(--success)"}}>−{discount.toFixed(2)} EGP</span>
                          </div>
                        )}
                        <div className="d-flex justify-content-between fw-700" style={{fontSize:18, marginTop:6}}>
                          <span>Total</span>
                          <span style={{color:"var(--brand)"}}>{total.toFixed(2)} EGP</span>
                        </div>
                      </div>

                      <button className="btn btn-primary w-100 mt-3 py-2 fw-600" onClick={placeOrder} style={{borderRadius:10, fontSize:15}} disabled={cart.length===0}>
                        Place Order →
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ════════════════ STEP: CHECKOUT ════════════════ */}
        {step === "checkout" && order && (
          <div className="row justify-content-center">
            <div className="col-lg-7">
              <div className="card border-0 shadow-sm" style={{borderRadius:16}}>
                <div className="card-body p-4">
                  <div className="section-title mb-4">Order Summary</div>

                  {/* Order Items */}
                  <div className="mb-4">
                    {order.items.map(item => (
                      <div key={item.id} className="d-flex justify-content-between py-2 border-bottom">
                        <div>
                          <span style={{fontSize:14, fontWeight:500}}>{item.image_url} {item.name}</span>
                          <span className="text-muted ms-2" style={{fontSize:12}}>×{item.qty}</span>
                        </div>
                        <span style={{fontSize:14, fontWeight:600}}>{item.subtotal.toFixed(0)} EGP</span>
                      </div>
                    ))}
                  </div>

                  {/* Totals */}
                  <div className="p-3 rounded-3 mb-4" style={{background:"#f8fafc"}}>
                    <div className="d-flex justify-content-between mb-1">
                      <span className="text-muted" style={{fontSize:13}}>Subtotal</span>
                      <span>{order.subtotal.toFixed(2)} EGP</span>
                    </div>
                    {order.discount > 0 && (
                      <div className="d-flex justify-content-between mb-1">
                        <span style={{fontSize:13, color:"var(--success)"}}>Voucher ({order.voucher_code})</span>
                        <span style={{color:"var(--success)"}}>−{order.discount.toFixed(2)} EGP</span>
                      </div>
                    )}
                    <div className="d-flex justify-content-between fw-700 border-top pt-2 mt-1" style={{fontSize:17}}>
                      <span>Total</span>
                      <span style={{color:"var(--brand)"}}>{order.total.toFixed(2)} EGP</span>
                    </div>
                  </div>

                  {/* Payment Method – FR10 */}
                  <div className="section-title mb-3" style={{fontSize:17}}>Select Payment Method</div>
                  <div className="row g-2 mb-4">
                    {[
                      { id:"online",    label:"💳 Online Payment",  desc:"Credit/Debit card via secure gateway" },
                      { id:"cash",      label:"💵 Cash on Delivery", desc:"Pay when you collect your order" },
                      { id:"wallet",    label:"👛 Wallet",           desc:"Deduct from your digital wallet" },
                      { id:"meal_plan", label:"🎓 Meal Plan",        desc:"Use your university meal credits" },
                    ].map(m => (
                      <div key={m.id} className="col-sm-6">
                        <div className={`pay-method ${payMethod===m.id?"selected":""}`} onClick={()=>setPayMethod(m.id)}>
                          <div className="fw-600" style={{fontSize:14}}>{m.label}</div>
                          <div className="text-muted" style={{fontSize:11,marginTop:2}}>{m.desc}</div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="d-flex gap-3">
                    <button className="btn btn-outline-secondary flex-fill" onClick={()=>setStep("cart")}>← Back</button>
                    <button className="btn btn-primary flex-fill py-2 fw-600" onClick={startPayment} style={{borderRadius:10}}>
                      Proceed to Payment →
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ════════════════ STEP: PAYMENT ════════════════ */}
        {step === "payment" && order && (
          <div className="row justify-content-center">
            <div className="col-lg-6">
              <div className="card border-0 shadow-sm" style={{borderRadius:16}}>
                <div className="card-body p-4 text-center">

                  {/* Processing */}
                  {payState === "processing" && payMethod === "online" && (
                    <>
                      <div style={{fontSize:56, marginBottom:12}}>🔐</div>
                      <div className="section-title mb-2">Secure Payment</div>
                      <div className="text-muted mb-3" style={{fontSize:13}}>Complete your payment of <strong>{order.total.toFixed(2)} EGP</strong></div>

                      {/* FR24 – countdown */}
                      <div className="p-3 rounded-3 mb-4" style={{background:"#fef3c7", border:"1.5px solid #fde68a"}}>
                        <div className="timer-ring" style={{fontSize:32, fontWeight:700, color:"#d97706"}}>{fmtTime(timeLeft||0)}</div>
                        <div style={{fontSize:12, color:"#92400e", marginTop:4}}>Session expires in {fmtTime(timeLeft||0)}</div>
                      </div>

                      {/* Simulated card form */}
                      <div className="text-start mb-4">
                        <label className="form-label" style={{fontSize:13, fontWeight:600}}>Card Number</label>
                        <input className="form-control mb-2" placeholder="4111 1111 1111 1111" style={{fontFamily:"monospace"}}/>
                        <div className="row g-2">
                          <div className="col-6">
                            <label className="form-label" style={{fontSize:13, fontWeight:600}}>Expiry</label>
                            <input className="form-control" placeholder="MM/YY"/>
                          </div>
                          <div className="col-6">
                            <label className="form-label" style={{fontSize:13, fontWeight:600}}>CVV</label>
                            <input className="form-control" placeholder="•••"/>
                          </div>
                        </div>
                      </div>

                      <button className="btn btn-success w-100 py-2 fw-600 mb-3" onClick={confirmOrder} style={{borderRadius:10}}>
                        Pay {order.total.toFixed(2)} EGP
                      </button>

                      <div className="text-muted mb-2" style={{fontSize:12}}>— Simulate gateway response (dev) —</div>
                      <div className="d-flex gap-2 justify-content-center">
                        <button className="btn btn-sm btn-outline-danger" onClick={()=>simulateFailure("insufficient_funds")}>Fail: NSF</button>
                        <button className="btn btn-sm btn-outline-danger" onClick={()=>simulateFailure("card_expired")}>Fail: Expired</button>
                        <button className="btn btn-sm btn-outline-danger" onClick={()=>simulateFailure("gateway_error")}>Fail: Gateway</button>
                      </div>
                    </>
                  )}

                  {/* Non-online processing */}
                  {payState === "processing" && payMethod !== "online" && (
                    <>
                      <div className="spinner-border text-primary mb-3" style={{width:48,height:48}}/>
                      <div className="fw-600">Processing {payMethod.replace("_"," ")} payment…</div>
                    </>
                  )}

                  {/* FR13 – Success */}
                  {payState === "success" && (
                    <>
                      <div style={{fontSize:64, animation:"none"}}>✅</div>
                      <div className="section-title mt-2 mb-1" style={{color:"var(--success)"}}>Payment Confirmed!</div>
                      <div className="text-muted mb-1" style={{fontSize:14}}>Order ID: <strong>{order.id}</strong></div>
                      <div className="text-muted mb-4" style={{fontSize:13}}>Your order is confirmed and being processed.</div>
                      <button className="btn btn-primary w-100 py-2 fw-600" onClick={proceedToTracking} style={{borderRadius:10}}>
                        Track My Order →
                      </button>
                    </>
                  )}

                  {/* FR12 – Failed */}
                  {payState === "failed" && (
                    <>
                      <div style={{fontSize:64}}>❌</div>
                      <div className="section-title mt-2 mb-1" style={{color:"var(--danger)"}}>Payment Failed</div>
                      <div className="p-3 rounded-3 mb-4" style={{background:"#fef2f2", border:"1.5px solid #fecaca"}}>
                        <div style={{fontSize:14, color:"var(--danger)", fontWeight:500}}>{payError}</div>
                      </div>
                      <div className="d-flex gap-3">
                        <button className="btn btn-outline-secondary flex-fill" onClick={()=>setStep("checkout")}>Change Method</button>
                        <button className="btn btn-primary flex-fill py-2 fw-600" onClick={retryPayment} style={{borderRadius:10}}>Retry Payment</button>
                      </div>
                    </>
                  )}

                  {/* FR24 – Timeout */}
                  {payState === "timeout" && (
                    <>
                      <div style={{fontSize:64}}>⏰</div>
                      <div className="section-title mt-2 mb-1" style={{color:"var(--warning)"}}>Session Expired</div>
                      <div className="text-muted mb-4" style={{fontSize:14}}>
                        Payment session timed out. Your cart has been preserved.
                      </div>
                      <button className="btn btn-warning w-100 py-2 fw-600" onClick={retryPayment} style={{borderRadius:10}}>
                        Restart Payment
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ════════════════ STEP: TRACKING ════════════════ */}
        {step === "tracking" && order && (
          <div className="row justify-content-center">
            <div className="col-lg-8">
              <div className="card border-0 shadow-sm" style={{borderRadius:16}}>
                <div className="card-body p-4">

                  <div className="d-flex justify-content-between align-items-start mb-4">
                    <div>
                      <div className="section-title">📦 Order Tracking</div>
                      <div className="text-muted" style={{fontSize:13}}>Order #{order.id}</div>
                    </div>
                    <span className={`badge-status bg-${STATUS_COLORS[order.status] || "secondary"} text-white`}>
                      {STATUS_LABELS[order.status] || order.status}
                    </span>
                  </div>

                  {/* Progress steps */}
                  {order.status !== "cancelled" && order.status !== "payment_timeout" && (
                    <div className="mb-4">
                      {["confirmed","preparing","ready_for_pickup","delivered"].map((s,i) => {
                        const statusOrder = ["confirmed","preparing","ready_for_pickup","delivered"];
                        const currentIdx  = statusOrder.indexOf(order.status);
                        const done  = i <= currentIdx;
                        const icons = ["✅","👨‍🍳","🏪","🎉"];
                        return (
                          <div key={s} className="d-flex align-items-center gap-3 mb-3">
                            <div style={{
                              width:40, height:40, borderRadius:"50%",
                              background: done ? "var(--brand)" : "#e2e8f0",
                              color: done ? "#fff" : "#94a3b8",
                              display:"flex", alignItems:"center", justifyContent:"center", fontSize:16, flexShrink:0
                            }}>
                              {icons[i]}
                            </div>
                            <div>
                              <div className="fw-600" style={{fontSize:14, color: done?"#1e293b":"#94a3b8"}}>{STATUS_LABELS[s]}</div>
                              {done && <div className="text-muted" style={{fontSize:12}}>Completed</div>}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Cancelled state */}
                  {order.status === "cancelled" && (
                    <div className="p-3 rounded-3 mb-4 text-center" style={{background:"#fef2f2", border:"1.5px solid #fecaca"}}>
                      <div style={{fontSize:32}}>🚫</div>
                      <div className="fw-600 mt-1" style={{color:"var(--danger)"}}>Order Cancelled</div>
                      {order.payment_method && ["online","wallet","meal_plan"].includes(order.payment_method) &&
                        <div className="text-muted" style={{fontSize:12, marginTop:4}}>Refund will be processed within 3-5 business days</div>
                      }
                    </div>
                  )}

                  {/* Staff simulator (FR16) */}
                  {!["cancelled","delivered","payment_timeout"].includes(order.status) && (
                    <div className="p-3 rounded-3 mb-4" style={{background:"#f0f9ff", border:"1.5px solid #bae6fd"}}>
                      <div className="fw-600 mb-2" style={{fontSize:13, color:"#0369a1"}}>👨‍💼 Staff Panel (Simulate Status Update)</div>
                      <div className="d-flex gap-2 flex-wrap">
                        {["preparing","ready_for_pickup","delivered"].map(s=>(
                          <button key={s} className="btn btn-sm btn-outline-primary" style={{fontSize:11}} onClick={()=>simulateStatusUpdate(s)}>
                            → {STATUS_LABELS[s]}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Order items summary */}
                  <div className="border-top pt-3">
                    <div className="fw-600 mb-2" style={{fontSize:14}}>Items Ordered</div>
                    {order.items.map(item => (
                      <div key={item.id} className="d-flex justify-content-between py-1">
                        <span style={{fontSize:13}}>{item.image_url} {item.name} ×{item.qty}</span>
                        <span style={{fontSize:13, fontWeight:600}}>{item.subtotal.toFixed(0)} EGP</span>
                      </div>
                    ))}
                    <div className="d-flex justify-content-between border-top mt-2 pt-2 fw-700">
                      <span>Total Paid</span>
                      <span style={{color:"var(--brand)"}}>{order.total.toFixed(2)} EGP</span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="d-flex gap-3 mt-4">
                    <button className="btn btn-outline-secondary" onClick={()=>{setStep("cart");setCart([]);setOrder(null);setPayState("idle");}}>
                      New Order
                    </button>
                    {["confirmed","preparing"].includes(order.status) && (
                      <button className="btn btn-outline-danger" onClick={()=>setCancelModal(true)}>
                        Cancel Order
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

      </div>

      {/* FR14 – Cancel Modal */}
      {cancelModal && (
        <div className="modal d-block" style={{background:"rgba(0,0,0,.5)"}}>
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content border-0" style={{borderRadius:14}}>
              <div className="modal-header border-0 pb-0">
                <h5 className="modal-title">Cancel Order?</h5>
                <button className="btn-close" onClick={()=>setCancelModal(false)}/>
              </div>
              <div className="modal-body">
                <p className="text-muted" style={{fontSize:14}}>
                  Are you sure you want to cancel order <strong>{order?.id}</strong>?
                  {["online","wallet","meal_plan"].includes(order?.payment_method) &&
                    " A full refund will be processed within 3-5 business days."}
                </p>
              </div>
              <div className="modal-footer border-0 pt-0">
                <button className="btn btn-outline-secondary" onClick={()=>setCancelModal(false)}>Keep Order</button>
                <button className="btn btn-danger" onClick={handleCancel}>Yes, Cancel</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* FR26 – Partial Refund Modal */}
      {partialModal && (
        <div className="modal d-block" style={{background:"rgba(0,0,0,.5)"}}>
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content border-0" style={{borderRadius:14}}>
              <div className="modal-header border-0 pb-0">
                <h5 className="modal-title">⚠️ Cancellation Window Passed</h5>
                <button className="btn-close" onClick={()=>setPartialModal(false)}/>
              </div>
              <div className="modal-body">
                <div className="p-3 rounded-3" style={{background:"#fffbeb", border:"1.5px solid #fde68a"}}>
                  <p style={{fontSize:14, marginBottom:8}}>
                    The 15-minute cancellation window has passed.
                    A <strong>50% partial refund</strong> of <strong>{((order?.total||0)*0.5).toFixed(2)} EGP</strong> may apply.
                  </p>
                  <p className="text-muted mb-0" style={{fontSize:13}}>Do you want to proceed with the partial refund?</p>
                </div>
              </div>
              <div className="modal-footer border-0 pt-0">
                <button className="btn btn-outline-secondary" onClick={()=>setPartialModal(false)}>Keep Order</button>
                <button className="btn btn-warning" onClick={confirmPartialRefund}>Accept Partial Refund</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
