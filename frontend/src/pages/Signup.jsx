import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { API } from "../api";
import ThemeToggle from "../components/ThemeToggle";

const providers = [
  { id: "google", label: "Google" },
];

export default function Signup() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const signup = async () => {
    if (!email.trim() || !password.trim() || !confirmPassword.trim()) {
      setError("Please fill all fields");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords must match");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${API}/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });

      const data = await res.json();
      if (res.ok && data.msg) {
        navigate("/login");
      } else {
        setError(data.detail || data.error || "Signup failed");
      }
    } catch {
      setError("Server error");
    } finally {
      setLoading(false);
    }
  };

  const oauthSignup = (provider) => {
    window.location.href = `${API}/oauth/${provider}/start`;
  };

  return (
    <div className="auth-page">
      <ThemeToggle className="auth-theme-toggle" />
      <div className="auth-card">
        <div className="auth-header">
          <p className="auth-kicker">Study Assistant</p>
          <h2>Create account</h2>
          <p>Save chats and uploaded study context to your account.</p>
        </div>

        <input
          className="auth-input"
          type="email"
          placeholder="Email address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && signup()}
        />

        <input
          className="auth-input"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && signup()}
        />

        <input
          className="auth-input"
          type="password"
          placeholder="Confirm password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && signup()}
        />

        {error ? <p className="error-text">{error}</p> : null}

        <button
          className="primary-button"
          onClick={signup}
          disabled={loading}
          style={{ width: "100%", marginTop: "15px" }}
        >
          {loading ? "Creating..." : "Create account"}
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
              onClick={() => oauthSignup(provider.id)}
              disabled={loading}
            >
              {provider.label}
            </button>
          ))}
        </div>

        <p onClick={() => navigate("/login")} className="link-text">
          Already have an account? Login
        </p>
      </div>
    </div>
  );
}
