"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Icon } from "@/components/Icon";
import { Empty, ErrorNote, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime, relative } from "@/lib/format";

type Delivery = { channel: string; status: string; is_fallback: boolean; sent_at: string | null; delivered_at: string | null; read_at: string | null };
type Note = { id: string; category: string; title: string; body: string; link: string; urgent: boolean; read_at: string | null; created_at: string; deliveries: Delivery[] };

const CATS = [["", "All"], ["diary", "Court"], ["appointment", "Appointments"], ["billing", "Billing"], ["security", "Security"]];
const CAT_ICON: Record<string, string> = { diary: "gavel", appointment: "clock", agenda: "calendar", billing: "receipt", security: "lock", general: "bell" };
const CHANNEL_ICON: Record<string, string> = { email: "mail", whatsapp: "whatsapp", sms: "smartphone" };
const STATUS_TEXT: Record<string, string> = { queued: "Waiting to send", sent: "Sent", delivered: "Delivered", read: "Read", failed: "Could not be delivered", skipped: "Skipped" };

export default function NotificationsPage() {
  const router = useRouter();
  const [category, setCategory] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const { data, setData, error, loading } = useLoad(
    () => api<{ results: Note[] }>("/notifications/", { query: { category, "read_at__isnull": unreadOnly ? "true" : undefined, page_size: 100 } }).then((r) => r.results),
    [category, unreadOnly],
  );

  async function open(n: Note) {
    if (!n.read_at) {
      api(`/notifications/${n.id}/read/`, { method: "POST" }).catch(() => undefined);
      setData(data?.map((x) => (x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x)));
    }
    setExpanded(expanded === n.id ? null : n.id);
  }

  async function readAll() {
    await api("/notifications/read-all/", { method: "POST" });
    setData(data?.map((x) => ({ ...x, read_at: x.read_at ?? new Date().toISOString() })));
  }

  return (
    <div className="page" style={{ maxWidth: 860 }}>
      <div className="page-head">
        <div>
          <h1>Notifications</h1>
          <p>Everything we have told you, and how each message reached you.</p>
        </div>
        <div className="row wrap">
          <Link href="/settings/notifications" className="btn"><Icon name="settings" /> Preferences</Link>
          <button className="btn" onClick={readAll}><Icon name="check" /> Mark all read</button>
        </div>
      </div>

      <div className="row-between wrap" style={{ marginBottom: 14 }}>
        <div className="chips">
          {CATS.map(([k, l]) => <button key={k} className="chip" aria-pressed={category === k} onClick={() => setCategory(k)}>{l}</button>)}
        </div>
        <label className="check small" style={{ alignItems: "center" }}>
          <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} /> Unread only
        </label>
      </div>

      <ErrorNote error={error} />

      <div className="card">
        {loading ? (
          <div className="card-body stack">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 58 }} />)}</div>
        ) : !data?.length ? (
          <Empty icon="bell" title="You are all caught up">Court dates, appointments and updates will appear here.</Empty>
        ) : (
          <ul className="list">
            {data.map((n) => (
              <li key={n.id}>
                <button className="list-item" onClick={() => open(n)} aria-expanded={expanded === n.id} style={{ alignItems: "flex-start" }}>
                  <span style={{ width: 38, height: 38, borderRadius: 11, display: "grid", placeItems: "center", flex: "none", background: n.urgent ? "var(--danger-soft)" : "var(--primary-soft)", color: n.urgent ? "var(--danger)" : "var(--primary)" }}>
                    <Icon name={CAT_ICON[n.category] ?? "bell"} size={19} />
                  </span>
                  <span className="grow">
                    <span style={{ display: "block", fontWeight: n.read_at ? 500 : 700 }}>{n.title}</span>
                    <span className="muted small">{relative(n.created_at)}</span>
                  </span>
                  <span className="row" style={{ ["--gap" as string]: "6px", color: "var(--muted)" }}>
                    {n.deliveries.map((d) => (
                      <span key={d.channel + d.is_fallback} title={`${d.channel}: ${STATUS_TEXT[d.status]}`} style={{ color: d.status === "failed" ? "var(--danger)" : d.status === "read" || d.status === "delivered" ? "var(--success)" : undefined }}>
                        <Icon name={CHANNEL_ICON[d.channel] ?? "bell"} size={15} />
                      </span>
                    ))}
                    {!n.read_at && <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--accent)" }} />}
                  </span>
                </button>
                {expanded === n.id && (
                  <div style={{ padding: "0 20px 18px 72px" }} className="stack">
                    <p style={{ whiteSpace: "pre-line", color: "var(--ink-2)" }}>{n.body}</p>
                    {n.deliveries.length > 0 && (
                      <div className="stack small" style={{ ["--gap" as string]: "6px" }}>
                        {n.deliveries.map((d) => (
                          <span key={d.channel + d.is_fallback} className="row" style={{ ["--gap" as string]: "8px" }}>
                            <Icon name={CHANNEL_ICON[d.channel] ?? "bell"} size={15} />
                            <span style={{ textTransform: "capitalize" }}>{d.channel === "sms" ? "SMS" : d.channel}{d.is_fallback ? " (backup)" : ""}:</span>
                            <span className="muted">{STATUS_TEXT[d.status]}{d.read_at ? ` ${fmtDateTime(d.read_at)}` : d.delivered_at ? ` ${fmtDateTime(d.delivered_at)}` : d.sent_at ? ` ${fmtDateTime(d.sent_at)}` : ""}</span>
                          </span>
                        ))}
                      </div>
                    )}
                    {n.link && <button className="btn btn-sm" style={{ justifySelf: "start" }} onClick={() => router.push(n.link)}>Open <Icon name="arrow-right" /></button>}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
