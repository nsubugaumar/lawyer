"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { type CourtEvent, CourtEventModal } from "@/components/forms";
import { Icon } from "@/components/Icon";
import { PrivilegedNotice } from "@/components/Privileged";
import { Avatar, Empty, ErrorNote, Field, Spinner, StatusBadge, useLoad, useToast } from "@/components/ui";
import { api, errorMessage, openFile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtLong, fmtTime, isoDay, localToIso, relative } from "@/lib/format";
import { getBrief, removeBrief, saveBrief } from "@/lib/offline";

type Note = { id: string; body: string; author: { full_name: string } | null; created_at: string; court_event_label: string; shared_with_client: boolean };
type Brief = {
  event: CourtEvent;
  matter: {
    id: string; reference: string; title: string; client_name: string; client_phone: string; court: string; case_number: string; judge: string;
    opposing_counsel: string; description: string; practice_area: string; is_restricted: boolean; lead_lawyer: string;
  };
  parties: { id: string; name: string; role_display: string; represented_by: string }[];
  history: { id: string; kind: string; title: string; starts_at: string; outcome: string; outcome_display: string; outcome_notes: string }[];
  documents: { id: string; title: string; category_display: string; latest: { original_filename: string } | null }[];
  tasks: { id: string; title: string; assigned_to_detail: { full_name: string } | null; due_on: string | null }[];
  privileged: boolean;
  hearing_notes: Note[];
  file_notes: Note[];
};

export default function CourtBriefPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const toast = useToast();
  const router = useRouter();
  const [fromPhone, setFromPhone] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [offlineBusy, setSavingOffline] = useState<string | null>(null);
  const brief = useLoad(async () => {
    const saved = await getBrief(id).catch(() => undefined);
    setSavedAt(saved?.savedAt ?? null);
    try {
      const live = await api<Brief>(`/diary/${id}/brief/`);
      setFromPhone(false);
      return live;
    } catch (err) {
      // No signal in the court house: show what was saved on this phone.
      if (saved) {
        setFromPhone(true);
        return saved.brief as Brief;
      }
      throw err;
    }
  }, [id]);

  async function saveForCourt() {
    if (!user) return;
    try {
      localStorage.setItem("lexdesk.offline.user", user.id);
      const saved = await saveBrief(id, user.id, (done, total) => setSavingOffline(total ? `Saving documents ${done} of ${total}…` : "Saving…"));
      setSavedAt(saved.savedAt);
      toast("Saved on this phone. It opens in court even without signal.");
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setSavingOffline(null);
    }
  }
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [showAllNotes, setShowAllNotes] = useState(false);

  if (brief.loading && !brief.data) return <div className="page"><Spinner /></div>;
  const b = brief.data;
  if (!b) return <div className="page"><ErrorNote error={brief.error ?? { message: "This court date could not be found." }} /></div>;
  const e = b.event;
  const m = b.matter;
  const upcoming = new Date(e.starts_at).getTime() > Date.now() - 6 * 3600 * 1000;

  async function addNote(ev: React.FormEvent) {
    ev.preventDefault();
    if (!note.trim()) return;
    setSaving(true);
    try {
      await api("/notes/", { method: "POST", body: { matter: m.id, court_event: e.id, body: note } });
      setNote("");
      brief.reload();
      toast("Note saved to the file.");
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setSaving(false);
    }
  }

  const canEdit = user?.role !== "accountant" && user?.role !== "client";

  return (
    <div className="page" style={{ maxWidth: 980 }}>
      <div className="row-between wrap" style={{ marginBottom: 12 }}>
        <Link href="/diary" className="small row" style={{ ["--gap" as string]: "4px", textDecoration: "none" }}>
          <Icon name="chevron-left" size={16} /> Court diary
        </Link>
        {savedAt ? (
          <span className="row small" style={{ ["--gap" as string]: "8px" }}>
            <span className="badge badge-green"><Icon name="download" size={12} /> Saved on this phone</span>
            {!fromPhone && <button className="btn btn-ghost btn-sm" disabled={!!offlineBusy} onClick={saveForCourt}>{offlineBusy ?? "Update"}</button>}
            {!fromPhone && <button className="btn btn-ghost btn-sm" onClick={async () => { await removeBrief(id); setSavedAt(null); }}>Remove</button>}
          </span>
        ) : (
          <button className="btn btn-sm" disabled={!!offlineBusy} onClick={saveForCourt}><Icon name="download" /> {offlineBusy ?? "Save for court (offline)"}</button>
        )}
      </div>
      {fromPhone && (
        <div className="notice warn" style={{ marginBottom: 14 }}>
          <Icon name="info" />
          <span>No connection: showing the copy saved on this phone{savedAt ? ` on ${fmtDate(savedAt, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}` : ""}. Documents open from <Link href={`/offline?brief=${id}`}>Saved for court</Link>.</span>
        </div>
      )}

      {/* ------------------------------------------------------ the hearing */}
      <section className="card" style={{ overflow: "hidden", marginBottom: 18 }}>
        <div style={{ padding: "22px 22px 18px", background: "linear-gradient(150deg, var(--primary), var(--primary-strong))", color: "#fff" }}>
          <div className="row wrap" style={{ ["--gap" as string]: "8px", marginBottom: 8 }}>
            <span className="eyebrow" style={{ color: "#d9be8a" }}>Court brief · {m.reference}</span>
            {e.is_deadline && <span className="badge badge-red">Deadline</span>}
            <StatusBadge status={e.outcome} />
          </div>
          <h1 style={{ color: "#fff" }}>{e.kind_display}: {e.title}</h1>
          <p style={{ color: "#cfd9ec", marginTop: 6, fontSize: 17 }}>
            {e.all_day ? fmtLong(e.starts_at) : `${fmtLong(e.starts_at)} at ${fmtTime(e.starts_at)}`}
            {upcoming && e.outcome === "pending" ? ` · ${relative(e.starts_at)}` : ""}
          </p>
          {e.location && (
            <p className="row" style={{ ["--gap" as string]: "8px", color: "#fff", marginTop: 10, fontSize: 17, fontWeight: 600 }}>
              <Icon name="pin" size={20} /> {e.location}
            </p>
          )}
        </div>
        <div className="card-body grid-2" style={{ gap: 14 }}>
          <Fact label="Matter" value={m.title} />
          <Fact label="Client" value={m.client_name} action={m.client_phone ? <a className="btn btn-sm" href={`tel:${m.client_phone}`}><Icon name="phone" /> Call</a> : null} />
          <Fact label="Court" value={m.court} />
          <Fact label="Case number" value={m.case_number} big />
          <Fact label="Before" value={m.judge} />
          <Fact label="Opposing counsel" value={m.opposing_counsel} />
        </div>
        {canEdit && (
          <div className="card-foot" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
            <Link href={`/matters/${m.id}`} className="btn btn-sm"><Icon name="briefcase" /> Full matter file</Link>
            <button className="btn btn-sm" onClick={() => setEditing(true)}><Icon name="edit" /> Edit or move this date</button>
          </div>
        )}
      </section>

      <div className="grid-2" style={{ alignItems: "start" }}>
        <div className="stack" style={{ ["--gap" as string]: "18px" }}>
          {/* -------------------------------------------- notes for court */}
          <section className="card">
            <div className="card-head">
              <h2>My notes for this hearing</h2>
              <span className="muted small row" style={{ ["--gap" as string]: "6px" }}><Icon name="lock" size={14} /> Privileged</span>
            </div>
            {b.privileged ? (
              <>
                <form className="card-body stack" onSubmit={addNote} style={{ borderBottom: "1px solid var(--line)", ["--gap" as string]: "10px" }}>
                  <textarea
                    className="textarea"
                    style={{ fontSize: 16, minHeight: 110 }}
                    placeholder="Points to make, questions for the witness, what the judge said, what happens next…"
                    value={note}
                    onChange={(ev) => setNote(ev.target.value)}
                    aria-label="Note for this hearing"
                  />
                  <button className="btn btn-primary" style={{ justifySelf: "end" }} disabled={saving || !note.trim()}>{saving ? "Saving…" : "Save note"}</button>
                </form>
                {b.hearing_notes.length === 0 ? (
                  <p className="muted small" style={{ padding: "14px 20px" }}>No notes for this hearing yet. Write your preparation points here; they stay on the file.</p>
                ) : (
                  <ul className="list">{b.hearing_notes.map((n) => <NoteRow key={n.id} n={n} />)}</ul>
                )}
              </>
            ) : (
              <PrivilegedNotice />
            )}
          </section>

          {/* -------------------------------------------------- file notes */}
          {b.privileged && b.file_notes.length > 0 && (
            <section className="card">
              <div className="card-head"><h2>Earlier file notes</h2><span className="muted small">{b.file_notes.length}</span></div>
              <ul className="list">{(showAllNotes ? b.file_notes : b.file_notes.slice(0, 5)).map((n) => <NoteRow key={n.id} n={n} showHearing />)}</ul>
              {b.file_notes.length > 5 && (
                <button className="list-item" style={{ justifyContent: "center", fontWeight: 600, borderTop: "1px solid var(--line)" }} onClick={() => setShowAllNotes((s) => !s)}>
                  {showAllNotes ? "Show fewer" : `Show all ${b.file_notes.length} notes`}
                </button>
              )}
            </section>
          )}

          {m.description && (
            <section className="card card-pad stack">
              <span className="eyebrow">Case summary</span>
              <p style={{ whiteSpace: "pre-line", fontSize: 15.5 }}>{m.description}</p>
            </section>
          )}
        </div>

        <div className="stack" style={{ ["--gap" as string]: "18px" }}>
          {/* ------------------------------------------------ court bundle */}
          <section className="card">
            <div className="card-head"><h2>Court bundle</h2><span className="muted small">{b.documents.length} documents</span></div>
            {b.documents.length === 0 ? (
              <Empty icon="file" title="Nothing in the bundle">In the matter's Documents, switch on "Court bundle" for the papers you need in court.</Empty>
            ) : (
              <ul className="list">
                {b.documents.map((d) => (
                  <li key={d.id}>
                    <button className="list-item" onClick={() => openFile(`/documents/${d.id}/download/`, d.latest?.original_filename ?? d.title, true).catch((err) => toast(errorMessage(err), "err"))}>
                      <span style={{ width: 38, height: 38, borderRadius: 10, display: "grid", placeItems: "center", background: "var(--primary-soft)", color: "var(--primary)", flex: "none" }}><Icon name="file" size={19} /></span>
                      <span className="grow"><strong className="truncate" style={{ display: "block" }}>{d.title}</strong><span className="muted small">{d.category_display}</span></span>
                      <Icon name="eye" size={18} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* ------------------------------------------------------ parties */}
          {b.parties.length > 0 && (
            <section className="card">
              <div className="card-head"><h2>Parties</h2></div>
              <ul className="list">
                {b.parties.map((p) => (
                  <li key={p.id} className="list-item">
                    <Avatar name={p.name} />
                    <span className="grow"><strong style={{ display: "block" }}>{p.name}</strong><span className="muted small">{p.role_display}{p.represented_by ? ` · ${p.represented_by}` : ""}</span></span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* ---------------------------------------------------- history */}
          <section className="card">
            <div className="card-head"><h2>Previous dates</h2></div>
            {b.history.length === 0 ? (
              <p className="muted small" style={{ padding: "14px 20px" }}>This is the first date on this matter.</p>
            ) : (
              <ul className="list">
                {b.history.map((h) => (
                  <li key={h.id}>
                    <Link href={`/diary/${h.id}`} className="list-item" style={{ alignItems: "flex-start" }}>
                      <span className="grow">
                        <strong style={{ display: "block" }}>{h.kind}, {fmtDate(h.starts_at)}</strong>
                        {h.outcome_notes ? <span className="small" style={{ color: "var(--ink-2)", whiteSpace: "pre-line" }}>{h.outcome_notes}</span> : <span className="muted small">{h.title}</span>}
                      </span>
                      <StatusBadge status={h.outcome} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {b.tasks.length > 0 && (
            <section className="card">
              <div className="card-head"><h2>Open tasks</h2></div>
              <ul className="list">
                {b.tasks.map((t) => (
                  <li key={t.id} className="list-item">
                    <Icon name="check-circle" size={18} />
                    <span className="grow"><span style={{ display: "block" }}>{t.title}</span><span className="muted small">{t.assigned_to_detail?.full_name ?? "Unassigned"}{t.due_on ? ` · due ${fmtDate(t.due_on)}` : ""}</span></span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>

      {/* ------------------------------------------------- after court */}
      {canEdit && <RecordOutcome event={e} onDone={(next) => (next ? router.push(`/diary/${next}`) : brief.reload())} />}

      {editing && <CourtEventModal event={e} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); brief.reload(); }} />}
    </div>
  );
}

function Fact({ label, value, big, action }: { label: string; value: string; big?: boolean; action?: React.ReactNode }) {
  if (!value) return null;
  return (
    <div className="row-between" style={{ alignItems: "flex-start" }}>
      <span>
        <span className="muted tiny" style={{ display: "block", textTransform: "uppercase", letterSpacing: ".06em", fontWeight: 600 }}>{label}</span>
        <span style={{ fontSize: big ? 18 : 15.5, fontWeight: big ? 700 : 500 }}>{value}</span>
      </span>
      {action}
    </div>
  );
}

function NoteRow({ n, showHearing }: { n: Note; showHearing?: boolean }) {
  return (
    <li className="list-item" style={{ alignItems: "flex-start" }}>
      <Avatar name={n.author?.full_name ?? "?"} />
      <span className="grow">
        <span className="row wrap" style={{ ["--gap" as string]: "8px" }}>
          <strong>{n.author?.full_name ?? "Former colleague"}</strong>
          <span className="muted tiny">{relative(n.created_at)}</span>
          {showHearing && n.court_event_label && <span className="badge badge-blue plain">{n.court_event_label}</span>}
          {n.shared_with_client && <span className="badge badge-gold">Shared</span>}
        </span>
        <p style={{ whiteSpace: "pre-line", marginTop: 4, fontSize: 15.5 }}>{n.body}</p>
      </span>
    </li>
  );
}

function RecordOutcome({ event, onDone }: { event: CourtEvent; onDone: (nextId?: string) => void }) {
  const toast = useToast();
  const [outcome, setOutcome] = useState(event.outcome === "pending" ? "" : event.outcome);
  const [notes, setNotes] = useState(event.outcome_notes ?? "");
  const [nextDay, setNextDay] = useState("");
  const [nextTime, setNextTime] = useState("09:00");
  const [busy, setBusy] = useState(false);

  const choices: [string, string][] = event.is_deadline
    ? [["met", "Deadline met"], ["vacated", "No longer needed"]]
    : [["held", "Heard"], ["adjourned", "Adjourned"], ["vacated", "Vacated"]];

  async function save() {
    setBusy(true);
    try {
      const body: Record<string, unknown> = { outcome, outcome_notes: notes };
      if (nextDay) body.next = { starts_at: localToIso(nextDay, nextTime) };
      const result = await api<{ next_event: CourtEvent | null }>(`/diary/${event.id}/record-outcome/`, { method: "POST", body });
      toast(result.next_event ? "Recorded. The next date is in the diary and everyone has been told." : "Outcome recorded.");
      onDone(result.next_event?.id);
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" style={{ marginTop: 18 }}>
      <div className="card-head"><h2>After court: record what happened</h2></div>
      <div className="card-body stack" style={{ ["--gap" as string]: "14px" }}>
        <div className="chips">
          {choices.map(([k, l]) => (
            <button key={k} className="chip" aria-pressed={outcome === k} onClick={() => setOutcome(k)} style={{ padding: "9px 16px", fontSize: 14 }}>
              {outcome === k && <Icon name="check" />} {l}
            </button>
          ))}
        </div>
        <Field label="What happened" htmlFor="o-notes" hint="e.g. Adjourned at the defence's request; costs in the cause. Shown in the matter's history.">
          <textarea id="o-notes" className="textarea" style={{ minHeight: 80 }} value={notes} onChange={(ev) => setNotes(ev.target.value)} />
        </Field>
        {!event.is_deadline && (
          <div className="grid-2" style={{ gap: 14, gridTemplateColumns: "1fr 1fr" }}>
            <Field label="Next date (if given)" htmlFor="o-next"><input id="o-next" type="date" className="input" min={isoDay(new Date())} value={nextDay} onChange={(ev) => setNextDay(ev.target.value)} /></Field>
            <Field label="Time" htmlFor="o-time"><input id="o-time" type="time" className="input" value={nextTime} onChange={(ev) => setNextTime(ev.target.value)} /></Field>
          </div>
        )}
        <div className="row-between wrap">
          <span className="muted small">{nextDay ? "The next date goes into the diary, and the team is notified on WhatsApp, email and the app." : ""}</span>
          <button className="btn btn-primary" disabled={!outcome || busy} onClick={save}>{busy ? "Saving…" : "Save"}</button>
        </div>
      </div>
    </section>
  );
}
