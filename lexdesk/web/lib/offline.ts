/**
 * Offline court mode.
 *
 * Many court houses have little or no signal. A lawyer saves the briefs for
 * their coming hearings (notes, case details and the court bundle) onto the
 * phone, and opens them in court without a connection.
 *
 * Everything is kept in this browser's IndexedDB, for the signed-in person
 * only. It is deleted when they sign out, and each brief is removed two days
 * after its hearing. The phone's own screen lock protects it in between,
 * which is why the app asks lawyers to keep one.
 */

import { api, fetchFile } from "./api";

const DB = "lexdesk-offline";
const VERSION = 1;
const KEEP_AFTER_HEARING_MS = 2 * 86400000;

export type SavedBrief = { id: string; userId: string; savedAt: string; startsAt: string; title: string; reference: string; brief: any; documentIds: string[] };
type SavedFile = { id: string; name: string; type: string; blob: Blob };

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") return reject(new Error("Offline storage is not available on this device."));
    const request = indexedDB.open(DB, VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("briefs")) db.createObjectStore("briefs", { keyPath: "id" });
      if (!db.objectStoreNames.contains("files")) db.createObjectStore("files", { keyPath: "id" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function tx<T>(store: string, mode: IDBTransactionMode, run: (s: IDBObjectStore) => IDBRequest<T> | void): Promise<T | undefined> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const request = run(t.objectStore(store));
    t.oncomplete = () => resolve(request ? (request as IDBRequest<T>).result : undefined);
    t.onerror = () => reject(t.error);
  });
}

export async function saveBrief(eventId: string, userId: string, onProgress?: (done: number, total: number) => void): Promise<SavedBrief> {
  const brief = await api<any>(`/diary/${eventId}/brief/`);
  const docs: { id: string; title: string; latest: { original_filename: string; content_type: string } | null }[] = brief.documents ?? [];
  let done = 0;
  onProgress?.(0, docs.length);
  for (const d of docs) {
    const blob = await fetchFile(`/documents/${d.id}/download/`);
    const file: SavedFile = { id: d.id, name: d.latest?.original_filename ?? d.title, type: blob.type || d.latest?.content_type || "application/octet-stream", blob };
    await tx("files", "readwrite", (s) => s.put(file));
    onProgress?.(++done, docs.length);
  }
  const saved: SavedBrief = {
    id: eventId, userId, savedAt: new Date().toISOString(), startsAt: brief.event.starts_at,
    title: `${brief.event.kind_display}: ${brief.event.title}`, reference: brief.matter.reference, brief, documentIds: docs.map((d) => d.id),
  };
  await tx("briefs", "readwrite", (s) => s.put(saved));
  return saved;
}

export async function getBrief(eventId: string): Promise<SavedBrief | undefined> {
  return tx<SavedBrief>("briefs", "readonly", (s) => s.get(eventId));
}

export async function listBriefs(userId: string): Promise<SavedBrief[]> {
  await expire();
  const all = (await tx<SavedBrief[]>("briefs", "readonly", (s) => s.getAll())) ?? [];
  return all.filter((b) => b.userId === userId).sort((a, b) => a.startsAt.localeCompare(b.startsAt));
}

export async function removeBrief(eventId: string) {
  const brief = await getBrief(eventId);
  await tx("briefs", "readwrite", (s) => s.delete(eventId));
  if (!brief) return;
  const still = new Set(((await tx<SavedBrief[]>("briefs", "readonly", (s) => s.getAll())) ?? []).flatMap((b) => b.documentIds));
  for (const id of brief.documentIds) if (!still.has(id)) await tx("files", "readwrite", (s) => s.delete(id));
}

/** Hearings more than two days past are removed automatically. */
export async function expire() {
  const all = (await tx<SavedBrief[]>("briefs", "readonly", (s) => s.getAll()).catch(() => [])) ?? [];
  for (const b of all) if (new Date(b.startsAt).getTime() + KEEP_AFTER_HEARING_MS < Date.now()) await removeBrief(b.id);
}

/** Called on sign-out: nothing privileged stays on the device. */
export async function clearOffline() {
  if (typeof indexedDB === "undefined") return;
  await new Promise<void>((resolve) => {
    const request = indexedDB.deleteDatabase(DB);
    request.onsuccess = request.onerror = request.onblocked = () => resolve();
  });
}

export async function openSavedFile(id: string) {
  const file = await tx<SavedFile>("files", "readonly", (s) => s.get(id));
  if (!file) throw new Error("This document was not saved for offline use.");
  // Inside the Android app the phone's own viewer opens it.
  const bridge = (window as unknown as { LexDeskApp?: { openBase64?: (name: string, type: string, data: string) => void } }).LexDeskApp;
  if (bridge?.openBase64) {
    const data = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
      reader.readAsDataURL(file.blob);
    });
    bridge.openBase64(file.name, file.type, data);
    return;
  }
  const href = URL.createObjectURL(file.blob);
  window.open(href, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(href), 60000);
}
