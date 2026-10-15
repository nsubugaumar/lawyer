"use client";

import Link from "next/link";
import { useState } from "react";
import { Icon } from "@/components/Icon";
import { Field } from "@/components/ui";
import { api, errorMessage, fieldError } from "@/lib/api";

/**
 * A law firm joins LexDesk. The managing partner registers the firm and
 * themselves; after activating from the email, they add their colleagues.
 */
export default function RegisterFirmPage() {
  const [form, setForm] = useState({
    firm_name: "", firm_phone: "", firm_email: "", city: "", first_name: "", last_name: "", email: "", phone: "", title: "Managing Partner", agree: false, website: "",
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<{ detail: string; firm: { name: string; code: string } } | null>(null);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setDone(await api("/firm/register/", { method: "POST", body: form }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="auth-card">
        <span style={{ width: 56, height: 56, borderRadius: "50%", display: "grid", placeItems: "center", background: "var(--success-soft)", color: "var(--success)" }}>
          <Icon name="mail" size={28} />
        </span>
        <h1>Check your email</h1>
        <p>{done.detail}</p>
        <div className="card card-pad stack" style={{ ["--gap" as string]: "10px" }}>
          <strong>What happens next</strong>
          <ol style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>
            <li>Open the email and choose your password.</li>
            <li>Sign in and set up two-factor sign-in on your phone.</li>
            <li>Add your colleagues under <strong>Settings › Team</strong>. Each gets their own invitation.</li>
            <li>Make the firm yours in <strong>Settings › Firm settings</strong>: logo, colours, office hours, WhatsApp.</li>
          </ol>
          <span className="muted small">Your case numbers will start with <strong>{done.firm.code}</strong>, e.g. {done.firm.code}-{new Date().getFullYear()}-0001.</span>
        </div>
        <Link href="/login" className="btn btn-primary btn-lg">Go to sign in</Link>
      </div>
    );
  }

  return (
    <form className="auth-card" style={{ width: "min(560px, 100%)" }} onSubmit={submit} noValidate>
      <div>
        <span className="eyebrow">For law firms</span>
        <h1 style={{ marginTop: 8 }}>Bring your firm to LexDesk</h1>
        <p className="muted" style={{ marginTop: 6 }}>
          Your own secure space for files, court diary, clients, billing and your website. Register as the managing partner; you will add your team next.
        </p>
      </div>
      {error ? <div className="notice err" role="alert"><Icon name="alert" /><span>{errorMessage(error)}</span></div> : null}

      <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0, ["--gap" as string]: "14px" }}>
        <legend className="label" style={{ marginBottom: 10 }}>The firm</legend>
        <Field label="Firm name" htmlFor="r-firm" error={fieldError(error, "firm_name")}>
          <input id="r-firm" className="input" required autoComplete="organization" placeholder="e.g. Mugisha & Partners Advocates" value={form.firm_name} onChange={set("firm_name")} />
        </Field>
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="Office phone" htmlFor="r-fphone" error={fieldError(error, "firm_phone")}>
            <input id="r-fphone" className="input" type="tel" required placeholder="0414 123 456" value={form.firm_phone} onChange={set("firm_phone")} />
          </Field>
          <Field label="Town or city" htmlFor="r-city">
            <input id="r-city" className="input" placeholder="Kampala" value={form.city} onChange={set("city")} />
          </Field>
        </div>
        <Field label="Office email (optional)" htmlFor="r-femail" error={fieldError(error, "firm_email")}>
          <input id="r-femail" className="input" type="email" value={form.firm_email} onChange={set("firm_email")} />
        </Field>
      </fieldset>

      <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0, ["--gap" as string]: "14px" }}>
        <legend className="label" style={{ marginBottom: 10 }}>You, the managing partner</legend>
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="First name" htmlFor="r-first" error={fieldError(error, "first_name")}><input id="r-first" className="input" required autoComplete="given-name" value={form.first_name} onChange={set("first_name")} /></Field>
          <Field label="Last name" htmlFor="r-last" error={fieldError(error, "last_name")}><input id="r-last" className="input" required autoComplete="family-name" value={form.last_name} onChange={set("last_name")} /></Field>
        </div>
        <Field label="Your work email" htmlFor="r-email" hint="We send your activation link here" error={fieldError(error, "email")}>
          <input id="r-email" className="input" type="email" required autoComplete="email" value={form.email} onChange={set("email")} />
        </Field>
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="Your mobile" htmlFor="r-phone" hint="For WhatsApp reminders" error={fieldError(error, "phone")}><input id="r-phone" className="input" type="tel" required autoComplete="tel" value={form.phone} onChange={set("phone")} /></Field>
          <Field label="Your title" htmlFor="r-title"><input id="r-title" className="input" value={form.title} onChange={set("title")} /></Field>
        </div>
      </fieldset>

      <input type="text" tabIndex={-1} autoComplete="off" className="sr-only" aria-hidden value={form.website} onChange={set("website")} />
      <label className="check">
        <input type="checkbox" checked={form.agree} onChange={set("agree")} />
        <span>I am authorised to register this firm, and I agree to the terms of use and to keep client information confidential.</span>
      </label>
      {fieldError(error, "agree") && <span className="error-text">{fieldError(error, "agree")}</span>}

      <button className="btn btn-primary btn-lg btn-block" disabled={busy || !form.agree}>{busy ? "Registering…" : "Register the firm"}</button>
      <p className="muted small" style={{ textAlign: "center" }}>
        Already on LexDesk? <Link href="/login">Sign in</Link>. Joining a firm that is already here? Ask your managing partner to add you.
      </p>
    </form>
  );
}
