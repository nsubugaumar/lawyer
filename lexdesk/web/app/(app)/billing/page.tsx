"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { Empty, ErrorNote, Field, Modal, Spinner, StatusBadge, useLoad, useToast } from "@/components/ui";
import { api, errorMessage, fieldError, list } from "@/lib/api";
import { isFeeEarner, useAuth } from "@/lib/auth";
import { fmtDate, isoDay, money } from "@/lib/format";

type Invoice = {
  id: string; number: string; matter: string; matter_reference: string; client_name: string; status: string; currency: string;
  issue_date: string | null; due_date: string | null; tax_rate: string; notes: string;
  lines: { id: string; description: string; quantity: string; unit_price: string; amount: string }[];
  payments: { id: string; amount: string; method_display: string; reference: string; received_on: string }[];
  subtotal: string; tax: string; total: string; paid: string; balance: string;
};
type TimeEntry = { id: string; matter_reference: string; date: string; minutes: number; description: string; amount: string; is_billed: boolean; billable: boolean };

const MANAGES = ["admin", "partner", "accountant"];

export default function BillingPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Billing />
    </Suspense>
  );
}

/** Back from the payment page: confirm with the server, which checks with the provider. */
function PaymentReturn() {
  const ref = useSearchParams().get("payment");
  const router = useRouter();
  const [state, setState] = useState<{ status: string; amount: string; currency: string; invoice_number: string } | null>(null);

  useEffect(() => {
    if (!ref) return;
    let tries = 0;
    const check = () =>
      api<{ status: string; amount: string; currency: string; invoice_number: string }>(`/billing/online-payments/${ref}/`)
        .then((r) => {
          setState(r);
          // Mobile Money can take a little while to confirm.
          if (r.status === "pending" && tries++ < 10) setTimeout(check, 4000);
        })
        .catch(() => setState({ status: "unknown", amount: "0", currency: "", invoice_number: "" }));
    check();
  }, [ref]);

  if (!ref || !state) return null;
  const ok = state.status === "successful";
  const pending = state.status === "pending";
  return (
    <div className={`notice ${ok ? "ok" : pending ? "" : "err"}`} style={{ marginBottom: 16 }}>
      <Icon name={ok ? "check-circle" : pending ? "clock" : "alert"} />
      <span className="grow">
        {ok
          ? `Thank you. Your payment of ${money(state.amount, state.currency)} for invoice ${state.invoice_number} has been received.`
          : pending
            ? "Waiting for the payment to be confirmed. If you approved it on your phone, this updates in a moment."
            : "The payment did not go through. No money was taken. You can try again."}
      </span>
      <button className="btn btn-ghost btn-sm" onClick={() => router.replace("/billing")}>Close</button>
    </div>
  );
}

function Billing() {
  const { user } = useAuth();
  const isClient = user?.role === "client";
  const manages = MANAGES.includes(user?.role ?? "");
  const [tab, setTab] = useState<"invoices" | "time">(manages || isClient ? "invoices" : "time");

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{isClient ? "Invoices" : "Billing"}</h1>
          <p>{isClient ? "Fees for your matters. Pay by Mobile Money or bank transfer, quoting the invoice number." : "Time, invoices and payments."}</p>
        </div>
      </div>
      {!isClient && (manages || isFeeEarner(user)) && (
        <div className="tabs" role="tablist" style={{ marginBottom: 18 }}>
          {manages && <button role="tab" aria-selected={tab === "invoices"} onClick={() => setTab("invoices")}>Invoices</button>}
          {isFeeEarner(user) && <button role="tab" aria-selected={tab === "time"} onClick={() => setTab("time")}>My time</button>}
        </div>
      )}
      <PaymentReturn />
      {tab === "invoices" ? <Invoices manages={manages} /> : <Time />}
    </div>
  );
}

function Invoices({ manages }: { manages: boolean }) {
  const [status, setStatus] = useState("");
  const invoices = useLoad(() => list<Invoice>("/billing/invoices/", { status, ordering: "-created_at" }), [status]);
  const [open, setOpen] = useState<Invoice | null>(null);
  const [generating, setGenerating] = useState(false);

  return (
    <>
      <div className="row-between wrap" style={{ marginBottom: 14 }}>
        <div className="chips">
          {[["", "All"], ...(manages ? [["draft", "Drafts"]] : []), ["issued", "Unpaid"], ["part_paid", "Part paid"], ["paid", "Paid"]].map(([k, l]) => (
            <button key={k} className="chip" aria-pressed={status === k} onClick={() => setStatus(k)}>{l}</button>
          ))}
        </div>
        {manages && <button className="btn btn-primary" onClick={() => setGenerating(true)}><Icon name="plus" /> Invoice unbilled time</button>}
      </div>
      <ErrorNote error={invoices.error} />
      <div className="card">
        {invoices.loading ? <Spinner /> : !invoices.data?.length ? (
          <Empty icon="receipt" title="No invoices here">{manages ? "Turn a matter's recorded time into a draft invoice in one step." : "When the firm sends an invoice, it will appear here."}</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Invoice</th><th className="desktop-only">Client</th><th className="desktop-only">Due</th><th className="num">Total</th><th className="num">Balance</th><th>Status</th></tr></thead>
              <tbody>
                {invoices.data.map((i) => (
                  <tr key={i.id} className="clickable" onClick={() => setOpen(i)}>
                    <td><strong>{i.number}</strong><div className="muted tiny">{i.matter_reference}</div></td>
                    <td className="desktop-only">{i.client_name}</td>
                    <td className="desktop-only">{i.due_date ? fmtDate(i.due_date) : "–"}</td>
                    <td className="num">{money(i.total, i.currency)}</td>
                    <td className="num" style={{ fontWeight: 600 }}>{money(i.balance, i.currency)}</td>
                    <td><StatusBadge status={i.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {open && <InvoiceModal invoice={open} manages={manages} onClose={() => setOpen(null)} onChanged={(inv) => { setOpen(inv); invoices.reload(); }} />}
      {generating && <GenerateModal onClose={() => setGenerating(false)} onDone={(inv) => { setGenerating(false); setOpen(inv); invoices.reload(); }} />}
    </>
  );
}

function InvoiceModal({ invoice: i, manages, onClose, onChanged }: { invoice: Invoice; manages: boolean; onClose: () => void; onChanged: (i: Invoice) => void }) {
  const toast = useToast();
  const [opening, setOpening] = useState(false);

  async function payNow() {
    setOpening(true);
    try {
      const r = await api<{ checkout_url: string }>(`/billing/invoices/${i.id}/pay-online/`, { method: "POST" });
      window.location.href = r.checkout_url;
    } catch (err) {
      toast(errorMessage(err), "err");
      setOpening(false);
    }
  }
  const [paying, setPaying] = useState(false);
  const [payment, setPayment] = useState({ amount: "", method: "mobile_money", reference: "", received_on: isoDay(new Date()) });
  const [error, setError] = useState<unknown>(null);

  async function act(path: string, body?: object, message?: string) {
    setError(null);
    try {
      onChanged(await api<Invoice>(`/billing/invoices/${i.id}/${path}/`, { method: "POST", body }));
      if (message) toast(message);
      setPaying(false);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <Modal title={`Invoice ${i.number}`} subtitle={`${i.client_name} · ${i.matter_reference}`} onClose={onClose} wide
      footer={!manages && Number(i.balance) > 0 ? (
        <button className="btn btn-primary" disabled={opening} onClick={payNow}><Icon name="wallet" /> {opening ? "Opening…" : `Pay ${money(i.balance, i.currency)} now`}</button>
      ) : manages ? (
        <>
          {i.status === "draft" && <button className="btn btn-danger" onClick={() => act("void", undefined, "Voided.")}>Void</button>}
          {i.status === "draft" && <button className="btn btn-primary" onClick={() => act("issue", undefined, "Issued. The client has been notified.")}><Icon name="send" /> Issue to client</button>}
          {["issued", "part_paid"].includes(i.status) && <button className="btn btn-primary" onClick={() => setPaying(true)}><Icon name="wallet" /> Record a payment</button>}
        </>
      ) : undefined}>
      <div className="stack" style={{ ["--gap" as string]: "16px" }}>
        {error ? <div className="notice err"><Icon name="alert" /><span>{errorMessage(error)}</span></div> : null}
        <div className="row wrap" style={{ ["--gap" as string]: "18px" }}>
          <StatusBadge status={i.status} />
          {i.issue_date && <span className="small muted">Issued {fmtDate(i.issue_date)}</span>}
          {i.due_date && <span className="small muted">Due {fmtDate(i.due_date)}</span>}
        </div>
        <div className="table-wrap card">
          <table className="table">
            <thead><tr><th>Description</th><th className="num">Qty</th><th className="num">Rate</th><th className="num">Amount</th></tr></thead>
            <tbody>
              {i.lines.map((l) => (
                <tr key={l.id}><td>{l.description}</td><td className="num">{Number(l.quantity)}</td><td className="num">{money(l.unit_price, i.currency)}</td><td className="num">{money(l.amount, i.currency)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="stack" style={{ justifyItems: "end", ["--gap" as string]: "4px" }}>
          <span className="small">Subtotal {money(i.subtotal, i.currency)}</span>
          <span className="small">Tax ({Number(i.tax_rate)}%) {money(i.tax, i.currency)}</span>
          <strong className="serif" style={{ fontSize: 20 }}>Total {money(i.total, i.currency)}</strong>
          {Number(i.paid) > 0 && <span className="small" style={{ color: "var(--success)" }}>Paid {money(i.paid, i.currency)}</span>}
          <strong>Balance {money(i.balance, i.currency)}</strong>
        </div>
        {i.payments.length > 0 && (
          <div className="stack" style={{ ["--gap" as string]: "6px" }}>
            <span className="label">Payments</span>
            {i.payments.map((p) => <span key={p.id} className="small">{fmtDate(p.received_on)} · {p.method_display} · {money(p.amount, i.currency)}{p.reference ? ` · ${p.reference}` : ""}</span>)}
          </div>
        )}
        {paying && (
          <div className="card card-pad stack" style={{ ["--gap" as string]: "12px", background: "var(--surface-2)" }}>
            <div className="grid-2" style={{ gap: 12 }}>
              <Field label="Amount" htmlFor="pay-amt" error={fieldError(error, "amount")}><input id="pay-amt" className="input" inputMode="decimal" placeholder={i.balance} value={payment.amount} onChange={(e) => setPayment({ ...payment, amount: e.target.value })} /></Field>
              <Field label="Method" htmlFor="pay-m">
                <select id="pay-m" className="select" value={payment.method} onChange={(e) => setPayment({ ...payment, method: e.target.value })}>
                  <option value="mobile_money">Mobile Money</option><option value="bank">Bank transfer</option><option value="card">Card</option><option value="cash">Cash</option><option value="cheque">Cheque</option>
                </select>
              </Field>
              <Field label="Reference" htmlFor="pay-ref"><input id="pay-ref" className="input" placeholder="Transaction ID" value={payment.reference} onChange={(e) => setPayment({ ...payment, reference: e.target.value })} /></Field>
              <Field label="Received on" htmlFor="pay-date"><input id="pay-date" type="date" className="input" value={payment.received_on} onChange={(e) => setPayment({ ...payment, received_on: e.target.value })} /></Field>
            </div>
            <button className="btn btn-primary" style={{ justifySelf: "end" }} onClick={() => act("payments", payment, "Payment recorded.")}>Save payment</button>
          </div>
        )}
      </div>
    </Modal>
  );
}

function GenerateModal({ onClose, onDone }: { onClose: () => void; onDone: (i: Invoice) => void }) {
  const matters = useLoad(() => list<{ id: string; reference: string; title: string }>("/matters/", { status: "open" }), []);
  const [matter, setMatter] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function go() {
    setError(null);
    try {
      onDone(await api<Invoice>("/billing/invoices/generate/", { method: "POST", body: { matter } }));
    } catch (err) {
      setError(err);
    }
  }

  return (
    <Modal title="Invoice unbilled time" subtitle="Every billable time entry not yet invoiced becomes a line on a draft." onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={!matter} onClick={go}>Create draft</button></>}>
      <div className="stack">
        {error ? <div className="notice err"><Icon name="alert" /><span>{errorMessage(error)}</span></div> : null}
        <Field label="Matter" htmlFor="g-matter">
          <select id="g-matter" className="select" value={matter} onChange={(e) => setMatter(e.target.value)}>
            <option value="">Choose…</option>
            {(matters.data ?? []).map((m) => <option key={m.id} value={m.id}>{m.reference} · {m.title}</option>)}
          </select>
        </Field>
      </div>
    </Modal>
  );
}

function Time() {
  const toast = useToast();
  const entries = useLoad(() => list<TimeEntry>("/billing/time/", { ordering: "-date" }), []);
  const matters = useLoad(() => list<{ id: string; reference: string; title: string }>("/matters/", { status: "open" }), []);
  const [form, setForm] = useState({ matter: "", date: isoDay(new Date()), hours: "", minutes: "30", description: "" });

  async function add(e: React.FormEvent) {
    e.preventDefault();
    const minutes = Number(form.hours || 0) * 60 + Number(form.minutes || 0);
    try {
      await api("/billing/time/", { method: "POST", body: { matter: form.matter, date: form.date, minutes, description: form.description } });
      toast("Time recorded.");
      setForm({ ...form, description: "", hours: "", minutes: "30" });
      entries.reload();
    } catch (err) {
      toast(errorMessage(err), "err");
    }
  }

  const total = (entries.data ?? []).filter((t) => !t.is_billed).reduce((s, t) => s + t.minutes, 0);
  return (
    <div className="stack" style={{ ["--gap" as string]: "18px" }}>
      <form className="card card-body stack" style={{ ["--gap" as string]: "12px" }} onSubmit={add}>
        <h3>Record time</h3>
        <div className="grid-2" style={{ gap: 12 }}>
          <Field label="Matter" htmlFor="tm-matter">
            <select id="tm-matter" className="select" required value={form.matter} onChange={(e) => setForm({ ...form, matter: e.target.value })}>
              <option value="">Choose…</option>
              {(matters.data ?? []).map((m) => <option key={m.id} value={m.id}>{m.reference} · {m.title}</option>)}
            </select>
          </Field>
          <Field label="Date" htmlFor="tm-date"><input id="tm-date" type="date" className="input" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></Field>
        </div>
        <div className="row wrap">
          <Field label="Hours" htmlFor="tm-h"><input id="tm-h" className="input" inputMode="numeric" style={{ width: 90 }} value={form.hours} onChange={(e) => setForm({ ...form, hours: e.target.value })} /></Field>
          <Field label="Minutes" htmlFor="tm-m"><input id="tm-m" className="input" inputMode="numeric" style={{ width: 90 }} value={form.minutes} onChange={(e) => setForm({ ...form, minutes: e.target.value })} /></Field>
          <div className="grow" style={{ minWidth: 220 }}>
            <Field label="What did you do?" htmlFor="tm-d"><input id="tm-d" className="input" required placeholder="e.g. Drafted written submissions" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          </div>
        </div>
        <button className="btn btn-primary" style={{ justifySelf: "end" }}>Add time</button>
      </form>
      <section className="card">
        <div className="card-head"><h3>My time sheet</h3><span className="muted small">{(total / 60).toFixed(1)} h not yet billed</span></div>
        {entries.loading ? <Spinner /> : !entries.data?.length ? <Empty icon="clock" title="No time recorded yet" /> : (
          <ul className="list">
            {entries.data.map((t) => (
              <li key={t.id} className="list-item">
                <span className="grow">
                  <strong style={{ display: "block" }}>{t.description}</strong>
                  <span className="muted small">{fmtDate(t.date)} · {t.matter_reference}</span>
                </span>
                <span className="num small">{Math.floor(t.minutes / 60)}h {t.minutes % 60}m</span>
                {t.is_billed ? <span className="badge badge-green">Billed</span> : <span className="badge">Unbilled</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
