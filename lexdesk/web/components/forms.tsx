"use client";

import { useEffect, useState } from "react";
import { api, errorMessage, fieldError, list } from "@/lib/api";
import { isoDay, localToIso, fmtTime } from "@/lib/format";
import { Icon } from "./Icon";
import { Field, Modal, useToast } from "./ui";

export type CourtEvent = {
  id: string;
  matter: string;
  matter_reference: string;
  matter_title: string;
  kind: string;
  kind_display: string;
  is_deadline: boolean;
  title: string;
  starts_at: string;
  ends_at: string | null;
  all_day: boolean;
  location: string;
  attendees: string[];
  notes: string;
  outcome: string;
  outcome_notes: string;
  notify_client: boolean;
};

export type Appointment = {
  id: string;
  client: string;
  client_name: string;
  matter: string | null;
  lawyer: string;
  lawyer_detail: { id: string; full_name: string; title: string };
  starts_at: string;
  ends_at: string;
  mode: string;
  mode_display: string;
  status: string;
  status_display: string;
  purpose: string;
  location: string;
  video_link: string;
  internal_notes?: string;
  cancellation_reason: string;
};

export const COURT_KINDS = [
  ["hearing", "Hearing"],
  ["mention", "Mention"],
  ["trial", "Trial"],
  ["judgment", "Judgment / ruling"],
  ["filing_deadline", "Filing deadline"],
  ["limitation", "Limitation date"],
  ["mediation", "Mediation"],
  ["other", "Other"],
];

type MatterLite = { id: string; reference: string; title: string; court: string };
type Member = { user: { id: string; full_name: string; title: string }; role: string };

/* ------------------------------------------------------------ court date */

export function CourtEventModal({
  event,
  matterId,
  defaultDay,
  onClose,
  onSaved,
}: {
  event?: CourtEvent;
  matterId?: string;
  defaultDay?: string;
  onClose: () => void;
  onSaved: (e: CourtEvent) => void;
}) {
  const toast = useToast();
  const [matters, setMatters] = useState<MatterLite[]>([]);
  const [team, setTeam] = useState<Member[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(() => ({
    matter: event?.matter ?? matterId ?? "",
    kind: event?.kind ?? "hearing",
    title: event?.title ?? "",
    day: event ? isoDay(event.starts_at) : defaultDay ?? isoDay(new Date(Date.now() + 86400000)),
    time: event && !event.all_day ? fmtTime(event.starts_at) : "09:00",
    all_day: event?.all_day ?? false,
    location: event?.location ?? "",
    attendees: event?.attendees ?? ([] as string[]),
    notify_client: event?.notify_client ?? false,
    notes: event?.notes ?? "",
  }));

  useEffect(() => {
    if (!matterId && !event) list<MatterLite>("/matters/", { status: "open" }).then(setMatters).catch(() => undefined);
  }, [matterId, event]);

  useEffect(() => {
    if (!form.matter) return setTeam([]);
    api<Member[]>(`/matters/${form.matter}/team/`).then(setTeam).catch(() => setTeam([]));
    const m = matters.find((x) => x.id === form.matter);
    if (m && !form.location && m.court) setForm((f) => ({ ...f, location: m.court }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.matter, matters]);

  const deadline = form.kind === "filing_deadline" || form.kind === "limitation";

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const allDay = form.all_day || deadline;
    const body = {
      matter: form.matter,
      kind: form.kind,
      title: form.title || COURT_KINDS.find((k) => k[0] === form.kind)?.[1],
      starts_at: localToIso(form.day, allDay ? "00:00" : form.time),
      all_day: allDay,
      location: form.location,
      attendees: form.attendees,
      notify_client: form.notify_client,
      notes: form.notes,
    };
    try {
      const saved = event
        ? await api<CourtEvent>(`/diary/${event.id}/`, { method: "PATCH", body })
        : await api<CourtEvent>("/diary/", { method: "POST", body });
      toast(event ? "Saved. Everyone involved has been told." : "In the diary. You and the team have been notified.");
      onSaved(saved);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const toggle = (id: string) =>
    setForm((f) => ({ ...f, attendees: f.attendees.includes(id) ? f.attendees.filter((a) => a !== id) : [...f.attendees, id] }));

  return (
    <Modal
      title={event ? "Edit court date" : "Add a court date"}
      subtitle="Everyone attending is told at once, and reminded before the day."
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" form="court-form" disabled={busy || !form.matter}>
            {busy ? "Saving…" : event ? "Save changes" : "Add to diary"}
          </button>
        </>
      }
    >
      <form id="court-form" className="stack" style={{ ["--gap" as string]: "14px" }} onSubmit={save}>
        {error ? <div className="notice err"><Icon name="alert" /><span>{errorMessage(error)}</span></div> : null}
        {!matterId && !event && (
          <Field label="Matter" htmlFor="ce-matter" error={fieldError(error, "matter")}>
            <select id="ce-matter" className="select" required value={form.matter} onChange={(e) => setForm({ ...form, matter: e.target.value })}>
              <option value="">Choose a matter…</option>
              {matters.map((m) => <option key={m.id} value={m.id}>{m.reference} · {m.title}</option>)}
            </select>
          </Field>
        )}
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="What is it?" htmlFor="ce-kind">
            <select id="ce-kind" className="select" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
              {COURT_KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </Field>
          <Field label="Short description" htmlFor="ce-title" error={fieldError(error, "title")}>
            <input id="ce-title" className="input" placeholder="e.g. Hearing of the main suit" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </Field>
        </div>
        <div className="grid-2" style={{ gap: 14 }}>
          <Field label="Date" htmlFor="ce-day" error={fieldError(error, "starts_at")}>
            <input id="ce-day" className="input" type="date" required value={form.day} onChange={(e) => setForm({ ...form, day: e.target.value })} />
          </Field>
          {!deadline && !form.all_day && (
            <Field label="Time" htmlFor="ce-time">
              <input id="ce-time" className="input" type="time" required value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} />
            </Field>
          )}
        </div>
        {!deadline && (
          <label className="check">
            <input type="checkbox" checked={form.all_day} onChange={(e) => setForm({ ...form, all_day: e.target.checked })} />
            <span>All day (no fixed time on the cause list)</span>
          </label>
        )}
        {deadline && (
          <div className="notice warn">
            <Icon name="alert" />
            <span>Deadlines are reminded from 9am on the day and earlier, at each person's reminder times.</span>
          </div>
        )}
        <Field label="Court and room" htmlFor="ce-loc">
          <input id="ce-loc" className="input" placeholder="e.g. High Court (Commercial Division), Court 4" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
        </Field>
        {team.length > 0 && (
          <div className="field">
            <span className="label">Who is attending?</span>
            <div className="chips">
              {team.map((m) => (
                <button type="button" key={m.user.id} className="chip" aria-pressed={form.attendees.includes(m.user.id)} onClick={() => toggle(m.user.id)}>
                  {form.attendees.includes(m.user.id) && <Icon name="check" />} {m.user.full_name}
                </button>
              ))}
            </div>
            <span className="hint">The lead lawyer is always told. If you choose nobody, it is you.</span>
          </div>
        )}
        <label className="check">
          <input type="checkbox" checked={form.notify_client} onChange={(e) => setForm({ ...form, notify_client: e.target.checked })} />
          <span>
            <strong>Tell the client too</strong>
            <span className="muted small" style={{ display: "block" }}>They get the date, place and reminders, without internal details.</span>
          </span>
        </label>
        <Field label="Notes for the team (optional)" htmlFor="ce-notes">
          <textarea id="ce-notes" className="textarea" style={{ minHeight: 70 }} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </Field>
        <div className="row small muted" style={{ ["--gap" as string]: "8px" }}>
          <Icon name="whatsapp" size={16} /> <Icon name="mail" size={16} /> <Icon name="bell" size={16} />
          <span>Notified by WhatsApp, email and in the app.</span>
        </div>
      </form>
    </Modal>
  );
}

/* ----------------------------------------------------------- appointment */

type Lawyer = { id: string; name: string; title: string };
type ClientLite = { id: string; name: string; email: string; phone: string };

export function AppointmentModal({
  appointment,
  defaultClient,
  defaultLawyer,
  onClose,
  onSaved,
}: {
  appointment?: Appointment;
  defaultClient?: string;
  defaultLawyer?: string;
  onClose: () => void;
  onSaved: (a: Appointment) => void;
}) {
  const toast = useToast();
  const [lawyers, setLawyers] = useState<Lawyer[]>([]);
  const [clients, setClients] = useState<ClientLite[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(() => ({
    client: appointment?.client ?? defaultClient ?? "",
    lawyer: appointment?.lawyer ?? defaultLawyer ?? "",
    day: appointment ? isoDay(appointment.starts_at) : isoDay(new Date(Date.now() + 86400000)),
    time: appointment ? fmtTime(appointment.starts_at) : "10:00",
    minutes: appointment ? Math.round((new Date(appointment.ends_at).getTime() - new Date(appointment.starts_at).getTime()) / 60000) : 30,
    mode: appointment?.mode ?? "in_person",
    purpose: appointment?.purpose ?? "",
    location: appointment?.location ?? "",
    video_link: appointment?.video_link ?? "",
  }));

  useEffect(() => {
    api<Lawyer[]>("/appointments/public/lawyers/").then(setLawyers).catch(() => undefined);
    if (!appointment) list<ClientLite>("/clients/").then(setClients).catch(() => undefined);
  }, [appointment]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const starts = localToIso(form.day, form.time);
    const ends = new Date(new Date(starts).getTime() + form.minutes * 60000).toISOString();
    const body: Record<string, unknown> = {
      lawyer: form.lawyer,
      starts_at: starts,
      ends_at: ends,
      mode: form.mode,
      purpose: form.purpose,
      location: form.location,
      video_link: form.video_link,
    };
    if (!appointment) body.client = form.client;
    try {
      const saved = appointment
        ? await api<Appointment>(`/appointments/${appointment.id}/`, { method: "PATCH", body })
        : await api<Appointment>("/appointments/", { method: "POST", body });
      toast(appointment ? "Appointment updated. The client has been told." : "Booked and confirmed. The client and lawyer have been notified.");
      onSaved(saved);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={appointment ? "Change appointment" : "New appointment"}
      subtitle="Confirmations and reminders go out automatically."
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" form="appt-form" disabled={busy}>{busy ? "Saving…" : appointment ? "Save changes" : "Book appointment"}</button>
        </>
      }
    >
      <form id="appt-form" className="stack" style={{ ["--gap" as string]: "14px" }} onSubmit={save}>
        {error ? <div className="notice err"><Icon name="alert" /><span>{errorMessage(error)}</span></div> : null}
        {!appointment && (
          <Field label="Client" htmlFor="ap-client" error={fieldError(error, "client")}>
            <select id="ap-client" className="select" required value={form.client} onChange={(e) => setForm({ ...form, client: e.target.value })}>
              <option value="">Choose a client…</option>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
        )}
        <Field label="Lawyer" htmlFor="ap-lawyer" error={fieldError(error, "lawyer")}>
          <select id="ap-lawyer" className="select" required value={form.lawyer} onChange={(e) => setForm({ ...form, lawyer: e.target.value })}>
            <option value="">Choose a lawyer…</option>
            {lawyers.map((l) => <option key={l.id} value={l.id}>{l.name}{l.title ? ` · ${l.title}` : ""}</option>)}
          </select>
        </Field>
        <div className="grid-3" style={{ gap: 14 }}>
          <Field label="Date" htmlFor="ap-day" error={fieldError(error, "starts_at")}>
            <input id="ap-day" className="input" type="date" required value={form.day} onChange={(e) => setForm({ ...form, day: e.target.value })} />
          </Field>
          <Field label="Time" htmlFor="ap-time">
            <input id="ap-time" className="input" type="time" required value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} />
          </Field>
          <Field label="Length" htmlFor="ap-len">
            <select id="ap-len" className="select" value={form.minutes} onChange={(e) => setForm({ ...form, minutes: Number(e.target.value) })}>
              {[15, 30, 45, 60, 90, 120].map((m) => <option key={m} value={m}>{m < 60 ? `${m} min` : `${m / 60} h`}</option>)}
            </select>
          </Field>
        </div>
        <div className="field">
          <span className="label">How</span>
          <div className="segmented" role="group">
            {[["in_person", "In person"], ["video", "Video"], ["phone", "Phone"]].map(([k, l]) => (
              <button type="button" key={k} aria-pressed={form.mode === k} onClick={() => setForm({ ...form, mode: k })}>{l}</button>
            ))}
          </div>
        </div>
        {form.mode === "in_person" && (
          <Field label="Where" htmlFor="ap-loc">
            <input id="ap-loc" className="input" placeholder="e.g. Boardroom, 6th floor" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
          </Field>
        )}
        {form.mode === "video" && (
          <Field label="Video link" htmlFor="ap-video" error={fieldError(error, "video_link")}>
            <input id="ap-video" className="input" type="url" placeholder="https://meet.google.com/…" value={form.video_link} onChange={(e) => setForm({ ...form, video_link: e.target.value })} />
          </Field>
        )}
        <Field label="What is it about?" htmlFor="ap-purpose" error={fieldError(error, "purpose")}>
          <textarea id="ap-purpose" className="textarea" style={{ minHeight: 70 }} required value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} />
        </Field>
      </form>
    </Modal>
  );
}
