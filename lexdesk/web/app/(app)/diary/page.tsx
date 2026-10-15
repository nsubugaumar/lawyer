"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { type Appointment, type CourtEvent, CourtEventModal } from "@/components/forms";
import { Icon } from "@/components/Icon";
import { Empty, ErrorNote, Modal, StatusBadge, useLoad, useToast } from "@/components/ui";
import { api, errorMessage, list } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dayNum, fmtDate, fmtDay, fmtLong, fmtTime, isoDay, monthShort } from "@/lib/format";
import { saveBrief } from "@/lib/offline";

type Item =
  | { type: "court"; id: string; at: string; title: string; sub: string; deadline: boolean; done: boolean; event: CourtEvent }
  | { type: "appt"; id: string; at: string; title: string; sub: string; deadline: false; done: boolean; appt: Appointment };

function monthGrid(year: number, month: number) {
  const first = new Date(Date.UTC(year, month, 1));
  const offset = (first.getUTCDay() + 6) % 7; // weeks start on Monday
  const start = new Date(Date.UTC(year, month, 1 - offset));
  return Array.from({ length: 42 }, (_, i) => new Date(start.getTime() + i * 86400000).toISOString().slice(0, 10));
}

export default function DiaryPage() {
  const { user } = useAuth();
  const now = new Date();
  const [cursor, setCursor] = useState({ y: Number(isoDay(now).slice(0, 4)), m: Number(isoDay(now).slice(5, 7)) - 1 });
  const [view, setView] = useState<"month" | "agenda">("month");
  const [mine, setMine] = useState(false);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [adding, setAdding] = useState<string | null>(null);
  const [open, setOpenItem] = useState<Item | null>(null);
  const router = useRouter();
  // A hearing opens its court brief; an appointment opens its details.
  const setOpen = (item: Item | null) => (item?.type === "court" ? router.push(`/diary/${item.id}`) : setOpenItem(item));

  const days = useMemo(() => monthGrid(cursor.y, cursor.m), [cursor]);
  const range = view === "month" ? { from: days[0], to: days[41] } : { from: isoDay(now), to: isoDay(new Date(Date.now() + 60 * 86400000)) };

  const { data, error, loading, reload } = useLoad(async () => {
    const q = { ...range, mine: mine ? 1 : undefined };
    const [events, appts] = await Promise.all([
      list<CourtEvent>("/diary/", q),
      list<Appointment>("/appointments/", q).catch(() => [] as Appointment[]),
    ]);
    const items: Item[] = [
      ...events.map((e) => ({
        type: "court" as const, id: e.id, at: e.starts_at, title: `${e.kind_display} · ${e.matter_reference}`,
        sub: e.location || e.title, deadline: e.is_deadline, done: e.outcome !== "pending", event: e,
      })),
      ...appts
        .filter((a) => a.status !== "cancelled")
        .map((a) => ({
          type: "appt" as const, id: a.id, at: a.starts_at, title: `Consultation · ${a.client_name}`,
          sub: `${a.mode_display} with ${a.lawyer_detail?.full_name ?? ""}`, deadline: false as const, done: a.status !== "confirmed" && a.status !== "requested", appt: a,
        })),
    ];
    return items.sort((a, b) => a.at.localeCompare(b.at));
  }, [range.from, range.to, mine]);

  const byDay = useMemo(() => {
    const map: Record<string, Item[]> = {};
    for (const item of data ?? []) (map[isoDay(item.at)] ??= []).push(item);
    return map;
  }, [data]);

  const today = isoDay(now);
  const monthLabel = new Date(Date.UTC(cursor.y, cursor.m, 15)).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
  const move = (delta: number) => setCursor(({ y, m }) => ({ y: m + delta < 0 ? y - 1 : m + delta > 11 ? y + 1 : y, m: (m + delta + 12) % 12 }));

  return (
    <div className="page" style={{ maxWidth: 1280 }}>
      <div className="page-head">
        <div>
          <h1>Court diary</h1>
          <p>Tap a hearing to open its court brief: your notes, the court bundle and the case details, so you never need the paper file in court.</p>
        </div>
        <div className="row wrap">
          <Link href="/settings/notifications#calendar" className="btn"><Icon name="link" /> Sync to my phone calendar</Link>
          {user?.role !== "client" && <SaveWeek />}
          {user?.role !== "accountant" && user?.role !== "client" && (
            <button className="btn btn-primary" onClick={() => setAdding(today)}><Icon name="plus" /> Add court date</button>
          )}
        </div>
      </div>

      <div className="row-between wrap" style={{ marginBottom: 14 }}>
        <div className="row">
          {view === "month" && (
            <>
              <button className="icon-btn" onClick={() => move(-1)} aria-label="Previous month"><Icon name="chevron-left" /></button>
              <h2 style={{ minWidth: 170, textAlign: "center", fontSize: "1.25rem" }}>{monthLabel}</h2>
              <button className="icon-btn" onClick={() => move(1)} aria-label="Next month"><Icon name="chevron-right" /></button>
              <button className="btn btn-sm" onClick={() => setCursor({ y: Number(today.slice(0, 4)), m: Number(today.slice(5, 7)) - 1 })}>Today</button>
            </>
          )}
          {view === "agenda" && <h2 style={{ fontSize: "1.25rem" }}>Next 60 days</h2>}
        </div>
        <div className="row wrap">
          <label className="check small" style={{ alignItems: "center" }}>
            <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> Only mine
          </label>
          <div className="segmented" role="group" aria-label="View">
            <button aria-pressed={view === "month"} onClick={() => setView("month")}>Month</button>
            <button aria-pressed={view === "agenda"} onClick={() => setView("agenda")}>Agenda</button>
          </div>
        </div>
      </div>

      <ErrorNote error={error} />

      {view === "month" ? (
        <div className="card" style={{ overflow: "hidden", opacity: loading ? 0.6 : 1, transition: "opacity .2s" }}>
          <div className="cal">
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d} className="dow">{d}</div>)}
            {days.map((d) => {
              const items = byDay[d] ?? [];
              const out = Number(d.slice(5, 7)) - 1 !== cursor.m;
              return (
                <div
                  key={d}
                  className={`cell ${out ? "out" : ""} ${d === today ? "today" : ""}`}
                  onClick={() => (items.length ? setSelectedDay(d) : user?.role !== "client" && setAdding(d))}
                  role="button"
                  tabIndex={0}
                  aria-label={`${fmtLong(d + "T12:00:00+03:00")}, ${items.length} items`}
                  onKeyDown={(e) => e.key === "Enter" && (items.length ? setSelectedDay(d) : setAdding(d))}
                >
                  <span className="n">{Number(d.slice(8))}</span>
                  {items.slice(0, 3).map((it) => (
                    <button
                      key={it.id}
                      className={`ev ${it.type === "appt" ? "appt" : it.deadline ? "deadline" : ""} ${it.done ? "done" : ""}`}
                      onClick={(e) => { e.stopPropagation(); setOpen(it); }}
                      style={{ border: 0, textAlign: "left", cursor: "pointer", width: "100%" }}
                    >
                      {it.type === "court" && !it.event.all_day ? `${fmtTime(it.at)} ` : ""}{it.title}
                    </button>
                  ))}
                  {items.length > 3 && <span className="tiny muted">+{items.length - 3} more</span>}
                  <span className="pips">{items.slice(0, 4).map((it) => <span key={it.id} className={`pip ${it.type === "appt" ? "appt" : it.deadline ? "deadline" : ""}`} />)}</span>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <AgendaList byDay={byDay} loading={loading} onOpen={setOpen} />
      )}

      <div className="row wrap small muted" style={{ marginTop: 12, ["--gap" as string]: "16px" }}>
        <span className="row" style={{ ["--gap" as string]: "6px" }}><span className="pip" /> Court</span>
        <span className="row" style={{ ["--gap" as string]: "6px" }}><span className="pip deadline" /> Deadline</span>
        <span className="row" style={{ ["--gap" as string]: "6px" }}><span className="pip appt" /> Appointment</span>
      </div>

      {selectedDay && (
        <Modal title={fmtLong(selectedDay + "T12:00:00+03:00")} onClose={() => setSelectedDay(null)}
          footer={user?.role !== "client" ? <button className="btn btn-primary" onClick={() => { setAdding(selectedDay); setSelectedDay(null); }}><Icon name="plus" /> Add on this day</button> : undefined}>
          <ul className="list" style={{ margin: "0 -22px" }}>
            {(byDay[selectedDay] ?? []).map((it) => (
              <li key={it.id}><ItemRow item={it} onOpen={(i) => { setSelectedDay(null); setOpen(i); }} /></li>
            ))}
          </ul>
        </Modal>
      )}

      {open && <ItemDetail item={open} onClose={() => setOpen(null)} onChanged={() => { setOpen(null); reload(); }} />}
      {adding && <CourtEventModal defaultDay={adding} onClose={() => setAdding(null)} onSaved={() => { setAdding(null); reload(); }} />}
    </div>
  );
}

function AgendaList({ byDay, loading, onOpen }: { byDay: Record<string, Item[]>; loading: boolean; onOpen: (i: Item) => void }) {
  const keys = Object.keys(byDay).sort();
  if (loading) return <div className="card card-body stack">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 60 }} />)}</div>;
  if (!keys.length) return <div className="card"><Empty icon="calendar" title="Nothing in the next 60 days">Add a court date and it will appear here.</Empty></div>;
  return (
    <div className="stack" style={{ ["--gap" as string]: "16px" }}>
      {keys.map((k) => (
        <section key={k} className="card">
          <div className="card-head"><h3>{fmtLong(k + "T12:00:00+03:00")}</h3></div>
          <ul className="list">{byDay[k].map((it) => <li key={it.id}><ItemRow item={it} onOpen={onOpen} /></li>)}</ul>
        </section>
      ))}
    </div>
  );
}

function ItemRow({ item, onOpen }: { item: Item; onOpen: (i: Item) => void }) {
  return (
    <button className="list-item" onClick={() => onOpen(item)}>
      <span className={`date-tile ${item.type === "appt" ? "appt" : item.deadline ? "deadline" : ""}`}>
        <span className="m">{monthShort(item.at)}</span>
        <span className="d">{dayNum(item.at)}</span>
      </span>
      <span className="grow">
        <strong className="truncate" style={{ display: "block", textDecoration: item.done ? "line-through" : undefined }}>{item.title}</strong>
        <span className="muted small truncate" style={{ display: "block" }}>
          {item.type === "court" && item.event.all_day ? "All day" : fmtTime(item.at)} · {item.sub}
        </span>
      </span>
      {item.type === "court" ? <StatusBadge status={item.event.outcome} /> : <StatusBadge status={item.appt.status} />}
    </button>
  );
}

function ItemDetail({ item, onClose, onChanged }: { item: Item; onClose: () => void; onChanged: () => void }) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const { user } = useAuth();

  if (item.type === "appt") {
    const a = item.appt;
    return (
      <Modal title={item.title} subtitle={`${fmtDay(a.starts_at)}, ${fmtTime(a.starts_at)}–${fmtTime(a.ends_at)}`} onClose={onClose}
        footer={<Link className="btn btn-primary" href="/appointments">Open appointments</Link>}>
        <div className="stack">
          <Detail icon="user" label="Lawyer" value={a.lawyer_detail?.full_name} />
          <Detail icon={a.mode === "video" ? "video" : a.mode === "phone" ? "phone" : "building"} label="How" value={a.mode_display} />
          {a.location && <Detail icon="pin" label="Where" value={a.location} />}
          <Detail icon="message" label="About" value={a.purpose} />
          <div><StatusBadge status={a.status} /></div>
        </div>
      </Modal>
    );
  }

  const e = item.event;
  if (editing) return <CourtEventModal event={e} onClose={() => setEditing(false)} onSaved={onChanged} />;

  async function setOutcome(outcome: string) {
    setBusy(true);
    try {
      await api(`/diary/${e.id}/`, { method: "PATCH", body: { outcome } });
      toast(outcome === "vacated" || outcome === "adjourned" ? "Updated. Everyone has been told and reminders cancelled." : "Outcome recorded.");
      onChanged();
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setBusy(false);
    }
  }

  const canEdit = user?.role !== "client" && user?.role !== "accountant";
  return (
    <Modal
      title={`${e.kind_display}: ${e.title}`}
      subtitle={e.all_day ? fmtDate(e.starts_at, { weekday: "long", day: "numeric", month: "long", year: "numeric" }) : `${fmtLong(e.starts_at)} at ${fmtTime(e.starts_at)}`}
      onClose={onClose}
      footer={
        canEdit ? (
          <>
            <Link className="btn" href={`/matters/${e.matter}`}>Open matter</Link>
            <button className="btn btn-primary" onClick={() => setEditing(true)}><Icon name="edit" /> Edit or move</button>
          </>
        ) : undefined
      }
    >
      <div className="stack" style={{ ["--gap" as string]: "14px" }}>
        <Detail icon="briefcase" label="Matter" value={`${e.matter_reference} · ${e.matter_title}`} />
        {e.location && <Detail icon="pin" label="Where" value={e.location} />}
        {e.notes && <Detail icon="message" label="Notes" value={e.notes} />}
        <div className="row"><StatusBadge status={e.outcome} />{e.notify_client && <span className="badge badge-gold">Client is notified</span>}</div>
        {canEdit && e.outcome === "pending" && (
          <>
            <hr className="divider" />
            <span className="label">Record what happened</span>
            <div className="row wrap">
              {e.is_deadline ? (
                <button className="btn btn-sm" disabled={busy} onClick={() => setOutcome("met")}><Icon name="check" /> Deadline met</button>
              ) : (
                <>
                  <button className="btn btn-sm" disabled={busy} onClick={() => setOutcome("held")}><Icon name="check" /> Held</button>
                  <button className="btn btn-sm" disabled={busy} onClick={() => setOutcome("adjourned")}>Adjourned</button>
                </>
              )}
              <button className="btn btn-sm btn-danger" disabled={busy} onClick={() => setOutcome("vacated")}>Vacated</button>
            </div>
            <span className="hint">Adjourned? Record it, then add the new date: everyone is told about both.</span>
          </>
        )}
      </div>
    </Modal>
  );
}

function Detail({ icon, label, value }: { icon: string; label: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="row" style={{ alignItems: "flex-start" }}>
      <span style={{ color: "var(--accent-strong)", marginTop: 2 }}><Icon name={icon} size={18} /></span>
      <span>
        <span className="muted tiny" style={{ display: "block" }}>{label}</span>
        <span style={{ whiteSpace: "pre-line" }}>{value}</span>
      </span>
    </div>
  );
}

function SaveWeek() {
  const { user } = useAuth();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);

  async function save() {
    if (!user) return;
    setBusy("Finding your hearings…");
    try {
      localStorage.setItem("lexdesk.offline.user", user.id);
      const events = await list<CourtEvent>("/diary/", { from: isoDay(new Date()), to: isoDay(new Date(Date.now() + 7 * 86400000)), mine: 1 });
      const pending = events.filter((e) => e.outcome === "pending");
      let i = 0;
      for (const e of pending) {
        setBusy(`Saving ${++i} of ${pending.length}…`);
        await saveBrief(e.id, user.id);
      }
      toast(pending.length ? `${pending.length} court brief${pending.length === 1 ? "" : "s"} saved on this phone for offline use.` : "No hearings of yours in the next 7 days.");
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <button className="btn" disabled={!!busy} onClick={save}><Icon name="download" /> {busy ?? "Save this week for court"}</button>
      <Link href="/offline" className="btn btn-ghost">Saved for court</Link>
    </>
  );
}
