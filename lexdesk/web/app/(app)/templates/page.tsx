"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Icon } from "@/components/Icon";
import { Empty, Field, Modal, Spinner, copyText, useLoad, useToast } from "@/components/ui";
import { api, errorMessage, fieldError, list } from "@/lib/api";

type Template = { id: string; name: string; category: string; category_display: string; description: string; body: string; letterhead: boolean };
const CATEGORIES = [["correspondence", "Correspondence"], ["pleading", "Pleading"], ["contract", "Contract / agreement"], ["internal", "Internal memo"], ["other", "Other"]];

export default function TemplatesPage() {
  const toast = useToast();
  const templates = useLoad(() => list<Template>("/documents/templates/"), []);
  const [editing, setEditing] = useState<Template | "new" | null>(null);
  const [drafting, setDrafting] = useState<Template | null>(null);

  async function starter() {
    const created = await api<Template[]>("/documents/templates/starter/", { method: "POST" });
    toast(created.length ? `${created.length} starter templates added.` : "You already have the starter templates.");
    templates.reload();
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Templates</h1>
          <p>Your firm's standard letters and pleadings. Pick a matter and LexDesk fills in the names, references and court details, and files a Word draft on the matter.</p>
        </div>
        <div className="row wrap">
          <button className="btn" onClick={starter}><Icon name="sparkle" /> Add starter templates</button>
          <button className="btn btn-primary" onClick={() => setEditing("new")}><Icon name="plus" /> New template</button>
        </div>
      </div>
      <div className="card">
        {templates.loading ? <Spinner /> : !templates.data?.length ? (
          <Empty icon="file" title="No templates yet" action={<button className="btn btn-primary" onClick={starter}>Add the starter set</button>}>
            Start with an engagement letter, a letter of demand, a letter to the registrar and an affidavit, then make them your own.
          </Empty>
        ) : (
          <ul className="list">
            {templates.data.map((t) => (
              <li key={t.id} className="list-item" style={{ flexWrap: "wrap" }}>
                <span style={{ width: 40, height: 40, borderRadius: 10, display: "grid", placeItems: "center", background: "var(--primary-soft)", color: "var(--primary)", flex: "none" }}><Icon name="file" size={19} /></span>
                <span className="grow" style={{ minWidth: 200 }}>
                  <strong style={{ display: "block" }}>{t.name}</strong>
                  <span className="muted small">{t.category_display}{t.description ? ` · ${t.description}` : ""}</span>
                </span>
                <span className="row">
                  <button className="btn btn-sm" onClick={() => setEditing(t)}><Icon name="edit" /> Edit</button>
                  <button className="btn btn-primary btn-sm" onClick={() => setDrafting(t)}><Icon name="sparkle" /> Draft</button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {editing && <TemplateModal template={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); templates.reload(); }} />}
      {drafting && <DraftModal template={drafting} onClose={() => setDrafting(null)} />}
    </div>
  );
}

function TemplateModal({ template, onClose, onSaved }: { template?: Template; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const placeholders = useLoad(() => api<{ key: string; label: string }[]>("/documents/templates/placeholders/"), []);
  const [form, setForm] = useState({ name: template?.name ?? "", category: template?.category ?? "correspondence", description: template?.description ?? "", body: template?.body ?? "", letterhead: template?.letterhead ?? true });
  const [error, setError] = useState<unknown>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (template) await api(`/documents/templates/${template.id}/`, { method: "PATCH", body: form });
      else await api("/documents/templates/", { method: "POST", body: form });
      toast("Template saved.");
      onSaved();
    } catch (err) {
      setError(err);
    }
  }

  async function remove() {
    if (!template || !confirm(`Delete the template "${template.name}"? Drafts already made are kept.`)) return;
    await api(`/documents/templates/${template.id}/`, { method: "DELETE" });
    onSaved();
  }

  return (
    <Modal title={template ? `Edit: ${template.name}` : "New template"} onClose={onClose} wide
      footer={<>{template && <button className="btn btn-danger" onClick={remove}>Delete</button>}<button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" form="tpl-form">Save template</button></>}>
      <form id="tpl-form" className="stack" style={{ ["--gap" as string]: "14px" }} onSubmit={save}>
        {error ? <div className="notice err"><Icon name="alert" /><span>{errorMessage(error)}</span></div> : null}
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="Name" htmlFor="t-name" error={fieldError(error, "name")}><input id="t-name" className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Files as" htmlFor="t-cat">
            <select id="t-cat" className="select" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>{CATEGORIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          </Field>
        </div>
        <Field label="Description" htmlFor="t-desc"><input id="t-desc" className="input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <Field label="Text" htmlFor="t-body" hint="Blank lines separate paragraphs. A line written **like this** comes out bold." error={fieldError(error, "body")}>
          <textarea id="t-body" className="textarea" style={{ minHeight: 280, fontFamily: "ui-monospace, Consolas, monospace", fontSize: 13.5 }} required value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
        </Field>
        <label className="check"><input type="checkbox" checked={form.letterhead} onChange={(e) => setForm({ ...form, letterhead: e.target.checked })} /> Start with the firm's letterhead</label>
        <div className="stack" style={{ ["--gap" as string]: "8px" }}>
          <span className="label">Placeholders (tap to copy)</span>
          <div className="chips">
            {(placeholders.data ?? []).map((p) => (
              <button type="button" key={p.key} className="chip" title={p.label} onClick={() => { copyText(`{{${p.key}}}`); toast(`Copied {{${p.key}}}`); }}>{`{{${p.key}}}`}</button>
            ))}
          </div>
        </div>
      </form>
    </Modal>
  );
}

function DraftModal({ template, onClose }: { template: Template; onClose: () => void }) {
  const toast = useToast();
  const router = useRouter();
  const matters = useLoad(() => list<{ id: string; reference: string; title: string }>("/matters/", { status: "open" }), []);
  const [matter, setMatter] = useState("");
  const [busy, setBusy] = useState(false);

  async function draft() {
    setBusy(true);
    try {
      await api(`/documents/templates/${template.id}/draft/`, { method: "POST", body: { matter } });
      toast("Draft filed on the matter, ready to download and edit in Word.");
      router.push(`/matters/${matter}?tab=documents`);
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={`Draft: ${template.name}`} subtitle="Filled from the matter and filed in its documents." onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={!matter || busy} onClick={draft}>{busy ? "Drafting…" : "Create draft"}</button></>}>
      <Field label="Matter" htmlFor="d-matter">
        <select id="d-matter" className="select" value={matter} onChange={(e) => setMatter(e.target.value)}>
          <option value="">Choose a matter…</option>
          {(matters.data ?? []).map((m) => <option key={m.id} value={m.id}>{m.reference} · {m.title}</option>)}
        </select>
      </Field>
    </Modal>
  );
}
