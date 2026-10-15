"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import { SettingsLayout } from "@/components/SettingsNav";
import { Empty, Field, FirmMark, SocialLinks, Spinner, Switch, copyText, useLoad, useToast } from "@/components/ui";
import { api, errorMessage, fieldError } from "@/lib/api";
import { isManager, useAuth } from "@/lib/auth";
import { DAY_NAMES, useFirm } from "@/lib/firm";
import { fmtDateTime, minutesLabel } from "@/lib/format";
import { APPOINTMENT_CHOICES, COURT_CHOICES } from "@/lib/types";

type Testimonial = { quote: string; name: string; detail: string };
type Settings = {
  slug: string; code: string; domain: string;
  name: string; tagline: string; about: string; founded_year: number | null; theme: string; practice_areas: string[]; testimonials: Testimonial[];
  phone: string; whatsapp_number: string; email: string; address: string; map_url: string;
  facebook_url: string; instagram_url: string; x_url: string; linkedin_url: string; youtube_url: string; tiktok_url: string;
  office_opens: string; office_closes: string; working_days: number[]; slot_minutes: number; booking_enabled: boolean; booking_days_ahead: number;
  court_offsets: number[]; appointment_offsets: number[]; quiet_hours_start: string | null; quiet_hours_end: string | null; daily_agenda_at: string; staff_whatsapp_default: boolean;
  whatsapp_mode: string; whatsapp_phone_number_id: string; whatsapp_template: string; whatsapp_template_language: string; whatsapp_template_has_button: boolean;
  whatsapp_access_token?: string; whatsapp_app_secret?: string; whatsapp_verify_token?: string;
  sms_mode: string; at_username: string; at_sender_id: string; at_api_key?: string;
  payments_mode: string; flutterwave_public_key: string; flutterwave_secret_key?: string; flutterwave_webhook_hash?: string;
  sms_status: { backend: string; username_set: boolean; api_key_set: boolean; delivery_url: string };
  payments_status: { backend: string; secret_key_set: boolean; webhook_hash_set: boolean; webhook_url: string };
  // read-only
  logo_url: string; updated_at: string; updated_by_name: string | null;
  practice_area_choices: { key: string; label: string }[];
  theme_choices: { key: string; label: string }[];
  whatsapp_status: { backend: string; access_token_set: boolean; app_secret_set: boolean; verify_token_set: boolean; phone_number_id_set: boolean; webhook_url: string; verify_token: string };
};

const READ_ONLY = new Set(["slug", "code", "logo_url", "updated_at", "updated_by_name", "practice_area_choices", "theme_choices", "whatsapp_status", "sms_status", "payments_status"]);

const SECTIONS = [
  { key: "profile", label: "Firm profile", icon: "building" },
  { key: "contact", label: "Contact & social media", icon: "phone" },
  { key: "website", label: "Website & booking", icon: "globe" },
  { key: "look", label: "Look & feel", icon: "palette" },
  { key: "reminders", label: "Reminders", icon: "bell" },
  { key: "whatsapp", label: "WhatsApp connection", icon: "whatsapp" },
  { key: "sms", label: "SMS", icon: "smartphone" },
  { key: "payments", label: "Online payments", icon: "wallet" },
] as const;
type Section = (typeof SECTIONS)[number]["key"];

const SOCIAL_FIELDS = [
  { key: "facebook_url", network: "facebook", label: "Facebook", placeholder: "facebook.com/yourfirm or @yourfirm" },
  { key: "instagram_url", network: "instagram", label: "Instagram", placeholder: "@yourfirm" },
  { key: "x_url", network: "x", label: "X (Twitter)", placeholder: "@yourfirm" },
  { key: "linkedin_url", network: "linkedin", label: "LinkedIn", placeholder: "linkedin.com/company/yourfirm" },
  { key: "youtube_url", network: "youtube", label: "YouTube", placeholder: "@yourfirm" },
  { key: "tiktok_url", network: "tiktok", label: "TikTok", placeholder: "@yourfirm" },
] as const;

const THEME_COLORS: Record<string, [string, string, string]> = {
  navy_brass: ["#1b3a6b", "#a8823f", "#f7f4ee"],
  royal_ivory: ["#1f4e9c", "#b8954f", "#f7f4ee"],
  oxford_burgundy: ["#14325c", "#7c2d3b", "#f7f4ee"],
  slate_sky: ["#2b4a70", "#3f86c4", "#f7f4ee"],
};

export default function FirmSettingsPage() {
  const { user } = useAuth();
  const { refresh } = useFirm();
  const toast = useToast();
  const { data, setData, loading, error: loadError } = useLoad(() => api<Settings>("/firm/settings/"), []);
  const [draft, setDraft] = useState<Settings | null>(null);
  const [section, setSection] = useState<Section>("profile");
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data) setDraft({ ...structuredClone(data), ...BLANK_SECRETS });
  }, [data]);

  // Preview the theme live while choosing; put it back if not saved.
  useEffect(() => {
    if (draft) document.documentElement.dataset.theme = draft.theme;
  }, [draft?.theme]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => void refresh(), [refresh]);

  if (!isManager(user)) {
    return (
      <SettingsLayout title="Firm settings" intro="">
        <div className="card"><Empty icon="lock" title="For the managing partner and practice manager">Ask an administrator if something here needs changing.</Empty></div>
      </SettingsLayout>
    );
  }
  if (loading || !draft || !data) return <SettingsLayout title="Firm settings" intro="Everything about the firm, in one place."><Spinner /></SettingsLayout>;

  const set = <K extends keyof Settings>(key: K, value: Settings[K]) => setDraft((d) => (d ? { ...d, [key]: value } : d));
  const changed = Object.keys(draft).filter((k) => !READ_ONLY.has(k) && JSON.stringify(draft[k as keyof Settings] ?? "") !== JSON.stringify(data[k as keyof Settings] ?? ""));
  const dirty = changed.length > 0;

  async function save() {
    if (!draft) return;
    setSaving(true);
    setError(null);
    const body: Record<string, unknown> = {};
    for (const k of changed) body[k] = draft[k as keyof Settings];
    try {
      const saved = await api<Settings>("/firm/settings/", { method: "PATCH", body });
      setData(saved);
      await refresh();
      toast("Saved. The website and app are updated.");
    } catch (err) {
      setError(err);
      const fields = Object.keys((err as { fields?: object }).fields ?? {});
      const owner = SECTION_OF[fields[0]];
      if (owner) setSection(owner);
      toast(errorMessage(err), "err");
    } finally {
      setSaving(false);
    }
  }

  const fe = (f: string) => fieldError(error, f);

  return (
    <SettingsLayout title="Firm settings" intro="Your firm's details, website, look and reminders. Changes go live as soon as you save.">
      <div className="tabs" role="tablist" style={{ marginBottom: 18 }}>
        {SECTIONS.map((s) => (
          <button key={s.key} role="tab" aria-selected={section === s.key} onClick={() => setSection(s.key)}>
            {s.label}
          </button>
        ))}
      </div>

      {loadError ? <div className="notice err"><Icon name="alert" /><span>{errorMessage(loadError)}</span></div> : null}

      <div className="card card-pad">
        {/* ============================================== profile */}
        {section === "profile" && (
          <>
            <div className="form-section" style={{ paddingTop: 0 }}>
              <header><h3>Name &amp; logo</h3><p>How the firm appears on the website, in emails, on WhatsApp and in the app.</p></header>
              <div className="stack" style={{ ["--gap" as string]: "14px" }}>
                <Field label="Firm name" htmlFor="f-name" error={fe("name")}>
                  <input id="f-name" className="input" value={draft.name} onChange={(e) => set("name", e.target.value)} />
                </Field>
                <LogoPicker logoUrl={data.logo_url} name={draft.name} onChanged={(s) => { setData({ ...data, logo_url: s.logo_url, updated_at: s.updated_at }); refresh(); }} />
              </div>
            </div>
            <div className="form-section">
              <header><h3>Your firm on LexDesk</h3><p>Your website, and the prefix on every case and invoice number.</p></header>
              <div className="stack" style={{ ["--gap" as string]: "14px" }}>
                <div className="grid-2" style={{ gap: 14 }}>
                  <Field label="Website" htmlFor="f-site" hint="Share this link; it always shows your firm.">
                    <div className="row">
                      <input id="f-site" className="input" readOnly value={`${typeof window !== "undefined" ? window.location.origin : ""}/?firm=${data.slug}`} onFocus={(e) => e.target.select()} />
                      <a className="btn btn-sm" href={`/?firm=${data.slug}`} target="_blank" rel="noopener noreferrer"><Icon name="globe" /> Open</a>
                    </div>
                  </Field>
                  <Field label="Case number prefix" htmlFor="f-code" hint={`e.g. ${data.code}-${new Date().getFullYear()}-0001. Set when the firm joined.`}>
                    <input id="f-code" className="input" readOnly value={data.code} />
                  </Field>
                </div>
                <Field label="Your own domain (optional)" htmlFor="f-domain" error={fe("domain")} hint="If the firm has its own web address, point it at LexDesk and enter it here, e.g. www.yourfirm.co.ug">
                  <input id="f-domain" className="input" placeholder="www.yourfirm.co.ug" value={draft.domain} onChange={(e) => set("domain", e.target.value)} />
                </Field>
              </div>
            </div>
            <div className="form-section">
              <header><h3>About</h3><p>A short line for the top of the website, and a paragraph about who you are.</p></header>
              <div className="stack" style={{ ["--gap" as string]: "14px" }}>
                <Field label="Tagline" htmlFor="f-tag" error={fe("tagline")}>
                  <input id="f-tag" className="input" maxLength={200} value={draft.tagline} onChange={(e) => set("tagline", e.target.value)} />
                </Field>
                <Field label="About the firm" htmlFor="f-about">
                  <textarea id="f-about" className="textarea" style={{ minHeight: 130 }} value={draft.about} onChange={(e) => set("about", e.target.value)} />
                </Field>
                <Field label="Year founded" htmlFor="f-year" error={fe("founded_year")}>
                  <input id="f-year" className="input" type="number" min={1900} max={2100} style={{ maxWidth: 160 }} value={draft.founded_year ?? ""} onChange={(e) => set("founded_year", e.target.value ? Number(e.target.value) : null)} />
                </Field>
              </div>
            </div>
            <div className="form-section">
              <header><h3>Practice areas</h3><p>Shown on the website and offered when people book.</p></header>
              <div className="chips">
                {data.practice_area_choices.map((a) => {
                  const on = draft.practice_areas.includes(a.key);
                  return (
                    <button key={a.key} className="chip" aria-pressed={on} onClick={() => set("practice_areas", on ? draft.practice_areas.filter((x) => x !== a.key) : [...draft.practice_areas, a.key])}>
                      {on && <Icon name="check" />} {a.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </>
        )}

        {/* ============================================== contact */}
        {section === "contact" && (
          <>
            <div className="form-section" style={{ paddingTop: 0 }}>
              <header><h3>How clients reach you</h3><p>The WhatsApp number is the one clients chat with when they tap the green button on the website.</p></header>
              <div className="stack" style={{ ["--gap" as string]: "14px" }}>
                <div className="grid-2" style={{ gap: 14 }}>
                  <Field label="Office phone" htmlFor="c-phone" error={fe("phone")}>
                    <input id="c-phone" className="input" type="tel" placeholder="0414 123456" value={draft.phone} onChange={(e) => set("phone", e.target.value)} />
                  </Field>
                  <Field label="WhatsApp number for clients" htmlFor="c-wa" error={fe("whatsapp_number")} hint={draft.whatsapp_number ? <a href={`https://wa.me/${draft.whatsapp_number.replace(/\D/g, "")}`} target="_blank" rel="noopener noreferrer">Try the chat link →</a> : undefined}>
                    <input id="c-wa" className="input" type="tel" placeholder="0772 123456" value={draft.whatsapp_number} onChange={(e) => set("whatsapp_number", e.target.value)} />
                  </Field>
                </div>
                <Field label="Email" htmlFor="c-email" error={fe("email")}>
                  <input id="c-email" className="input" type="email" value={draft.email} onChange={(e) => set("email", e.target.value)} />
                </Field>
                <Field label="Office address" htmlFor="c-addr">
                  <textarea id="c-addr" className="textarea" style={{ minHeight: 80 }} value={draft.address} onChange={(e) => set("address", e.target.value)} />
                </Field>
                <Field label="Google Maps link" htmlFor="c-map" hint="Open the office in Google Maps, tap Share, and paste the link here." error={fe("map_url")}>
                  <input id="c-map" className="input" type="url" placeholder="https://maps.app.goo.gl/…" value={draft.map_url} onChange={(e) => set("map_url", e.target.value)} />
                </Field>
              </div>
            </div>
            <div className="form-section">
              <header>
                <h3>Social media</h3>
                <p>Paste the page link or just the handle. Each one appears as a button on the website and in the app; tapping it opens your page.</p>
              </header>
              <div className="stack" style={{ ["--gap" as string]: "12px" }}>
                {SOCIAL_FIELDS.map((s) => (
                  <Field key={s.key} label={s.label} htmlFor={s.key} error={fe(s.key)}>
                    <div className="input-group">
                      <span className="addon"><Icon name={s.network} size={17} /></span>
                      <input id={s.key} className="input" placeholder={s.placeholder} value={draft[s.key]} onChange={(e) => set(s.key, e.target.value)} />
                    </div>
                  </Field>
                ))}
                <div className="stack" style={{ ["--gap" as string]: "8px", marginTop: 6 }}>
                  <span className="label">Preview (saved links)</span>
                  <div style={{ background: "var(--primary-strong)", padding: 16, borderRadius: 12 }}>
                    <SocialLinks
                      whatsapp={data.whatsapp_number ? `https://wa.me/${data.whatsapp_number.replace(/\D/g, "")}` : undefined}
                      socials={SOCIAL_FIELDS.filter((s) => data[s.key]).map((s) => ({ network: s.network, label: s.label, url: data[s.key] }))}
                    />
                    {!SOCIAL_FIELDS.some((s) => data[s.key]) && !data.whatsapp_number && <span style={{ color: "#9fb0cc", fontSize: 13 }}>No links yet.</span>}
                  </div>
                </div>
              </div>
            </div>
          </>
        )}

        {/* ============================================== website */}
        {section === "website" && (
          <>
            <div className="form-section" style={{ paddingTop: 0 }}>
              <header><h3>Online booking</h3><p>Let people book a consultation from the website. Bookings arrive as requests for you to confirm.</p></header>
              <div className="stack" style={{ ["--gap" as string]: "14px" }}>
                <div className="row-between">
                  <strong>Accept bookings on the website</strong>
                  <Switch checked={draft.booking_enabled} onChange={(v) => set("booking_enabled", v)} label="Online booking" />
                </div>
                <div className="grid-2" style={{ gap: 14 }}>
                  <Field label="Consultation length" htmlFor="b-len" error={fe("slot_minutes")}>
                    <select id="b-len" className="select" value={draft.slot_minutes} onChange={(e) => set("slot_minutes", Number(e.target.value))}>
                      {[15, 20, 30, 45, 60, 90].map((m) => <option key={m} value={m}>{m} minutes</option>)}
                    </select>
                  </Field>
                  <Field label="How far ahead people can book" htmlFor="b-ahead" error={fe("booking_days_ahead")}>
                    <select id="b-ahead" className="select" value={draft.booking_days_ahead} onChange={(e) => set("booking_days_ahead", Number(e.target.value))}>
                      {[14, 30, 60, 90, 180].map((d) => <option key={d} value={d}>{d} days</option>)}
                    </select>
                  </Field>
                </div>
              </div>
            </div>
            <div className="form-section">
              <header><h3>Office hours</h3><p>Shown on the website, and used to offer booking times.</p></header>
              <div className="stack" style={{ ["--gap" as string]: "14px" }}>
                <div className="field">
                  <span className="label">Open on</span>
                  <div className="chips">
                    {DAY_NAMES.map((d, i) => {
                      const on = draft.working_days.includes(i);
                      return (
                        <button key={d} className="chip" aria-pressed={on} onClick={() => set("working_days", on ? draft.working_days.filter((x) => x !== i) : [...draft.working_days, i].sort())}>
                          {d.slice(0, 3)}
                        </button>
                      );
                    })}
                  </div>
                  {fe("working_days") && <span className="error-text">{fe("working_days")}</span>}
                </div>
                <div className="grid-2" style={{ gap: 14, gridTemplateColumns: "1fr 1fr" }}>
                  <Field label="Opens" htmlFor="h-open"><input id="h-open" type="time" className="input" value={draft.office_opens.slice(0, 5)} onChange={(e) => set("office_opens", e.target.value)} /></Field>
                  <Field label="Closes" htmlFor="h-close" error={fe("office_closes")}><input id="h-close" type="time" className="input" value={draft.office_closes.slice(0, 5)} onChange={(e) => set("office_closes", e.target.value)} /></Field>
                </div>
              </div>
            </div>
            <div className="form-section">
              <header>
                <h3>Client testimonials</h3>
                <p>Real words from real clients, used with their permission. The section shows on the website once you add one.</p>
              </header>
              <Testimonials value={draft.testimonials} onChange={(v) => set("testimonials", v)} error={fe("testimonials")} />
            </div>
          </>
        )}

        {/* ============================================== look */}
        {section === "look" && (
          <div className="form-section" style={{ paddingTop: 0, borderBottom: 0 }}>
            <header><h3>Colours</h3><p>Every theme is built on navy and the classic colours of the profession. The whole app previews your choice as you click.</p></header>
            <div className="grid-2" style={{ gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 200px), 1fr))" }}>
              {data.theme_choices.map((t) => {
                const [a, b, c] = THEME_COLORS[t.key] ?? THEME_COLORS.navy_brass;
                return (
                  <button key={t.key} className="theme-swatch" aria-pressed={draft.theme === t.key} onClick={() => set("theme", t.key)}>
                    <span className="bars"><span style={{ background: a }} /><span style={{ background: b }} /><span style={{ background: c, borderLeft: "1px solid var(--line)" }} /></span>
                    <span className="row-between"><strong>{t.label}</strong>{draft.theme === t.key && <Icon name="check-circle" size={18} />}</span>
                  </button>
                );
              })}
            </div>
            <div className="card card-pad" style={{ marginTop: 18, background: "var(--bg)" }}>
              <span className="eyebrow">Preview</span>
              <h2 style={{ marginTop: 6 }}>Legal help that feels human.</h2>
              <p className="muted" style={{ margin: "6px 0 14px" }}>Buttons, links and highlights use the colours you choose.</p>
              <div className="row wrap"><span className="btn btn-primary">Book a consultation</span><span className="btn btn-accent">Call us</span><span className="badge badge-gold">Highlight</span></div>
            </div>
          </div>
        )}

        {/* ============================================== reminders */}
        {section === "reminders" && (
          <>
            <div className="notice" style={{ marginBottom: 6 }}>
              <Icon name="info" />
              <span>These are the starting settings for new people. Everyone can then adjust their own under Notifications.</span>
            </div>
            <div className="form-section">
              <header><h3>Court dates</h3><p>When to remind the team before hearings and deadlines.</p></header>
              <OffsetChips choices={COURT_CHOICES} value={draft.court_offsets} onChange={(v) => set("court_offsets", v)} />
            </div>
            <div className="form-section">
              <header><h3>Appointments</h3><p>When to remind lawyers and clients before a consultation.</p></header>
              <OffsetChips choices={APPOINTMENT_CHOICES} value={draft.appointment_offsets} onChange={(v) => set("appointment_offsets", v)} />
            </div>
            <div className="form-section">
              <header><h3>Quiet hours &amp; morning agenda</h3><p>No WhatsApp messages overnight unless urgent; the day's agenda arrives before work.</p></header>
              <div className="grid-3" style={{ gap: 14 }}>
                <Field label="Quiet from" htmlFor="r-qs"><input id="r-qs" type="time" className="input" value={(draft.quiet_hours_start ?? "").slice(0, 5)} onChange={(e) => set("quiet_hours_start", e.target.value || null)} /></Field>
                <Field label="Until" htmlFor="r-qe"><input id="r-qe" type="time" className="input" value={(draft.quiet_hours_end ?? "").slice(0, 5)} onChange={(e) => set("quiet_hours_end", e.target.value || null)} /></Field>
                <Field label="Morning agenda at" htmlFor="r-ag"><input id="r-ag" type="time" className="input" value={draft.daily_agenda_at.slice(0, 5)} onChange={(e) => set("daily_agenda_at", e.target.value)} /></Field>
              </div>
            </div>
            <div className="form-section">
              <header><h3>WhatsApp for new staff</h3><p>Staff consent to work messages in their contract, so they can get WhatsApp reminders from their first day. Clients always choose for themselves.</p></header>
              <div className="row-between">
                <strong>Turn on WhatsApp for new staff</strong>
                <Switch checked={draft.staff_whatsapp_default} onChange={(v) => set("staff_whatsapp_default", v)} label="WhatsApp for new staff" />
              </div>
            </div>
          </>
        )}

        {/* ============================================== whatsapp */}
        {section === "whatsapp" && <WhatsAppSection draft={draft} data={data} set={set} fe={fe} />}
        {section === "sms" && <SmsSection draft={draft} data={data} set={set} fe={fe} />}
        {section === "payments" && <PaymentsSection draft={draft} data={data} set={set} fe={fe} />}

        <p className="muted tiny" style={{ marginTop: 18 }}>
          Last changed {fmtDateTime(data.updated_at)}{data.updated_by_name ? ` by ${data.updated_by_name}` : ""}. Every change is recorded in the audit trail.
        </p>
      </div>

      {dirty && (
        <div className="sticky-save" role="region" aria-label="Unsaved changes">
          <span>{changed.length} unsaved change{changed.length === 1 ? "" : "s"}</span>
          <span className="row">
            <button className="btn btn-sm" style={{ background: "transparent", color: "#fff", borderColor: "rgba(255,255,255,.3)" }} onClick={() => setDraft({ ...structuredClone(data), ...BLANK_SECRETS })}>Discard</button>
            <button className="btn btn-sm btn-accent" disabled={saving} onClick={save}>{saving ? "Saving…" : "Save changes"}</button>
          </span>
        </div>
      )}
    </SettingsLayout>
  );
}

const BLANK_SECRETS = { whatsapp_access_token: "", whatsapp_app_secret: "", at_api_key: "", flutterwave_secret_key: "", flutterwave_webhook_hash: "" };

const SECTION_OF: Record<string, Section> = {
  sms_mode: "sms", at_username: "sms", at_api_key: "sms", at_sender_id: "sms",
  payments_mode: "payments", flutterwave_secret_key: "payments", flutterwave_webhook_hash: "payments",
  domain: "profile", name: "profile", tagline: "profile", about: "profile", founded_year: "profile", practice_areas: "profile",
  phone: "contact", whatsapp_number: "contact", email: "contact", address: "contact", map_url: "contact",
  facebook_url: "contact", instagram_url: "contact", x_url: "contact", linkedin_url: "contact", youtube_url: "contact", tiktok_url: "contact",
  office_opens: "website", office_closes: "website", working_days: "website", slot_minutes: "website", booking_days_ahead: "website", testimonials: "website",
  court_offsets: "reminders", appointment_offsets: "reminders",
  whatsapp_mode: "whatsapp", whatsapp_phone_number_id: "whatsapp", whatsapp_access_token: "whatsapp", whatsapp_app_secret: "whatsapp",
};

function OffsetChips({ choices, value, onChange }: { choices: number[]; value: number[]; onChange: (v: number[]) => void }) {
  return (
    <div className="chips">
      {choices.map((m) => {
        const on = value.includes(m);
        return (
          <button key={m} className="chip" aria-pressed={on} onClick={() => onChange(on ? value.filter((x) => x !== m) : [...value, m].sort((a, b) => b - a))}>
            {on && <Icon name="check" />} {minutesLabel(m)}
          </button>
        );
      })}
    </div>
  );
}

function LogoPicker({ logoUrl, name, onChanged }: { logoUrl: string; name: string; onChanged: (s: Settings) => void }) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function upload(file: File) {
    setBusy(true);
    const body = new FormData();
    body.set("logo", file);
    try {
      onChanged(await api<Settings>("/firm/logo/", { method: "POST", body }));
      toast("Logo updated.");
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    await api("/firm/logo/", { method: "DELETE" });
    onChanged(await api<Settings>("/firm/settings/"));
  }

  return (
    <div className="row wrap" style={{ ["--gap" as string]: "16px" }}>
      <div style={{ padding: 10, borderRadius: 14, border: "1px solid var(--line)", background: "var(--surface-2)" }}>
        <FirmMark firm={{ name, logo_url: logoUrl }} size={64} />
      </div>
      <div className="stack" style={{ ["--gap" as string]: "6px" }}>
        <div className="row wrap">
          <button className="btn btn-sm" disabled={busy} onClick={() => input.current?.click()}><Icon name="upload" /> {logoUrl ? "Replace logo" : "Upload logo"}</button>
          {logoUrl && <button className="btn btn-sm btn-ghost" onClick={remove}>Remove</button>}
        </div>
        <span className="hint">A square PNG, JPEG or WebP, under 2 MB. Without one, we show the scales of justice.</span>
      </div>
      <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
    </div>
  );
}

function Testimonials({ value, onChange, error }: { value: Testimonial[]; onChange: (v: Testimonial[]) => void; error?: string }) {
  const update = (i: number, patch: Partial<Testimonial>) => onChange(value.map((t, j) => (j === i ? { ...t, ...patch } : t)));
  return (
    <div className="stack" style={{ ["--gap" as string]: "12px" }}>
      {value.map((t, i) => (
        <div key={i} className="card card-pad stack" style={{ ["--gap" as string]: "10px", background: "var(--surface-2)" }}>
          <textarea className="textarea" style={{ minHeight: 70 }} placeholder="What the client said" aria-label="Testimonial" value={t.quote} onChange={(e) => update(i, { quote: e.target.value })} />
          <div className="row wrap">
            <input className="input grow" placeholder="Name, e.g. Sarah N." aria-label="Client name" value={t.name} onChange={(e) => update(i, { name: e.target.value })} />
            <input className="input grow" placeholder="Context, e.g. Land dispute" aria-label="Context" value={t.detail} onChange={(e) => update(i, { detail: e.target.value })} />
            <button className="icon-btn" aria-label="Remove testimonial" onClick={() => onChange(value.filter((_, j) => j !== i))}><Icon name="trash" /></button>
          </div>
        </div>
      ))}
      {error && <span className="error-text">{error}</span>}
      {value.length < 12 && (
        <button className="btn btn-sm" style={{ justifySelf: "start" }} onClick={() => onChange([...value, { quote: "", name: "", detail: "" }])}>
          <Icon name="plus" /> Add a testimonial
        </button>
      )}
    </div>
  );
}

function WhatsAppSection({ draft, data, set, fe }: { draft: Settings; data: Settings; set: <K extends keyof Settings>(k: K, v: Settings[K]) => void; fe: (f: string) => string | undefined }) {
  const toast = useToast();
  const status = data.whatsapp_status;
  const [testing, setTesting] = useState(false);
  const mode = draft.whatsapp_mode || (status.backend === "meta" ? "live" : status.backend === "off" ? "off" : "test");

  async function test() {
    setTesting(true);
    try {
      await api("/notifications/test/", { method: "POST", body: { channel: "whatsapp" } });
      toast(status.backend === "meta" ? "Sent. Check WhatsApp on your phone." : "Test mode: the message was logged, not sent.");
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setTesting(false);
    }
  }

  return (
    <>
      <div className="form-section" style={{ paddingTop: 0 }}>
        <header>
          <h3>Status</h3>
          <p>WhatsApp reminders go out from the firm's own WhatsApp Business number.</p>
        </header>
        <div className="stack" style={{ ["--gap" as string]: "14px" }}>
          <div className={`notice ${status.backend === "meta" ? "ok" : status.backend === "off" ? "warn" : ""}`}>
            <Icon name={status.backend === "meta" ? "check-circle" : "info"} />
            <span>
              {status.backend === "meta"
                ? "Live. Court dates and appointments are being sent on WhatsApp."
                : status.backend === "off"
                  ? "WhatsApp is off. People get email and in-app notifications only."
                  : "Test mode. Messages are recorded but not sent, so you can try everything safely."}
            </span>
          </div>
          <div className="segmented" role="group" aria-label="WhatsApp mode">
            {[["off", "Off"], ["test", "Test mode"], ["live", "Live"]].map(([k, l]) => (
              <button key={k} aria-pressed={mode === k} onClick={() => set("whatsapp_mode", k)}>{l}</button>
            ))}
          </div>
          {fe("whatsapp_mode") && <span className="error-text">{fe("whatsapp_mode")}</span>}
          <button className="btn btn-whatsapp btn-sm" style={{ justifySelf: "start" }} disabled={testing || status.backend === "off"} onClick={test}>
            <Icon name="send" /> {testing ? "Sending…" : "Send a test to my WhatsApp"}
          </button>
        </div>
      </div>

      <div className="form-section">
        <header>
          <h3>Connection details</h3>
          <p>From Meta's WhatsApp Manager. Secrets are encrypted and never shown again once saved.</p>
        </header>
        <div className="stack" style={{ ["--gap" as string]: "14px" }}>
          <Field label="Phone number ID" htmlFor="w-pid" error={fe("whatsapp_phone_number_id")} hint="WhatsApp Manager → API Setup → Phone number ID">
            <input id="w-pid" className="input" inputMode="numeric" value={draft.whatsapp_phone_number_id} onChange={(e) => set("whatsapp_phone_number_id", e.target.value)} />
          </Field>
          <SecretField id="w-token" label="Permanent access token" isSet={status.access_token_set} value={draft.whatsapp_access_token ?? ""} onChange={(v) => set("whatsapp_access_token", v)} hint="From a System User with the whatsapp_business_messaging permission." />
          <SecretField id="w-secret" label="App secret" isSet={status.app_secret_set} value={draft.whatsapp_app_secret ?? ""} onChange={(v) => set("whatsapp_app_secret", v)} hint="App settings → Basic → App secret. Proves delivery receipts really come from Meta." />
          <div className="grid-3" style={{ gap: 14 }}>
            <Field label="Message template" htmlFor="w-tpl"><input id="w-tpl" className="input" value={draft.whatsapp_template} onChange={(e) => set("whatsapp_template", e.target.value)} /></Field>
            <Field label="Language" htmlFor="w-lang"><input id="w-lang" className="input" value={draft.whatsapp_template_language} onChange={(e) => set("whatsapp_template_language", e.target.value)} /></Field>
            <div className="field">
              <span className="label">Has "Open" button</span>
              <Switch checked={draft.whatsapp_template_has_button} onChange={(v) => set("whatsapp_template_has_button", v)} label="Template has a link button" />
            </div>
          </div>
        </div>
      </div>

      <div className="form-section">
        <header>
          <h3>Delivery receipts</h3>
          <p>Paste these into WhatsApp Manager → Configuration → Webhook, and subscribe to "messages". You then see delivered and read ticks here, and STOP replies are honoured.</p>
        </header>
        <div className="stack" style={{ ["--gap" as string]: "12px" }}>
          <CopyRow label="Callback URL" value={status.webhook_url} />
          <CopyRow label="Verify token" value={status.verify_token || "Created when you switch to Live"} disabled={!status.verify_token} />
        </div>
      </div>

      <div className="form-section">
        <header>
          <h3>The message template</h3>
          <p>Create it once in WhatsApp Manager → Message templates. Category: Utility. Meta usually approves it within minutes.</p>
        </header>
        <div className="grid-2" style={{ gap: 18, alignItems: "start" }}>
          <div className="stack" style={{ ["--gap" as string]: "10px" }}>
            <CopyRow label="Name" value={draft.whatsapp_template || "lexdesk_notice"} />
            <div className="field">
              <span className="label">Body</span>
              <pre className="card card-pad" style={{ margin: 0, fontSize: 13, background: "var(--surface-2)", whiteSpace: "pre-wrap" }}>{"{{1}}\n\n{{2}}\n\n{{3}}"}</pre>
              <span className="hint">1 is the headline, 2 the details, 3 the firm name.</span>
            </div>
          </div>
          <div className="phone-preview" aria-label="Example message">
            <div className="wa-head"><span className="avatar" style={{ background: "#1f9d55", width: 30, height: 30, fontSize: 12 }}><Icon name="scale" size={16} /></span>{draft.name}</div>
            <div className="wa-chat">
              <div className="wa-bubble">
                <strong>Added to the diary: Hearing on Tue 20 Oct 2026, 09:00</strong>
                {"\n\n"}Hearing LD-2026-0004 Tue 20 Oct 2026, 09:00 at High Court, Court 4.{"\n\n"}
                <em>{draft.name}</em>
                <span className="t">09:02</span>
              </div>
              <div className="wa-bubble">
                <strong>Reminder: hearing in 2 hours</strong>
                {"\n\n"}Hearing LD-2026-0004 Tue 20 Oct 2026, 09:00 at High Court, Court 4.{"\n\n"}
                <em>{draft.name}</em>
                <span className="t">07:00</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function SecretField({ id, label, isSet, value, onChange, hint }: { id: string; label: string; isSet: boolean; value: string; onChange: (v: string) => void; hint: string }) {
  return (
    <Field label={label} htmlFor={id} hint={isSet && !value ? "Saved. Leave blank to keep it, or paste a new one to replace it." : hint}>
      <div className="input-group">
        <span className="addon" style={{ color: isSet ? "var(--success)" : undefined }}><Icon name={isSet ? "check-circle" : "lock"} size={16} /></span>
        <input id={id} className="input" type="password" autoComplete="off" placeholder={isSet ? "••••••••••••  saved" : "Paste here"} value={value} onChange={(e) => onChange(e.target.value)} />
      </div>
    </Field>
  );
}

function CopyRow({ label, value, disabled }: { label: string; value: string; disabled?: boolean }) {
  const toast = useToast();
  return (
    <div className="field">
      <span className="label">{label}</span>
      <div className="row">
        <input className="input" readOnly value={value} onFocus={(e) => e.target.select()} aria-label={label} />
        <button className="btn btn-sm" disabled={disabled} onClick={() => { copyText(value); toast(`${label} copied.`); }}><Icon name="copy" /> Copy</button>
      </div>
    </div>
  );
}

type Setter = <K extends keyof Settings>(k: K, v: Settings[K]) => void;

function ModeSwitch({ value, onChange, labels }: { value: string; onChange: (v: string) => void; labels: [string, string][] }) {
  return (
    <div className="segmented" role="group">
      {labels.map(([k, l]) => <button key={k} type="button" aria-pressed={value === k} onClick={() => onChange(k)}>{l}</button>)}
    </div>
  );
}

function SmsSection({ draft, data, set, fe }: { draft: Settings; data: Settings; set: Setter; fe: (f: string) => string | undefined }) {
  const toast = useToast();
  const status = data.sms_status;
  const mode = draft.sms_mode || (status.backend === "africastalking" ? "live" : status.backend === "off" ? "off" : "test");
  async function test() {
    try {
      await api("/notifications/test/", { method: "POST", body: { channel: "sms" } });
      toast(status.backend === "africastalking" ? "SMS sent. Check your phone." : "Test mode: the SMS was recorded, not sent.");
    } catch (err) {
      toast(errorMessage(err), "err");
    }
  }
  return (
    <>
      <div className="form-section" style={{ paddingTop: 0 }}>
        <header><h3>Status</h3><p>SMS reaches people without WhatsApp or data, and is the backup when a WhatsApp message cannot be delivered.</p></header>
        <div className="stack" style={{ ["--gap" as string]: "14px" }}>
          <div className={`notice ${status.backend === "africastalking" ? "ok" : status.backend === "off" ? "warn" : ""}`}>
            <Icon name={status.backend === "africastalking" ? "check-circle" : "info"} />
            <span>{status.backend === "africastalking" ? "Live: SMS is sent through your Africa's Talking account." : status.backend === "off" ? "SMS is off." : "Test mode: SMS messages are recorded but not sent."}</span>
          </div>
          <ModeSwitch value={mode} onChange={(v) => set("sms_mode", v)} labels={[["off", "Off"], ["test", "Test mode"], ["live", "Live"]]} />
          {fe("sms_mode") && <span className="error-text">{fe("sms_mode")}</span>}
          <button className="btn btn-sm" style={{ justifySelf: "start" }} disabled={status.backend === "off"} onClick={test}><Icon name="send" /> Send a test SMS to my phone</button>
        </div>
      </div>
      <div className="form-section">
        <header><h3>Africa's Talking account</h3><p>From account.africastalking.com. Use the username "sandbox" while testing. The API key is encrypted and never shown again.</p></header>
        <div className="stack" style={{ ["--gap" as string]: "14px" }}>
          <div className="grid-2" style={{ gap: 14 }}>
            <Field label="Username" htmlFor="at-user"><input id="at-user" className="input" value={draft.at_username} onChange={(e) => set("at_username", e.target.value)} /></Field>
            <Field label="Sender ID" htmlFor="at-sender" hint="Shown instead of a number, once approved" error={fe("at_sender_id")}><input id="at-sender" className="input" maxLength={11} placeholder="e.g. NSCADVOC" value={draft.at_sender_id} onChange={(e) => set("at_sender_id", e.target.value)} /></Field>
          </div>
          <SecretField id="at-key" label="API key" isSet={status.api_key_set} value={draft.at_api_key ?? ""} onChange={(v) => set("at_api_key", v)} hint="Settings → API Key in your Africa's Talking app." />
          <CopyRow label="Delivery reports callback URL (optional)" value={status.delivery_url} />
        </div>
      </div>
    </>
  );
}

function PaymentsSection({ draft, data, set, fe }: { draft: Settings; data: Settings; set: Setter; fe: (f: string) => string | undefined }) {
  const status = data.payments_status;
  const mode = draft.payments_mode || "off";
  return (
    <>
      <div className="form-section" style={{ paddingTop: 0 }}>
        <header><h3>Status</h3><p>Clients pay invoices from their portal by MTN or Airtel Mobile Money, or card. The money goes straight to your Flutterwave account.</p></header>
        <div className="stack" style={{ ["--gap" as string]: "14px" }}>
          <div className={`notice ${status.backend === "flutterwave" ? "ok" : status.backend === "off" ? "warn" : ""}`}>
            <Icon name={status.backend === "flutterwave" ? "check-circle" : "info"} />
            <span>{status.backend === "flutterwave" ? "Live: clients can pay invoices online." : status.backend === "test" ? "Test mode: a practice checkout lets you try paying without real money." : "Off: clients see your bank and Mobile Money details instead."}</span>
          </div>
          <ModeSwitch value={mode} onChange={(v) => set("payments_mode", v)} labels={[["off", "Off"], ["test", "Test mode"], ["live", "Live"]]} />
          {fe("payments_mode") && <span className="error-text">{fe("payments_mode")}</span>}
        </div>
      </div>
      <div className="form-section">
        <header><h3>Flutterwave account</h3><p>From dashboard.flutterwave.com → Settings → API keys and Webhooks. Secrets are encrypted and never shown again.</p></header>
        <div className="stack" style={{ ["--gap" as string]: "14px" }}>
          <Field label="Public key" htmlFor="fw-pub"><input id="fw-pub" className="input" placeholder="FLWPUBK-…" value={draft.flutterwave_public_key} onChange={(e) => set("flutterwave_public_key", e.target.value)} /></Field>
          <SecretField id="fw-secret" label="Secret key" isSet={status.secret_key_set} value={draft.flutterwave_secret_key ?? ""} onChange={(v) => set("flutterwave_secret_key", v)} hint="FLWSECK-…" />
          <SecretField id="fw-hash" label="Webhook secret hash" isSet={status.webhook_hash_set} value={draft.flutterwave_webhook_hash ?? ""} onChange={(v) => set("flutterwave_webhook_hash", v)} hint="Any long random phrase; enter the same in Flutterwave's webhook settings." />
          <CopyRow label="Webhook URL (paste into Flutterwave)" value={status.webhook_url} />
        </div>
      </div>
    </>
  );
}
