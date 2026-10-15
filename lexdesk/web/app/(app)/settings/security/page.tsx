"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { QRCodeSVG } from "qrcode.react";
import { Suspense, useState } from "react";
import { Icon } from "@/components/Icon";
import { SettingsLayout } from "@/components/SettingsNav";
import { Field, Spinner, copyText, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";

export default function SecurityPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Security />
    </Suspense>
  );
}

function Security() {
  const { user, acceptSession, mfaSetupRequired } = useAuth();
  const toast = useToast();
  const router = useRouter();
  const setupFirst = useSearchParams().get("setup") === "1" || mfaSetupRequired;
  const [enrol, setEnrol] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [disable, setDisable] = useState({ password: "", code: "" });

  async function start() {
    setError(null);
    try {
      setEnrol(await api("/auth/mfa/setup/", { method: "POST" }));
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function confirm(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const body = await api<{ recovery_codes: string[] }>("/auth/mfa/confirm/", { method: "POST", body: { code } });
      acceptSession(body);
      setCodes(body.recovery_codes);
      setEnrol(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function turnOff(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/auth/mfa/disable/", { method: "POST", body: disable });
      acceptSession(await api("/auth/refresh/", { method: "POST" }));
      toast("Two-factor turned off.");
      location.reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (!user) return null;
  return (
    <SettingsLayout title="Sign-in & security" intro="Keep client files safe, even if a password leaks.">
      <div className="stack" style={{ ["--gap" as string]: "18px" }}>
        {setupFirst && !user.mfa_enabled && (
          <div className="notice warn"><Icon name="shield" /><span>The firm requires two-factor sign-in for staff. Set it up below to continue; it takes a minute.</span></div>
        )}
        <section className="card">
          <div className="card-head">
            <h3 className="row" style={{ ["--gap" as string]: "8px" }}><Icon name="shield" size={20} /> Two-factor sign-in</h3>
            {user.mfa_enabled ? <span className="badge badge-green">On</span> : <span className="badge badge-amber">Off</span>}
          </div>
          <div className="card-body stack" style={{ ["--gap" as string]: "16px" }}>
            {error && <div className="notice err"><Icon name="alert" /><span>{error}</span></div>}

            {codes ? (
              <>
                <div className="notice ok"><Icon name="check-circle" /><span>Two-factor is on. Save these recovery codes somewhere safe. Each works once if you lose your phone.</span></div>
                <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 8 }}>
                  {codes.map((c) => <code key={c} className="card" style={{ padding: "8px 12px", textAlign: "center", fontSize: 15, letterSpacing: ".06em" }}>{c}</code>)}
                </div>
                <div className="row wrap">
                  <button className="btn" onClick={() => { copyText(codes.join("\n")); toast("Codes copied."); }}><Icon name="copy" /> Copy codes</button>
                  <button className="btn btn-primary" onClick={() => router.replace(homeFor(user))}>I have saved them</button>
                </div>
              </>
            ) : enrol ? (
              <form className="grid-2" style={{ alignItems: "center", gap: 24 }} onSubmit={confirm}>
                <div className="stack" style={{ justifyItems: "center", ["--gap" as string]: "10px" }}>
                  <div style={{ padding: 14, background: "#fff", borderRadius: 14, border: "1px solid var(--line)" }}>
                    <QRCodeSVG value={enrol.otpauth_uri} size={188} />
                  </div>
                  <span className="muted tiny">Can't scan? Enter this key: <code>{enrol.secret}</code></span>
                </div>
                <div className="stack" style={{ ["--gap" as string]: "14px" }}>
                  <ol style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>
                    <li>Open Google Authenticator, Microsoft Authenticator or 1Password on your phone.</li>
                    <li>Scan the code.</li>
                    <li>Type the six digits it shows.</li>
                  </ol>
                  <Field label="Six-digit code" htmlFor="mfa-code">
                    <input id="mfa-code" className="input" inputMode="numeric" autoComplete="one-time-code" autoFocus value={code} onChange={(e) => setCode(e.target.value)} style={{ fontSize: 20, letterSpacing: ".3em", textAlign: "center" }} />
                  </Field>
                  <button className="btn btn-primary" disabled={code.replace(/\s/g, "").length < 6}>Turn on two-factor</button>
                </div>
              </form>
            ) : user.mfa_enabled ? (
              <form className="stack" style={{ ["--gap" as string]: "12px" }} onSubmit={turnOff}>
                <p>Each sign-in asks for a code from your phone, so a stolen password alone is not enough.</p>
                {user.role === "client" && (
                  <>
                    <div className="grid-2" style={{ gap: 12 }}>
                      <Field label="Password" htmlFor="d-pw"><input id="d-pw" type="password" className="input" value={disable.password} onChange={(e) => setDisable({ ...disable, password: e.target.value })} /></Field>
                      <Field label="Current code" htmlFor="d-code"><input id="d-code" className="input" inputMode="numeric" value={disable.code} onChange={(e) => setDisable({ ...disable, code: e.target.value })} /></Field>
                    </div>
                    <button className="btn btn-danger" style={{ justifySelf: "start" }}>Turn off two-factor</button>
                  </>
                )}
              </form>
            ) : (
              <>
                <p>Add a second step to signing in: a six-digit code from an app on your phone. It protects every client file you can open.</p>
                <button className="btn btn-primary" style={{ justifySelf: "start" }} onClick={start}><Icon name="shield" /> Set up two-factor</button>
              </>
            )}
          </div>
        </section>
      </div>
    </SettingsLayout>
  );
}
