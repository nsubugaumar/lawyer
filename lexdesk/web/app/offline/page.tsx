"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { Avatar, Empty, Spinner } from "@/components/ui";
import { fmtDate, fmtLong, fmtTime } from "@/lib/format";
import { getBrief, openSavedFile, removeBrief, type SavedBrief } from "@/lib/offline";

/**
 * Saved for court: works with no connection. It never calls the server; it
 * reads only what the lawyer saved on this phone.
 */
export default function OfflinePage() {
  const [briefs, setBriefs] = useState<SavedBrief[] | null>(null);
  const [open, setOpen] = useState<SavedBrief | null>(null);
  const [online, setOnline] = useState(true);

  async function load() {
    try {
      const user = localStorage.getItem("lexdesk.offline.user") ?? "";
      const { listBriefs } = await import("@/lib/offline");
      setBriefs(user ? await listBriefs(user) : []);
    } catch {
      setBriefs([]);
    }
  }

  useEffect(() => {
    load();
    const id = new URLSearchParams(location.search).get("brief");
    if (id) getBrief(id).then((b) => b && setOpen(b));
    setOnline(navigator.onLine);
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    addEventListener("online", on);
    addEventListener("offline", off);
    return () => {
      removeEventListener("online", on);
      removeEventListener("offline", off);
    };
  }, []);

  return (
    <div className="app-root">
      <div className="page" style={{ maxWidth: 860 }}>
        <div className="page-head">
          <div>
            <span className="eyebrow">{online ? "Online" : "No connection"}</span>
            <h1 style={{ marginTop: 6 }}>Saved for court</h1>
            <p>Court briefs and bundles kept on this phone. They open without signal, and are removed two days after each hearing.</p>
          </div>
          {online && <Link href="/diary" className="btn"><Icon name="calendar" /> Back to the diary</Link>}
        </div>

        {open ? (
          <SavedBriefView saved={open} onBack={() => setOpen(null)} />
        ) : briefs === null ? (
          <Spinner />
        ) : briefs.length === 0 ? (
          <div className="card">
            <Empty icon="download" title="Nothing saved on this phone">
              Open a hearing's court brief while you have signal and tap "Save for court", or save the whole week from the diary.
            </Empty>
          </div>
        ) : (
          <div className="card">
            <ul className="list">
              {briefs.map((b) => (
                <li key={b.id} className="list-item">
                  <button className="list-item grow" style={{ padding: 0 }} onClick={() => setOpen(b)}>
                    <span className="date-tile"><span className="m">{fmtDate(b.startsAt, { month: "short" })}</span><span className="d">{fmtDate(b.startsAt, { day: "numeric" })}</span></span>
                    <span className="grow">
                      <strong style={{ display: "block" }}>{b.title}</strong>
                      <span className="muted small">{b.reference} · {fmtTime(b.startsAt)} · {b.documentIds.length} documents</span>
                    </span>
                  </button>
                  <button className="icon-btn" aria-label="Remove from this phone" onClick={async () => { await removeBrief(b.id); load(); }}><Icon name="trash" /></button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function SavedBriefView({ saved, onBack }: { saved: SavedBrief; onBack: () => void }) {
  const b = saved.brief;
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="stack" style={{ ["--gap" as string]: "16px" }}>
      <button className="btn btn-ghost btn-sm" style={{ justifySelf: "start" }} onClick={onBack}><Icon name="chevron-left" /> All saved briefs</button>
      <section className="card card-pad stack" style={{ background: "linear-gradient(150deg, var(--primary), var(--primary-strong))", color: "#fff", border: 0 }}>
        <span className="eyebrow" style={{ color: "#d9be8a" }}>Court brief · {b.matter.reference} · saved {fmtDate(saved.savedAt, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
        <h1 style={{ color: "#fff" }}>{saved.title}</h1>
        <p style={{ color: "#cfd9ec", fontSize: 17 }}>{fmtLong(b.event.starts_at)} at {fmtTime(b.event.starts_at)}</p>
        {b.event.location && <p style={{ fontWeight: 600, fontSize: 17 }}><Icon name="pin" size={18} /> {b.event.location}</p>}
      </section>
      <section className="card card-body grid-2" style={{ gap: 12 }}>
        {[["Matter", b.matter.title], ["Client", b.matter.client_name], ["Court", b.matter.court], ["Case number", b.matter.case_number], ["Before", b.matter.judge], ["Opposing counsel", b.matter.opposing_counsel]]
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k}><span className="muted tiny" style={{ display: "block", textTransform: "uppercase", letterSpacing: ".06em", fontWeight: 600 }}>{k}</span><span style={{ fontSize: 15.5 }}>{v}</span></div>
          ))}
      </section>
      {error && <div className="notice err"><Icon name="alert" /><span>{error}</span></div>}
      <section className="card">
        <div className="card-head"><h2>Court bundle</h2></div>
        <ul className="list">
          {b.documents.map((d: { id: string; title: string; category_display: string }) => (
            <li key={d.id}>
              <button className="list-item" onClick={() => openSavedFile(d.id).catch((e) => setError(e.message))}>
                <Icon name="file" size={19} />
                <span className="grow"><strong style={{ display: "block" }}>{d.title}</strong><span className="muted small">{d.category_display}</span></span>
                <Icon name="eye" size={18} />
              </button>
            </li>
          ))}
          {b.documents.length === 0 && <li className="list-item muted small">No documents in the bundle.</li>}
        </ul>
      </section>
      {b.privileged && (
        <section className="card">
          <div className="card-head"><h2>Notes</h2><span className="muted small"><Icon name="lock" size={14} /> Privileged</span></div>
          <ul className="list">
            {[...b.hearing_notes, ...b.file_notes].map((n: { id: string; body: string; author: { full_name: string } | null; created_at: string }) => (
              <li key={n.id} className="list-item" style={{ alignItems: "flex-start" }}>
                <Avatar name={n.author?.full_name ?? "?"} />
                <span className="grow"><strong>{n.author?.full_name}</strong><p style={{ whiteSpace: "pre-line", fontSize: 15.5 }}>{n.body}</p></span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {b.history?.length > 0 && (
        <section className="card">
          <div className="card-head"><h2>Previous dates</h2></div>
          <ul className="list">
            {b.history.map((h: { id: string; kind: string; starts_at: string; outcome_display: string; outcome_notes: string }) => (
              <li key={h.id} className="list-item" style={{ alignItems: "flex-start" }}>
                <span className="grow"><strong>{h.kind}, {fmtDate(h.starts_at)}</strong><span className="small" style={{ display: "block", whiteSpace: "pre-line" }}>{h.outcome_notes || h.outcome_display}</span></span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
