"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { SettingsLayout } from "@/components/SettingsNav";
import { Field, Spinner, Switch, copyText, useLoad, useToast } from "@/components/ui";
import { api, errorMessage, fieldError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, minutesLabel } from "@/lib/format";
import { APPOINTMENT_CHOICES, COURT_CHOICES } from "@/lib/types";

type Prefs = {
  channels: Record<string, string[]>;
  categories: { key: string; label: string; locked: string[]; unavailable: string[] }[];
  whatsapp_active: boolean;
  whatsapp_number: string;
  whatsapp_number_in_use: string;
  sms_fallback: boolean;
  court_offsets: number[];
  appointment_offsets: number[];
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  daily_agenda: boolean;
  daily_agenda_at: string;
};

const CHANNELS = [
  { key: "in_app", label: "In the app", icon: "bell" },
  { key: "email", label: "Email", icon: "mail" },
  { key: "whatsapp", label: "WhatsApp", icon: "whatsapp" },
  { key: "sms", label: "SMS", icon: "smartphone" },
];

const CATEGORY_HELP: Record<string, string> = {
  diary: "New, moved and cancelled court dates, deadlines, and reminders",
  appointment: "Bookings, confirmations, changes and reminders",
  agenda: "Your day on one screen, each morning",
  billing: "Invoices and payments",
  security: "Sign-ins, password and two-factor changes",
  general: "Everything else",
};

export default function NotificationSettingsPage() {
  const { user } = useAuth();
  const toast = useToast();
  const { data, loading, setData } = useLoad(() => api<Prefs>("/notifications/preferences/"), []);
  const [draft, setDraft] = useState<Prefs | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);

  useEffect(() => {
    if (data) setDraft(structuredClone(data));
  }, [data]);

  if (loading || !draft || !data) return <SettingsLayout title="Settings" intro="How LexDesk reaches you."><Spinner /></SettingsLayout>;

  const isClient = user?.role === "client";
  const dirty = JSON.stringify(draft) !== JSON.stringify(data);
  const categories = draft.categories.filter((c) => !(isClient && c.key === "agenda"));

  function toggleChannel(category: string, channel: string, on: boolean) {
    setDraft((d) => {
      if (!d) return d;
      const current = new Set(d.channels[category] ?? []);
      if (on) current.add(channel);
      else current.delete(channel);
      return { ...d, channels: { ...d.channels, [category]: [...current] } };
    });
  }

  function toggleOffset(field: "court_offsets" | "appointment_offsets", minutes: number) {
    setDraft((d) => {
      if (!d) return d;
      const set = new Set(d[field]);
      if (set.has(minutes)) set.delete(minutes);
      else set.add(minutes);
      return { ...d, [field]: [...set].sort((a, b) => b - a) };
    });
  }

  async function save() {
    if (!draft || !data) return;
    setSaving(true);
    setError(null);
    const body: Record<string, unknown> = {
      channels: draft.channels,
      whatsapp_number: draft.whatsapp_number,
      court_offsets: draft.court_offsets,
      appointment_offsets: draft.appointment_offsets,
      quiet_hours_start: draft.quiet_hours_start || null,
      quiet_hours_end: draft.quiet_hours_end || null,
      daily_agenda: draft.daily_agenda,
      daily_agenda_at: draft.daily_agenda_at,
    };
    if (draft.whatsapp_active !== data.whatsapp_active) body.whatsapp_enabled = draft.whatsapp_active;
    try {
      const saved = await api<Prefs>("/notifications/preferences/", { method: "PATCH", body });
      setData(saved);
      toast("Saved. Upcoming reminders have been rescheduled to match.");
    } catch (err) {
      setError(err);
      toast(errorMessage(err), "err");
    } finally {
      setSaving(false);
    }
  }

  async function test(channel: string) {
    setTesting(channel);
    try {
      await api("/notifications/test/", { method: "POST", body: { channel } });
      toast(channel === "whatsapp" ? "Test sent. Check WhatsApp on your phone." : channel === "email" ? "Test sent. Check your inbox." : "Test sent. Look at the bell.");
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setTesting(null);
    }
  }

  return (
    <SettingsLayout title="Notifications" intro="Choose where court dates, appointments and updates reach you.">
      <div className="card card-pad">
        {/* --------------------------------------------------- WhatsApp */}
        <div className="form-section" style={{ paddingTop: 0 }}>
          <header>
            <h3 className="row" style={{ ["--gap" as string]: "8px" }}><Icon name="whatsapp" size={20} /> WhatsApp</h3>
            <p>The fastest way to reach you on the day. Reply STOP to any message to turn it off.</p>
          </header>
          <div className="stack" style={{ ["--gap" as string]: "14px" }}>
            <div className="row-between">
              <span>
                <strong style={{ display: "block" }}>Send me WhatsApp messages</strong>
                <span className="muted small">{draft.whatsapp_active ? `To ${draft.whatsapp_number || draft.whatsapp_number_in_use || "your phone number"}` : "Off"}</span>
              </span>
              <Switch checked={draft.whatsapp_active} onChange={(v) => setDraft({ ...draft, whatsapp_active: v })} label="WhatsApp messages" />
            </div>
            {draft.whatsapp_active && (
              <Field label="WhatsApp number" htmlFor="wa" hint={draft.whatsapp_number_in_use && !draft.whatsapp_number ? `Using your account number, ${draft.whatsapp_number_in_use}. Enter another to use that instead.` : "Include the country code, e.g. +256 772 123456."} error={fieldError(error, "whatsapp_number")}>
                <input id="wa" className="input" type="tel" inputMode="tel" placeholder={draft.whatsapp_number_in_use || "+256 7…"} value={draft.whatsapp_number} onChange={(e) => setDraft({ ...draft, whatsapp_number: e.target.value })} />
              </Field>
            )}
            <div className="row wrap">
              <button className="btn btn-whatsapp btn-sm" disabled={!data.whatsapp_active || testing !== null || dirty} onClick={() => test("whatsapp")}>
                <Icon name="send" /> {testing === "whatsapp" ? "Sending…" : "Send me a test"}
              </button>
              <button className="btn btn-sm" disabled={testing !== null} onClick={() => test("email")}><Icon name="mail" /> Test email</button>
              <button className="btn btn-sm" disabled={testing !== null || dirty} onClick={() => test("sms")}><Icon name="smartphone" /> Test SMS</button>
              {dirty && <span className="muted small">Save first, then test.</span>}
            </div>
          </div>
        </div>

        {/* ---------------------------------------------- channel matrix */}
        <div className="form-section">
          <header>
            <h3>What goes where</h3>
            <p>Tick each place you want to hear about each kind of message.</p>
          </header>
          <div className="table-wrap">
            <table className="matrix">
              <thead>
                <tr>
                  <th scope="col"><span className="sr-only">Kind of message</span></th>
                  {CHANNELS.map((c) => (
                    <th key={c.key} scope="col"><Icon name={c.icon} />{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {categories.map((cat) => (
                  <tr key={cat.key}>
                    <td>
                      <strong style={{ display: "block" }}>{cat.label}</strong>
                      <span className="muted tiny">{CATEGORY_HELP[cat.key]}</span>
                    </td>
                    {CHANNELS.map((c) => {
                      const locked = cat.locked.includes(c.key);
                      const unavailable = cat.unavailable.includes(c.key) || (c.key === "whatsapp" && !draft.whatsapp_active) || (c.key === "sms" && !draft.whatsapp_number_in_use);
                      const on = locked || (!unavailable && (draft.channels[cat.key] ?? []).includes(c.key));
                      return (
                        <td key={c.key}>
                          <span title={locked ? "Always on, for your security" : cat.unavailable.includes(c.key) ? "Never sent this way, for your security" : undefined}>
                            <Switch checked={on} disabled={locked || unavailable} onChange={(v) => toggleChannel(cat.key, c.key, v)} label={`${cat.label} by ${c.label}`} />
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* -------------------------------------------------- reminders */}
        <div className="form-section">
          <header>
            <h3>Reminder times</h3>
            <p>When to remind you before each date. Changing these reschedules every upcoming reminder.</p>
          </header>
          <div className="stack" style={{ ["--gap" as string]: "18px" }}>
            {!isClient && (
              <div className="field">
                <span className="label">Court dates &amp; deadlines</span>
                <div className="chips">
                  {COURT_CHOICES.map((m) => (
                    <button key={m} className="chip" aria-pressed={draft.court_offsets.includes(m)} onClick={() => toggleOffset("court_offsets", m)}>
                      {draft.court_offsets.includes(m) && <Icon name="check" />} {minutesLabel(m)}
                    </button>
                  ))}
                </div>
                {fieldError(error, "court_offsets") && <span className="error-text">{fieldError(error, "court_offsets")}</span>}
              </div>
            )}
            <div className="field">
              <span className="label">Appointments</span>
              <div className="chips">
                {APPOINTMENT_CHOICES.map((m) => (
                  <button key={m} className="chip" aria-pressed={draft.appointment_offsets.includes(m)} onClick={() => toggleOffset("appointment_offsets", m)}>
                    {draft.appointment_offsets.includes(m) && <Icon name="check" />} {minutesLabel(m)}
                  </button>
                ))}
              </div>
            </div>
            {isClient && (
              <p className="muted small">If your lawyer shares a court date with you, you will be reminded a week, a day and two hours before.</p>
            )}
          </div>
        </div>

        {/* ---------------------------------------- quiet hours, agenda */}
        <div className="form-section">
          <header>
            <h3>Quiet hours</h3>
            <p>No WhatsApp messages overnight, unless something urgent changes, like a hearing moved to tomorrow morning.</p>
          </header>
          <div className="stack" style={{ ["--gap" as string]: "14px" }}>
            <div className="row-between">
              <strong>Keep my phone quiet at night</strong>
              <Switch
                checked={Boolean(draft.quiet_hours_start)}
                onChange={(v) => setDraft({ ...draft, quiet_hours_start: v ? "21:00" : null, quiet_hours_end: v ? "07:00" : null })}
                label="Quiet hours"
              />
            </div>
            {draft.quiet_hours_start && (
              <div className="grid-2" style={{ gap: 14, gridTemplateColumns: "1fr 1fr" }}>
                <Field label="From" htmlFor="qs"><input id="qs" type="time" className="input" value={draft.quiet_hours_start.slice(0, 5)} onChange={(e) => setDraft({ ...draft, quiet_hours_start: e.target.value })} /></Field>
                <Field label="Until" htmlFor="qe"><input id="qe" type="time" className="input" value={(draft.quiet_hours_end ?? "07:00").slice(0, 5)} onChange={(e) => setDraft({ ...draft, quiet_hours_end: e.target.value })} /></Field>
              </div>
            )}
          </div>
        </div>

        {!isClient && (
          <div className="form-section">
            <header>
              <h3>Morning agenda</h3>
              <p>Your hearings and appointments for the day, in one message, before you leave home.</p>
            </header>
            <div className="stack" style={{ ["--gap" as string]: "14px" }}>
              <div className="row-between">
                <strong>Send me my day each morning</strong>
                <Switch checked={draft.daily_agenda} onChange={(v) => setDraft({ ...draft, daily_agenda: v })} label="Morning agenda" />
              </div>
              {draft.daily_agenda && (
                <Field label="At" htmlFor="ag"><input id="ag" type="time" className="input" style={{ maxWidth: 160 }} value={draft.daily_agenda_at.slice(0, 5)} onChange={(e) => setDraft({ ...draft, daily_agenda_at: e.target.value })} /></Field>
              )}
            </div>
          </div>
        )}

        <CalendarSync />
      </div>

      {dirty && (
        <div className="sticky-save" role="region" aria-label="Unsaved changes">
          <span>You have unsaved changes.</span>
          <span className="row">
            <button className="btn btn-sm" style={{ background: "transparent", color: "#fff", borderColor: "rgba(255,255,255,.3)" }} onClick={() => setDraft(structuredClone(data))}>Discard</button>
            <button className="btn btn-sm btn-accent" disabled={saving} onClick={save}>{saving ? "Saving…" : "Save changes"}</button>
          </span>
        </div>
      )}
    </SettingsLayout>
  );
}

function CalendarSync() {
  const toast = useToast();
  const status = useLoad(() => api<{ active: boolean; created_at: string | null; last_used_at: string | null }>("/notifications/calendar-feed/"), []);
  const [link, setLink] = useState<{ url: string; webcal_url: string } | null>(null);

  async function create() {
    if (status.data?.active && !confirm("This replaces your current link. Calendars using the old one will stop updating. Continue?")) return;
    try {
      setLink(await api("/notifications/calendar-feed/", { method: "POST" }));
      status.reload();
    } catch (err) {
      toast(errorMessage(err), "err");
    }
  }

  async function revoke() {
    await api("/notifications/calendar-feed/", { method: "DELETE" });
    setLink(null);
    status.reload();
    toast("Calendar link turned off.");
  }

  return (
    <div className="form-section" id="calendar">
      <header>
        <h3 className="row" style={{ ["--gap" as string]: "8px" }}><Icon name="calendar" size={20} /> Phone calendar</h3>
        <p>See every court date and appointment in Google Calendar, Apple Calendar or Outlook, with alarms, even offline.</p>
      </header>
      <div className="stack" style={{ ["--gap" as string]: "14px" }}>
        {link ? (
          <>
            <div className="notice warn"><Icon name="lock" /><span>This private link is shown once. Anyone with it can see your diary, so do not share it.</span></div>
            <div className="input-group">
              <span className="addon"><Icon name="link" size={16} /></span>
              <input className="input" readOnly value={link.url} onFocus={(e) => e.target.select()} aria-label="Calendar link" />
            </div>
            <div className="row wrap">
              <button className="btn btn-sm" onClick={() => { copyText(link.url); toast("Link copied."); }}><Icon name="copy" /> Copy</button>
              <a className="btn btn-sm" href={link.webcal_url}><Icon name="smartphone" /> Apple / Outlook</a>
              <a className="btn btn-sm" href={`https://calendar.google.com/calendar/r?cid=${encodeURIComponent(link.webcal_url)}`} target="_blank" rel="noopener noreferrer"><Icon name="globe" /> Google Calendar</a>
            </div>
          </>
        ) : status.data?.active ? (
          <p className="muted small">
            Your calendar link is on{status.data.created_at ? ` (created ${fmtDate(status.data.created_at)})` : ""}
            {status.data.last_used_at ? `, last synced ${fmtDate(status.data.last_used_at)}` : ", not synced yet"}.
          </p>
        ) : (
          <p className="muted small">Not connected.</p>
        )}
        <div className="row wrap">
          <button className="btn btn-primary btn-sm" onClick={create}>{status.data?.active ? "Make a new link" : "Connect my calendar"}</button>
          {status.data?.active && <button className="btn btn-sm btn-danger" onClick={revoke}>Turn off</button>}
        </div>
      </div>
    </div>
  );
}
