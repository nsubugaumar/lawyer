"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Icon, PRACTICE_ICONS } from "@/components/Icon";
import { Empty, ErrorNote, Field, Modal, Spinner, StatusBadge, useLoad, useToast } from "@/components/ui";
import { api, errorMessage, fieldError, list } from "@/lib/api";
import { isFeeEarner, isManager, useAuth } from "@/lib/auth";
import { fmtDay, fmtTime } from "@/lib/format";
import { type Matter, PRACTICE_AREAS } from "@/lib/types";

export default function MattersPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Matters />
    </Suspense>
  );
}

function Matters() {
  const params = useSearchParams();
  const { user } = useAuth();
  const [search, setSearch] = useState(params.get("search") ?? "");
  const [status, setStatus] = useState("open");
  const [creating, setCreating] = useState(false);
  const router = useRouter();

  useEffect(() => setSearch(params.get("search") ?? ""), [params]);

  const { data, error, loading } = useLoad(
    () => list<Matter>("/matters/", { search, status: status === "all" ? undefined : status, ordering: "-updated_at" }),
    [search, status],
  );

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Matters</h1>
          <p>Every case and piece of work, with its people, dates and documents.</p>
        </div>
        {(isFeeEarner(user) || isManager(user)) && (
          <button className="btn btn-primary" onClick={() => setCreating(true)}><Icon name="plus" /> Open a matter</button>
        )}
      </div>

      <div className="row wrap" style={{ marginBottom: 14 }}>
        <div className="search card" style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 12px", height: 42, flex: 1, minWidth: 220, maxWidth: 420 }}>
          <Icon name="search" size={17} />
          <input
            aria-label="Search matters"
            placeholder="Reference, title, client, case number…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ border: 0, outline: 0, background: "transparent", width: "100%" }}
          />
        </div>
        <div className="segmented" role="group" aria-label="Status">
          {[["open", "Open"], ["intake", "Intake"], ["on_hold", "On hold"], ["closed", "Closed"], ["all", "All"]].map(([k, l]) => (
            <button key={k} aria-pressed={status === k} onClick={() => setStatus(k)}>{l}</button>
          ))}
        </div>
      </div>

      <ErrorNote error={error} />

      <div className="card">
        {loading ? (
          <div className="card-body stack">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 58 }} />)}</div>
        ) : !data?.length ? (
          <Empty icon="briefcase" title={search ? "No matters match that search" : "No matters here yet"}>
            {search ? "Try a client's surname, a case number or a reference like LD-2026." : "Open a matter to start a file for a client."}
          </Empty>
        ) : (
          <ul className="list">
            {data.map((m) => (
              <li key={m.id}>
                <Link href={`/matters/${m.id}`} className="list-item">
                  <span style={{ width: 42, height: 42, borderRadius: 12, display: "grid", placeItems: "center", background: "var(--primary-soft)", color: "var(--primary)", flex: "none" }}>
                    <Icon name={PRACTICE_ICONS[m.practice_area] ?? "scale"} size={20} />
                  </span>
                  <span className="grow">
                    <span className="row" style={{ ["--gap" as string]: "8px" }}>
                      <span className="tiny strong" style={{ color: "var(--accent-strong)", letterSpacing: ".04em" }}>{m.reference}</span>
                      {m.is_restricted && <span className="badge badge-red plain"><Icon name="lock" size={11} /> Walled</span>}
                    </span>
                    <strong className="truncate" style={{ display: "block" }}>{m.title}</strong>
                    <span className="muted small truncate" style={{ display: "block" }}>
                      {m.client_name} · {m.practice_area_display}{m.lead_lawyer_detail ? ` · ${m.lead_lawyer_detail.full_name}` : ""}
                    </span>
                  </span>
                  <span className="desktop-only small muted" style={{ textAlign: "right", minWidth: 150 }}>
                    {m.next_event ? (
                      <>
                        <span style={{ display: "block", color: "var(--ink-2)", fontWeight: 600 }}>{m.next_event.kind_display}</span>
                        {fmtDay(m.next_event.starts_at)}, {fmtTime(m.next_event.starts_at)}
                      </>
                    ) : (
                      "No date set"
                    )}
                  </span>
                  <StatusBadge status={m.status} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      {creating && <NewMatterModal onClose={() => setCreating(false)} onSaved={(m) => router.push(`/matters/${m.id}`)} />}
    </div>
  );
}

function NewMatterModal({ onClose, onSaved }: { onClose: () => void; onSaved: (m: Matter) => void }) {
  const toast = useToast();
  const { user } = useAuth();
  const clients = useLoad(() => list<{ id: string; name: string }>("/clients/"), []);
  const [form, setForm] = useState({ title: "", client: "", practice_area: "litigation", court: "", case_number: "", description: "", is_restricted: false });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const m = await api<Matter>("/matters/", { method: "POST", body: form });
      toast(`${m.reference} opened.`);
      onSaved(m);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Open a matter"
      subtitle="You become the lead lawyer. You can add colleagues afterwards."
      onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" form="matter-form" disabled={busy}>{busy ? "Opening…" : "Open matter"}</button></>}
    >
      <form id="matter-form" className="stack" style={{ ["--gap" as string]: "14px" }} onSubmit={save}>
        {error ? <div className="notice err"><Icon name="alert" /><span>{errorMessage(error)}</span></div> : null}
        <Field label="Title" htmlFor="m-title" hint="e.g. Okello v. Kampala Traders Ltd" error={fieldError(error, "title")}>
          <input id="m-title" className="input" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </Field>
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="Client" htmlFor="m-client" error={fieldError(error, "client")}>
            <select id="m-client" className="select" required value={form.client} onChange={(e) => setForm({ ...form, client: e.target.value })}>
              <option value="">Choose…</option>
              {(clients.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Practice area" htmlFor="m-area">
            <select id="m-area" className="select" value={form.practice_area} onChange={(e) => setForm({ ...form, practice_area: e.target.value })}>
              {PRACTICE_AREAS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </Field>
        </div>
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="Court (if any)" htmlFor="m-court">
            <input id="m-court" className="input" value={form.court} onChange={(e) => setForm({ ...form, court: e.target.value })} />
          </Field>
          <Field label="Case number" htmlFor="m-case">
            <input id="m-case" className="input" value={form.case_number} onChange={(e) => setForm({ ...form, case_number: e.target.value })} />
          </Field>
        </div>
        <Field label="Summary" htmlFor="m-desc">
          <textarea id="m-desc" className="textarea" style={{ minHeight: 70 }} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
        {isManager(user) && (
          <label className="check">
            <input type="checkbox" checked={form.is_restricted} onChange={(e) => setForm({ ...form, is_restricted: e.target.checked })} />
            <span><strong>Ethical wall</strong><span className="muted small" style={{ display: "block" }}>Only the matter team can see this file, not even other partners.</span></span>
          </label>
        )}
      </form>
    </Modal>
  );
}
