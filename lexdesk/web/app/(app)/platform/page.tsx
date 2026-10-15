"use client";

import { useState } from "react";
import { Icon } from "@/components/Icon";
import { Empty, ErrorNote, Field, Modal, Spinner, Switch, useLoad, useToast } from "@/components/ui";
import { api, errorMessage, fieldError, list } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";

type Firm = {
  id: number; name: string; slug: string; code: string; domain: string; is_active: boolean; created_at: string | null;
  staff_count: number; matter_count: number; phone: string; email: string;
};

export default function PlatformPage() {
  const { user } = useAuth();
  const toast = useToast();
  const firms = useLoad(() => list<Firm>("/platform/firms/"), []);
  const [adding, setAdding] = useState(false);

  async function setActive(f: Firm, is_active: boolean) {
    if (!is_active && !confirm(`Suspend ${f.name}? Everyone at the firm is signed out at once and cannot sign in until you reactivate it. Their files are kept.`)) return;
    try {
      await api(`/platform/firms/${f.id}/`, { method: "PATCH", body: { is_active } });
      toast(is_active ? `${f.name} is active again.` : `${f.name} is suspended.`);
      firms.reload();
    } catch (err) {
      toast(errorMessage(err), "err");
    }
  }

  if (!user?.is_platform_operator) {
    return <div className="page"><div className="card"><Empty icon="lock" title="For LexDesk's platform owners" /></div></div>;
  }

  const active = (firms.data ?? []).filter((f) => f.is_active);
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <span className="eyebrow">LexDesk platform</span>
          <h1 style={{ marginTop: 6 }}>Law firms</h1>
          <p>Every firm works in its own sealed space. You manage the firms, not their files: no client, case or document is visible here.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setAdding(true)}><Icon name="plus" /> Add a law firm</button>
      </div>

      <div className="grid-3" style={{ marginBottom: 18, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 180px), 1fr))" }}>
        <div className="card stat"><span className="value">{active.length}</span><span className="label">Active firms</span></div>
        <div className="card stat"><span className="value">{active.reduce((s, f) => s + f.staff_count, 0)}</span><span className="label">Lawyers & staff</span></div>
        <div className="card stat"><span className="value">{active.reduce((s, f) => s + f.matter_count, 0)}</span><span className="label">Matters on file</span></div>
      </div>

      <ErrorNote error={firms.error} />
      <div className="card">
        {firms.loading ? <Spinner /> : !firms.data?.length ? (
          <Empty icon="building" title="No firms yet">Add the first law firm. Its managing partner gets an email to set up their account.</Empty>
        ) : (
          <ul className="list">
            {firms.data.map((f) => (
              <li key={f.id} className="list-item" style={{ flexWrap: "wrap", opacity: f.is_active ? 1 : 0.6 }}>
                <span style={{ width: 46, height: 46, borderRadius: 12, display: "grid", placeItems: "center", background: "var(--primary)", color: "#fff", fontWeight: 700, fontSize: 13, flex: "none" }}>{f.code}</span>
                <span className="grow" style={{ minWidth: 200 }}>
                  <strong style={{ display: "block" }}>{f.name}</strong>
                  <span className="muted small">
                    {f.staff_count} staff · {f.matter_count} matters{f.created_at ? ` · joined ${fmtDate(f.created_at)}` : ""}
                  </span>
                  <span className="small" style={{ display: "block" }}>
                    <a href={f.domain ? `https://${f.domain}` : `/?firm=${f.slug}`} target="_blank" rel="noopener noreferrer">
                      {f.domain || `Website: /?firm=${f.slug}`}
                    </a>
                  </span>
                </span>
                <span className="row" style={{ ["--gap" as string]: "10px" }}>
                  {f.is_active ? <span className="badge badge-green">Active</span> : <span className="badge badge-red">Suspended</span>}
                  <Switch checked={f.is_active} onChange={(v) => setActive(f, v)} label={`${f.name} active`} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {adding && <AddFirm onClose={() => setAdding(false)} onDone={() => { setAdding(false); firms.reload(); }} />}
    </div>
  );
}

function AddFirm({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState({ name: "", code: "", slug: "", phone: "", email: "", partner_first_name: "", partner_last_name: "", partner_email: "", partner_phone: "" });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const suggestCode = (name: string) => name.split(/\s+/).filter((w) => /^[A-Za-z]/.test(w) && !/^(and|&|of|the|co\.?)$/i.test(w)).map((w) => w[0].toUpperCase()).join("").slice(0, 4);
  const suggestSlug = (name: string) => name.toLowerCase().replace(/&/g, "and").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/platform/firms/", { method: "POST", body: { ...form, slug: form.slug || suggestSlug(form.name) } });
      toast(`${form.name} added. ${form.partner_first_name} has been emailed an invitation.`);
      onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Add a law firm" subtitle="The firm gets its own sealed space, website and case numbering." onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" form="firm-form" disabled={busy}>{busy ? "Adding…" : "Add firm and invite partner"}</button></>}>
      <form id="firm-form" className="stack" style={{ ["--gap" as string]: "14px" }} onSubmit={save}>
        {error ? <div className="notice err"><Icon name="alert" /><span>{errorMessage(error)}</span></div> : null}
        <Field label="Firm name" htmlFor="pf-name" error={fieldError(error, "name")}>
          <input id="pf-name" className="input" required value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value, code: form.code && form.code !== suggestCode(form.name) ? form.code : suggestCode(e.target.value) })} />
        </Field>
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="Case number prefix" htmlFor="pf-code" hint={`Case numbers will look like ${form.code || "ABC"}-${new Date().getFullYear()}-0001`} error={fieldError(error, "code")}>
            <input id="pf-code" className="input" required maxLength={6} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase().replace(/[^A-Z]/g, "") })} />
          </Field>
          <Field label="Web address name" htmlFor="pf-slug" hint={`Website: /?firm=${form.slug || suggestSlug(form.name) || "name"}`} error={fieldError(error, "slug")}>
            <input id="pf-slug" className="input" placeholder={suggestSlug(form.name)} value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} />
          </Field>
        </div>
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="Office phone" htmlFor="pf-phone"><input id="pf-phone" className="input" type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
          <Field label="Office email" htmlFor="pf-email"><input id="pf-email" className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
        </div>
        <hr className="divider" />
        <span className="label">Managing partner</span>
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="First name" htmlFor="pf-pfirst" error={fieldError(error, "partner_first_name")}><input id="pf-pfirst" className="input" required value={form.partner_first_name} onChange={(e) => setForm({ ...form, partner_first_name: e.target.value })} /></Field>
          <Field label="Last name" htmlFor="pf-plast" error={fieldError(error, "partner_last_name")}><input id="pf-plast" className="input" required value={form.partner_last_name} onChange={(e) => setForm({ ...form, partner_last_name: e.target.value })} /></Field>
        </div>
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="Email" htmlFor="pf-pemail" hint="They get a link to set their password" error={fieldError(error, "partner_email")}><input id="pf-pemail" className="input" type="email" required value={form.partner_email} onChange={(e) => setForm({ ...form, partner_email: e.target.value })} /></Field>
          <Field label="Mobile" htmlFor="pf-pphone"><input id="pf-pphone" className="input" type="tel" value={form.partner_phone} onChange={(e) => setForm({ ...form, partner_phone: e.target.value })} /></Field>
        </div>
      </form>
    </Modal>
  );
}
