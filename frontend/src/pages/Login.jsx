import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API } from "../api";
import ThemeToggle from "../components/ThemeToggle";

const providers = [
  { id: "google", label: "Google" },
];

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [resetCode, setResetCode] = useState("");
  const [resetSession, setResetSession] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [mode, setMode] = useState("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [foundAccount, setFoundAccount] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (localStorage.getItem("token")) navigate("/");
  }, [navigate]);

  const saveTokens = (data) => {
    localStorage.setItem("token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    navigate("/");
  };

  const login = async () => {
    if (!email.trim() || !password.trim()) {
      setError("Please fill all fields");
      return;
    }

    setLoading(true);
    setError("");
    setMessage("");

    try {
      const res = await fetch(`${API}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });

      const data = await res.json();
      if (res.ok && data.access_token) {
        saveTokens(data);
      } else {
        setError(data.detail || data.error || "Invalid login");
      }
    } catch {
      setError("Server error");
    } finally {
      setLoading(false);
    }
  };

  const findAccount = async () => {
    if (!email.trim()) {
      setError("Enter your email first");
      return;
    }

    setLoading(true);
    setError("");
    setMessage("");

    try {
      const res = await fetch(`${API}/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || "Could not find that account");
        return;
      }
      setFoundAccount(data);
      setMode("send-code");
    } catch {
      setError("Server error");
    } finally {
      setLoading(false);
    }
  };

  const sendResetCode = async () => {
    setLoading(true);
    setError("");
    setMessage("");

    try {
      const res = await fetch(`${API}/send-reset-code`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      const data = await res.json();
      if (res.ok) {
        setMessage(`Code sent to ${data.masked_email}.`);
        setMode("verify-code");
      } else {
        setError(data.detail || "Could not send reset code");
      }
    } catch {
      setError("Server error");
    } finally {
      setLoading(false);
    }
  };

  const verifyResetCode = async () => {
    if (!resetCode.trim()) {
      setError("Enter the code from your email");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");

    try {
      const res = await fetch(`${API}/verify-reset-code`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), code: resetCode.trim() }),
      });
      const data = await res.json();
      if (res.ok && data.reset_token) {
        setResetSession(data.reset_token);
        setMode("change-password");
      } else {
        setError(data.detail || "Verification code is wrong");
      }
    } catch {
      setError("Server error");
    } finally {
      setLoading(false);
    }
  };

  const changePassword = async () => {
    if (!newPassword.trim() || !confirmPassword.trim()) {
      setError("Enter and confirm your new password");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords must match");
      return;
    }

    setLoading(true);
    setError("");
    setMessage("");

    try {
      const res = await fetch(`${API}/change-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          reset_token: resetSession,
          password: newPassword,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setMode("login");
        setPassword("");
        setResetCode("");
        setResetSession("");
        setNewPassword("");
        setConfirmPassword("");
        setFoundAccount(null);
        setMessage("Password updated. You can log in now.");
      } else {
        setError(data.detail || "Could not change password");
      }
    } catch {
      setError("Server error");
    } finally {
      setLoading(false);
    }
  };

  const oauthLogin = (provider) => {
    window.location.href = `${API}/oauth/${provider}/start`;
  };

  const resetTitle = {
    login: "Welcome back",
    find: "Find your account",
    "send-code": "Reset your password",
    "verify-code": "Code verification",
    "change-password": "Change password",
  }[mode];

  const resetSubtitle = {
    login: "Log in to continue your saved study chats.",
    find: "Enter your email address to search for your account.",
    "send-code": "Choose how you want to receive the code.",
    "verify-code": "Enter the code that was sent to your email.",
    "change-password": "Pick a strong new password.",
  }[mode];

  return (
    <div className="auth-page">
      <ThemeToggle className="auth-theme-toggle" />
      <div className="auth-card">
        <div className="auth-header">
          <p className="auth-kicker">Study Assistant</p>
          <h2>{resetTitle}</h2>
          <p>{resetSubtitle}</p>
        </div>

        {mode === "login" ? (
          <>
            <input
              className="auth-input"
              type="email"
              placeholder="Email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && login()}
            />

            <input
              className="auth-input"
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && login()}
            />
          </>
        ) : mode === "find" ? (
          <input
            className="auth-input"
            type="email"
            placeholder="Email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && findAccount()}
          />
        ) : mode === "send-code" ? (
          <div className="reset-choice">
            <label>
              <input type="radio" checked readOnly />
              <span>
                Send code via email
                <small>{foundAccount?.masked_email || email}</small>
              </span>
            </label>
          </div>
        ) : mode === "verify-code" ? (
          <input
            className="auth-input"
            type="text"
            inputMode="numeric"
            maxLength={6}
            placeholder="Code"
            value={resetCode}
            onChange={(e) => setResetCode(e.target.value.replace(/\D/g, ""))}
            onKeyDown={(e) => e.key === "Enter" && verifyResetCode()}
          />
        ) : (
          <>
            <input
              className="auth-input"
              type="password"
              placeholder="New password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />

            <input
              className="auth-input"
              type="password"
              placeholder="Confirm new password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && changePassword()}
            />
          </>
        )}

        {error ? <p className="error-text">{error}</p> : null}
        {message ? <p className="success-text">{message}</p> : null}

        <button
          className="primary-button"
          onClick={
            mode === "login"
              ? login
              : mode === "find"
                ? findAccount
                : mode === "send-code"
                  ? sendResetCode
                  : mode === "verify-code"
                    ? verifyResetCode
                    : changePassword
          }
          disabled={loading}
          style={{ width: "100%", marginTop: "15px" }}
        >
          {loading ? "Working..." : mode === "login" ? "Login" : "Continue"}
        </button>

        {mode === "login" ? (
          <>
            <button
              className="text-button"
              type="button"
              onClick={() => {
                setError("");
                setMessage("");
                setMode("find");
              }}
              disabled={loading}
            >
              Forgot password?
            </button>

            <div className="auth-divider">
              <span>or continue with</span>
            </div>

            <div className="provider-grid">
              {providers.map((provider) => (
                <button
                  key={provider.id}
                  className="provider-button"
                  type="button"
                  onClick={() => oauthLogin(provider.id)}
                  disabled={loading}
                >
                  {provider.label}
                </button>
              ))}
            </div>

            <p onClick={() => navigate("/signup")} className="link-text">
              Don't have an account? Sign up
            </p>
          </>
        ) : (
          <p
            onClick={() => {
              setMode("login");
              setError("");
              setMessage("");
            }}
            className="link-text"
          >
            Back to login
          </p>
        )}
      </div>
    </div>
  );
}
