// ============================================================
// frontend/src/features/auth/auth_components.jsx
// ── FIXES APPLIED ────────────────────────────────────────────
// FIX-1: Removed the dead `handleSubmit` function that was
//         declared OUTSIDE the component at the bottom of the file
//         (lines after ResetSent). It referenced `username`,
//         `setError`, `setLoading` which don't exist in that scope
//         — it would have thrown a ReferenceError at runtime.
//         The real submit handler is `handleLogin` inside Login.
//
// FIX-2: Removed the duplicate local `apiFetch` definition.
//         All calls now go through the shared `apiFetch` imported
//         from "../../shared/api" (including the Reset flows).
//
// FIX-3: `handleLogin` now calls the shared `apiLogin` helper
//         (imported from shared/api) instead of duplicating the
//         fetch logic.  `apiLogin` already saves `jwt_token`.
//
// FIX-4: Role-based navigation now matches App.jsx routes exactly:
//         admin  → /admin   (was "/admin" ✓)
//         staff  → /stock   (was "/kitchen" ✗ — route doesn't exist)
//         student→ /menu    (unchanged ✓)
//
// FIX-5: onLoginSuccess receives the payload from apiLogin which
//         already has the correct shape. We pass `{ user }` so
//         App.jsx can localStorage.setItem("user", ...) correctly.
// ============================================================

import React, { useState, useEffect, useCallback, useRef } from "react";
import { apiLogin, apiFetch } from "../../shared/api";  // FIX-2 + FIX-3

// ── Google Fonts & Bootstrap Icons ───────────────────────────
if (typeof document !== "undefined") {
  if (!document.querySelector('link[href*="Inter"]')) {
    const f = document.createElement("link");
    f.rel  = "stylesheet";
    f.href = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Sora:wght@400;600;700&display=swap";
    document.head.appendChild(f);
  }
  if (!document.querySelector('link[href*="bootstrap-icons"]')) {
    const i = document.createElement("link");
    i.rel  = "stylesheet";
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

// ── University Logo Component ─────────────────────────────────
function UniversityLogo() {
  return (
    <div className="uc-uni-logo">
      <svg viewBox="0 0 80 80" className="uc-uni-logo-svg">
        {/* Outer ring */}
        <circle cx="40" cy="40" r="36" fill="none" stroke="var(--uc-gold)" strokeWidth="2" opacity="0.3"/>
        <circle cx="40" cy="40" r="32" fill="none" stroke="var(--uc-gold)" strokeWidth="1.5" opacity="0.5"/>
        
        {/* Inner decorative arcs */}
        <path d="M40 12 Q55 25, 55 40 Q55 55, 40 68" fill="none" stroke="var(--uc-gold)" strokeWidth="2.5" strokeLinecap="round"/>
        <path d="M40 12 Q25 25, 25 40 Q25 55, 40 68" fill="none" stroke="var(--uc-gold)" strokeWidth="2.5" strokeLinecap="round"/>
        
        {/* Center dot */}
        <circle cx="40" cy="40" r="8" fill="#c41e3a"/>
        <circle cx="40" cy="40" r="5" fill="none" stroke="white" strokeWidth="1.5"/>
        
        {/* Top accent */}
        <circle cx="40" cy="12" r="4" fill="#c41e3a"/>
      </svg>
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

  // FIX-3: uses shared apiLogin; FIX-4: correct staff route; FIX-5: correct payload shape
  const handleLogin = useCallback(async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    // Frontend domain validation (instant, before API call)
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
      // FIX-3: delegate to shared apiLogin — no duplicate fetch logic
      const data = await apiLogin(email, password);

      // FIX-5: pass full payload; App.jsx extracts data.user for localStorage
      if (onLoginSuccess) onLoginSuccess(data);

      // FIX-4: corrected staff route from "/kitchen" → "/stock"
      if (navigate) {
        const map = { student: "/menu", staff: "/stock", admin: "/admin" };
        navigate(map[data.user?.role] ?? "/menu");
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
        <div className="uc-mesh"  aria-hidden="true" />
        <div className="uc-grid"  aria-hidden="true" />
        <FloatingIcons />

        <div className="uc-center">
          {/* University Logo */}
          <UniversityLogo />

          {/* App Logo */}
          <div className="uc-logo">
            <div className="uc-logo-mark">🍽️</div>
            <span className="uc-logo-name">CampusBite</span>
          </div>

          {/* ── LOGIN ── */}
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

                {/* Email */}
                <div className="uc-field">
                  <label htmlFor="uc-email" className="uc-label">University Email</label>
                  <div className="uc-iw">
                    <i className="bi bi-envelope uc-iico" aria-hidden="true" />
                    <input
                      ref={emailRef}
                      id="uc-email"
                      data-testid="email-input"
                      type="email"
                      className={`uc-input${error ? " uc-input--err" : ""}`}
                      placeholder="name.ID@ejust.edu.eg"
                      value={email}
                      onChange={e => { setEmail(e.target.value); setError(null); }}
                      disabled={loading || secondsLeft > 0}
                      required
                      autoComplete="username"
                    />
                    {email.includes("@") && (
                      <span className={`uc-domain-badge ${isUniversityEmail(email) ? "valid" : "invalid"}`}>
                        <i className={`bi ${isUniversityEmail(email) ? "bi-check-circle-fill" : "bi-x-circle-fill"}`} />
                        {isUniversityEmail(email) ? " University" : " Invalid domain"}
                      </span>
                    )}
                  </div>
                </div>

                {/* Password */}
                <div className="uc-field">
                  <div className="uc-field-row">
                    <label htmlFor="uc-pw" className="uc-label" style={{ marginBottom: 0 }}>Password</label>
                    <button type="button" className="uc-link-btn"
                      onClick={() => setView("reset-request")}
                      data-testid="forgot-password-link">
                      Forgot password?
                    </button>
                  </div>
                  <div className="uc-iw">
                    <i className="bi bi-lock uc-iico" aria-hidden="true" />
                    <input
                      id="uc-pw"
                      data-testid="password-input"
                      type={showPass ? "text" : "password"}
                      className={`uc-input${error ? " uc-input--err" : ""}`}
                      placeholder="Min. 8 characters"
                      value={password}
                      onChange={e => { setPassword(e.target.value); setError(null); }}
                      disabled={loading || secondsLeft > 0}
                      required
                      autoComplete="current-password"
                    />
                    <button type="button" className="uc-eye"
                      onClick={() => setShowPass(v => !v)}
                      aria-label={showPass ? "Hide password" : "Show password"}>
                      <i className={`bi ${showPass ? "bi-eye-slash" : "bi-eye"}`} aria-hidden="true" />
                    </button>
                  </div>
                  {password.length > 0 && <StrengthBar pw={password} />}
                </div>

                {/* Submit */}
                <button
                  type="submit"
                  data-testid="login-submit"
                  className={`uc-btn${secondsLeft > 0 ? " uc-btn--locked" : ""}`}
                  disabled={loading || secondsLeft > 0 || !email || !password}
                >
                  {loading ? (
                    <><span className="uc-spinner" /><span>Signing in…</span></>
                  ) : secondsLeft > 0 ? (
                    <><i className="bi bi-lock-fill" aria-hidden="true" />
                      <span>Locked — <span className="uc-mono">{lockDisplay}</span></span></>
                  ) : (
                    <><i className="bi bi-box-arrow-in-right" aria-hidden="true" /><span>Sign In</span></>
                  )}
                </button>

              </form>

              <p className="uc-hint">
                <i className="bi bi-info-circle me-1" />
                Only <strong>@ejust.edu.eg</strong> email addresses are accepted
              </p>
            </div>
          )}

          {/* ── RESET REQUEST ── */}
          {view === "reset-request" && (
            <ResetRequest onBack={() => setView("login")} onSent={() => setView("reset-sent")} />
          )}

          {/* ── RESET SENT ── */}
          {view === "reset-sent" && (
            <ResetSent onBack={() => setView("login")} />
          )}

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
    INVALID_EMAIL_DOMAIN: {
      type: "warn", icon: "bi-envelope-x-fill",
      title: "Invalid email domain",
      body: error.message || `Only @${ALLOWED_DOMAINS.join(", @")} addresses are allowed.`,
    },
    ACCOUNT_LOCKED: {
      type: "warn", icon: "bi-lock-fill",
      title: "Account temporarily locked",
      body: <>Too many failed attempts. Unlocks in{" "}
        <span className="uc-mono" style={{ color: "var(--uc-gold)" }}>{lockDisplay}</span></>,
    },
    ACCOUNT_SUSPENDED: {
      type: "danger", icon: "bi-slash-circle-fill",
      title: "Account suspended",
      body: "Contact the university helpdesk to resolve this issue.",
    },
    INVALID_CREDENTIALS: {
      type: "danger", icon: "bi-exclamation-triangle-fill",
      title: "Invalid credentials",
      body: error.message || "Please check your email and password.",
    },
    EMPTY_RESPONSE: {
      type: "danger", icon: "bi-wifi-off",
      title: "Cannot reach server",
      body: "Make sure the backend is running on port 8000.",
    },
    INVALID_JSON: {
      type: "danger", icon: "bi-bug-fill",
      title: "Server error",
      body: "Check the terminal for errors.",
    },
  };

  const cfg = map[error?.code] ?? {
    type: "danger", icon: "bi-exclamation-circle",
    title: "Something went wrong",
    body: error?.message || "Please try again.",
  };

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
// FIX-2: uses shared apiFetch instead of local duplicate
function ResetRequest({ onBack, onSent }) {
  const [email,   setEmail]   = useState("");
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
            <i className="bi bi-envelope uc-iico" aria-hidden="true" />
            <input id="uc-rem" data-testid="reset-email-input" type="email"
              className="uc-input" placeholder="name.ID@ejust.edu.eg"
              value={email} onChange={e => setEmail(e.target.value)}
              required disabled={loading} autoFocus />
          </div>
        </div>
        <button type="submit" data-testid="reset-submit" className="uc-btn" disabled={loading || !email}>
          {loading
            ? <><span className="uc-spinner" /><span>Sending…</span></>
            : <><i className="bi bi-send" aria-hidden="true" /><span>Send Reset Link</span></>}
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
          A reset link has been sent if your email is registered.
          It expires in <strong style={{ color: "var(--uc-text)" }}>15 minutes</strong>.
        </p>
        <button type="button" data-testid="back-to-login" className="uc-btn"
          onClick={onBack} style={{ maxWidth: 200, margin: "0 auto" }}>
          <i className="bi bi-arrow-left" aria-hidden="true" /><span>Back to Sign In</span>
        </button>
      </div>
    </div>
  );
}

// FIX-1: The dead `handleSubmit` function that was here has been DELETED.
//         It lived outside the component, referenced undefined variables
//         (username, setError, setLoading), and was never called.

// ════════════════════════════════════════════════════════════
// CSS  (REDESIGNED: Premium dark navy + gold glassmorphism)
// ════════════════════════════════════════════════════════════
const CSS = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --uc-bg:    #0f172a; --uc-card:  rgba(30, 41, 59, 0.7);
    --uc-brd:   rgba(180, 142, 50, 0.15); --uc-brd-hi: rgba(180, 142, 50, 0.5);
    --uc-acc:   #b48e32; --uc-acc2:  #d4a843; --uc-gold: #b48e32;
    --uc-text:  #f1f5f9; --uc-muted: #94a3b8;
    --uc-danger:#ef4444; --uc-warn:  #f59e0b;
    --uc-inp:   rgba(255,255,255,0.05);
    --uc-r:20px; --uc-rs:12px;
    --fd:'Sora',sans-serif; --fb:'Inter',sans-serif;
  }
  .uc-page {
    min-height:100vh; display:flex; align-items:center; justify-content:center;
    background:var(--uc-bg); font-family:var(--fb); color:var(--uc-text);
    position:relative; overflow:hidden; padding:24px 16px;
  }
  .uc-mesh { position:fixed; inset:0; z-index:0; pointer-events:none; overflow:hidden; }
  .uc-mesh::before {
    content:''; position:absolute; inset:-40%;
    background:
      radial-gradient(ellipse 65% 55% at 15% 25%,rgba(180,142,50,.12) 0%,transparent 60%),
      radial-gradient(ellipse 55% 45% at 85% 75%,rgba(180,142,50,.08) 0%,transparent 55%),
      radial-gradient(ellipse 45% 55% at 55% 5%, rgba(196,30,58,.06) 0%,transparent 50%);
    animation:meshMove 18s ease-in-out infinite alternate;
  }
  @keyframes meshMove { from{transform:translate(0,0) rotate(0)} to{transform:translate(2%,1.5%) rotate(2deg)} }
  .uc-grid {
    position:fixed; inset:0; z-index:0; pointer-events:none;
    background-image:linear-gradient(rgba(180,142,50,.03) 1px,transparent 1px),
                     linear-gradient(90deg,rgba(180,142,50,.03) 1px,transparent 1px);
    background-size:60px 60px;
  }
  .uc-float-icons { position:fixed; inset:0; z-index:0; pointer-events:none; }
  .uc-fi { position:absolute; font-size:clamp(18px,2.5vw,28px); opacity:.07; filter:blur(.3px); animation:drift ease-in-out infinite; }
  .uc-fi--0{top:6%;left:4%;animation-duration:22s;animation-delay:0s}
  .uc-fi--1{top:14%;right:5%;animation-duration:19s;animation-delay:3s}
  .uc-fi--2{top:72%;left:3%;animation-duration:25s;animation-delay:6s}
  .uc-fi--3{top:82%;right:4%;animation-duration:20s;animation-delay:1s}
  .uc-fi--4{top:42%;left:2%;animation-duration:23s;animation-delay:8s}
  .uc-fi--5{top:58%;right:3%;animation-duration:21s;animation-delay:4s}
  .uc-fi--6{top:28%;left:8%;animation-duration:18s;animation-delay:10s}
  .uc-fi--7{top:91%;left:50%;animation-duration:24s;animation-delay:2s}
  @keyframes drift{0%,100%{transform:translate(0,0) rotate(0)}25%{transform:translate(7px,-10px) rotate(4deg)}50%{transform:translate(-5px,7px) rotate(-3deg)}75%{transform:translate(9px,5px) rotate(3deg)}}
  
  /* University Logo */
  .uc-uni-logo {
    display:flex; flex-direction:column; align-items:center; gap:12px; margin-bottom:20px;
    animation:fadeUp .5s ease both;
  }
  .uc-uni-logo-svg { width:70px; height:70px; }
  .uc-uni-text { text-align:center; line-height:1.4; }
  .uc-uni-name-en { display:block; font-family:var(--fd); font-size:11px; font-weight:600; color:var(--uc-text); letter-spacing:.02em; }
  .uc-uni-name-ar { display:block; font-size:10px; color:var(--uc-muted); margin-top:2px; direction:rtl; }
  .uc-uni-name-jp { display:block; font-size:9px; color:var(--uc-muted); margin-top:1px; }
  
  .uc-center {
    position:relative; z-index:1; width:100%; max-width:420px;
    display:flex; flex-direction:column; align-items:center;
    animation:fadeUp .45s ease both;
  }
  @keyframes fadeUp { from{opacity:0;transform:translateY(18px)} to{opacity:1;transform:translateY(0)} }
  .uc-logo { display:flex; align-items:center; gap:12px; margin-bottom:28px; }
  .uc-logo-mark {
    width:52px; height:52px; border-radius:16px;
    background:linear-gradient(135deg,var(--uc-gold),#d4a843);
    display:flex; align-items:center; justify-content:center; font-size:24px;
    box-shadow:0 8px 24px rgba(180,142,50,.35);
  }
  .uc-logo-name { font-family:var(--fd); font-size:26px; font-weight:700; letter-spacing:-.02em; color:var(--uc-text); }
  .uc-card {
    width:100%; 
    background:var(--uc-card); 
    border:1px solid var(--uc-brd);
    border-radius:var(--uc-r); 
    padding:clamp(28px,5vw,40px);
    box-shadow:0 4px 24px rgba(0,0,0,.4), 0 0 0 1px rgba(180,142,50,.1), inset 0 1px 0 rgba(255,255,255,.05);
    backdrop-filter:blur(20px);
    -webkit-backdrop-filter:blur(20px);
    transition:border-color .25s, box-shadow .25s;
  }
  .uc-card:focus-within { border-color:var(--uc-brd-hi); box-shadow:0 4px 24px rgba(0,0,0,.4), 0 0 0 1px rgba(180,142,50,.25), 0 0 40px rgba(180,142,50,.08), inset 0 1px 0 rgba(255,255,255,.05); }
  .uc-shake { animation:shake .5s ease; }
  @keyframes shake{0%,100%{transform:translateX(0)}20%{transform:translateX(-8px)}40%{transform:translateX(8px)}60%{transform:translateX(-5px)}80%{transform:translateX(5px)}}
  .uc-card-head { margin-bottom:24px; }
  .uc-heading { font-family:var(--fd); font-size:clamp(22px,3vw,28px); font-weight:700; letter-spacing:-.025em; margin-bottom:6px; color:var(--uc-text); }
  .uc-sub { font-size:14px; color:var(--uc-muted); line-height:1.6; }
  .uc-sub strong { color:var(--uc-gold); }
  .uc-field { margin-bottom:20px; }
  .uc-field-row { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
  .uc-label { display:block; font-size:11px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--uc-muted); margin-bottom:8px; }
  .uc-iw { position:relative; display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
  .uc-iico { position:absolute; left:14px; z-index:1; color:var(--uc-muted); font-size:15px; pointer-events:none; transition:color .2s; }
  .uc-iw:focus-within .uc-iico { color:var(--uc-gold); }
  .uc-input {
    width:100%; background:var(--uc-inp); border:1px solid rgba(255,255,255,.08); border-radius:var(--uc-rs);
    color:var(--uc-text); font-family:var(--fb); font-size:15px; padding:14px 44px;
    outline:none; transition:border-color .2s,box-shadow .2s,background .2s; -webkit-appearance:none;
  }
  .uc-input::placeholder { color:rgba(148,163,184,.5); }
  .uc-input:focus { border-color:var(--uc-gold); background:rgba(180,142,50,.05); box-shadow:0 0 0 3px rgba(180,142,50,.15); }
  .uc-input:disabled { opacity:.45; cursor:not-allowed; }
  .uc-input--err { border-color:var(--uc-danger) !important; }
  .uc-input--err:focus { box-shadow:0 0 0 3px rgba(239,68,68,.15) !important; }
  .uc-eye { position:absolute; right:12px; background:none; border:none; cursor:pointer; color:var(--uc-muted); font-size:15px; padding:4px; transition:color .2s; }
  .uc-eye:hover { color:var(--uc-gold); }
  .uc-link-btn { background:none; border:none; cursor:pointer; padding:0; font-family:var(--fb); font-size:12px; font-weight:600; color:var(--uc-gold); transition:opacity .2s; }
  .uc-link-btn:hover { opacity:.75; }
  .uc-domain-badge {
    display:inline-flex; align-items:center; gap:5px;
    font-size:11px; font-weight:600; padding:4px 10px; border-radius:100px;
    margin-top:6px; width:100%;
  }
  .uc-domain-badge.valid   { background:rgba(34,197,94,.12);  color:#4ade80; border:1px solid rgba(34,197,94,.25); }
  .uc-domain-badge.invalid { background:rgba(239,68,68,.12); color:#f87171; border:1px solid rgba(239,68,68,.25); }
  .uc-hint { font-size:12px; color:var(--uc-muted); margin-top:18px; text-align:center; line-height:1.5; }
  .uc-hint strong { color:var(--uc-gold); }
  .uc-str-wrap { display:flex; align-items:center; gap:10px; margin-top:8px; }
  .uc-str-bars { display:flex; gap:5px; flex:1; }
  .uc-str-bar  { flex:1; height:4px; border-radius:2px; background:rgba(255,255,255,.1); transition:background .3s; }
  .uc-str-bar--weak   { background:var(--uc-danger); }
  .uc-str-bar--medium { background:var(--uc-warn); }
  .uc-str-bar--strong { background:#4ade80; }
  .uc-str-label { font-size:11px; font-weight:600; min-width:40px; }
  .uc-str-label--weak   { color:var(--uc-danger); }
  .uc-str-label--medium { color:var(--uc-warn); }
  .uc-str-label--strong { color:#4ade80; }
  .uc-btn {
    width:100%; display:flex; align-items:center; justify-content:center; gap:10px;
    background:linear-gradient(135deg,var(--uc-gold) 0%,#9a7628 100%);
    border:none; border-radius:var(--uc-rs); color:#0f172a;
    font-family:var(--fb); font-size:15px; font-weight:600;
    padding:14px 24px; cursor:pointer; letter-spacing:.01em;
    box-shadow:0 4px 20px rgba(180,142,50,.35), inset 0 1px 0 rgba(255,255,255,.2);
    transition:transform .15s,box-shadow .15s,opacity .2s;
    position:relative; overflow:hidden; margin-top:8px;
  }
  .uc-btn::after { content:''; position:absolute; inset:0; background:linear-gradient(rgba(255,255,255,.15),transparent); opacity:0; transition:opacity .2s; }
  .uc-btn:hover:not(:disabled)::after { opacity:1; }
  .uc-btn:hover:not(:disabled) { transform:translateY(-2px); box-shadow:0 8px 30px rgba(180,142,50,.45), inset 0 1px 0 rgba(255,255,255,.2); }
  .uc-btn:active:not(:disabled) { transform:translateY(0); }
  .uc-btn:disabled { opacity:.5; cursor:not-allowed; transform:none; box-shadow:none; }
  .uc-btn--locked { background:linear-gradient(135deg,#78350f,#92400e) !important; color:#fef3c7 !important; box-shadow:0 4px 16px rgba(245,158,11,.2) !important; }
  .uc-ghost-btn {
    width:100%; background:rgba(255,255,255,.03); border:1px solid rgba(255,255,255,.1); border-radius:var(--uc-rs);
    color:var(--uc-muted); font-family:var(--fb); font-size:14px; padding:12px;
    cursor:pointer; transition:border-color .2s,color .2s,background .2s;
  }
  .uc-ghost-btn:hover { border-color:var(--uc-gold); color:var(--uc-text); background:rgba(180,142,50,.05); }
  .uc-spinner { width:16px; height:16px; flex-shrink:0; border:2px solid rgba(15,23,42,.3); border-top-color:#0f172a; border-radius:50%; animation:spin .7s linear infinite; }
  @keyframes spin { to{transform:rotate(360deg)} }
  .uc-mono { font-family:monospace; font-size:15px; font-weight:700; color:var(--uc-gold); }
  .uc-alert {
    display:flex; align-items:flex-start; gap:12px; border-radius:var(--uc-rs);
    padding:14px 16px; margin-bottom:20px; line-height:1.5; animation:fadeUp .25s ease both;
  }
  .uc-alert--danger { background:rgba(239,68,68,.1); border:1px solid rgba(239,68,68,.2); color:#fca5a5; }
  .uc-alert--warn   { background:rgba(245,158,11,.1);  border:1px solid rgba(245,158,11,.2);  color:#fcd34d; }
  .uc-alert-ico   { font-size:16px; flex-shrink:0; margin-top:1px; }
  .uc-alert-title { display:block; font-size:13px; font-weight:700; color:var(--uc-text); margin-bottom:3px; }
  .uc-alert-body  { display:block; font-size:12px; opacity:.9; }
  .uc-steps { display:flex; gap:8px; justify-content:center; margin-bottom:20px; }
  .uc-dot { width:8px; height:8px; border-radius:50%; background:rgba(255,255,255,.15); transition:all .3s; }
  .uc-dot.active { background:var(--uc-gold); width:24px; border-radius:4px; }
  .uc-dot.done   { background:#4ade80; }
  .uc-divider { display:flex; align-items:center; gap:12px; margin:20px 0; color:var(--uc-muted); font-size:12px; }
  .uc-divider::before,.uc-divider::after { content:''; flex:1; height:1px; background:rgba(255,255,255,.1); }
  .uc-success { text-align:center; padding:10px 0; }
  .uc-success-icon {
    width:68px; height:68px; border-radius:50%;
    background:rgba(180,142,50,.12); border:2px solid rgba(180,142,50,.3);
    display:flex; align-items:center; justify-content:center; font-size:28px;
    margin:0 auto 16px; animation:popIn .4s cubic-bezier(.175,.885,.32,1.275) both;
  }
  @keyframes popIn { from{transform:scale(.55);opacity:0} to{transform:scale(1);opacity:1} }
  .uc-footer { margin-top:24px; font-size:12px; color:var(--uc-muted); text-align:center; }
  .uc-footer a { color:var(--uc-gold); text-decoration:none; font-weight:500; transition:opacity .2s; }
  .uc-footer a:hover { opacity:.75; text-decoration:underline; }
  .uc-sep { margin:0 8px; opacity:.3; }
  @media(max-width:480px) { .uc-card{padding:24px 20px;border-radius:16px} .uc-uni-logo-svg{width:60px;height:60px} }
`;

export default Login;