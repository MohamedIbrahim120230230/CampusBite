// ============================================================
// frontend/src/features/auth/auth_components.jsx
// ── Redesigned visual styling from V0, logic from original ───
// ============================================================

import React, { useState, useEffect, useCallback, useRef } from "react";
import { apiLogin, apiFetch } from "../../shared/api";

// ── Google Fonts & Bootstrap Icons ───────────────────────────
if (typeof document !== "undefined") {
  if (!document.querySelector('link[href*="Inter"]')) {
    const f = document.createElement("link");
    f.rel = "stylesheet";
    f.href = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Sora:wght@400;600;700&display=swap";
    document.head.appendChild(f);
  }
  if (!document.querySelector('link[href*="bootstrap-icons"]')) {
    const i = document.createElement("link");
    i.rel = "stylesheet";
    i.href = "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css";
    document.head.appendChild(i);
  }
}

// ── University domain config ──────────────────────────────────
const ALLOWED_DOMAINS = ["ejust.edu.eg"];

function isUniversityEmail(email) {
  try {
    const domain = email.trim().split("@")[1]?.toLowerCase();
    return ALLOWED_DOMAINS.includes(domain);
  } catch {
    return false;
  }
}

// ── Lockout countdown ─────────────────────────────────────────
function useLockoutTimer(unlocksAt) {
  const [secondsLeft, setSecondsLeft] = useState(0);
  useEffect(() => {
    if (!unlocksAt) { setSecondsLeft(0); return; }
    const tick = () =>
      setSecondsLeft(Math.max(0, Math.ceil((new Date(unlocksAt) - Date.now()) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [unlocksAt]);
  const mm = String(Math.floor(secondsLeft / 60)).padStart(2, "0");
  const ss = String(secondsLeft % 60).padStart(2, "0");
  return { secondsLeft, display: `${mm}:${ss}` };
}

// ── Password strength ─────────────────────────────────────────
function getStrength(pw) {
  if (!pw) return { score: 0, label: "", cls: "" };
  let s = 0;
  if (pw.length >= 8)           s++;
  if (/[A-Z]/.test(pw))        s++;
  if (/[0-9]/.test(pw))        s++;
  if (/[^A-Za-z0-9]/.test(pw)) s++;
  return {
    score: s,
    label: ["", "Weak", "Weak", "Fair", "Strong"][s],
    cls:   ["", "weak", "weak", "medium", "strong"][s],
  };
}

// ── Step dots ─────────────────────────────────────────────────
function StepDots({ current, total }) {
  return (
    <div className="uc-steps" role="progressbar" aria-valuenow={current} aria-valuemax={total}>
      {Array.from({ length: total }).map((_, i) => (
        <span key={i} className={`uc-dot ${i === current ? "active" : i < current ? "done" : ""}`} />
      ))}
    </div>
  );
}

// ── Floating food icons ───────────────────────────────────────
function FloatingIcons() {
  const icons = ["🍕","🥗","☕","🍱","🥪","🍜","🥤","🍔"];
  return (
    <div className="uc-float-icons" aria-hidden="true">
      {icons.map((ic, i) => (
        <span key={i} className={`uc-fi uc-fi--${i}`}>{ic}</span>
      ))}
    </div>
  );
}

// ── University Logo ───────────────────────────────────────────
function UniversityLogo() {
  return (
    <div className="uc-uni-logo">
      <div className="uc-uni-logo-mark">
        <svg viewBox="0 0 80 80" className="uc-uni-svg">
          <circle cx="40" cy="40" r="36" fill="none" stroke="#b48e32" strokeWidth="2" />
          <circle cx="40" cy="25" r="10" fill="#dc2626" />
          <path
            d="M40 38 L40 58 M30 48 Q40 42 50 48 M25 58 Q40 50 55 58"
            fill="none" stroke="#1e3a5f" strokeWidth="3" strokeLinecap="round"
          />
        </svg>
      </div>
      <div className="uc-uni-text">
        <span className="uc-uni-name-en">Egypt-Japan University of Science and Technology</span>
        <span className="uc-uni-name-ar">الجامعة المصرية اليابانية للعلوم و التكنولوجيا</span>
        <span className="uc-uni-name-jp">エジプト日本科学技術大学</span>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// MAIN EXPORT
// ════════════════════════════════════════════════════════════
export function Login({ onLoginSuccess, navigate }) {
  const [view,      setView]      = useState("login");
  const [email,     setEmail]     = useState("");
  const [password,  setPassword]  = useState("");
  const [showPass,  setShowPass]  = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState(null);
  const [unlocksAt, setUnlocksAt] = useState(null);
  const [shake,     setShake]     = useState(false);
  const emailRef = useRef(null);

  const { secondsLeft, display: lockDisplay } = useLockoutTimer(unlocksAt);

  useEffect(() => { emailRef.current?.focus(); }, []);

  const triggerShake = () => {
    setShake(true);
    setTimeout(() => setShake(false), 600);
  };

  const handleLogin = useCallback(async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    if (!isUniversityEmail(email)) {
      const domainList = ALLOWED_DOMAINS.map(d => `@${d}`).join(", ");
      setError({
        code: "INVALID_EMAIL_DOMAIN",
        message: `Only university email addresses are allowed (${domainList}).`,
      });
      triggerShake();
      setLoading(false);
      return;
    }

    try {
      const data = await apiLogin(email, password);
      if (onLoginSuccess) onLoginSuccess(data);
      if (navigate) {
        const map = { student: "/menu", staff: "/stock", admin: "/admin" };
        const role = data?.user?.role ?? data?.role;
        navigate(map[role] ?? "/menu");
      }
    } catch (err) {
      setError(err);
      triggerShake();
      if (err?.code === "ACCOUNT_LOCKED" && err?.details?.unlocks_at) {
        setUnlocksAt(err.details.unlocks_at);
      }
    } finally {
      setLoading(false);
    }
  }, [email, password, navigate, onLoginSuccess]);

  return (
    <>
      <style>{CSS}</style>
      <div className="uc-page">
        <div className="uc-mesh" aria-hidden="true" />
        <div className="uc-grid" aria-hidden="true" />
        <FloatingIcons />

        <div className="uc-center">
          <UniversityLogo />

          <div className="uc-logo">
            <div className="uc-logo-mark">🍽️</div>
            <span className="uc-logo-name">CampusBite</span>
          </div>

          {view === "login" && (
            <div className={`uc-card ${shake ? "uc-shake" : ""}`}>
              <div className="uc-card-head">
                <h1 className="uc-heading">Welcome back</h1>
                <p className="uc-sub">
                  Sign in with your <strong>@ejust.edu.eg</strong> account
                </p>
              </div>

              {error && <ErrorBanner error={error} lockDisplay={lockDisplay} />}

              <form onSubmit={handleLogin} noValidate data-testid="login-form">

                {/* ── Email field ── */}
                <div className="uc-field">
                  <label htmlFor="uc-email" className="uc-label">University Email</label>
                  <div className="uc-iw">
                    <div className="uc-input-wrap">
                      <i className="bi bi-envelope uc-iico" aria-hidden="true" />
                      <input
                        ref={emailRef}
                        id="uc-email"
                        data-testid="email-input"
                        type="email"
                        className={`uc-input${error ? " uc-input--err" : ""}`}
                        placeholder="name.ID@ejust.edu.eg"
                        value={email}
                        onChange={(e) => { setEmail(e.target.value); setError(null); }}
                        disabled={loading || secondsLeft > 0}
                        required
                        autoComplete="username"
                      />
                    </div>
                    {email.includes("@") && (
                      <span className={`uc-domain-badge ${isUniversityEmail(email) ? "valid" : "invalid"}`}>
                        <i className={`bi ${isUniversityEmail(email) ? "bi-check-circle-fill" : "bi-x-circle-fill"}`} />
                        {isUniversityEmail(email) ? " University" : " Invalid domain"}
                      </span>
                    )}
                  </div>
                </div>

                {/* ── Password field ── */}
                <div className="uc-field">
                  <div className="uc-field-row">
                    <label htmlFor="uc-pw" className="uc-label" style={{ marginBottom: 0 }}>Password</label>
                    <button type="button" className="uc-link-btn" onClick={() => setView("reset-request")} data-testid="forgot-password-link">
                      Forgot password?
                    </button>
                  </div>
                  <div className="uc-iw">
                    <div className="uc-input-wrap">
                      <i className="bi bi-lock uc-iico" aria-hidden="true" />
                      <input
                        id="uc-pw"
                        data-testid="password-input"
                        type={showPass ? "text" : "password"}
                        className={`uc-input${error ? " uc-input--err" : ""}`}
                        placeholder="Min. 8 characters"
                        value={password}
                        onChange={(e) => { setPassword(e.target.value); setError(null); }}
                        disabled={loading || secondsLeft > 0}
                        required
                        autoComplete="current-password"
                      />
                      <button type="button" className="uc-eye" onClick={() => setShowPass(v => !v)} aria-label={showPass ? "Hide password" : "Show password"}>
                        <i className={`bi ${showPass ? "bi-eye-slash" : "bi-eye"}`} aria-hidden="true" />
                      </button>
                    </div>
                    {password.length > 0 && <StrengthBar pw={password} />}
                  </div>
                </div>

                <button
                  type="submit"
                  data-testid="login-submit"
                  className={`uc-btn${secondsLeft > 0 ? " uc-btn--locked" : ""}`}
                  disabled={loading || secondsLeft > 0 || !email || !password}
                >
                  {loading ? (
                    <><span className="uc-spinner" /><span>Signing in…</span></>
                  ) : secondsLeft > 0 ? (
                    <><i className="bi bi-lock-fill" aria-hidden="true" /><span>Locked — <span className="uc-mono">{lockDisplay}</span></span></>
                  ) : (
                    <><i className="bi bi-box-arrow-in-right" aria-hidden="true" /><span>Sign In</span></>
                  )}
                </button>
              </form>

              <p className="uc-hint">
                <i className="bi bi-info-circle" /> Only <strong>@ejust.edu.eg</strong> email addresses are accepted
              </p>
            </div>
          )}

          {view === "reset-request" && (
            <ResetRequest
              onBack={() => setView("login")}
              onSent={() => setView("reset-sent")}
              apiFetch={apiFetch}
            />
          )}

          {view === "reset-sent" && <ResetSent onBack={() => setView("login")} />}

          <p className="uc-footer">
            Need help? <a href="mailto:helpdesk@ejust.edu.eg">Contact IT Helpdesk</a>
            <span className="uc-sep">·</span>
            <a href="/privacy">Privacy</a>
          </p>
        </div>
      </div>
    </>
  );
}

// ── Error banner ──────────────────────────────────────────────
function ErrorBanner({ error, lockDisplay }) {
  const map = {
    INVALID_EMAIL_DOMAIN: { type: "warn",   icon: "bi-envelope-x-fill",         title: "Invalid email domain",        body: error.message || `Only @${ALLOWED_DOMAINS.join(", @")} addresses are allowed.` },
    ACCOUNT_LOCKED:       { type: "warn",   icon: "bi-lock-fill",                title: "Account temporarily locked",  body: <></>  },
    ACCOUNT_SUSPENDED:    { type: "danger", icon: "bi-slash-circle-fill",        title: "Account suspended",           body: "Contact the university helpdesk to resolve this issue." },
    INVALID_CREDENTIALS:  { type: "danger", icon: "bi-exclamation-triangle-fill",title: "Invalid credentials",         body: error.message || "Please check your email and password." },
    EMPTY_RESPONSE:       { type: "danger", icon: "bi-wifi-off",                 title: "Cannot reach server",         body: "Make sure the backend is running on port 8000." },
    INVALID_JSON:         { type: "danger", icon: "bi-bug-fill",                 title: "Server error",                body: "Check the terminal for errors." },
  };

  const cfg = map[error?.code ?? ""] ?? {
    type: "danger", icon: "bi-exclamation-circle",
    title: "Something went wrong", body: error?.message || "Please try again.",
  };

  if (error?.code === "ACCOUNT_LOCKED") {
    cfg.body = <>Too many failed attempts. Unlocks in <span className="uc-mono" style={{ color: "var(--uc-gold)" }}>{lockDisplay}</span></>;
  }

  return (
    <div role="alert" aria-live="assertive" className={`uc-alert uc-alert--${cfg.type}`}>
      <i className={`bi ${cfg.icon} uc-alert-ico`} aria-hidden="true" />
      <div>
        <strong className="uc-alert-title">{cfg.title}</strong>
        <span className="uc-alert-body">{cfg.body}</span>
      </div>
    </div>
  );
}

// ── Strength bar ──────────────────────────────────────────────
function StrengthBar({ pw }) {
  const { score, label, cls } = getStrength(pw);
  return (
    <div className="uc-str-wrap" role="meter" aria-label={`Password strength: ${label}`}>
      <div className="uc-str-bars">
        {[0,1,2,3].map(i => (
          <div key={i} className={`uc-str-bar${i < score ? ` uc-str-bar--${cls}` : ""}`} />
        ))}
      </div>
      {label && <span className={`uc-str-label uc-str-label--${cls}`}>{label}</span>}
    </div>
  );
}

// ── Reset request ─────────────────────────────────────────────
function ResetRequest({ onBack, onSent, apiFetch }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);

  const handle = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await apiFetch("/auth/password-reset/request", {
        method: "POST",
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });
      onSent();
    } catch {
      onSent(); // always show success (anti-enumeration)
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="uc-card" data-testid="reset-request-form">
      <StepDots current={0} total={2} />
      <div className="uc-card-head">
        <h2 className="uc-heading">Reset password</h2>
        <p className="uc-sub">Enter your university email — we'll send a link valid for 15 minutes.</p>
      </div>
      <form onSubmit={handle} noValidate>
        <div className="uc-field">
          <label htmlFor="uc-rem" className="uc-label">University Email</label>
          <div className="uc-iw">
            <div className="uc-input-wrap">
              <i className="bi bi-envelope uc-iico" aria-hidden="true" />
              <input
                id="uc-rem" data-testid="reset-email-input" type="email"
                className="uc-input" placeholder="name.ID@ejust.edu.eg"
                value={email} onChange={(e) => setEmail(e.target.value)}
                required disabled={loading} autoFocus
              />
            </div>
          </div>
        </div>
        <button type="submit" data-testid="reset-submit" className="uc-btn" disabled={loading || !email}>
          {loading ? <><span className="uc-spinner" /><span>Sending…</span></> : <><i className="bi bi-send" aria-hidden="true" /><span>Send Reset Link</span></>}
        </button>
      </form>
      <div className="uc-divider">or</div>
      <button type="button" className="uc-ghost-btn" onClick={onBack}>
        <i className="bi bi-arrow-left" aria-hidden="true" /> Back to Sign In
      </button>
    </div>
  );
}

// ── Reset sent ────────────────────────────────────────────────
function ResetSent({ onBack }) {
  return (
    <div className="uc-card">
      <StepDots current={1} total={2} />
      <div className="uc-success">
        <div className="uc-success-icon">✉️</div>
        <h2 className="uc-heading" style={{ fontSize: 20 }}>Check your inbox</h2>
        <p className="uc-sub" style={{ marginBottom: 24 }}>
          A reset link has been sent if your email is registered. It expires in{" "}
          <strong style={{ color: "var(--uc-text)" }}>15 minutes</strong>.
        </p>
        <button type="button" data-testid="back-to-login" className="uc-btn" onClick={onBack} style={{ maxWidth: 200, margin: "0 auto" }}>
          <i className="bi bi-arrow-left" aria-hidden="true" />
          <span>Back to Sign In</span>
        </button>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// CSS
// ════════════════════════════════════════════════════════════
const CSS = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --uc-bg:    #0f172a;
    --uc-bg2:   #1e293b;
    --uc-card:  rgba(30, 41, 59, 0.7);
    --uc-brd:   rgba(180, 142, 50, 0.15);
    --uc-brd-hi: rgba(180, 142, 50, 0.5);
    --uc-acc:   #b48e32;
    --uc-acc2:  #d4a84b;
    --uc-gold:  #b48e32;
    --uc-text:  #f1f5f9;
    --uc-muted: #94a3b8;
    --uc-danger:#ef4444;
    --uc-warn:  #f59e0b;
    --uc-success: #22c55e;
    --uc-inp:   rgba(15, 23, 42, 0.6);
    --uc-r:18px;
    --uc-rs:12px;
    --fd:'Sora', 'Inter', sans-serif;
    --fb:'Inter', 'Sora', sans-serif;
  }
  .uc-page {
    min-height:100vh; display:flex; align-items:center; justify-content:center;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
    font-family:var(--fb); color:var(--uc-text); position:relative; overflow:hidden; padding:24px 16px;
  }
  .uc-mesh { position:fixed; inset:0; z-index:0; pointer-events:none; overflow:hidden; }
  .uc-mesh::before {
    content:''; position:absolute; inset:-40%;
    background:
      radial-gradient(ellipse 60% 50% at 20% 30%, rgba(180,142,50,.08) 0%,transparent 50%),
      radial-gradient(ellipse 50% 40% at 80% 70%, rgba(180,142,50,.06) 0%,transparent 45%),
      radial-gradient(ellipse 40% 50% at 50% 10%, rgba(220,38,38,.04) 0%,transparent 40%);
    animation:meshMove 20s ease-in-out infinite alternate;
  }
  @keyframes meshMove { from{transform:translate(0,0) rotate(0deg) scale(1)} to{transform:translate(2%,2%) rotate(3deg) scale(1.02)} }
  .uc-grid {
    position:fixed; inset:0; z-index:0; pointer-events:none;
    background-image: linear-gradient(rgba(180,142,50,.03) 1px,transparent 1px), linear-gradient(90deg,rgba(180,142,50,.03) 1px,transparent 1px);
    background-size:60px 60px;
  }
  .uc-float-icons { position:fixed; inset:0; z-index:0; pointer-events:none; }
  .uc-fi { position:absolute; font-size:clamp(18px,2.5vw,28px); opacity:.06; filter:blur(.3px); animation:drift ease-in-out infinite; }
  .uc-fi--0{top:8%;left:5%;animation-duration:24s;animation-delay:0s}
  .uc-fi--1{top:16%;right:6%;animation-duration:20s;animation-delay:3s}
  .uc-fi--2{top:70%;left:4%;animation-duration:26s;animation-delay:6s}
  .uc-fi--3{top:80%;right:5%;animation-duration:22s;animation-delay:1s}
  .uc-fi--4{top:44%;left:3%;animation-duration:25s;animation-delay:8s}
  .uc-fi--5{top:56%;right:4%;animation-duration:23s;animation-delay:4s}
  .uc-fi--6{top:30%;left:9%;animation-duration:19s;animation-delay:10s}
  .uc-fi--7{top:90%;left:48%;animation-duration:27s;animation-delay:2s}
  @keyframes drift{0%,100%{transform:translate(0,0) rotate(0)}25%{transform:translate(8px,-12px) rotate(5deg)}50%{transform:translate(-6px,8px) rotate(-4deg)}75%{transform:translate(10px,6px) rotate(4deg)}}
  .uc-uni-logo { display:flex; flex-direction:column; align-items:center; margin-bottom:20px; animation:fadeUp .5s ease both; }
  .uc-uni-logo-mark { width:80px; height:80px; margin-bottom:12px; filter:drop-shadow(0 4px 20px rgba(180,142,50,.3)); }
  .uc-uni-svg { width:100%; height:100%; }
  .uc-uni-text { display:flex; flex-direction:column; align-items:center; text-align:center; gap:2px; }
  .uc-uni-name-en { font-family:var(--fd); font-size:11px; font-weight:600; color:var(--uc-text); letter-spacing:.02em; }
  .uc-uni-name-ar { font-size:10px; color:var(--uc-muted); direction:rtl; }
  .uc-uni-name-jp { font-size:9px; color:var(--uc-muted); opacity:.8; }
  .uc-center { position:relative; z-index:1; width:100%; max-width:420px; display:flex; flex-direction:column; align-items:center; animation:fadeUp .5s ease both; }
  @keyframes fadeUp { from{opacity:0;transform:translateY(24px)} to{opacity:1;transform:translateY(0)} }
  .uc-logo { display:flex; align-items:center; gap:12px; margin-bottom:28px; }
  .uc-logo-mark { width:52px; height:52px; border-radius:16px; background:linear-gradient(135deg,var(--uc-acc) 0%,var(--uc-acc2) 100%); display:flex; align-items:center; justify-content:center; font-size:24px; box-shadow:0 8px 24px rgba(180,142,50,.35),0 0 0 1px rgba(180,142,50,.2); }
  .uc-logo-name { font-family:var(--fd); font-size:26px; font-weight:700; letter-spacing:-.03em; background:linear-gradient(135deg,var(--uc-text) 0%,var(--uc-acc2) 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
  .uc-card { width:100%; background:rgba(30,41,59,.6); backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px); border:1px solid rgba(180,142,50,.15); border-radius:var(--uc-r); padding:clamp(28px,6vw,40px); box-shadow:0 32px 64px rgba(0,0,0,.4),0 0 0 1px rgba(255,255,255,.05) inset,0 1px 0 rgba(255,255,255,.1) inset; transition:border-color .3s ease,box-shadow .3s ease; }
  .uc-card:focus-within { border-color:rgba(180,142,50,.4); box-shadow:0 32px 64px rgba(0,0,0,.5),0 0 40px rgba(180,142,50,.1),0 0 0 1px rgba(255,255,255,.05) inset,0 1px 0 rgba(255,255,255,.1) inset; }
  .uc-shake { animation:shake .5s cubic-bezier(.36,.07,.19,.97) both; }
  @keyframes shake{0%,100%{transform:translateX(0)}20%{transform:translateX(-10px)}40%{transform:translateX(10px)}60%{transform:translateX(-6px)}80%{transform:translateX(6px)}}
  .uc-card-head { margin-bottom:24px; text-align:center; }
  .uc-heading { font-family:var(--fd); font-size:clamp(22px,4vw,28px); font-weight:700; letter-spacing:-.03em; margin-bottom:8px; color:var(--uc-text); }
  .uc-sub { font-size:14px; color:var(--uc-muted); line-height:1.6; }
  .uc-sub strong { color:var(--uc-acc); }
  .uc-field { margin-bottom:20px; }
  .uc-field-row { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
  .uc-label { display:block; font-size:11px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--uc-muted); margin-bottom:8px; }

  /* ── FIXED: iw is now a column container; input-wrap holds the icon+input row ── */
  .uc-iw { display:flex; flex-direction:column; gap:8px; width:100%; }
  .uc-input-wrap { position:relative; display:flex; align-items:center; width:100%; }

  .uc-iico { position:absolute; left:16px; top:50%; transform:translateY(-50%); z-index:2; color:var(--uc-muted); font-size:15px; pointer-events:none; transition:color .25s ease; }
  .uc-input-wrap:focus-within .uc-iico { color:var(--uc-acc); }

  .uc-input { width:100%; background:var(--uc-inp); border:1px solid rgba(148,163,184,.15); border-radius:var(--uc-rs); color:var(--uc-text); font-family:var(--fb); font-size:15px; padding:14px 48px; outline:none; transition:all .25s ease; -webkit-appearance:none; }
  .uc-input::placeholder { color:rgba(148,163,184,.5); }
  .uc-input:focus { border-color:var(--uc-acc); background:rgba(180,142,50,.05); box-shadow:0 0 0 4px rgba(180,142,50,.12); }
  .uc-input:disabled { opacity:.4; cursor:not-allowed; }
  .uc-input--err { border-color:var(--uc-danger) !important; }
  .uc-input--err:focus { box-shadow:0 0 0 4px rgba(239,68,68,.15) !important; }
  .uc-eye { position:absolute; right:14px; top:50%; transform:translateY(-50%); background:none; border:none; cursor:pointer; color:var(--uc-muted); font-size:15px; padding:6px; transition:color .25s ease; border-radius:6px; z-index:2; }
  .uc-eye:hover { color:var(--uc-acc); background:rgba(180,142,50,.1); }
  .uc-link-btn { background:none; border:none; cursor:pointer; padding:0; font-family:var(--fb); font-size:12px; font-weight:600; color:var(--uc-acc); transition:opacity .25s ease; }
  .uc-link-btn:hover { opacity:.75; }
  .uc-domain-badge { display:inline-flex; align-items:center; gap:5px; font-size:11px; font-weight:600; padding:4px 12px; border-radius:100px; width:100%; }
  .uc-domain-badge.valid { background:rgba(34,197,94,.1); color:var(--uc-success); border:1px solid rgba(34,197,94,.25); }
  .uc-domain-badge.invalid { background:rgba(239,68,68,.1); color:var(--uc-danger); border:1px solid rgba(239,68,68,.25); }
  .uc-hint { font-size:12px; color:var(--uc-muted); margin-top:18px; text-align:center; line-height:1.5; }
  .uc-hint strong { color:var(--uc-acc); }
  .uc-str-wrap { display:flex; align-items:center; gap:10px; width:100%; }
  .uc-str-bars { display:flex; gap:5px; flex:1; }
  .uc-str-bar { flex:1; height:4px; border-radius:3px; background:rgba(148,163,184,.2); transition:background .3s ease; }
  .uc-str-bar--weak { background:var(--uc-danger); }
  .uc-str-bar--medium { background:var(--uc-warn); }
  .uc-str-bar--strong { background:var(--uc-success); }
  .uc-str-label { font-size:11px; font-weight:600; min-width:42px; }
  .uc-str-label--weak { color:var(--uc-danger); }
  .uc-str-label--medium { color:var(--uc-warn); }
  .uc-str-label--strong { color:var(--uc-success); }
  .uc-btn { width:100%; display:flex; align-items:center; justify-content:center; gap:10px; background:linear-gradient(135deg,var(--uc-acc) 0%,#9a7a2c 100%); border:none; border-radius:var(--uc-rs); color:#fff; font-family:var(--fb); font-size:15px; font-weight:600; padding:15px 24px; cursor:pointer; letter-spacing:.01em; box-shadow:0 6px 20px rgba(180,142,50,.35),0 0 0 1px rgba(255,255,255,.1) inset; transition:all .25s ease; position:relative; overflow:hidden; margin-top:8px; }
  .uc-btn::before { content:''; position:absolute; inset:0; background:linear-gradient(rgba(255,255,255,.15),transparent); opacity:0; transition:opacity .25s ease; }
  .uc-btn:hover:not(:disabled)::before { opacity:1; }
  .uc-btn:hover:not(:disabled) { transform:translateY(-2px); box-shadow:0 12px 32px rgba(180,142,50,.45),0 0 0 1px rgba(255,255,255,.1) inset; }
  .uc-btn:active:not(:disabled) { transform:translateY(0); }
  .uc-btn:disabled { opacity:.4; cursor:not-allowed; transform:none; box-shadow:none; }
  .uc-btn--locked { background:linear-gradient(135deg,#78350f,#92400e) !important; box-shadow:0 6px 20px rgba(245,158,11,.25) !important; }
  .uc-ghost-btn { width:100%; background:transparent; border:1px solid rgba(148,163,184,.2); border-radius:var(--uc-rs); color:var(--uc-muted); font-family:var(--fb); font-size:14px; padding:13px; cursor:pointer; transition:all .25s ease; }
  .uc-ghost-btn:hover { border-color:var(--uc-acc); color:var(--uc-acc); background:rgba(180,142,50,.05); }
  .uc-spinner { width:16px; height:16px; flex-shrink:0; border:2px solid rgba(255,255,255,.3); border-top-color:#fff; border-radius:50%; animation:spin .7s linear infinite; }
  @keyframes spin { to{transform:rotate(360deg)} }
  .uc-mono { font-family:'SF Mono',Monaco,'Cascadia Code',monospace; font-size:15px; font-weight:700; color:var(--uc-gold); }
  .uc-alert { display:flex; align-items:flex-start; gap:12px; border-radius:var(--uc-rs); padding:14px 16px; margin-bottom:20px; line-height:1.5; animation:fadeUp .3s ease both; }
  .uc-alert--danger { background:rgba(239,68,68,.1); border:1px solid rgba(239,68,68,.25); color:#fca5a5; }
  .uc-alert--warn { background:rgba(245,158,11,.1); border:1px solid rgba(245,158,11,.25); color:var(--uc-warn); }
  .uc-alert-ico { font-size:16px; flex-shrink:0; margin-top:1px; }
  .uc-alert-title { display:block; font-size:13px; font-weight:700; color:#fff; margin-bottom:3px; }
  .uc-alert-body { display:block; font-size:12px; opacity:.9; }
  .uc-steps { display:flex; gap:8px; justify-content:center; margin-bottom:22px; }
  .uc-dot { width:8px; height:8px; border-radius:50%; background:rgba(148,163,184,.3); transition:all .3s ease; }
  .uc-dot.active { background:var(--uc-acc); width:24px; border-radius:4px; box-shadow:0 0 12px rgba(180,142,50,.4); }
  .uc-dot.done { background:var(--uc-success); }
  .uc-divider { display:flex; align-items:center; gap:12px; margin:20px 0; color:var(--uc-muted); font-size:11px; text-transform:uppercase; letter-spacing:.1em; }
  .uc-divider::before,.uc-divider::after { content:''; flex:1; height:1px; background:linear-gradient(90deg,transparent,rgba(148,163,184,.2),transparent); }
  .uc-success { text-align:center; padding:12px 0; }
  .uc-success-icon { width:68px; height:68px; border-radius:50%; background:rgba(34,197,94,.1); border:2px solid rgba(34,197,94,.3); display:flex; align-items:center; justify-content:center; font-size:28px; margin:0 auto 18px; animation:popIn .4s cubic-bezier(.175,.885,.32,1.275) both; }
  @keyframes popIn { from{transform:scale(.5);opacity:0} to{transform:scale(1);opacity:1} }
  .uc-footer { margin-top:24px; font-size:12px; color:var(--uc-muted); text-align:center; }
  .uc-footer a { color:var(--uc-acc); text-decoration:none; font-weight:500; transition:opacity .25s ease; }
  .uc-footer a:hover { opacity:.75; text-decoration:underline; }
  .uc-sep { margin:0 8px; opacity:.3; }
  @media(max-width:480px) {
    .uc-card{padding:24px 20px;border-radius:14px}
    .uc-uni-logo-mark{width:64px;height:64px}
    .uc-logo-mark{width:44px;height:44px}
    .uc-logo-name{font-size:22px}
  }
`;

export default Login;