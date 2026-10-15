"use client";

import { useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { Icon } from "./Icon";
import { Field, Modal, useToast } from "./ui";

const DOC_CATEGORIES = [["pleading", "Pleading"], ["evidence", "Evidence / exhibit"], ["authority", "Legal authority"], ["correspondence", "Correspondence"], ["contract", "Contract / agreement"], ["court_order", "Court order / judgment"], ["internal", "Internal memo"], ["other", "Other"]];

export function fileSize(bytes: number) {
  return bytes > 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function UploadModal({ matterId, onClose, onDone, clientMode }: { matterId: string; onClose: () => void; onDone: () => void; clientMode?: boolean }) {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("pleading");
  const [shared, setShared] = useState(false);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);

  async function upload() {
    if (!file) return;
    setBusy(true);
    const body = new FormData();
    body.set("matter", matterId);
    body.set("title", title || file.name.replace(/\.[^.]+$/, ""));
    body.set("file", file);
    if (!clientMode) {
      body.set("category", category);
      body.set("shared_with_client", String(shared));
    }
    try {
      await api("/documents/", { method: "POST", body });
      toast("Uploaded and encrypted.");
      onDone();
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Upload a document" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={!file || busy} onClick={upload}>{busy ? "Uploading…" : "Upload"}</button></>}>
      <div className="stack" style={{ ["--gap" as string]: "14px" }}>
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) setFile(f); }}
          style={{ border: `2px dashed ${drag ? "var(--primary)" : "var(--line-strong)"}`, borderRadius: 14, padding: 28, background: drag ? "var(--primary-soft)" : "var(--surface-2)", cursor: "pointer", display: "grid", justifyItems: "center", gap: 8 }}
        >
          <Icon name="upload" size={30} />
          <strong>{file ? file.name : "Choose a file or drop it here"}</strong>
          <span className="muted small">{file ? fileSize(file.size) : "PDF, Word, images. Up to 50 MB."}</span>
        </button>
        <input ref={fileRef} type="file" hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <Field label="Title" htmlFor="u-title"><input id="u-title" className="input" placeholder={file?.name ?? ""} value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
        {!clientMode && (
          <>
            <Field label="Type" htmlFor="u-cat">
              <select id="u-cat" className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
                {DOC_CATEGORIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </Field>
            <label className="check"><input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} /> Share with the client in their portal</label>
          </>
        )}
      </div>
    </Modal>
  );
}
