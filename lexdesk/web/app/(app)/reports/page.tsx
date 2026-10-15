"use client";

import Link from "next/link";
import { useState } from "react";
import { Icon } from "@/components/Icon";
import { Empty, ErrorNote, Spinner, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { isManager, useAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import { PRACTICE_AREAS } from "@/lib/types";

type Report = {
  generated_at: string;
  summary: {
    open_matters: number; active_clients: number; retainer_clients: number; one_off_clients: number; monthly_retainer_income: string;
    outstanding: string; billed_this_month: string; collected_this_month: string; court_dates_next_30_days: number;
  };
  workload: {
    id: string; name: string; title: string; leading: number; on_team: number; retainer_clients: number; one_off_clients: number;
    hours_this_month: number; billable_hours_this_month: number; overdue_tasks: number; court_dates_next_30_days: number;
  }[];
  months: { month: string; label: string; opened: number; closed: number; billed: string; collected: string; new_clients: number; appointments: number }[];
  matters_by_area: Record<string, number>;
  clients_by_source: Record<string, number>;
  aging: Record<string, string>;
};

const AREA = Object.fromEntries(PRACTICE_AREAS);
const SOURCE: Record<string, string> = { walk_in: "Walk-in", website: "Website booking", referral: "Referral", phone: "Phone", other: "Other" };
const AGING: [string, string][] = [["current", "Not yet due"], ["1_30", "1–30 days late"], ["31_60", "31–60 days late"], ["61_90", "61–90 days late"], ["over_90", "Over 90 days late"]];

const compact = (n: number) => (n >= 1e9 ? `${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}K` : String(Math.round(n)));

export default function ReportsPage() {
  const { user } = useAuth();
  const report = useLoad(() => api<Report>("/reports/"), []);
  if (!isManager(user)) return <div className="page"><div className="card"><Empty icon="lock" title="Reports are for partners and the practice manager" /></div></div>;
  if (report.loading) return <div className="page"><Spinner /></div>;
  const r = report.data;
  if (!r) return <div className="page"><ErrorNote error={report.error} /></div>;
  const s = r.summary;

  return (
    <div className="page" style={{ maxWidth: 1240 }}>
      <div className="page-head">
        <div>
          <h1>Reports</h1>
          <p>How the firm is doing, and how the work is shared. Numbers only: nothing here opens a client's file.</p>
        </div>
      </div>

      <div className="grid-3" style={{ marginBottom: 18, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 190px), 1fr))" }}>
        <Tile label="Open matters" value={String(s.open_matters)} />
        <Tile label="Clients on retainer" value={String(s.retainer_clients)} note={`${money(s.monthly_retainer_income)} a month`} />
        <Tile label="One-off clients" value={String(s.one_off_clients)} note="came for a single service" />
        <Tile label="Billed this month" value={money(s.billed_this_month)} small />
        <Tile label="Collected this month" value={money(s.collected_this_month)} small />
        <Tile label="Owed to the firm" value={money(s.outstanding)} small />
      </div>

      {/* ------------------------------------------------- workload */}
      <section className="card" style={{ marginBottom: 18 }}>
        <div className="card-head">
          <h2>Lawyer workload</h2>
          <span className="muted small">{r.workload.length} fee earners</span>
        </div>
        {r.workload.length === 0 ? <Empty icon="users" title="No lawyers yet" /> : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Lawyer</th>
                  <th className="num">Leading</th>
                  <th className="num">On team</th>
                  <th className="num">Retainer clients</th>
                  <th className="num">One-off clients</th>
                  <th className="num">Hours this month</th>
                  <th className="num">Court dates (30 days)</th>
                  <th className="num">Overdue tasks</th>
                </tr>
              </thead>
              <tbody>
                {r.workload.map((w) => {
                  const max = Math.max(...r.workload.map((x) => x.leading), 1);
                  return (
                    <tr key={w.id}>
                      <td><strong style={{ display: "block" }}>{w.name}</strong><span className="muted small">{w.title}</span></td>
                      <td className="num">
                        <span className="row" style={{ justifyContent: "flex-end", ["--gap" as string]: "8px" }}>
                          <span style={{ width: 70, height: 8, borderRadius: 4, background: "var(--surface-2)", overflow: "hidden" }} aria-hidden>
                            <span style={{ display: "block", height: "100%", width: `${(w.leading / max) * 100}%`, background: "var(--chart-1)", borderRadius: 4 }} />
                          </span>
                          <strong>{w.leading}</strong>
                        </span>
                      </td>
                      <td className="num">{w.on_team}</td>
                      <td className="num">{w.retainer_clients}</td>
                      <td className="num">{w.one_off_clients}</td>
                      <td className="num" title={`${w.billable_hours_this_month} billable`}>{w.hours_this_month}</td>
                      <td className="num">{w.court_dates_next_30_days}</td>
                      <td className="num">{w.overdue_tasks > 0 ? <span className="badge badge-red plain">{w.overdue_tasks}</span> : 0}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted tiny" style={{ padding: "10px 20px" }}>
          Leading: open matters where they are lead counsel. On team: open matters they work on. Clients are counted against their responsible lawyer.
        </p>
      </section>

      <div className="grid-2" style={{ alignItems: "start" }}>
        <ChartCard
          title="Billed and collected"
          subtitle="Last 12 months"
          series={[
            { label: "Billed", color: "var(--chart-1)", values: r.months.map((m) => Number(m.billed)) },
            { label: "Collected", color: "var(--chart-2)", values: r.months.map((m) => Number(m.collected)) },
          ]}
          labels={r.months.map((m) => m.label)}
          format={(n) => money(n)}
          axis={compact}
        />
        <ChartCard
          title="New matters opened"
          subtitle="Last 12 months"
          series={[{ label: "Opened", color: "var(--chart-1)", values: r.months.map((m) => m.opened) }]}
          labels={r.months.map((m) => m.label)}
          format={(n) => `${n} matter${n === 1 ? "" : "s"}`}
          axis={(n) => String(Math.round(n))}
        />

        <section className="card">
          <div className="card-head"><h2>Money owed to the firm</h2><Link href="/billing" className="btn btn-ghost btn-sm">Invoices <Icon name="chevron-right" /></Link></div>
          <div className="card-body stack" style={{ ["--gap" as string]: "12px" }}>
            {AGING.map(([k, label]) => {
              const total = Math.max(...AGING.map(([kk]) => Number(r.aging[kk])), 1);
              const v = Number(r.aging[k]);
              return (
                <div key={k} className="hbar">
                  <span>{label}</span>
                  <span className="track"><span className="fill" style={{ display: "block", width: `${(v / total) * 100}%` }} /></span>
                  <strong className="num" style={{ minWidth: 110 }}>{money(v)}</strong>
                </div>
              );
            })}
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2>Open matters by practice area</h2></div>
          <div className="card-body stack" style={{ ["--gap" as string]: "12px" }}>
            <HBars rows={Object.entries(r.matters_by_area).map(([k, v]) => [AREA[k] ?? k, v])} empty="No open matters." />
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2>Where new clients came from</h2><span className="muted small">Last 12 months</span></div>
          <div className="card-body stack" style={{ ["--gap" as string]: "12px" }}>
            <HBars rows={Object.entries(r.clients_by_source).map(([k, v]) => [SOURCE[k] ?? k, v])} empty="No new clients yet." />
          </div>
        </section>
      </div>
    </div>
  );
}

function Tile({ label, value, note, small }: { label: string; value: string; note?: string; small?: boolean }) {
  return (
    <div className="card stat">
      <span className="value" style={small ? { fontSize: 21 } : undefined}>{value}</span>
      <span className="label">{label}</span>
      {note && <span className="muted tiny">{note}</span>}
    </div>
  );
}

function HBars({ rows, empty }: { rows: [string, number][]; empty: string }) {
  if (!rows.length) return <p className="muted small">{empty}</p>;
  const max = Math.max(...rows.map(([, v]) => v), 1);
  return (
    <>
      {rows.sort((a, b) => b[1] - a[1]).map(([label, v]) => (
        <div key={label} className="hbar">
          <span className="truncate">{label}</span>
          <span className="track"><span className="fill" style={{ display: "block", width: `${(v / max) * 100}%` }} /></span>
          <strong className="num" style={{ minWidth: 28 }}>{v}</strong>
        </div>
      ))}
    </>
  );
}

type Series = { label: string; color: string; values: number[] };

/** Monthly bars on one axis, with a hover tooltip per month and a table view. */
function ChartCard({ title, subtitle, series, labels, format, axis }: {
  title: string; subtitle: string; series: Series[]; labels: string[]; format: (n: number) => string; axis: (n: number) => string;
}) {
  const [asTable, setAsTable] = useState(false);
  const max = Math.max(...series.flatMap((s) => s.values), 0);
  const top = max <= 0 ? 1 : niceTop(max);
  const ticks = [top, top / 2, 0];

  return (
    <section className="card">
      <div className="card-head">
        <span>
          <h2>{title}</h2>
          <span className="muted small">{subtitle}</span>
        </span>
        <button className="btn btn-ghost btn-sm" onClick={() => setAsTable((t) => !t)} aria-pressed={asTable}>
          {asTable ? "Show chart" : "Show as table"}
        </button>
      </div>
      <div className="card-body stack" style={{ ["--gap" as string]: "12px" }}>
        {series.length > 1 && (
          <div className="legend">{series.map((s) => <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>)}</div>
        )}
        {asTable ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Month</th>{series.map((s) => <th key={s.label} className="num">{s.label}</th>)}</tr></thead>
              <tbody>{labels.map((l, i) => <tr key={l}><td>{l}</td>{series.map((s) => <td key={s.label} className="num">{format(s.values[i])}</td>)}</tr>)}</tbody>
            </table>
          </div>
        ) : max === 0 ? (
          <p className="muted small">Nothing recorded in the last 12 months yet.</p>
        ) : (
          <div className="chart" role="img" aria-label={`${title}, ${subtitle}`}>
            <div className="chart-y" aria-hidden>{ticks.map((t) => <span key={t}>{axis(t)}</span>)}</div>
            <div className="chart-plot">
              {ticks.map((t) => <span key={t} className="gridline" style={{ bottom: `calc(22px + ${(t / top) * (100)}% * (198 / 220))` }} />)}
              {labels.map((label, i) => (
                <div key={label} className="chart-group" tabIndex={0} aria-label={`${label}: ${series.map((s) => `${s.label} ${format(s.values[i])}`).join(", ")}`}>
                  {series.map((s) => (
                    <span key={s.label} className="chart-bar" style={{ height: `${(s.values[i] / top) * 100}%`, background: s.color }} />
                  ))}
                  <span className="chart-x">{label.slice(0, 3)}</span>
                  <span className="chart-tip">
                    <strong style={{ display: "block", marginBottom: 4 }}>{label}</strong>
                    {series.map((s) => (
                      <span key={s.label} className="row" style={{ ["--gap" as string]: "6px" }}>
                        <i style={{ width: 8, height: 8, borderRadius: 2, background: s.color, display: "inline-block" }} />
                        {s.label}: <strong>{format(s.values[i])}</strong>
                      </span>
                    ))}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function niceTop(max: number) {
  const magnitude = 10 ** Math.floor(Math.log10(max));
  for (const step of [1, 2, 2.5, 5, 10]) {
    if (step * magnitude >= max) return step * magnitude;
  }
  return 10 * magnitude;
}
