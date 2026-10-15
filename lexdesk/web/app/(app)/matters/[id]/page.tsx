"use client";

import Link from "next/link";
import { PrivilegedNotice } from "@/components/Privileged";
import { useParams, useSearchParams } from "next/navigation";
import { useState } from "react";
import { type CourtEvent, CourtEventModal } from "@/components/forms";
import { Icon } from "@/components/Icon";
import { UploadModal, fileSize } from "@/components/UploadModal";
import { Avatar, Empty, ErrorNote, Field, Modal, Spinner, StatusBadge, Switch, useLoad, useToast } from "@/components/ui";
import { api, errorMessage, list, openFile } from "@/lib/api";
import { dayNum, fmtDate, fmtDay, fmtTime, monthShort, relative } from "@/lib/format";
import type { Matter } from "@/lib/types";

type Tab = "overview" | "diary" | "documents" | "tasks" | "notes" | "messages" | "team";

type Doc = {
  id: string; title: string; category: string; category_display: string; description: string; shared_with_client: boolean; court_bundle: boolean;
  current_version: number; latest: { original_filename: string; size: number; content_type: string; created_at: string; uploaded_by: { full_name: string } | null } | null;
  signature: { id: string; status: string; signed_at: string | null; signer_name: string } | null;
};
type Task = { id: string; title: string; details: string; assigned_to: string | null; assigned_to_detail: { full_name: string } | null; due_on: string | null; status: string; priority: string };
type Note = { id: string; author: { full_name: string } | null; body: string; shared_with_client: boolean; court_event_label: string; created_at: string };

export default function MatterPage() {
  const { id } = useParams<{ id: string }>();
  const initialTab = useSearchParams().get("tab") as Tab | null;
  const [tab, setTab] = useState<Tab>(initialTab ?? "overview");
  const matter = useLoad(() => api<Matter>(`/matters/${id}/`), [id]);
  const m = matter.data;

  if (matter.loading && !m) return <div className="page"><Spinner /></div>;
  if (!m) return <div className="page"><ErrorNote error={matter.error ?? { message: "This matter could not be found." }} /></div>;

  const tabs: [Tab, string][] = [["overview", "Overview"], ["diary", "Court dates"], ["documents", "Documents"], ["tasks", "Tasks"], ["notes", "File notes"], ["messages", "Messages"], ["team", "Team"]];

  return (
    <div className="page">
      <Link href="/matters" className="small row" style={{ ["--gap" as string]: "4px", textDecoration: "none", marginBottom: 10 }}>
        <Icon name="chevron-left" size={16} /> All matters
      </Link>
      <div className="page-head" style={{ marginBottom: 14 }}>
        <div style={{ minWidth: 0 }}>
          <div className="row wrap" style={{ ["--gap" as string]: "8px" }}>
            <span className="eyebrow">{m.reference}</span>
            <StatusBadge status={m.status} />
            {m.is_restricted && <span className="badge badge-red"><Icon name="lock" size={11} /> Ethical wall</span>}
          </div>
          <h1 style={{ marginTop: 6 }}>{m.title}</h1>
          <p>{m.client_name} · {m.practice_area_display}{m.case_number ? ` · ${m.case_number}` : ""}</p>
        </div>
      </div>

      <div className="tabs" role="tablist" style={{ marginBottom: 20 }}>
        {tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}</button>)}
      </div>

      {tab === "overview" && <Overview m={m} onEdit={matter.reload} goDiary={() => setTab("diary")} />}
      {tab === "diary" && <MatterDiary matterId={m.id} />}
      {tab === "documents" && <Documents matterId={m.id} />}
      {tab === "tasks" && <Tasks m={m} />}
      {tab === "notes" && (m.on_team ? <Notes matterId={m.id} /> : <section className="card"><PrivilegedNotice /></section>)}
      {tab === "messages" && (
        <section className="card card-pad stack" style={{ ["--gap" as string]: "12px" }}>
          {m.on_team ? (
            <>
              <p>The secure conversation with {m.client_name} about this matter. Only the client and the matter team can read it.</p>
              <Link className="btn btn-primary" style={{ justifySelf: "start" }} href={`/messages?matter=${m.id}`}><Icon name="message" /> Open the conversation</Link>
            </>
          ) : (
            <PrivilegedNotice />
          )}
        </section>
      )}
      {tab === "team" && <Team m={m} onChange={matter.reload} />}
    </div>
  );
}

/* ----------------------------------------------------------- overview */

function Overview({ m, onEdit, goDiary }: { m: Matter; onEdit: () => void; goDiary: () => void }) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ status: m.status, court: m.court, case_number: m.case_number, judge: m.judge, opposing_counsel: m.opposing_counsel, description: m.description });

  async function save() {
    try {
      await api(`/matters/${m.id}/`, { method: "PATCH", body: form });
      toast("Matter updated.");
      setEditing(false);
      onEdit();
    } catch (err) {
      toast(errorMessage(err), "err");
    }
  }

  const rows: [string, string][] = [["Court", m.court], ["Case number", m.case_number], ["Judge", m.judge], ["Opposing counsel", m.opposing_counsel], ["Opened", fmtDate(m.opened_on)]];

  return (
    <div className="grid-2" style={{ alignItems: "start" }}>
      <section className="card">
        <div className="card-head">
          <h2>Details</h2>
          {!editing ? <button className="btn btn-sm" onClick={() => setEditing(true)}><Icon name="edit" /> Edit</button> : null}
        </div>
        {editing ? (
          <div className="card-body stack" style={{ ["--gap" as string]: "12px" }}>
            <Field label="Status" htmlFor="o-status">
              <select id="o-status" className="select" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {[["intake", "Intake"], ["open", "Open"], ["on_hold", "On hold"], ["closed", "Closed"]].map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </Field>
            {(["court", "case_number", "judge", "opposing_counsel"] as const).map((f) => (
              <Field key={f} label={f.replace("_", " ").replace(/^./, (c) => c.toUpperCase())} htmlFor={`o-${f}`}>
                <input id={`o-${f}`} className="input" value={form[f]} onChange={(e) => setForm({ ...form, [f]: e.target.value })} />
              </Field>
            ))}
            <Field label="Summary" htmlFor="o-desc">
              <textarea id="o-desc" className="textarea" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
            <div className="row" style={{ justifyContent: "flex-end" }}>
              <button className="btn" onClick={() => setEditing(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={save}>Save</button>
            </div>
          </div>
        ) : (
          <div className="card-body stack" style={{ ["--gap" as string]: "14px" }}>
            {m.description && <p style={{ whiteSpace: "pre-line" }}>{m.description}</p>}
            <dl style={{ display: "grid", gridTemplateColumns: "max-content 1fr", gap: "10px 18px", margin: 0 }}>
              {rows.filter(([, v]) => v).map(([k, v]) => (
                <div key={k} style={{ display: "contents" }}>
                  <dt className="muted small">{k}</dt>
                  <dd style={{ margin: 0 }}>{v}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </section>

      <div className="stack" style={{ ["--gap" as string]: "16px" }}>
        <section className="card card-pad stack">
          <span className="eyebrow">Next date</span>
          {m.next_event ? (
            <button className="list-item" style={{ padding: 0 }} onClick={goDiary}>
              <span className="date-tile"><span className="m">{monthShort(m.next_event.starts_at)}</span><span className="d">{dayNum(m.next_event.starts_at)}</span></span>
              <span className="grow">
                <strong style={{ display: "block" }}>{m.next_event.kind_display}: {m.next_event.title}</strong>
                <span className="muted small">{fmtDay(m.next_event.starts_at)}, {fmtTime(m.next_event.starts_at)}{m.next_event.location ? ` · ${m.next_event.location}` : ""}</span>
              </span>
            </button>
          ) : (
            <p className="muted">No upcoming date. <button className="btn btn-ghost btn-sm" onClick={goDiary}>Add one</button></p>
          )}
        </section>
        <section className="card card-pad stack">
          <span className="eyebrow">Lead lawyer</span>
          {m.lead_lawyer_detail ? (
            <div className="row"><Avatar name={m.lead_lawyer_detail.full_name} /><span><strong style={{ display: "block" }}>{m.lead_lawyer_detail.full_name}</strong><span className="muted small">{m.lead_lawyer_detail.title}</span></span></div>
          ) : <p className="muted">Not assigned</p>}
        </section>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- diary */

function MatterDiary({ matterId }: { matterId: string }) {
  const events = useLoad(() => list<CourtEvent>("/diary/", { matter: matterId }), [matterId]);
  const [editing, setEditing] = useState<CourtEvent | "new" | null>(null);
  const now = Date.now();
  const upcoming = (events.data ?? []).filter((e) => new Date(e.starts_at).getTime() >= now - 86400000);
  const past = (events.data ?? []).filter((e) => new Date(e.starts_at).getTime() < now - 86400000).reverse();

  return (
    <section className="card">
      <div className="card-head">
        <h2>Court dates &amp; deadlines</h2>
        <button className="btn btn-primary btn-sm" onClick={() => setEditing("new")}><Icon name="plus" /> Add date</button>
      </div>
      {events.loading ? <Spinner /> : !events.data?.length ? (
        <Empty icon="gavel" title="No dates yet">Add the next hearing or a filing deadline. The team will be reminded automatically.</Empty>
      ) : (
        <ul className="list">
          {[...upcoming, ...past].map((e) => (
            <li key={e.id}>
              <Link className="list-item" href={`/diary/${e.id}`}>
                <span className={`date-tile ${e.is_deadline ? "deadline" : ""}`}><span className="m">{monthShort(e.starts_at)}</span><span className="d">{dayNum(e.starts_at)}</span></span>
                <span className="grow">
                  <strong style={{ display: "block" }}>{e.kind_display}: {e.title}</strong>
                  <span className="muted small">{e.all_day ? fmtDay(e.starts_at) : `${fmtDay(e.starts_at)}, ${fmtTime(e.starts_at)}`}{e.location ? ` · ${e.location}` : ""}</span>
                </span>
                {e.notify_client && <span className="badge badge-gold desktop-only">Client told</span>}
                <StatusBadge status={e.outcome} />
              </Link>
            </li>
          ))}
        </ul>
      )}
      {editing && (
        <CourtEventModal
          matterId={matterId}
          event={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); events.reload(); }}
        />
      )}
    </section>
  );
}

/* ---------------------------------------------------------- documents */

function Documents({ matterId }: { matterId: string }) {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const docs = useLoad(() => list<Doc>("/documents/", { matter: matterId, q: query }), [matterId, query]);
  const [uploading, setUploading] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [asking, setAsking] = useState<Doc | null>(null);

  async function toggle(d: Doc, field: "shared_with_client" | "court_bundle", value: boolean) {
    try {
      await api(`/documents/${d.id}/`, { method: "PATCH", body: { [field]: value } });
      docs.setData(docs.data?.map((x) => (x.id === d.id ? { ...x, [field]: value } : x)));
    } catch (err) {
      toast(errorMessage(err), "err");
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <h2>Documents</h2>
        <span className="row wrap">
          <button className="btn btn-sm" onClick={() => setDrafting(true)}><Icon name="sparkle" /> Draft from template</button>
          <button className="btn btn-primary btn-sm" onClick={() => setUploading(true)}><Icon name="upload" /> Upload</button>
        </span>
      </div>
      <form className="card-body" style={{ borderBottom: "1px solid var(--line)", paddingTop: 12, paddingBottom: 12 }} onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); }}>
        <div className="row">
          <div className="input-group grow">
            <span className="addon"><Icon name="search" size={16} /></span>
            <input className="input" placeholder="Search inside the documents, e.g. ‘interest rate’ or a witness's name" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search inside documents" />
          </div>
          {query && <button type="button" className="btn btn-sm btn-ghost" onClick={() => { setQ(""); setQuery(""); }}>Clear</button>}
        </div>
      </form>
      {docs.loading ? <Spinner /> : !docs.data?.length ? (
        query ? <Empty icon="search" title="No document contains all of those words" /> :
        <Empty icon="file" title="No documents yet">Upload pleadings, evidence and correspondence. Every file is encrypted and every view is logged.</Empty>
      ) : (
        <ul className="list">
          {docs.data.map((d) => (
            <li key={d.id} className="list-item" style={{ flexWrap: "wrap" }}>
              <span style={{ width: 40, height: 40, borderRadius: 10, display: "grid", placeItems: "center", background: "var(--surface-2)", color: "var(--primary)", flex: "none" }}><Icon name="file" size={20} /></span>
              <span className="grow" style={{ minWidth: 180 }}>
                <strong className="truncate" style={{ display: "block" }}>{d.title}</strong>
                <span className="muted small">{d.category_display}{d.latest ? ` · ${fileSize(d.latest.size)} · v${d.current_version} · ${relative(d.latest.created_at)}` : ""}</span>
                {d.signature && (
                  <span className={`badge ${d.signature.status === "signed" ? "badge-green" : d.signature.status === "pending" ? "badge-amber" : "badge-red"}`} style={{ marginTop: 4 }}>
                    {d.signature.status === "signed" ? `Signed by ${d.signature.signer_name}` : d.signature.status === "pending" ? "Waiting for client's signature" : "Signature declined"}
                  </span>
                )}
              </span>
              <span className="row wrap small" style={{ ["--gap" as string]: "14px" }}>
                <label className="row" style={{ ["--gap" as string]: "6px" }} title="The client can see and download it">
                  <Switch checked={d.shared_with_client} onChange={(v) => toggle(d, "shared_with_client", v)} label="Share with client" /> Client
                </label>
                <label className="row" style={{ ["--gap" as string]: "6px" }} title="Available offline in court">
                  <Switch checked={d.court_bundle} onChange={(v) => toggle(d, "court_bundle", v)} label="Court bundle" /> Court bundle
                </label>
                <button className="btn btn-sm" onClick={() => openFile(`/documents/${d.id}/download/`, d.latest?.original_filename ?? d.title, true).catch((e) => toast(errorMessage(e), "err"))}>
                  <Icon name="eye" /> View
                </button>
                <button className="icon-btn" aria-label="Download" onClick={() => openFile(`/documents/${d.id}/download/`, d.latest?.original_filename ?? d.title, false).catch((e) => toast(errorMessage(e), "err"))}>
                  <Icon name="download" />
                </button>
                {(!d.signature || d.signature.status === "declined") && (
                  <button className="btn btn-sm" onClick={() => setAsking(d)} title="Ask the client to sign this electronically"><Icon name="edit" /> Ask to sign</button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      {uploading && <UploadModal matterId={matterId} onClose={() => setUploading(false)} onDone={() => { setUploading(false); docs.reload(); }} />}
      {drafting && <DraftHere matterId={matterId} onClose={() => setDrafting(false)} onDone={() => { setDrafting(false); docs.reload(); }} />}
      {asking && <AskToSign doc={asking} onClose={() => setAsking(null)} onDone={() => { setAsking(null); docs.reload(); }} />}
    </section>
  );
}

/* -------------------------------------------------------------- tasks */

function Tasks({ m }: { m: Matter }) {
  const toast = useToast();
  const tasks = useLoad(() => list<Task>("/tasks/", { matter: m.id }), [m.id]);
  const [title, setTitle] = useState("");
  const [assignee, setAssignee] = useState("");
  const [due, setDue] = useState("");

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      await api("/tasks/", { method: "POST", body: { matter: m.id, title, assigned_to: assignee || null, due_on: due || null } });
      setTitle("");
      setDue("");
      tasks.reload();
    } catch (err) {
      toast(errorMessage(err), "err");
    }
  }

  async function toggle(t: Task) {
    const status = t.status === "done" ? "todo" : "done";
    tasks.setData(tasks.data?.map((x) => (x.id === t.id ? { ...x, status } : x)));
    await api(`/tasks/${t.id}/`, { method: "PATCH", body: { status } }).catch((err) => toast(errorMessage(err), "err"));
  }

  const today = new Date().toISOString().slice(0, 10);
  return (
    <section className="card">
      <div className="card-head"><h2>Tasks</h2></div>
      <form className="card-body row wrap" onSubmit={add} style={{ borderBottom: "1px solid var(--line)" }}>
        <input className="input grow" style={{ minWidth: 200 }} placeholder="Add a task, e.g. File written submissions" value={title} onChange={(e) => setTitle(e.target.value)} aria-label="New task" />
        <select className="select" style={{ width: "auto" }} value={assignee} onChange={(e) => setAssignee(e.target.value)} aria-label="Assign to">
          <option value="">Unassigned</option>
          {m.team.map((t) => <option key={t.user.id} value={t.user.id}>{t.user.full_name}</option>)}
        </select>
        <input className="input" type="date" style={{ width: "auto" }} value={due} onChange={(e) => setDue(e.target.value)} aria-label="Due date" />
        <button className="btn btn-primary"><Icon name="plus" /> Add</button>
      </form>
      {tasks.loading ? <Spinner /> : !tasks.data?.length ? (
        <Empty icon="check-circle" title="No tasks">Break the work down and share it with the team.</Empty>
      ) : (
        <ul className="list">
          {tasks.data.map((t) => (
            <li key={t.id} className="list-item">
              <input type="checkbox" checked={t.status === "done"} onChange={() => toggle(t)} aria-label={`Mark ${t.title} done`} style={{ width: 20, height: 20, accentColor: "var(--primary)" }} />
              <span className="grow">
                <span style={{ display: "block", fontWeight: 500, textDecoration: t.status === "done" ? "line-through" : undefined, color: t.status === "done" ? "var(--muted)" : undefined }}>{t.title}</span>
                <span className="muted small">
                  {t.assigned_to_detail?.full_name ?? "Unassigned"}
                  {t.due_on && (
                    <span style={{ color: t.status !== "done" && t.due_on < today ? "var(--danger)" : undefined, fontWeight: t.due_on < today ? 600 : undefined }}> · due {fmtDate(t.due_on)}</span>
                  )}
                </span>
              </span>
              {t.priority === "urgent" || t.priority === "high" ? <span className="badge badge-red">{t.priority}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* -------------------------------------------------------------- notes */

function Notes({ matterId }: { matterId: string }) {
  const toast = useToast();
  const notes = useLoad(() => list<Note>("/notes/", { matter: matterId }), [matterId]);
  const [body, setBody] = useState("");
  const [shared, setShared] = useState(false);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    try {
      await api("/notes/", { method: "POST", body: { matter: matterId, body, shared_with_client: shared } });
      setBody("");
      setShared(false);
      notes.reload();
    } catch (err) {
      toast(errorMessage(err), "err");
    }
  }

  return (
    <section className="card">
      <div className="card-head"><h2>File notes</h2><span className="muted small row" style={{ ["--gap" as string]: "6px" }}><Icon name="lock" size={14} /> Encrypted</span></div>
      <form className="card-body stack" onSubmit={add} style={{ borderBottom: "1px solid var(--line)" }}>
        <textarea className="textarea" placeholder="Attendance note, call note, strategy…" value={body} onChange={(e) => setBody(e.target.value)} aria-label="New file note" />
        <div className="row-between wrap">
          <label className="check small"><input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} /> Share with the client</label>
          <button className="btn btn-primary" disabled={!body.trim()}>Save note</button>
        </div>
      </form>
      {notes.loading ? <Spinner /> : !notes.data?.length ? (
        <Empty icon="message" title="No notes yet">Record calls and meetings as they happen; they stay on the file.</Empty>
      ) : (
        <ul className="list">
          {notes.data.map((n) => (
            <li key={n.id} className="list-item" style={{ alignItems: "flex-start" }}>
              <Avatar name={n.author?.full_name ?? "?"} />
              <span className="grow">
                <span className="row wrap" style={{ ["--gap" as string]: "8px" }}>
                  <strong>{n.author?.full_name ?? "Former colleague"}</strong>
                  <span className="muted tiny">{relative(n.created_at)}</span>
                  {n.court_event_label && <span className="badge badge-blue plain">{n.court_event_label}</span>}
                  {n.shared_with_client && <span className="badge badge-gold">Shared</span>}
                </span>
                <p style={{ whiteSpace: "pre-line", marginTop: 4 }}>{n.body}</p>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* --------------------------------------------------------------- team */

function Team({ m, onChange }: { m: Matter; onChange: () => void }) {
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [people, setPeople] = useState<{ id: string; name: string; title: string }[]>([]);
  const [chosen, setChosen] = useState("");
  const [role, setRole] = useState("associate");

  async function openAdd() {
    setAdding(true);
    setPeople(await api("/appointments/public/lawyers/"));
  }

  async function add() {
    try {
      await api(`/matters/${m.id}/team/`, { method: "POST", body: { user_id: chosen, role } });
      toast("Added to the team.");
      setAdding(false);
      onChange();
    } catch (err) {
      toast(errorMessage(err), "err");
    }
  }

  async function remove(userId: string) {
    try {
      await api(`/matters/${m.id}/team/${userId}/`, { method: "DELETE" });
      onChange();
    } catch (err) {
      toast(errorMessage(err), "err");
    }
  }

  return (
    <section className="card">
      <div className="card-head"><h2>Matter team</h2><button className="btn btn-sm" onClick={openAdd}><Icon name="plus" /> Add someone</button></div>
      <ul className="list">
        {m.team.map((t) => (
          <li key={t.user.id} className="list-item">
            <Avatar name={t.user.full_name} />
            <span className="grow"><strong style={{ display: "block" }}>{t.user.full_name}</strong><span className="muted small">{t.user.title || t.role}</span></span>
            <span className="badge">{t.role === "lead" ? "Lead counsel" : t.role}</span>
            {t.role !== "lead" && <button className="icon-btn" aria-label={`Remove ${t.user.full_name}`} onClick={() => remove(t.user.id)}><Icon name="x" /></button>}
          </li>
        ))}
      </ul>
      {adding && (
        <Modal title="Add to the team" onClose={() => setAdding(false)} footer={<><button className="btn" onClick={() => setAdding(false)}>Cancel</button><button className="btn btn-primary" disabled={!chosen} onClick={add}>Add</button></>}>
          <div className="stack">
            <Field label="Person" htmlFor="t-user">
              <select id="t-user" className="select" value={chosen} onChange={(e) => setChosen(e.target.value)}>
                <option value="">Choose…</option>
                {people.filter((p) => !m.team.some((t) => t.user.id === p.id)).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
            <Field label="Role" htmlFor="t-role">
              <select id="t-role" className="select" value={role} onChange={(e) => setRole(e.target.value)}>
                <option value="associate">Associate</option><option value="paralegal">Paralegal</option><option value="support">Support</option>
              </select>
            </Field>
          </div>
        </Modal>
      )}
    </section>
  );
}

function DraftHere({ matterId, onClose, onDone }: { matterId: string; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const templates = useLoad(() => list<{ id: string; name: string; description: string }>("/documents/templates/"), []);
  const [busy, setBusy] = useState<string | null>(null);

  async function draft(id: string) {
    setBusy(id);
    try {
      await api(`/documents/templates/${id}/draft/`, { method: "POST", body: { matter: matterId } });
      toast("Draft filed. Download it to edit in Word.");
      onDone();
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Modal title="Draft from a template" subtitle="Names, references and court details are filled in for you." onClose={onClose}>
      {templates.loading ? <Spinner /> : !templates.data?.length ? (
        <Empty icon="file" title="No templates yet" action={<Link className="btn btn-primary" href="/templates">Set up templates</Link>} />
      ) : (
        <ul className="list" style={{ margin: "0 -22px" }}>
          {templates.data.map((t) => (
            <li key={t.id}>
              <button className="list-item" disabled={busy !== null} onClick={() => draft(t.id)}>
                <Icon name="file" size={19} />
                <span className="grow"><strong style={{ display: "block" }}>{t.name}</strong><span className="muted small">{t.description}</span></span>
                {busy === t.id ? <span className="spinner" /> : <Icon name="chevron-right" size={18} />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

function AskToSign({ doc, onClose, onDone }: { doc: Doc; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    setBusy(true);
    try {
      await api(`/documents/${doc.id}/request-signature/`, { method: "POST", body: { message } });
      toast("Sent. The client can read and sign it in their portal.");
      onDone();
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Ask the client to sign" subtitle={doc.title} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={busy} onClick={send}><Icon name="send" /> {busy ? "Sending…" : "Send for signature"}</button></>}>
      <div className="stack" style={{ ["--gap" as string]: "12px" }}>
        <div className="notice"><Icon name="shield" /><span>The client signs version {doc.current_version} exactly. If you upload a new version, they will need to sign again. A signature certificate is filed on the matter when they sign.</span></div>
        <Field label="Message to the client (optional)" htmlFor="sig-msg">
          <textarea id="sig-msg" className="textarea" style={{ minHeight: 80 }} placeholder="e.g. Please read our terms of engagement and sign below." value={message} onChange={(e) => setMessage(e.target.value)} />
        </Field>
      </div>
    </Modal>
  );
}
