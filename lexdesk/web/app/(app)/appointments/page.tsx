"use client";

import Link from "next/link";
import { useState } from "react";
import { type Appointment, AppointmentModal } from "@/components/forms";
import { Icon } from "@/components/Icon";
import { Avatar, Empty, ErrorNote, Modal, StatusBadge, useLoad, useToast } from "@/components/ui";
import { api, errorMessage, list } from "@/lib/api";
import { isFeeEarner, useAuth } from "@/lib/auth";
import { dayNum, fmtDay, fmtTime, isoDay, monthShort } from "@/lib/format";

type Tab = "requests" | "upcoming" | "past";

export default function AppointmentsPage() {
  const { user } = useAuth();
  const toast = useToast();
  const isClient = user?.role === "client";
  const [tab, setTab] = useState<Tab>(isClient ? "upcoming" : "upcoming");
  const [mine, setMine] = useState(isFeeEarner(user));
  const [editing, setEditing] = useState<Appointment | "new" | null>(null);
  const [cancelling, setCancelling] = useState<Appointment | null>(null);

  const today = isoDay(new Date());
  const { data, error, loading, reload } = useLoad(
    () =>
      list<Appointment>("/appointments/", {
        mine: mine && !isClient ? 1 : undefined,
        from: tab === "past" ? isoDay(new Date(Date.now() - 180 * 86400000)) : today,
        to: tab === "past" ? isoDay(new Date(Date.now() - 86400000)) : undefined,
        status: tab === "requests" ? "requested" : undefined,
        ordering: tab === "past" ? "-starts_at" : "starts_at",
      }),
    [tab, mine],
  );

  const requests = useLoad(() => (isClient ? Promise.resolve([]) : list<Appointment>("/appointments/", { status: "requested", from: today })), [tab]);

  async function act(a: Appointment, action: "confirm" | "complete" | "no-show") {
    try {
      await api(`/appointments/${a.id}/${action}/`, { method: "POST" });
      toast(action === "confirm" ? `Confirmed. ${a.client_name} has been notified.` : "Updated.");
      reload();
      requests.reload();
    } catch (err) {
      toast(errorMessage(err), "err");
    }
  }

  const rows = tab === "upcoming" ? (data ?? []).filter((a) => a.status !== "cancelled") : data ?? [];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{isClient ? "Your appointments" : "Appointments"}</h1>
          <p>{isClient ? "Meetings with your lawyer. We remind you the day before and an hour before." : "Consultations booked online, by phone and at the front desk."}</p>
        </div>
        {isClient ? (
          <Link href="/book" className="btn btn-primary"><Icon name="plus" /> Book a new appointment</Link>
        ) : (
          <button className="btn btn-primary" onClick={() => setEditing("new")}><Icon name="plus" /> New appointment</button>
        )}
      </div>

      <div className="row-between wrap" style={{ marginBottom: 14 }}>
        <div className="tabs" role="tablist" style={{ borderBottom: 0 }}>
          {!isClient && (
            <button role="tab" aria-selected={tab === "requests"} onClick={() => setTab("requests")}>
              To confirm {requests.data && requests.data.length > 0 && <span className="badge badge-amber plain" style={{ marginLeft: 6 }}>{requests.data.length}</span>}
            </button>
          )}
          <button role="tab" aria-selected={tab === "upcoming"} onClick={() => setTab("upcoming")}>Upcoming</button>
          <button role="tab" aria-selected={tab === "past"} onClick={() => setTab("past")}>Past</button>
        </div>
        {!isClient && (
          <label className="check small" style={{ alignItems: "center" }}>
            <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> Only my appointments
          </label>
        )}
      </div>

      <ErrorNote error={error} />

      <div className="card">
        {loading ? (
          <div className="card-body stack">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 64 }} />)}</div>
        ) : rows.length === 0 ? (
          <Empty icon="clock" title={tab === "requests" ? "No requests waiting" : tab === "past" ? "No past appointments" : "Nothing booked yet"}>
            {tab === "requests" ? "New website bookings will appear here for you to confirm." : isClient ? "Book a time with your lawyer whenever you need to talk." : "Book a consultation for a client and they will be notified at once."}
          </Empty>
        ) : (
          <ul className="list">
            {rows.map((a) => (
              <li key={a.id} className="list-item" style={{ flexWrap: "wrap" }}>
                <span className="date-tile appt">
                  <span className="m">{monthShort(a.starts_at)}</span>
                  <span className="d">{dayNum(a.starts_at)}</span>
                </span>
                <span className="grow" style={{ minWidth: 200 }}>
                  <strong style={{ display: "block" }}>{isClient ? `With ${a.lawyer_detail.full_name}` : a.client_name}</strong>
                  <span className="muted small" style={{ display: "block" }}>
                    {fmtDay(a.starts_at)}, {fmtTime(a.starts_at)}–{fmtTime(a.ends_at)} · {a.mode_display}
                    {!isClient && ` · ${a.lawyer_detail.full_name}`}
                  </span>
                  {a.purpose && <span className="small truncate" style={{ display: "block", maxWidth: 520, color: "var(--ink-2)" }}>{a.purpose}</span>}
                  {a.video_link && a.status === "confirmed" && (
                    <a href={a.video_link} target="_blank" rel="noopener noreferrer" className="small"><Icon name="video" size={14} /> Join video call</a>
                  )}
                </span>
                <span className="row wrap" style={{ ["--gap" as string]: "8px" }}>
                  <StatusBadge status={a.status} />
                  {!isClient && a.status === "requested" && <button className="btn btn-primary btn-sm" onClick={() => act(a, "confirm")}><Icon name="check" /> Confirm</button>}
                  {!isClient && ["requested", "confirmed"].includes(a.status) && (
                    <>
                      <button className="btn btn-sm" onClick={() => setEditing(a)}>Change</button>
                      {tab === "past" && <button className="btn btn-sm" onClick={() => act(a, "complete")}>Done</button>}
                    </>
                  )}
                  {["requested", "confirmed"].includes(a.status) && (
                    <button className="btn btn-sm btn-ghost" onClick={() => setCancelling(a)}>Cancel</button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {editing && (
        <AppointmentModal
          appointment={editing === "new" ? undefined : editing}
          defaultLawyer={isFeeEarner(user) ? user?.id : undefined}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); reload(); requests.reload(); }}
        />
      )}
      {cancelling && <CancelModal appointment={cancelling} onClose={() => setCancelling(null)} onDone={() => { setCancelling(null); reload(); requests.reload(); }} />}
    </div>
  );
}

function CancelModal({ appointment, onClose, onDone }: { appointment: Appointment; onClose: () => void; onDone: () => void }) {
  const { user } = useAuth();
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const isClient = user?.role === "client";

  async function cancel() {
    setBusy(true);
    try {
      await api(`/appointments/${appointment.id}/cancel/`, { method: "POST", body: { reason } });
      toast(isClient ? "Cancelled. Your lawyer has been told." : `Cancelled. ${appointment.client_name} has been told.`);
      onDone();
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Cancel this appointment?"
      subtitle={`${fmtDay(appointment.starts_at)} at ${fmtTime(appointment.starts_at)}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>Keep it</button>
          <button className="btn btn-danger" onClick={cancel} disabled={busy}>{busy ? "Cancelling…" : "Cancel appointment"}</button>
        </>
      }
    >
      <div className="stack">
        <div className="row">
          <Avatar name={isClient ? appointment.lawyer_detail.full_name : appointment.client_name} />
          <strong>{isClient ? appointment.lawyer_detail.full_name : appointment.client_name}</strong>
        </div>
        <label className="label" htmlFor="reason">Reason (shared with {isClient ? "the firm" : "the client"})</label>
        <input id="reason" className="input" placeholder={isClient ? "e.g. I am travelling that week" : "e.g. Lawyer called to court"} value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
    </Modal>
  );
}
