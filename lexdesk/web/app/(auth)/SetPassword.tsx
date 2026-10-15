"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { Field, Spinner } from "@/components/ui";
import { api, errorMessage, fieldError } from "@/lib/api";

/** First-time activation and password reset share one screen. */
export function SetPassword({ purpose }: { purpose: "activate" | "reset" }) {
  const params = useSearchParams();
  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";
  const [who, setWho] = useState<{ first_name: string; email: string } | null>(null);
  const [checking, setChecking] = useState(true);
  const [linkError, setLinkError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    api<{ first_name: string; email: string }>("/auth/activate/", { query: { uid, token } })
      .then(setWho)
      .catch((e) => setLinkError(errorMessage(e)))
      .finally(() => setChecking(false));
  }, [uid, token]);

  const strength = [
    password.length >= 12,
    /[A-Z]/.test(password) && /[a-z]/.test(password),
    /\d/.test(password),
    /[^A-Za-z0-9]/.test(password),
  ].filter(Boolean).length;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setError({ fields: { confirm: ["The two passwords do not match."] } });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api("/auth/activate/", { method: "POST", body: { uid, token, password } });
      setDone(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (checking) return <Spinner />;

  if (linkError)
    return (
      <div className="auth-card">
        <h1>This link has expired</h1>
        <p className="muted">{linkError} Links work once and last three days.</p>
        <Link className="btn btn-primary" href="/forgot-password">Send me a new link</Link>
      </div>
    );

  if (done)
    return (
      <div className="auth-card">
        <span style={{ width: 56, height: 56, borderRadius: "50%", display: "grid", placeItems: "center", background: "var(--success-soft)", color: "var(--success)" }}>
          <Icon name="check" size={30} />
        </span>
        <h1>You are all set</h1>
        <p className="muted">Your password is saved. Sign in with {who?.email}.</p>
        <Link className="btn btn-primary btn-lg" href="/login">Sign in</Link>
      </div>
    );

  return (
    <form className="auth-card" onSubmit={submit}>
      <div>
        <span className="eyebrow">{purpose === "activate" ? "Welcome" : "Password reset"}</span>
        <h1 style={{ marginTop: 8 }}>{purpose === "activate" ? `Hello ${who?.first_name}, choose a password` : "Choose a new password"}</h1>
        <p className="muted" style={{ marginTop: 6 }}>For {who?.email}. Use at least 12 characters; a short sentence works well.</p>
      </div>
      {error && !fieldError(error, "confirm") ? (
        <div className="notice err"><Icon name="alert" /><span>{errorMessage(error)}</span></div>
      ) : null}
      <Field label="New password" htmlFor="pw" error={fieldError(error, "password")}>
        <input id="pw" className="input" type="password" autoComplete="new-password" autoFocus value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <div className="progress" aria-label={`Password strength ${strength} of 4`}>
        {[1, 2, 3, 4].map((i) => <span key={i} className={i <= strength ? "on" : ""} />)}
      </div>
      <Field label="Type it again" htmlFor="pw2" error={fieldError(error, "confirm")}>
        <input id="pw2" className="input" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </Field>
      <button className="btn btn-primary btn-lg btn-block" disabled={busy || password.length < 12}>
        {busy ? "Saving…" : "Save password"}
      </button>
    </form>
  );
}
