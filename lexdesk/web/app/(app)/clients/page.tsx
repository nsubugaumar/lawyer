"use client";

import Link from "next/link";
import { useState } from "react";
import { AppointmentModal } from "@/components/forms";
import { Icon } from "@/components/Icon";
import { Avatar, Empty, ErrorNote, Field, Modal, StatusBadge, useLoad, useToast } from "@/components/ui";
import { api, errorMessage, fieldError, list } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Client = {
  id: string; kind: string; name: string; contact_person: string; email: string; phone: string; address: string;
  national_id: string; notes: string; status: string; source: string; responsible_lawyer: string | null; responsible_lawyer_name: string | null; has_portal_access: boolean;
  engagement: string; retainer_fee: string | null; retainer_start: string | null; retainer_end: string | null;
};

export default function ClientsPage() {
  const { user } = useAuth();
  const [search, setSearch] = useState("");
  const [engagement, setEngagement] = useState("");
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState<Client | null>(null);
  const [booking, setBooking] = useState<Client | null>(null);
  const clients = useLoad(() => list<Client>("/clients/", { search, engagement }), [search, engagement]);
  const canEdit = user?.role !== "accountant";

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Clients</h1>
          <p>The people and organisations the firm acts for.</p>
        </div>
        {canEdit && <button className="btn btn-primary" onClick={() => setCreating(true)}><Icon name="plus" /> New client</button>}
      </div>

      <div className="row wrap" style={{ marginBottom: 14 }}>
      <div className="card" style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 12px", height: 42, flex: 1, minWidth: 220, maxWidth: 420 }}>
        <Icon name="search" size={17} />
        <input aria-label="Search clients" placeholder="Name, email or phone…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ border: 0, outline: 0, background: "transparent", width: "100%" }} />
      </div>
      <div className="chips">
        {[["", "All"], ["retainer", "On retainer"], ["one_off", "One-off"]].map(([k, l]) => <button key={k} className="chip" aria-pressed={engagement === k} onClick={() => setEngagement(k)}>{l}</button>)}
      </div>
      </div>

      <ErrorNote error={clients.error} />

      <div className="card">
        {clients.loading ? (
          <div className="card-body stack">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 54 }} />)}</div>
        ) : !clients.data?.length ? (
          <Empty icon="users" title={search ? "Nobody by that name" : "No clients yet"}>Add a client, or they appear here when they book online.</Empty>
        ) : (
          <ul className="list">
            {clients.data.map((c) => (
              <li key={c.id}>
                <button className="list-item" onClick={() => setOpen(c)}>
                  <Avatar name={c.name} />
                  <span className="grow">
                    <strong className="truncate" style={{ display: "block" }}>{c.name}</strong>
                    <span className="muted small truncate" style={{ display: "block" }}>{[c.phone, c.email].filter(Boolean).join(" · ") || "No contact details"}</span>
                  </span>
                  {c.engagement === "retainer" ? <span className="badge badge-gold desktop-only">Retainer</span> : <span className="badge desktop-only">One-off</span>}
                  {c.has_portal_access && <span className="badge badge-blue desktop-only">Portal</span>}
                  <StatusBadge status={c.status} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {creating && <ClientModal onClose={() => setCreating(false)} onSaved={() => { setCreating(false); clients.reload(); }} />}
      {open && (
        <ClientDetail client={open} canEdit={canEdit} onClose={() => setOpen(null)} onBook={() => { setBooking(open); setOpen(null); }} onChanged={() => clients.reload()} />
      )}
      {booking && <AppointmentModal defaultClient={booking.id} onClose={() => setBooking(null)} onSaved={() => setBooking(null)} />}
    </div>
  );
}

function ClientDetail({ client, canEdit, onClose, onBook, onChanged }: { client: Client; canEdit: boolean; onClose: () => void; onBook: () => void; onChanged: () => void }) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  // Opening the full record is logged; the list holds only what the list needs.
  const full = useLoad(() => api<Client>(`/clients/${client.id}/`), [client.id]);
  const matters = useLoad(() => list<{ id: string; reference: string; title: string; status: string }>("/matters/", { client: client.id }), [client.id]);
  const c = full.data ?? client;

  async function grant() {
    try {
      const r = await api<{ detail: string }>(`/clients/${c.id}/grant_portal_access/`, { method: "POST" });
      toast(r.detail);
      full.reload();
      onChanged();
    } catch (err) {
      toast(errorMessage(err), "err");
    }
  }

  if (editing) return <ClientModal client={c} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); full.reload(); onChanged(); }} />;

  return (
    <Modal title={c.name} subtitle={c.kind === "organisation" && c.contact_person ? `Contact: ${c.contact_person}` : undefined} onClose={onClose} wide
      footer={canEdit ? <><button className="btn" onClick={() => setEditing(true)}><Icon name="edit" /> Edit</button><button className="btn btn-primary" onClick={onBook}><Icon name="clock" /> Book appointment</button></> : undefined}>
      <div className="grid-2" style={{ gap: 20 }}>
        <div className="stack" style={{ ["--gap" as string]: "10px" }}>
          {c.phone && <a href={`tel:${c.phone}`} className="row"><Icon name="phone" size={17} /> {c.phone}</a>}
          {c.phone && <a href={`https://wa.me/${c.phone.replace(/\D/g, "").replace(/^0/, "256")}`} target="_blank" rel="noopener noreferrer" className="row"><Icon name="whatsapp" size={17} /> WhatsApp</a>}
          {c.email && <a href={`mailto:${c.email}`} className="row"><Icon name="mail" size={17} /> {c.email}</a>}
          {c.address && <span className="row" style={{ alignItems: "flex-start" }}><Icon name="pin" size={17} /> <span style={{ whiteSpace: "pre-line" }}>{c.address}</span></span>}
          {c.national_id && <span className="row"><Icon name="passport" size={17} /> {c.national_id}</span>}
          {c.responsible_lawyer_name && <span className="row"><Icon name="user" size={17} /> {c.responsible_lawyer_name}</span>}
          {c.engagement === "retainer" ? (
            <span className="row"><Icon name="handshake" size={17} /> On retainer{c.retainer_fee ? `, ${Number(c.retainer_fee).toLocaleString("en-GB")} a month` : ""}{c.retainer_end ? ` until ${c.retainer_end}` : ""}</span>
          ) : (
            <span className="row"><Icon name="handshake" size={17} /> One-off service</span>
          )}
          <div className="row wrap"><StatusBadge status={c.status} />{c.has_portal_access ? <span className="badge badge-blue">Has portal access</span> : canEdit && <button className="btn btn-sm" onClick={grant}>Give portal access</button>}</div>
          {c.notes && <div className="card card-pad" style={{ background: "var(--surface-2)", whiteSpace: "pre-line" }}><span className="label" style={{ display: "block", marginBottom: 4 }}>Private notes</span>{c.notes}</div>}
        </div>
        <div className="stack" style={{ ["--gap" as string]: "8px" }}>
          <span className="label">Matters</span>
          {matters.data?.length ? matters.data.map((m) => (
            <Link key={m.id} href={`/matters/${m.id}`} className="card" style={{ padding: "10px 14px", textDecoration: "none", color: "inherit", display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span className="truncate"><span className="tiny strong" style={{ color: "var(--accent-strong)" }}>{m.reference}</span><br />{m.title}</span>
              <StatusBadge status={m.status} />
            </Link>
          )) : <span className="muted small">No matters yet.</span>}
        </div>
      </div>
    </Modal>
  );
}

function ClientModal({ client, onClose, onSaved }: { client?: Client; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState({
    kind: client?.kind ?? "individual", name: client?.name ?? "", contact_person: client?.contact_person ?? "", email: client?.email ?? "",
    phone: client?.phone ?? "", address: client?.address ?? "", national_id: client?.national_id ?? "", notes: client?.notes ?? "",
    engagement: client?.engagement ?? "one_off", retainer_fee: client?.retainer_fee ?? "", retainer_start: client?.retainer_start ?? "", retainer_end: client?.retainer_end ?? "",
    create_portal_account: true,
  });
  const [conflict, setConflict] = useState<{ clear: boolean; hits: unknown[] } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function check() {
    if (form.name.length > 2 && !client) setConflict(await api("/clients/conflict-check/", { query: { q: form.name } }).catch(() => null));
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        ...form,
        retainer_fee: form.engagement === "retainer" && form.retainer_fee ? form.retainer_fee : null,
        retainer_start: form.engagement === "retainer" && form.retainer_start ? form.retainer_start : null,
        retainer_end: form.engagement === "retainer" && form.retainer_end ? form.retainer_end : null,
      };
      if (client) await api(`/clients/${client.id}/`, { method: "PATCH", body });
      else await api("/clients/", { method: "POST", body });
      toast(client ? "Saved." : form.create_portal_account && form.email ? "Client added. They have been emailed a link to their portal." : "Client added.");
      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={client ? `Edit ${client.name}` : "New client"} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" form="client-form" disabled={busy}>{busy ? "Saving…" : "Save"}</button></>}>
      <form id="client-form" className="stack" style={{ ["--gap" as string]: "14px" }} onSubmit={save}>
        {error ? <div className="notice err"><Icon name="alert" /><span>{errorMessage(error)}</span></div> : null}
        <div className="segmented" role="group" aria-label="Client type">
          <button type="button" aria-pressed={form.kind === "individual"} onClick={() => setForm({ ...form, kind: "individual" })}>Person</button>
          <button type="button" aria-pressed={form.kind === "organisation"} onClick={() => setForm({ ...form, kind: "organisation" })}>Organisation</button>
        </div>
        <Field label={form.kind === "organisation" ? "Registered name" : "Full name"} htmlFor="c-name" error={fieldError(error, "name")}>
          <input id="c-name" className="input" required value={form.name} onBlur={check} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        {conflict && (
          <div className={`notice ${conflict.clear ? "ok" : "warn"}`}>
            <Icon name={conflict.clear ? "check-circle" : "alert"} />
            <span>{conflict.clear ? "Conflict check clear: no matching parties on any file." : `Possible conflict: ${conflict.hits.length} match(es) among parties on existing files. Check with a partner before acting.`}</span>
          </div>
        )}
        {form.kind === "organisation" && (
          <Field label="Contact person" htmlFor="c-contact"><input id="c-contact" className="input" value={form.contact_person} onChange={(e) => setForm({ ...form, contact_person: e.target.value })} /></Field>
        )}
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="Phone" htmlFor="c-phone"><input id="c-phone" className="input" type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
          <Field label="Email" htmlFor="c-email" error={fieldError(error, "email")}><input id="c-email" className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
        </div>
        <div className="field">
          <span className="label">How the firm acts for them</span>
          <div className="segmented" role="group" aria-label="Engagement">
            <button type="button" aria-pressed={form.engagement === "retainer"} onClick={() => setForm({ ...form, engagement: "retainer" })}>On retainer</button>
            <button type="button" aria-pressed={form.engagement === "one_off"} onClick={() => setForm({ ...form, engagement: "one_off" })}>One-off service</button>
          </div>
          <span className="hint">{form.engagement === "retainer" ? "An ongoing relationship with a regular fee." : "They came for a particular piece of work."}</span>
        </div>
        {form.engagement === "retainer" && (
          <div className="grid-3" style={{ gap: 14 }}>
            <Field label="Monthly fee" htmlFor="c-fee" error={fieldError(error, "retainer_fee")}><input id="c-fee" className="input" inputMode="decimal" value={form.retainer_fee} onChange={(e) => setForm({ ...form, retainer_fee: e.target.value.replace(/[^0-9.]/g, "") })} /></Field>
            <Field label="From" htmlFor="c-rs"><input id="c-rs" className="input" type="date" value={form.retainer_start} onChange={(e) => setForm({ ...form, retainer_start: e.target.value })} /></Field>
            <Field label="Until (optional)" htmlFor="c-re"><input id="c-re" className="input" type="date" value={form.retainer_end} onChange={(e) => setForm({ ...form, retainer_end: e.target.value })} /></Field>
          </div>
        )}
        <Field label="Address" htmlFor="c-addr"><textarea id="c-addr" className="textarea" style={{ minHeight: 60 }} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></Field>
        <Field label="ID / passport / registration number" htmlFor="c-id" hint="Encrypted at rest"><input id="c-id" className="input" value={form.national_id} onChange={(e) => setForm({ ...form, national_id: e.target.value })} /></Field>
        <Field label="Private notes" htmlFor="c-notes" hint="Encrypted. Never shown to the client."><textarea id="c-notes" className="textarea" style={{ minHeight: 60 }} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
        {!client && (
          <label className="check">
            <input type="checkbox" checked={form.create_portal_account} onChange={(e) => setForm({ ...form, create_portal_account: e.target.checked })} />
            <span><strong>Give them a client portal</strong><span className="muted small" style={{ display: "block" }}>They get an email to set a password, then see their case, documents and appointments.</span></span>
          </label>
        )}
      </form>
    </Modal>
  );
}
