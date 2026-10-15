"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { SettingsLayout } from "@/components/SettingsNav";
import { ModePicker } from "@/components/ThemeToggle";
import { Avatar, Field, useToast } from "@/components/ui";
import { api, errorMessage, fieldError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function ProfilePage() {
  const { user, reload, acceptSession } = useAuth();
  const toast = useToast();
  const [form, setForm] = useState({ first_name: "", last_name: "", phone: "", title: "" });
  const [error, setError] = useState<unknown>(null);
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [pwError, setPwError] = useState<unknown>(null);

  useEffect(() => {
    if (user) setForm({ first_name: user.first_name, last_name: user.last_name, phone: user.phone, title: user.title });
  }, [user]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("/auth/me/", { method: "PATCH", body: form });
      await reload();
      toast("Profile saved.");
    } catch (err) {
      setError(err);
    }
  }

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    setPwError(null);
    try {
      acceptSession(await api("/auth/password/change/", { method: "POST", body: pw }));
      setPw({ current_password: "", new_password: "" });
      toast("Password changed. Other devices have been signed out.");
    } catch (err) {
      setPwError(err);
    }
  }

  if (!user) return null;
  return (
    <SettingsLayout title="My profile" intro="How you appear to colleagues and clients.">
      <div className="stack" style={{ ["--gap" as string]: "18px" }}>
        <form className="card" onSubmit={save}>
          <div className="card-body stack" style={{ ["--gap" as string]: "16px" }}>
            <div className="row">
              <Avatar name={user.full_name} size="lg" />
              <span>
                <strong style={{ display: "block", fontSize: 18 }} className="serif">{user.full_name}</strong>
                <span className="muted">{user.email} · {user.role_display}</span>
              </span>
            </div>
            {error ? <div className="notice err"><Icon name="alert" /><span>{errorMessage(error)}</span></div> : null}
            <div className="grid-2" style={{ gap: 14 }}>
              <Field label="First name" htmlFor="p-first" error={fieldError(error, "first_name")}><input id="p-first" className="input" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} /></Field>
              <Field label="Last name" htmlFor="p-last" error={fieldError(error, "last_name")}><input id="p-last" className="input" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} /></Field>
            </div>
            <div className="grid-2" style={{ gap: 14 }}>
              <Field label="Mobile number" htmlFor="p-phone" hint="Used for WhatsApp reminders unless you set another number" error={fieldError(error, "phone")}><input id="p-phone" className="input" type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
              {user.role !== "client" && (
                <Field label="Job title" htmlFor="p-title"><input id="p-title" className="input" placeholder="e.g. Senior Associate" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
              )}
            </div>
          </div>
          <div className="card-foot"><button className="btn btn-primary">Save profile</button></div>
        </form>

        <section className="card">
          <div className="card-head"><h3>Appearance</h3></div>
          <div className="card-body stack" style={{ ["--gap" as string]: "10px" }}>
            <ModePicker />
            <span className="hint">Dark is easier on the eyes at night; light is clearer in a bright courtroom. Remembered on this device.</span>
          </div>
        </section>

        <form className="card" onSubmit={changePassword}>
          <div className="card-head"><h3>Change password</h3></div>
          <div className="card-body stack" style={{ ["--gap" as string]: "14px" }}>
            {pwError && !fieldError(pwError, "current_password") ? <div className="notice err"><Icon name="alert" /><span>{errorMessage(pwError)}</span></div> : null}
            <Field label="Current password" htmlFor="pw-cur" error={fieldError(pwError, "current_password")}><input id="pw-cur" type="password" className="input" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></Field>
            <Field label="New password" htmlFor="pw-new" hint="At least 12 characters." error={fieldError(pwError, "new_password")}><input id="pw-new" type="password" className="input" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></Field>
          </div>
          <div className="card-foot"><button className="btn" disabled={!pw.current_password || pw.new_password.length < 12}>Change password</button></div>
        </form>
      </div>
    </SettingsLayout>
  );
}
