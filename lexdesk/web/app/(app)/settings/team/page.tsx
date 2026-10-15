"use client";

import { useState } from "react";
import { Icon } from "@/components/Icon";
import { SettingsLayout } from "@/components/SettingsNav";
import { Avatar, Empty, Field, Modal, Spinner, Switch, useLoad, useToast } from "@/components/ui";
import { api, errorMessage, fieldError, list } from "@/lib/api";
import { isManager, useAuth } from "@/lib/auth";
import { relative } from "@/lib/format";

type Member = {
  id: string; email: string; first_name: string; last_name: string; full_name: string; phone: string; role: string; title: string;
  hourly_rate: string | null; is_active: boolean; mfa_enabled: boolean; is_locked: boolean; has_activated: boolean; last_login: string | null;
};

const ROLES = [["partner", "Partner"], ["lawyer", "Lawyer"], ["paralegal", "Paralegal"], ["receptionist", "Receptionist"], ["accountant", "Accountant"], ["admin", "Administrator"]];
const ROLE_LABEL = Object.fromEntries(ROLES);

export default function TeamPage() {
  const { user } = useAuth();
  const toast = useToast();
  const team = useLoad(() => list<Member>("/auth/team/", { ordering: "last_name" }), []);
  const [editing, setEditing] = useState<Member | "new" | null>(null);

  async function action(m: Member, what: "resend_invitation" | "unlock" | "reset_mfa") {
    try {
      const r = await api<{ detail: string }>(`/auth/team/${m.id}/${what}/`, { method: "POST" });
      toast(r.detail);
      team.reload();
    } catch (err) {
      toast(errorMessage(err), "err");
    }
  }

  if (!isManager(user)) {
    return <SettingsLayout title="Team" intro=""><div className="card"><Empty icon="lock" title="For partners and the practice manager" /></div></SettingsLayout>;
  }

  return (
    <SettingsLayout title="Team" intro={`Everyone at ${user?.firm?.name ?? "the firm"}. Add colleagues; they get an email to set their own password.`}>
      <div className="card">
        <div className="card-head">
          <h3>{team.data?.filter((m) => m.is_active).length ?? "–"} active people</h3>
          <button className="btn btn-primary btn-sm" onClick={() => setEditing("new")}><Icon name="plus" /> Add someone</button>
        </div>
        {team.loading ? <Spinner /> : (
          <ul className="list">
            {(team.data ?? []).map((m) => (
              <li key={m.id} className="list-item" style={{ flexWrap: "wrap", opacity: m.is_active ? 1 : 0.55 }}>
                <Avatar name={m.full_name} />
                <span className="grow" style={{ minWidth: 180 }}>
                  <strong style={{ display: "block" }}>{m.full_name}</strong>
                  <span className="muted small">{m.title || ROLE_LABEL[m.role]} · {m.email}</span>
                </span>
                <span className="row wrap" style={{ ["--gap" as string]: "6px" }}>
                  {!m.is_active && <span className="badge">Deactivated</span>}
                  {m.is_active && !m.has_activated && <span className="badge badge-amber">Invitation sent</span>}
                  {m.is_locked && <span className="badge badge-red">Locked</span>}
                  {m.has_activated && <span className={`badge ${m.mfa_enabled ? "badge-green" : "badge-amber"}`}>{m.mfa_enabled ? "2FA on" : "No 2FA"}</span>}
                  <span className="muted tiny desktop-only" style={{ minWidth: 90, textAlign: "right" }}>{m.last_login ? `Seen ${relative(m.last_login)}` : "Never signed in"}</span>
                  {!m.has_activated && m.is_active && <button className="btn btn-sm" onClick={() => action(m, "resend_invitation")}>Resend invite</button>}
                  {m.is_locked && <button className="btn btn-sm" onClick={() => action(m, "unlock")}>Unlock</button>}
                  <button className="btn btn-sm" onClick={() => setEditing(m)}>Edit</button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {editing && (
        <MemberModal member={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); team.reload(); }} onResetMfa={(m) => action(m, "reset_mfa")} />
      )}
    </SettingsLayout>
  );
}

function MemberModal({ member, onClose, onSaved, onResetMfa }: { member?: Member; onClose: () => void; onSaved: () => void; onResetMfa: (m: Member) => void }) {
  const toast = useToast();
  const [form, setForm] = useState({
    email: member?.email ?? "", first_name: member?.first_name ?? "", last_name: member?.last_name ?? "", phone: member?.phone ?? "",
    role: member?.role ?? "lawyer", title: member?.title ?? "", hourly_rate: member?.hourly_rate ?? "", is_active: member?.is_active ?? true,
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = { ...form, hourly_rate: form.hourly_rate || null };
    try {
      if (member) await api(`/auth/team/${member.id}/`, { method: "PATCH", body });
      else await api("/auth/team/", { method: "POST", body });
      toast(member ? "Saved." : `Invitation sent to ${form.email}.`);
      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={member ? member.full_name : "Add a colleague"} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" form="member-form" disabled={busy}>{busy ? "Saving…" : member ? "Save" : "Send invitation"}</button></>}>
      <form id="member-form" className="stack" style={{ ["--gap" as string]: "14px" }} onSubmit={save}>
        {error ? <div className="notice err"><Icon name="alert" /><span>{errorMessage(error)}</span></div> : null}
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="First name" htmlFor="t-first" error={fieldError(error, "first_name")}><input id="t-first" className="input" required value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} /></Field>
          <Field label="Last name" htmlFor="t-last" error={fieldError(error, "last_name")}><input id="t-last" className="input" required value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} /></Field>
        </div>
        <Field label="Work email" htmlFor="t-email" error={fieldError(error, "email")}><input id="t-email" className="input" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="Role" htmlFor="t-role" error={fieldError(error, "role")}>
            <select id="t-role" className="select" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </Field>
          <Field label="Mobile (for WhatsApp)" htmlFor="t-phone"><input id="t-phone" className="input" type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
        </div>
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="Job title" htmlFor="t-title"><input id="t-title" className="input" placeholder="e.g. Associate" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
          <Field label="Hourly rate" htmlFor="t-rate"><input id="t-rate" className="input" inputMode="decimal" value={form.hourly_rate} onChange={(e) => setForm({ ...form, hourly_rate: e.target.value })} /></Field>
        </div>
        {member && (
          <>
            <div className="row-between">
              <span><strong style={{ display: "block" }}>Active</strong><span className="muted small">Turning this off signs them out everywhere, at once.</span></span>
              <Switch checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label="Active" />
            </div>
            {member.mfa_enabled && (
              <button type="button" className="btn btn-sm btn-danger" style={{ justifySelf: "start" }} onClick={() => { if (confirm(`Reset two-factor for ${member.full_name}? They will set it up again at next sign-in.`)) onResetMfa(member); }}>
                Reset two-factor (lost phone)
              </button>
            )}
          </>
        )}
      </form>
    </Modal>
  );
}
