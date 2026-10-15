"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";
import { Field, Modal, useToast } from "./ui";
import { api, errorMessage, openFile } from "@/lib/api";

export type SignatureRequest = {
  id: string; document: string; document_title: string; matter_reference: string; version_number: number; status: string;
  message: string; requested_by_name: string; created_at: string;
};

/** Draw a signature with a finger, stylus or mouse. Returns a PNG data URL. */
function Pad({ onChange }: { onChange: (dataUrl: string | null) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const drawn = useRef(false);

  useEffect(() => {
    const c = canvas.current!;
    const ratio = window.devicePixelRatio || 1;
    c.width = c.offsetWidth * ratio;
    c.height = c.offsetHeight * ratio;
    const ctx = c.getContext("2d")!;
    ctx.scale(ratio, ratio);
    ctx.lineWidth = 2.4;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#12294f";
  }, []);

  const point = (e: React.PointerEvent) => {
    const r = canvas.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };

  return (
    <div className="stack" style={{ ["--gap" as string]: "6px" }}>
      <canvas
        ref={canvas}
        aria-label="Signature pad: draw your signature"
        style={{ width: "100%", height: 170, background: "#fff", border: "1.5px dashed var(--line-strong)", borderRadius: 12, touchAction: "none", cursor: "crosshair" }}
        onPointerDown={(e) => {
          drawing.current = true;
          canvas.current!.setPointerCapture(e.pointerId);
          const ctx = canvas.current!.getContext("2d")!;
          const [x, y] = point(e);
          ctx.beginPath();
          ctx.moveTo(x, y);
        }}
        onPointerMove={(e) => {
          if (!drawing.current) return;
          const ctx = canvas.current!.getContext("2d")!;
          const [x, y] = point(e);
          ctx.lineTo(x, y);
          ctx.stroke();
          drawn.current = true;
        }}
        onPointerUp={() => {
          drawing.current = false;
          onChange(drawn.current ? canvas.current!.toDataURL("image/png") : null);
        }}
      />
      <div className="row-between">
        <span className="muted tiny">Sign inside the box</span>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => {
            const c = canvas.current!;
            c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
            drawn.current = false;
            onChange(null);
          }}
        >
          Clear
        </button>
      </div>
    </div>
  );
}

export function SignModal({ request, onClose, onDone }: { request: SignatureRequest; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [signature, setSignature] = useState<string | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [read, setRead] = useState(false);
  const [busy, setBusy] = useState(false);
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");

  async function sign() {
    setBusy(true);
    try {
      await api(`/documents/signatures/${request.id}/sign/`, { method: "POST", body: { full_name: name, signature, agreed } });
      toast("Signed. Thank you. Your lawyer has been told, and the certificate is in your documents.");
      onDone();
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setBusy(false);
    }
  }

  async function decline() {
    setBusy(true);
    try {
      await api(`/documents/signatures/${request.id}/decline/`, { method: "POST", body: { reason } });
      toast("Your lawyer has been told you would rather not sign yet.");
      onDone();
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={`Sign: ${request.document_title}`}
      subtitle={`${request.matter_reference} · requested by ${request.requested_by_name}`}
      onClose={onClose}
      footer={
        declining ? (
          <>
            <button className="btn" onClick={() => setDeclining(false)}>Back</button>
            <button className="btn btn-danger" disabled={busy} onClick={decline}>Decline to sign</button>
          </>
        ) : (
          <>
            <button className="btn btn-ghost" onClick={() => setDeclining(true)}>I do not want to sign</button>
            <button className="btn btn-primary" disabled={busy || !read || !agreed || !signature || name.trim().length < 3} onClick={sign}>
              {busy ? "Signing…" : "Sign document"}
            </button>
          </>
        )
      }
    >
      {declining ? (
        <Field label="Tell your lawyer why (optional)" htmlFor="decline">
          <textarea id="decline" className="textarea" value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
      ) : (
        <div className="stack" style={{ ["--gap" as string]: "14px" }}>
          {request.message && <div className="notice"><Icon name="message" /><span>{request.message}</span></div>}
          <div className="row-between wrap" style={{ padding: 12, borderRadius: 12, background: "var(--surface-2)" }}>
            <span className="row"><Icon name="file" size={20} /> <strong>{request.document_title}</strong></span>
            <button className="btn btn-sm" onClick={() => openFile(`/documents/${request.document}/download/`, request.document_title, true).then(() => setRead(true)).catch((e) => toast(errorMessage(e), "err"))}>
              <Icon name="eye" /> Read it first
            </button>
          </div>
          <Field label="Your full name" htmlFor="sig-name">
            <input id="sig-name" className="input" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <div className="field">
            <span className="label">Your signature</span>
            <Pad onChange={setSignature} />
          </div>
          <label className="check">
            <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} disabled={!read} />
            <span>I have read this document and I agree to sign it electronically.{!read && <span className="muted small" style={{ display: "block" }}>Open the document first.</span>}</span>
          </label>
          <p className="muted tiny">Your name, signature, the time and your device are recorded with a fingerprint of the exact document, under the Electronic Signatures Act, 2011.</p>
        </div>
      )}
    </Modal>
  );
}
