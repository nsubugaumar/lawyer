"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AppointmentModal, CourtEventModal } from "@/components/forms";
import { Icon } from "@/components/Icon";
import { Empty, ErrorNote, StatusBadge, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { isFeeEarner, useAuth } from "@/lib/auth";
import { dayNum, fmtDay, fmtLong, fmtTime, greeting, isoDay, money, monthShort } from "@/lib/format";

type Dashboard = {
  greeting_name: string;
  today: string;
  matters: Record<string, number>;
  upcoming_court: { id: string; kind: string; title: string; starts_at: string; location: string; matter_id: string; matter_reference: string; is_deadline: boolean }[];
  appointments: { id: string; starts_at: string; client: string; lawyer: string; mode: string; status: string }[];
  tasks?: { open: number; overdue: number; due_today: number };
  hours_this_week?: number;
  billing?: { outstanding_total: string; outstanding_count: number; overdue_count: number };
};

export default function DashboardPage() {
  const { user } = useAuth();
  const router = useRouter();
  const { data, error, loading, reload } = useLoad(() => api<Dashboard>("/dashboard/"), []);
  const [adding, setAdding] = useState<"court" | "appt" | null>(null);

  useEffect(() => {
    if (user?.role === "client") router.replace("/portal");
  }, [user, router]);

  const today = isoDay(new Date());
  const todayCourt = data?.upcoming_court.filter((e) => isoDay(e.starts_at) === today) ?? [];
  const later = data?.upcoming_court.filter((e) => isoDay(e.starts_at) !== today) ?? [];
  const openMatters = (data?.matters.open ?? 0) + (data?.matters.intake ?? 0);
  const todayCount = todayCourt.length + (data?.appointments.length ?? 0);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <span className="eyebrow">{fmtLong(new Date())}</span>
          <h1 style={{ marginTop: 6 }}>{greeting()}, {user?.first_name}.</h1>
          <p>
            {loading
              ? "Getting your day ready…"
              : todayCount === 0
                ? "Nothing in your diary today. A good day to catch up on files."
                : `You have ${todayCount} thing${todayCount === 1 ? "" : "s"} in your diary today.`}
          </p>
        </div>
        <div className="row wrap">
          <button className="btn" onClick={() => setAdding("appt")}><Icon name="clock" /> New appointment</button>
          {isFeeEarner(user) || user?.role === "receptionist" || user?.role === "admin" ? (
            <button className="btn btn-primary" onClick={() => setAdding("court")}><Icon name="plus" /> Add court date</button>
          ) : null}
        </div>
      </div>

      <ErrorNote error={error} />

      {/* -------------------------------------------------------- stats */}
      <div className="grid-3" style={{ marginBottom: 20, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 180px), 1fr))" }}>
        <Stat label="Open matters" value={loading ? "–" : String(openMatters)} href="/matters" icon="briefcase" />
        {data?.tasks && (
          <Stat
            label={data.tasks.overdue ? `${data.tasks.overdue} overdue` : "Open tasks"}
            value={String(data.tasks.open)}
            href="/matters"
            icon="check-circle"
            tone={data.tasks.overdue ? "danger" : undefined}
          />
        )}
        <Stat label="Court dates this week" value={loading ? "–" : String(data?.upcoming_court.length ?? 0)} href="/diary" icon="gavel" />
        {data?.hours_this_week !== undefined && <Stat label="Hours recorded this week" value={String(data.hours_this_week)} href="/billing" icon="clock" />}
        {data?.billing && (
          <Stat label={`${data.billing.outstanding_count} unpaid invoices`} value={money(data.billing.outstanding_total)} href="/billing" icon="receipt" small />
        )}
      </div>

      <div className="grid-2" style={{ alignItems: "start" }}>
        {/* ------------------------------------------------------- today */}
        <section className="card">
          <div className="card-head">
            <h2>Today</h2>
            <Link href="/diary" className="btn btn-ghost btn-sm">Open diary <Icon name="chevron-right" /></Link>
          </div>
          {loading ? (
            <div className="card-body stack">{[0, 1].map((i) => <div key={i} className="skeleton" style={{ height: 56 }} />)}</div>
          ) : todayCount === 0 ? (
            <Empty icon="sun" title="A clear day">No hearings or appointments today.</Empty>
          ) : (
            <ul className="list">
              {todayCourt.map((e) => (
                <li key={e.id}>
                  <Link href={`/diary/${e.id}`} className="list-item">
                    <span className={`date-tile ${e.is_deadline ? "deadline" : ""}`}>
                      <span className="m">{e.is_deadline ? "Due" : "Court"}</span>
                      <span className="d" style={{ fontSize: 16 }}>{fmtTime(e.starts_at)}</span>
                    </span>
                    <span className="grow">
                      <strong className="truncate" style={{ display: "block" }}>{e.kind} · {e.matter_reference}</strong>
                      <span className="muted small truncate" style={{ display: "block" }}>{e.location || e.title}</span>
                    </span>
                    <Icon name="chevron-right" size={18} />
                  </Link>
                </li>
              ))}
              {data?.appointments.map((a) => (
                <li key={a.id}>
                  <Link href="/appointments" className="list-item">
                    <span className="date-tile appt">
                      <span className="m">Meet</span>
                      <span className="d" style={{ fontSize: 16 }}>{fmtTime(a.starts_at)}</span>
                    </span>
                    <span className="grow">
                      <strong className="truncate" style={{ display: "block" }}>{a.client}</strong>
                      <span className="muted small">{a.mode} · with {a.lawyer}</span>
                    </span>
                    <StatusBadge status={a.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ---------------------------------------------------- this week */}
        <section className="card">
          <div className="card-head">
            <h2>Coming up</h2>
            <span className="muted small">Next 7 days</span>
          </div>
          {loading ? (
            <div className="card-body stack">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 56 }} />)}</div>
          ) : later.length === 0 ? (
            <Empty icon="calendar" title="Nothing else this week">New court dates you add will appear here.</Empty>
          ) : (
            <ul className="list">
              {later.map((e) => (
                <li key={e.id}>
                  <Link href={`/diary/${e.id}`} className="list-item">
                    <span className={`date-tile ${e.is_deadline ? "deadline" : ""}`}>
                      <span className="m">{monthShort(e.starts_at)}</span>
                      <span className="d">{dayNum(e.starts_at)}</span>
                    </span>
                    <span className="grow">
                      <strong className="truncate" style={{ display: "block" }}>{e.kind} · {e.matter_reference}</strong>
                      <span className="muted small truncate" style={{ display: "block" }}>
                        {fmtDay(e.starts_at)}, {fmtTime(e.starts_at)}{e.location ? ` · ${e.location}` : ""}
                      </span>
                    </span>
                    {e.is_deadline && <span className="badge badge-red">Deadline</span>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="notice" style={{ marginTop: 20 }}>
        <Icon name="whatsapp" />
        <span>
          Court dates and appointments are sent to your WhatsApp, email and this app automatically.{" "}
          <Link href="/settings/notifications">Choose how you are reminded</Link>.
        </span>
      </div>

      {adding === "court" && <CourtEventModal onClose={() => setAdding(null)} onSaved={() => { setAdding(null); reload(); }} />}
      {adding === "appt" && <AppointmentModal defaultLawyer={isFeeEarner(user) ? user?.id : undefined} onClose={() => setAdding(null)} onSaved={() => { setAdding(null); reload(); }} />}
    </div>
  );
}

function Stat({ label, value, href, icon, tone, small }: { label: string; value: string; href: string; icon: string; tone?: "danger"; small?: boolean }) {
  return (
    <Link href={href} className="card stat" style={{ textDecoration: "none", position: "relative" }}>
      <span style={{ position: "absolute", right: 16, top: 16, color: tone === "danger" ? "var(--danger)" : "var(--accent)" }}>
        <Icon name={icon} size={20} />
      </span>
      <span className="value" style={small ? { fontSize: 22 } : undefined}>{value}</span>
      <span className="label" style={tone === "danger" ? { color: "var(--danger)", fontWeight: 600 } : undefined}>{label}</span>
    </Link>
  );
}
