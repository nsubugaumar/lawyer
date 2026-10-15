"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/Icon";
import { Field, Spinner, useLoad } from "@/components/ui";
import { api, errorMessage, fieldError } from "@/lib/api";
import { useFirm } from "@/lib/firm";
import { avatarColor, fmtLong, fmtTime, initials, isoDay } from "@/lib/format";

type Lawyer = { id: string; name: string; title: string };
type Slot = { starts_at: string; ends_at: string };

const MODES = [
  { key: "in_person", label: "At the office", icon: "building", note: "Meet face to face" },
  { key: "video", label: "Video call", icon: "video", note: "We send you a link" },
  { key: "phone", label: "Phone call", icon: "phone", note: "We call you" },
];

export default function BookPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Booking />
    </Suspense>
  );
}

function Booking() {
  const { firm } = useFirm();
  const params = useSearchParams();
  const lawyers = useLoad(() => api<Lawyer[]>("/appointments/public/lawyers/"), []);

  const [step, setStep] = useState(0);
  const [lawyer, setLawyer] = useState<Lawyer | null>(null);
  const [mode, setMode] = useState("in_person");
  const [day, setDay] = useState<string>("");
  const [slot, setSlot] = useState<Slot | null>(null);
  const [form, setForm] = useState({ name: "", email: "", phone: "", practice_area: "", purpose: "", whatsapp_opt_in: true, website: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState<{ reference: string; detail: string } | null>(null);

  useEffect(() => {
    const wanted = params.get("lawyer");
    if (wanted && lawyers.data && !lawyer) {
      const found = lawyers.data.find((l) => l.id === wanted);
      if (found) {
        setLawyer(found);
        setStep(1);
      }
    }
  }, [params, lawyers.data, lawyer]);

  // The next working days, as the firm set them.
  const days = useMemo(() => {
    const out: string[] = [];
    const cursor = new Date();
    for (let i = 0; out.length < 21 && i < firm.booking_days_ahead; i++) {
      const d = new Date(cursor.getTime() + i * 86400000);
      if (firm.office_hours.days.includes((d.getDay() + 6) % 7)) out.push(isoDay(d));
    }
    return out;
  }, [firm.office_hours.days, firm.booking_days_ahead]);

  useEffect(() => {
    if (!day && days.length) setDay(days[0]);
  }, [days, day]);

  const slots = useLoad(
    () => (lawyer && day ? api<{ slots: Slot[] }>("/appointments/public/availability/", { query: { lawyer: lawyer.id, date: day } }).then((r) => r.slots) : Promise.resolve([])),
    [lawyer?.id, day],
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!lawyer || !slot) return;
    setSubmitting(true);
    setError(null);
    try {
      const body = await api<{ reference: string; detail: string }>("/appointments/public/book/", {
        method: "POST",
        body: { ...form, lawyer: lawyer.id, starts_at: slot.starts_at, mode },
      });
      setDone(body);
      setStep(3);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err);
      if ((err as { fields?: Record<string, unknown> }).fields?.starts_at) {
        setSlot(null);
        setStep(1);
        slots.reload();
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (!firm.booking_enabled) {
    return (
      <section className="section">
        <div className="container" style={{ maxWidth: 640 }}>
          <div className="card card-pad stack" style={{ ["--gap" as string]: "14px", textAlign: "center", justifyItems: "center" }}>
            <Icon name="calendar" size={40} />
            <h1>Online booking is paused</h1>
            <p className="muted">Please call or WhatsApp us and we will find you a time.</p>
            <div className="row wrap" style={{ justifyContent: "center" }}>
              {firm.phone && <a className="btn btn-primary" href={`tel:${firm.phone}`}><Icon name="phone" /> {firm.phone}</a>}
              {firm.whatsapp_link && <a className="btn btn-whatsapp" href={firm.whatsapp_link} target="_blank" rel="noopener noreferrer"><Icon name="whatsapp" /> WhatsApp</a>}
            </div>
          </div>
        </div>
      </section>
    );
  }

  const modeLabel = MODES.find((m) => m.key === mode)?.label;

  return (
    <section className="section" style={{ paddingTop: 40 }}>
      <div className="container">
        <div style={{ maxWidth: 720, marginBottom: 28 }}>
          <span className="eyebrow">Book a consultation</span>
          <h1 style={{ marginTop: 10 }}>{step === 3 ? "You're booked in" : "Let's find you a time"}</h1>
          {step < 3 && <p className="muted" style={{ marginTop: 8 }}>It takes about two minutes. No payment is needed to book.</p>}
        </div>

        {step < 3 && (
          <div className="progress" aria-hidden style={{ maxWidth: 720, marginBottom: 24 }}>
            {[0, 1, 2].map((i) => <span key={i} className={i <= step ? "on" : ""} />)}
          </div>
        )}

        <div className="book-shell">
          <div className="card card-pad">
            {/* ---------------------------------------------------- lawyer */}
            {step === 0 && (
              <div className="stack" style={{ ["--gap" as string]: "14px" }}>
                <h2>Who would you like to see?</h2>
                {lawyers.loading && <Spinner />}
                <div className="stack" style={{ ["--gap" as string]: "10px" }}>
                  {(lawyers.data ?? []).map((l) => (
                    <button key={l.id} className="choice" aria-pressed={lawyer?.id === l.id} onClick={() => { setLawyer(l); setSlot(null); setStep(1); }}>
                      <span className="avatar" style={{ background: avatarColor(l.name), width: 46, height: 46 }}>{initials(l.name)}</span>
                      <span className="grow">
                        <strong style={{ display: "block" }}>{l.name}</strong>
                        <span className="muted small">{l.title || "Advocate"}</span>
                      </span>
                      <Icon name="chevron-right" size={20} />
                    </button>
                  ))}
                </div>
                <p className="hint">Not sure? Choose anyone. If another lawyer is a better fit, we will tell you.</p>
              </div>
            )}

            {/* ------------------------------------------------------ time */}
            {step === 1 && lawyer && (
              <div className="stack" style={{ ["--gap" as string]: "22px" }}>
                <div className="stack" style={{ ["--gap" as string]: "10px" }}>
                  <h2>How would you like to meet?</h2>
                  <div className="grid-3" style={{ gap: 10 }}>
                    {MODES.map((m) => (
                      <button key={m.key} className="choice" aria-pressed={mode === m.key} onClick={() => setMode(m.key)} style={{ padding: 14 }}>
                        <Icon name={m.icon} size={22} />
                        <span>
                          <strong style={{ display: "block", fontSize: 14 }}>{m.label}</strong>
                          <span className="muted tiny">{m.note}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="stack" style={{ ["--gap" as string]: "10px" }}>
                  <h3>Choose a day</h3>
                  <div className="days" role="group" aria-label="Day">
                    {days.map((d) => {
                      const date = new Date(`${d}T12:00:00+03:00`);
                      return (
                        <button key={d} className="day" aria-pressed={day === d} onClick={() => { setDay(d); setSlot(null); }}>
                          <span className="dow">{date.toLocaleDateString("en-GB", { weekday: "short" })}</span>
                          <span className="dnum">{date.getDate()}</span>
                          <span className="mon">{date.toLocaleDateString("en-GB", { month: "short" })}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="stack" style={{ ["--gap" as string]: "10px" }}>
                  <h3>Choose a time</h3>
                  {slots.loading ? (
                    <Spinner />
                  ) : slots.data && slots.data.length ? (
                    <div className="slots" role="group" aria-label="Time">
                      {slots.data.map((s) => (
                        <button key={s.starts_at} className="slot-btn" aria-pressed={slot?.starts_at === s.starts_at} onClick={() => setSlot(s)}>
                          {fmtTime(s.starts_at)}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="notice">
                      <Icon name="info" />
                      <span>{lawyer.name.split(" ")[0]} is fully booked that day. Try another day.</span>
                    </div>
                  )}
                </div>

                <div className="row-between">
                  <button className="btn btn-ghost" onClick={() => setStep(0)}><Icon name="chevron-left" /> Back</button>
                  <button className="btn btn-primary" disabled={!slot} onClick={() => setStep(2)}>Continue <Icon name="arrow-right" /></button>
                </div>
              </div>
            )}

            {/* --------------------------------------------------- details */}
            {step === 2 && (
              <form className="stack" style={{ ["--gap" as string]: "16px" }} onSubmit={submit} noValidate>
                <h2>A little about you</h2>
                {error ? <div className="notice err"><Icon name="alert" /><span>{errorMessage(error)}</span></div> : null}
                <div className="grid-2" style={{ gap: 14 }}>
                  <Field label="Your full name" htmlFor="name" error={fieldError(error, "name")}>
                    <input id="name" className="input" autoComplete="name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                  </Field>
                  <Field label="Mobile number" htmlFor="phone" hint="For your reminder" error={fieldError(error, "phone")}>
                    <input id="phone" className="input" type="tel" autoComplete="tel" inputMode="tel" placeholder="0772 123 456" required value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
                  </Field>
                </div>
                <Field label="Email address" htmlFor="email" hint="We'll send your confirmation and a link to your secure portal" error={fieldError(error, "email")}>
                  <input id="email" className="input" type="email" autoComplete="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                </Field>
                {firm.practice_areas.length > 0 && (
                  <Field label="What is it about?" htmlFor="area">
                    <select id="area" className="select" value={form.practice_area} onChange={(e) => setForm({ ...form, practice_area: e.target.value })}>
                      <option value="">I'm not sure</option>
                      {firm.practice_areas.map((a) => <option key={a.key} value={a.key}>{a.label}</option>)}
                    </select>
                  </Field>
                )}
                <Field label="Tell us briefly what is happening" htmlFor="purpose" hint="Only your lawyer sees this. A few sentences is plenty." error={fieldError(error, "purpose")}>
                  <textarea id="purpose" className="textarea" required value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} />
                </Field>
                {/* Honeypot: invisible to people, irresistible to bots. */}
                <input type="text" tabIndex={-1} autoComplete="off" className="sr-only" aria-hidden value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} />
                <label className="check">
                  <input type="checkbox" checked={form.whatsapp_opt_in} onChange={(e) => setForm({ ...form, whatsapp_opt_in: e.target.checked })} />
                  <span>
                    <strong>Send my reminders on WhatsApp</strong>
                    <span className="muted small" style={{ display: "block" }}>You can stop any time by replying STOP.</span>
                  </span>
                </label>
                <div className="row-between">
                  <button type="button" className="btn btn-ghost" onClick={() => setStep(1)}><Icon name="chevron-left" /> Back</button>
                  <button className="btn btn-primary btn-lg" disabled={submitting || !form.name || !form.email || !form.phone || !form.purpose}>
                    {submitting ? "Booking…" : "Request this time"}
                  </button>
                </div>
              </form>
            )}

            {/* ------------------------------------------------------ done */}
            {step === 3 && done && (
              <div className="stack" style={{ ["--gap" as string]: "16px" }}>
                <span style={{ width: 56, height: 56, borderRadius: "50%", display: "grid", placeItems: "center", background: "var(--success-soft)", color: "var(--success)" }}>
                  <Icon name="check" size={30} />
                </span>
                <h2>Thank you, {form.name.split(" ")[0]}.</h2>
                <p>{done.detail}</p>
                <p className="muted">Your reference is <strong className="nowrap">{done.reference}</strong>. Keep it handy if you call us.</p>
                <div className="notice">
                  <Icon name="mail" />
                  <span>Check your email for a link to set up your secure client portal. You will see your appointment, and later your case, there.</span>
                </div>
                <div className="row wrap">
                  <Link href="/" className="btn">Back to the home page</Link>
                  {firm.whatsapp_link && <a href={firm.whatsapp_link} target="_blank" rel="noopener noreferrer" className="btn btn-whatsapp"><Icon name="whatsapp" /> Message us</a>}
                </div>
              </div>
            )}
          </div>

          {/* summary */}
          <aside className="card card-pad stack" style={{ ["--gap" as string]: "14px", position: "sticky", top: 96 }}>
            <span className="eyebrow">Your consultation</span>
            <div className="stack" style={{ ["--gap" as string]: "12px" }}>
              <SummaryRow icon="user" label="Lawyer" value={lawyer?.name} />
              <SummaryRow icon={MODES.find((m) => m.key === mode)?.icon ?? "building"} label="How" value={lawyer ? modeLabel : undefined} />
              <SummaryRow icon="calendar" label="When" value={slot ? `${fmtLong(slot.starts_at)} at ${fmtTime(slot.starts_at)}` : undefined} />
              <SummaryRow icon="clock" label="Length" value={`${firm.slot_minutes} minutes`} />
            </div>
            <hr className="divider" />
            <p className="muted small">Your information is confidential and protected by legal professional privilege from the moment you send it.</p>
          </aside>
        </div>
      </div>
    </section>
  );
}

function SummaryRow({ icon, label, value }: { icon: string; label: string; value?: string }) {
  return (
    <div className="row" style={{ alignItems: "flex-start" }}>
      <span style={{ color: "var(--accent-strong)", marginTop: 2 }}><Icon name={icon} size={18} /></span>
      <span>
        <span className="muted tiny" style={{ display: "block" }}>{label}</span>
        <span style={{ fontWeight: 600, color: value ? "var(--ink)" : "var(--muted)" }}>{value ?? "Not chosen yet"}</span>
      </span>
    </div>
  );
}
