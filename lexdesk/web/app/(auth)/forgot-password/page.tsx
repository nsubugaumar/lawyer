"use client";

import Link from "next/link";
import { useState } from "react";
import { Icon } from "@/components/Icon";
import { Field } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = await api<{ detail: string }>("/auth/password/forgot/", { method: "POST", body: { email } });
      setSent(body.detail);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="auth-card" onSubmit={submit}>
      <div>
        <span className="eyebrow">It happens to everyone</span>
        <h1 style={{ marginTop: 8 }}>Reset your password</h1>
        <p className="muted" style={{ marginTop: 6 }}>We will email you a link to choose a new one.</p>
      </div>
      {sent ? (
        <div className="notice ok"><Icon name="mail" /><span>{sent}</span></div>
      ) : (
        <>
          {error && <div className="notice err"><Icon name="alert" /><span>{error}</span></div>}
          <Field label="Email address" htmlFor="email">
            <input id="email" className="input" type="email" autoComplete="email" autoFocus required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <button className="btn btn-primary btn-lg btn-block" disabled={busy}>{busy ? "Sending…" : "Send reset link"}</button>
        </>
      )}
      <Link href="/login" className="small">← Back to sign in</Link>
    </form>
  );
}
