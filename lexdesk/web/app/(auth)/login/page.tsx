"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { Field, FirmMark, Spinner } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";
import { useFirm } from "@/lib/firm";
import { greeting } from "@/lib/format";

export default function LoginPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Login />
    </Suspense>
  );
}

function Login() {
  const { user, ready, login, verifyMfa, mfaSetupRequired } = useAuth();
  const { firm } = useFirm();
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ready && user) {
      // Only ever follow an in-app path, never an outside address.
      const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : null;
      router.replace(mfaSetupRequired ? "/settings/security?setup=1" : safeNext ?? homeFor(user));
    }
  }, [ready, user, next, router, mfaSetupRequired]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mfaToken) await verifyMfa(mfaToken, code);
      else {
        const result = await login(email, password);
        if ("mfa" in result) setMfaToken(result.mfa);
      }
    } catch (err) {
      setError(errorMessage(err));
      if ((err as { code?: string }).code === "mfa_expired") setMfaToken(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="auth-card" onSubmit={onSubmit}>
      <div className="mobile-only">
        <FirmMark firm={firm} size={48} />
      </div>
      <div>
        <span className="eyebrow">{greeting()}</span>
        <h1 style={{ marginTop: 8 }}>{mfaToken ? "One more step" : "Sign in to LexDesk"}</h1>
        <p className="muted" style={{ marginTop: 6 }}>
          {mfaToken ? "Enter the six-digit code from your authenticator app." : "For the firm's team and our clients."}
        </p>
      </div>

      {error && (
        <div className="notice err" role="alert">
          <Icon name="alert" />
          <span>{error}</span>
        </div>
      )}

      {mfaToken ? (
        <Field label="Verification code" htmlFor="code" hint="Lost your phone? Use one of your recovery codes, like ABCDE-12345.">
          <input
            id="code"
            className="input"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            value={code}
            onChange={(e) => setCode(e.target.value)}
            style={{ fontSize: 22, letterSpacing: "0.3em", textAlign: "center" }}
          />
        </Field>
      ) : (
        <>
          <Field label="Email address" htmlFor="email">
            <input id="email" className="input" type="email" autoComplete="username" autoFocus required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Password" htmlFor="password">
            <input id="password" className="input" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
        </>
      )}

      <button className="btn btn-primary btn-lg btn-block" disabled={busy}>
        {busy ? "Checking…" : mfaToken ? "Verify and continue" : "Sign in"}
      </button>

      <div className="row-between small">
        {mfaToken ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setMfaToken(null); setCode(""); }}>
            Use a different account
          </button>
        ) : (
          <Link href="/forgot-password">Forgotten your password?</Link>
        )}
        <Link href="/">Back to the website</Link>
      </div>
      {firm.booking_enabled && !mfaToken && (
        <p className="muted small" style={{ textAlign: "center" }}>
          New to the firm? <Link href="/book">Book a consultation</Link> and we will set up your portal.
        </p>
      )}
      {!mfaToken && (
        <p className="muted small" style={{ textAlign: "center", marginTop: -8 }}>
          Running a law firm? <Link href="/register">Register your firm on LexDesk</Link>.
        </p>
      )}
    </form>
  );
}
