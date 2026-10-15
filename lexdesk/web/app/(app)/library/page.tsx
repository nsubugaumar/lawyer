"use client";

import { useState } from "react";
import { Icon } from "@/components/Icon";
import { Empty, ErrorNote, Field, Modal, Spinner, useLoad, useToast } from "@/components/ui";
import { api, errorMessage, fieldError, list } from "@/lib/api";
import { PRACTICE_AREAS } from "@/lib/types";

type Authority = {
  id: string; kind: string; kind_display: string; title: string; citation: string; court: string; year: number | null;
  practice_area: string; summary: string; key_points: string; tags: string; url: string; added_by_name: string;
};

const KINDS = [["case", "Case law"], ["statute", "Statute / regulation"], ["precedent", "Precedent / pleading"], ["opinion", "Legal opinion"], ["article", "Article / commentary"], ["practice", "Practice direction"]];

export default function LibraryPage() {
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("");
  const [editing, setEditing] = useState<Authority | "new" | null>(null);
  const [open, setOpen] = useState<Authority | null>(null);
  const items = useLoad(() => list<Authority>("/library/", { search, kind }), [search, kind]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Research library</h1>
          <p>The cases, statutes and precedents your firm relies on, with your own notes. One lawyer's research becomes everyone's.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setEditing("new")}><Icon name="plus" /> Add an authority</button>
      </div>

      <div className="row wrap" style={{ marginBottom: 14 }}>
        <div className="card" style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 12px", height: 42, flex: 1, minWidth: 220, maxWidth: 460 }}>
          <Icon name="search" size={17} />
          <input aria-label="Search the library" placeholder="Title, citation, court, a phrase from your notes…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ border: 0, outline: 0, background: "transparent", width: "100%" }} />
        </div>
        <div className="chips">
          {[["", "All"], ...KINDS].map(([k, l]) => <button key={k} className="chip" aria-pressed={kind === k} onClick={() => setKind(k)}>{l}</button>)}
        </div>
      </div>

      <ErrorNote error={items.error} />
      <div className="card">
        {items.loading ? <Spinner /> : !items.data?.length ? (
          <Empty icon="scale" title={search ? "Nothing matches" : "Your library is empty"}>
            Add the authorities you cite most. Next time anyone at the firm drafts submissions, they start here.
          </Empty>
        ) : (
          <ul className="list">
            {items.data.map((a) => (
              <li key={a.id}>
                <button className="list-item" onClick={() => setOpen(a)} style={{ alignItems: "flex-start" }}>
                  <span style={{ width: 40, height: 40, borderRadius: 10, display: "grid", placeItems: "center", background: "var(--accent-soft)", color: "var(--accent-strong)", flex: "none" }}>
                    <Icon name={a.kind === "statute" ? "file" : a.kind === "case" ? "gavel" : "scale"} size={19} />
                  </span>
                  <span className="grow">
                    <strong style={{ display: "block" }} className="serif">{a.title}</strong>
                    <span className="muted small">{[a.citation, a.court, a.year].filter(Boolean).join(" · ")}</span>
                    {a.summary && <span className="small truncate" style={{ display: "block", color: "var(--ink-2)", maxWidth: 680 }}>{a.summary}</span>}
                  </span>
                  <span className="badge desktop-only">{a.kind_display}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {open && (
        <Modal title={open.title} subtitle={[open.citation, open.court, open.year].filter(Boolean).join(" · ")} onClose={() => setOpen(null)} wide
          footer={<><button className="btn" onClick={() => { setEditing(open); setOpen(null); }}><Icon name="edit" /> Edit</button>{open.url && <a className="btn btn-primary" href={open.url} target="_blank" rel="noopener noreferrer"><Icon name="globe" /> Full text</a>}</>}>
          <div className="stack" style={{ ["--gap" as string]: "14px" }}>
            <span className="badge badge-gold" style={{ justifySelf: "start" }}>{open.kind_display}</span>
            {open.summary && <p style={{ whiteSpace: "pre-line", fontSize: 15.5 }}>{open.summary}</p>}
            {open.key_points && (
              <div className="stack" style={{ ["--gap" as string]: "6px" }}>
                <span className="label">Key points</span>
                <ul style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 6 }}>
                  {open.key_points.split("\n").filter(Boolean).map((p, i) => <li key={i}>{p}</li>)}
                </ul>
              </div>
            )}
            {open.tags && <div className="chips">{open.tags.split(",").map((t) => t.trim()).filter(Boolean).map((t) => <span key={t} className="chip">{t}</span>)}</div>}
            <span className="muted tiny">Added by {open.added_by_name || "a colleague"}</span>
          </div>
        </Modal>
      )}
      {editing && <AuthorityModal item={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); items.reload(); }} />}
    </div>
  );
}

function AuthorityModal({ item, onClose, onSaved }: { item?: Authority; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState({
    kind: item?.kind ?? "case", title: item?.title ?? "", citation: item?.citation ?? "", court: item?.court ?? "", year: item?.year ? String(item.year) : "",
    practice_area: item?.practice_area ?? "", summary: item?.summary ?? "", key_points: item?.key_points ?? "", tags: item?.tags ?? "", url: item?.url ?? "",
  });
  const [error, setError] = useState<unknown>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const body = { ...form, year: form.year ? Number(form.year) : null };
    try {
      if (item) await api(`/library/${item.id}/`, { method: "PATCH", body });
      else await api("/library/", { method: "POST", body });
      toast("Saved to the library.");
      onSaved();
    } catch (err) {
      setError(err);
    }
  }

  async function remove() {
    if (!item || !confirm("Remove this from the library?")) return;
    await api(`/library/${item.id}/`, { method: "DELETE" });
    onSaved();
  }

  return (
    <Modal title={item ? "Edit authority" : "Add an authority"} onClose={onClose} wide
      footer={<>{item && <button className="btn btn-danger" onClick={remove}>Remove</button>}<button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" form="auth-form">Save</button></>}>
      <form id="auth-form" className="stack" style={{ ["--gap" as string]: "14px" }} onSubmit={save}>
        {error ? <div className="notice err"><Icon name="alert" /><span>{errorMessage(error)}</span></div> : null}
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="Type" htmlFor="a-kind">
            <select id="a-kind" className="select" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          </Field>
          <Field label="Practice area" htmlFor="a-area" error={fieldError(error, "practice_area")}>
            <select id="a-area" className="select" value={form.practice_area} onChange={(e) => setForm({ ...form, practice_area: e.target.value })}>
              <option value="">Any</option>{PRACTICE_AREAS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Title" htmlFor="a-title" error={fieldError(error, "title")}><input id="a-title" className="input" required placeholder="e.g. Mulindwa v. Uganda Breweries Ltd" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
        <div className="grid-3" style={{ gap: 14 }}>
          <Field label="Citation" htmlFor="a-cit"><input id="a-cit" className="input" placeholder="[2019] UGCA 42" value={form.citation} onChange={(e) => setForm({ ...form, citation: e.target.value })} /></Field>
          <Field label="Court" htmlFor="a-court"><input id="a-court" className="input" value={form.court} onChange={(e) => setForm({ ...form, court: e.target.value })} /></Field>
          <Field label="Year" htmlFor="a-year"><input id="a-year" className="input" inputMode="numeric" value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value.replace(/\D/g, "").slice(0, 4) })} /></Field>
        </div>
        <Field label="What it decides (in your words)" htmlFor="a-sum"><textarea id="a-sum" className="textarea" value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} /></Field>
        <Field label="Key points and quotable passages" htmlFor="a-kp" hint="One per line"><textarea id="a-kp" className="textarea" value={form.key_points} onChange={(e) => setForm({ ...form, key_points: e.target.value })} /></Field>
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="Tags" htmlFor="a-tags" hint="Comma separated, e.g. damages, contract"><input id="a-tags" className="input" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} /></Field>
          <Field label="Link to full text" htmlFor="a-url" error={fieldError(error, "url")}><input id="a-url" className="input" type="url" placeholder="https://ulii.org/…" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} /></Field>
        </div>
      </form>
    </Modal>
  );
}
