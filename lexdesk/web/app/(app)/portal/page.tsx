"use client";

import Link from "next/link";
import { useState } from "react";
import { Icon } from "@/components/Icon";
import { type SignatureRequest, SignModal } from "@/components/SignaturePad";
import { UploadModal } from "@/components/UploadModal";
import { Avatar, Empty, SocialLinks, Spinner, StatusBadge, useLoad, useToast } from "@/components/ui";
import { api, errorMessage, list, openFile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useFirm } from "@/lib/firm";
import { dayNum, fmtDate, fmtDay, fmtTime, greeting, money, monthShort, relative } from "@/lib/format";

type ClientMatter = { id: string; reference: string; title: string; practice_area_display: string; status: string; court: string; case_number: string; lead_lawyer: { full_name: string; title: string } | null; opened_on: string };
type Appt = { id: string; starts_at: string; ends_at: string; mode_display: string; status: string; lawyer_detail: { full_name: string }; video_link: string; location: string };
type Doc = { id: string; title: string; matter_reference: string; category_display: string; latest: { original_filename: string; created_at: string } | null };
type Inv = { id: string; number: string; total: string; balance: string; currency: string; status: string; due_date: string | null };
type Dash = { upcoming_court: { id: string; kind: string; title: string; starts_at: string; location: string; matter_reference: string }[] };

export default function PortalPage() {
  const { user } = useAuth();
  const { firm } = useFirm();
  const toast = useToast();
  const matters = useLoad(() => list<ClientMatter>("/matters/"), []);
  const appts = useLoad(() => list<Appt>("/appointments/", { from: new Date().toISOString().slice(0, 10) }), []);
  const docs = useLoad(() => list<Doc>("/documents/"), []);
  const invoices = useLoad(() => list<Inv>("/billing/invoices/"), []);
  const dash = useLoad(() => api<Dash>("/dashboard/"), []);
  const [uploadFor, setUploadFor] = useState<string | null>(null);
  const signatures = useLoad(() => list<SignatureRequest>("/documents/signatures/", { status: "pending" }), []);
  const [signing, setSigning] = useState<SignatureRequest | null>(null);
  const [paying, setPaying] = useState<string | null>(null);

  async function payNow(invoiceId: string) {
    setPaying(invoiceId);
    try {
      const r = await api<{ checkout_url: string }>(`/billing/invoices/${invoiceId}/pay-online/`, { method: "POST" });
      window.location.href = r.checkout_url;
    } catch (err) {
      toast(errorMessage(err), "err");
      setPaying(null);
    }
  }

  const next = appts.data?.find((a) => ["confirmed", "requested"].includes(a.status));
  const owing = (invoices.data ?? []).filter((i) => Number(i.balance) > 0);
  const lawyer = matters.data?.find((m) => m.lead_lawyer)?.lead_lawyer;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <span className="eyebrow">{firm.name}</span>
          <h1 style={{ marginTop: 6 }}>{greeting()}, {user?.first_name}.</h1>
          <p>Everything about your case, in one safe place.</p>
        </div>
        <Link href="/book" className="btn btn-primary"><Icon name="calendar" /> Book a meeting</Link>
      </div>

      {signatures.data && signatures.data.length > 0 && (
        <section className="card" style={{ marginBottom: 18, borderColor: "var(--accent)" }}>
          <div className="card-head"><h2>Waiting for your signature</h2><span className="badge badge-gold">{signatures.data.length}</span></div>
          <ul className="list">
            {signatures.data.map((s) => (
              <li key={s.id} className="list-item">
                <Icon name="edit" size={20} />
                <span className="grow"><strong style={{ display: "block" }}>{s.document_title}</strong><span className="muted small">{s.matter_reference} · from {s.requested_by_name}</span></span>
                <button className="btn btn-primary btn-sm" onClick={() => setSigning(s)}>Read and sign</button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="grid-2" style={{ alignItems: "start" }}>
        <div className="stack" style={{ ["--gap" as string]: "18px" }}>
          {/* next meeting */}
          <section className="card card-pad stack" style={{ background: "linear-gradient(150deg, var(--primary), var(--primary-strong))", color: "#fff", border: 0 }}>
            <span className="eyebrow" style={{ color: "#d9be8a" }}>Your next meeting</span>
            {appts.loading ? <div className="skeleton" style={{ height: 48, opacity: 0.3 }} /> : next ? (
              <>
                <h2 style={{ color: "#fff" }}>{fmtDay(next.starts_at)} at {fmtTime(next.starts_at)}</h2>
                <p style={{ color: "#cfd9ec" }}>{next.mode_display} with {next.lawyer_detail.full_name}{next.location ? ` · ${next.location}` : ""}</p>
                <div className="row wrap">
                  <StatusBadge status={next.status} />
                  {next.video_link && next.status === "confirmed" && <a className="btn btn-accent btn-sm" href={next.video_link} target="_blank" rel="noopener noreferrer"><Icon name="video" /> Join call</a>}
                  <Link className="btn btn-sm" href="/appointments" style={{ background: "transparent", color: "#fff", borderColor: "rgba(255,255,255,.3)" }}>Manage</Link>
                </div>
              </>
            ) : (
              <>
                <p style={{ color: "#cfd9ec" }}>Nothing booked. Need to talk? Book a time with your lawyer.</p>
                <Link href="/book" className="btn btn-accent btn-sm" style={{ justifySelf: "start" }}>Book a meeting</Link>
              </>
            )}
          </section>

          {/* court dates shared with client */}
          {dash.data?.upcoming_court.length ? (
            <section className="card">
              <div className="card-head"><h2>Court dates</h2></div>
              <ul className="list">
                {dash.data.upcoming_court.map((e) => (
                  <li key={e.id} className="list-item">
                    <span className="date-tile"><span className="m">{monthShort(e.starts_at)}</span><span className="d">{dayNum(e.starts_at)}</span></span>
                    <span className="grow"><strong style={{ display: "block" }}>{e.kind} · {e.matter_reference}</strong><span className="muted small">{fmtTime(e.starts_at)}{e.location ? ` · ${e.location}` : ""}</span></span>
                  </li>
                ))}
              </ul>
              <div className="card-body muted small" style={{ paddingTop: 0 }}>We remind you by WhatsApp and email before each date. Please arrive 30 minutes early.</div>
            </section>
          ) : null}

          {/* matters */}
          <section className="card">
            <div className="card-head"><h2>Your matters</h2></div>
            {matters.loading ? <Spinner /> : !matters.data?.length ? (
              <Empty icon="briefcase" title="No matters yet">After your first meeting, your case will appear here.</Empty>
            ) : (
              <ul className="list">
                {matters.data.map((m) => (
                  <li key={m.id} className="list-item" style={{ alignItems: "flex-start" }}>
                    <span className="grow">
                      <span className="tiny strong" style={{ color: "var(--accent-strong)" }}>{m.reference}</span>
                      <strong style={{ display: "block" }}>{m.title}</strong>
                      <span className="muted small">{m.practice_area_display}{m.court ? ` · ${m.court}` : ""}{m.case_number ? ` · ${m.case_number}` : ""}</span>
                    </span>
                    <span className="stack" style={{ justifyItems: "end", ["--gap" as string]: "8px" }}>
                      <StatusBadge status={m.status} />
                      <button className="btn btn-sm" onClick={() => setUploadFor(m.id)}><Icon name="upload" /> Send a document</button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <div className="stack" style={{ ["--gap" as string]: "18px" }}>
          {/* lawyer card */}
          {lawyer && (
            <section className="card card-pad stack" style={{ ["--gap" as string]: "14px" }}>
              <span className="eyebrow">Your lawyer</span>
              <div className="row"><Avatar name={lawyer.full_name} size="lg" /><span><strong className="serif" style={{ display: "block", fontSize: 18 }}>{lawyer.full_name}</strong><span className="muted">{lawyer.title}</span></span></div>
              <div className="row wrap">
                <Link className="btn btn-primary btn-sm" href="/messages"><Icon name="message" /> Message securely</Link>
                {firm.whatsapp_link && <a className="btn btn-whatsapp btn-sm" href={firm.whatsapp_link} target="_blank" rel="noopener noreferrer"><Icon name="whatsapp" /> WhatsApp the office</a>}
                {firm.phone && <a className="btn btn-sm" href={`tel:${firm.phone}`}><Icon name="phone" /> Call</a>}
              </div>
            </section>
          )}

          {/* invoices */}
          <section className="card">
            <div className="card-head"><h2>Invoices</h2><Link className="btn btn-ghost btn-sm" href="/billing">All</Link></div>
            {invoices.loading ? <Spinner /> : !invoices.data?.length ? <Empty icon="receipt" title="No invoices" /> : (
              <ul className="list">
                {(owing.length ? owing : invoices.data.slice(0, 3)).map((i) => (
                  <li key={i.id} className="list-item">
                    <span className="grow"><strong style={{ display: "block" }}>{i.number}</strong><span className="muted small">{i.due_date ? `Due ${fmtDate(i.due_date)}` : ""}</span></span>
                    <span className="num strong">{money(Number(i.balance) > 0 ? i.balance : i.total, i.currency)}</span>
                    {Number(i.balance) > 0 ? (
                      <button className="btn btn-primary btn-sm" disabled={paying !== null} onClick={() => payNow(i.id)}>
                        <Icon name="wallet" /> {paying === i.id ? "Opening…" : "Pay now"}
                      </button>
                    ) : (
                      <StatusBadge status={i.status} />
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* documents */}
          <section className="card">
            <div className="card-head"><h2>Documents</h2></div>
            {docs.loading ? <Spinner /> : !docs.data?.length ? (
              <Empty icon="file" title="No documents shared yet">Documents your lawyer shares, and anything you send us, appear here.</Empty>
            ) : (
              <ul className="list">
                {docs.data.slice(0, 8).map((d) => (
                  <li key={d.id}>
                    <button className="list-item" onClick={() => openFile(`/documents/${d.id}/download/`, d.latest?.original_filename ?? d.title, true).catch((e) => toast(errorMessage(e), "err"))}>
                      <Icon name="file" size={20} />
                      <span className="grow"><strong className="truncate" style={{ display: "block" }}>{d.title}</strong><span className="muted small">{d.category_display}{d.latest ? ` · ${relative(d.latest.created_at)}` : ""}</span></span>
                      <Icon name="eye" size={18} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card card-pad stack" style={{ ["--gap" as string]: "12px" }}>
            <span className="eyebrow">Follow us</span>
            <SocialLinks socials={firm.socials} whatsapp={firm.whatsapp_link} onLight />
          </section>
        </div>
      </div>

      {signing && <SignModal request={signing} onClose={() => setSigning(null)} onDone={() => { setSigning(null); signatures.reload(); docs.reload(); }} />}
      {uploadFor && <UploadModal matterId={uploadFor} clientMode onClose={() => setUploadFor(null)} onDone={() => { setUploadFor(null); docs.reload(); }} />}
    </div>
  );
}
