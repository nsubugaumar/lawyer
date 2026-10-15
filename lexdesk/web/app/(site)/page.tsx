"use client";

import Link from "next/link";
import { Icon, PRACTICE_BLURBS, PRACTICE_ICONS, Seal } from "@/components/Icon";
import { SocialLinks, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { hoursLabel, useFirm } from "@/lib/firm";
import { avatarColor, initials } from "@/lib/format";

type Lawyer = { id: string; name: string; title: string };

export default function HomePage() {
  const { firm } = useFirm();
  const lawyers = useLoad(() => api<Lawyer[]>("/appointments/public/lawyers/"), []);
  const years = firm.founded_year ? new Date().getFullYear() - firm.founded_year : null;

  return (
    <>
      {/* ------------------------------------------------------------ hero */}
      <section className="hero">
        <div className="container hero-grid">
          <div>
            <span className="eyebrow">{firm.name}</span>
            <h1 style={{ marginTop: 14 }}>
              Legal help that feels <em>human</em>, from people who answer.
            </h1>
            <p className="lede">
              {firm.tagline || "Trusted counsel. Clear answers. Every step of the way."} Book a consultation in two
              minutes, then follow your case, your documents and your court dates from your phone.
            </p>
            <div className="row wrap" style={{ marginTop: 28, ["--gap" as string]: "12px" }}>
              {firm.booking_enabled && (
                <Link href="/book" className="btn btn-primary btn-lg">
                  Book a consultation <Icon name="arrow-right" />
                </Link>
              )}
              {firm.whatsapp_link && (
                <a href={firm.whatsapp_link} target="_blank" rel="noopener noreferrer" className="btn btn-lg">
                  <Icon name="whatsapp" /> WhatsApp us
                </a>
              )}
            </div>
            <div className="trust">
              {years !== null && years > 0 && (
                <div>
                  <strong>{years}+ years</strong>
                  serving clients
                </div>
              )}
              <div>
                <strong>Secure portal</strong>
                your case, any time
              </div>
              <div>
                <strong>Reminders</strong>
                by WhatsApp &amp; email
              </div>
            </div>
          </div>

          <div className="hero-card" aria-hidden>
            <Seal className="seal" />
            <div className="stack" style={{ ["--gap" as string]: "16px", position: "relative" }}>
              <span className="eyebrow" style={{ color: "#d9be8a" }}>Your next step</span>
              <h3>A first conversation, without obligation</h3>
              <p style={{ color: "#cfd9ec", fontSize: 14.5 }}>
                Tell us what is happening. A lawyer reads it before you arrive, so the meeting starts with answers.
              </p>
              <div className="stack" style={{ ["--gap" as string]: "8px" }}>
                <div className="slot"><span>In person at our office</span><Icon name="building" size={18} /></div>
                <div className="slot"><span>Video call, wherever you are</span><Icon name="video" size={18} /></div>
                <div className="slot"><span>Phone call</span><Icon name="phone" size={18} /></div>
              </div>
              <p style={{ color: "#aebbd3", fontSize: 13 }}>Open {hoursLabel(firm)}</p>
            </div>
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------- practice */}
      <section className="section section-alt" id="practice">
        <div className="container">
          <div className="section-head">
            <span className="eyebrow">What we do</span>
            <h2>Practice areas</h2>
            <p>Whatever brought you here, someone on our team handles it every week.</p>
          </div>
          <div className="grid-3">
            {(firm.practice_areas.length ? firm.practice_areas : [{ key: "other", label: "General legal advice" }]).map((area) => (
              <div key={area.key} className="card area-card">
                <span className="icon"><Icon name={PRACTICE_ICONS[area.key] ?? "scale"} /></span>
                <h3>{area.label}</h3>
                <p className="muted">{PRACTICE_BLURBS[area.key] ?? PRACTICE_BLURBS.other}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------ team */}
      <section className="section" id="team">
        <div className="container">
          <div className="row-between wrap" style={{ alignItems: "flex-end", marginBottom: 36 }}>
            <div className="section-head" style={{ marginBottom: 0 }}>
              <span className="eyebrow">Our lawyers</span>
              <h2>The people beside you</h2>
              <p>Every client has a named lawyer who knows their file and returns their calls.</p>
            </div>
            {firm.booking_enabled && (
              <Link href="/book" className="btn">
                Choose your lawyer <Icon name="arrow-right" />
              </Link>
            )}
          </div>
          <div className="grid-3">
            {(lawyers.data ?? []).map((l) => (
              <div key={l.id} className="card person">
                <span className="portrait" style={{ background: avatarColor(l.name) }}>{initials(l.name)}</span>
                <div>
                  <h3>{l.name}</h3>
                  <p className="muted">{l.title || "Advocate"}</p>
                </div>
                {firm.booking_enabled && (
                  <Link href={`/book?lawyer=${l.id}`} className="btn btn-sm">
                    Book with {l.name.split(" ")[0]}
                  </Link>
                )}
              </div>
            ))}
            {lawyers.loading &&
              [0, 1, 2].map((i) => <div key={i} className="card skeleton" style={{ height: 210 }} />)}
          </div>
        </div>
      </section>

      {/* ----------------------------------------------------- how it works */}
      <section className="section section-alt" id="how">
        <div className="container">
          <div className="section-head">
            <span className="eyebrow">How it works</span>
            <h2>Clear from the first call</h2>
          </div>
          <div className="steps">
            <div className="card step">
              <h3>Book a time</h3>
              <p className="muted" style={{ marginTop: 6 }}>Pick a lawyer and a time that suits you, in person, by video or by phone.</p>
            </div>
            <div className="card step">
              <h3>Tell us your story</h3>
              <p className="muted" style={{ marginTop: 6 }}>We listen, explain your options in plain language, and give you an honest view.</p>
            </div>
            <div className="card step">
              <h3>Follow every step</h3>
              <p className="muted" style={{ marginTop: 6 }}>Your secure portal shows your case, documents and invoices, any time.</p>
            </div>
            <div className="card step">
              <h3>Never miss a date</h3>
              <p className="muted" style={{ marginTop: 6 }}>Court dates and appointments reach you by WhatsApp, email and the app.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------- voices */}
      {firm.testimonials.length > 0 && (
      <section className="section">
        <div className="container">
          <div className="section-head">
            <span className="eyebrow">In their words</span>
            <h2>What clients tell us</h2>
          </div>
          <div className="grid-3">
            {firm.testimonials.map((v) => (
              <figure key={v.name + v.quote.slice(0, 12)} className="card quote-card" style={{ margin: 0 }}>
                <p>“{v.quote}”</p>
                <figcaption className="row">
                  <span className="avatar" style={{ background: avatarColor(v.name) }}>{initials(v.name)}</span>
                  <span>
                    <strong style={{ display: "block" }}>{v.name}</strong>
                    {v.detail && <span className="muted small">{v.detail}</span>}
                  </span>
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      </section>
      )}

      {/* ------------------------------------------------------ about + CTA */}
      {firm.about && (
        <section className="section section-alt">
          <div className="container grid-2" style={{ alignItems: "center", gap: 40 }}>
            <div>
              <span className="eyebrow">About the firm</span>
              <h2 style={{ marginTop: 8, fontSize: "clamp(1.7rem, 1.2rem + 1.6vw, 2.5rem)" }}>Small enough to know you. Strong enough to win.</h2>
            </div>
            <div className="stack" style={{ ["--gap" as string]: "18px" }}>
              <p style={{ fontSize: "1.08rem", color: "var(--ink-2)" }}>{firm.about}</p>
              <SocialLinks socials={firm.socials} whatsapp={firm.whatsapp_link} onLight />
            </div>
          </div>
        </section>
      )}

      <section className="section">
        <div className="container">
          <div className="cta-band">
            <div>
              <h2>Talk to a lawyer this week</h2>
              <p>The first step is a conversation. We will tell you honestly where you stand.</p>
            </div>
            <div className="row wrap">
              {firm.booking_enabled && (
                <Link href="/book" className="btn btn-accent btn-lg">Book a consultation</Link>
              )}
              {firm.phone && (
                <a href={`tel:${firm.phone}`} className="btn btn-lg" style={{ background: "transparent", color: "#fff", borderColor: "rgba(255,255,255,.35)" }}>
                  <Icon name="phone" /> {firm.phone}
                </a>
              )}
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
