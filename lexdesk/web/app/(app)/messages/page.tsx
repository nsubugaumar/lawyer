"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import { Avatar, Empty, Spinner, useLoad, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, fmtTime, relative } from "@/lib/format";

type Thread = {
  matter: string; reference: string; title: string; client_name: string; lead_lawyer: string;
  last_at: string | null; last_sender: string; last_preview: string; unread: number;
};
type Message = { id: string; body: string; sender_name: string; sender_is_client: boolean; mine: boolean; document: string | null; document_title: string | null; created_at: string };

export default function MessagesPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Messages />
    </Suspense>
  );
}

function Messages() {
  const { user } = useAuth();
  const params = useSearchParams();
  const router = useRouter();
  const selected = params.get("matter");
  const isClient = user?.role === "client";
  const threads = useLoad(() => api<{ threads: Thread[] }>("/messages/threads/", { query: { all: 1 } }).then((r) => r.threads), []);

  // Clients usually have one matter: open it straight away.
  useEffect(() => {
    if (!selected && threads.data?.length && (isClient || window.innerWidth > 860)) {
      router.replace(`/messages?matter=${threads.data[0].matter}`);
    }
  }, [selected, threads.data, isClient, router]);

  const current = threads.data?.find((t) => t.matter === selected);

  return (
    <div className="page" style={{ maxWidth: 1180 }}>
      <div className="page-head">
        <div>
          <h1>Messages</h1>
          <p>
            {isClient
              ? "Talk to your lawyer securely. Everything you write here is confidential and stays on your file."
              : "Secure conversations with clients, one per matter. Privileged: only the client and the matter team can read them."}
          </p>
        </div>
      </div>

      <div className="card" style={{ display: "grid", gridTemplateColumns: "minmax(0, 340px) minmax(0, 1fr)", minHeight: "62dvh", overflow: "hidden" }} data-split>
        <aside style={{ borderRight: "1px solid var(--line)", overflowY: "auto", display: selected ? undefined : "block" }} className={selected ? "desktop-only" : ""}>
          {threads.loading ? <Spinner /> : !threads.data?.length ? (
            <Empty icon="message" title="No conversations yet">
              {isClient ? "Once your lawyer opens your matter, you can message them here." : "Conversations appear for matters you are on the team for."}
            </Empty>
          ) : (
            <ul className="list">
              {threads.data.map((t) => (
                <li key={t.matter}>
                  <Link href={`/messages?matter=${t.matter}`} className="list-item" style={{ alignItems: "flex-start", background: t.matter === selected ? "var(--primary-soft)" : undefined }}>
                    <Avatar name={isClient ? t.lead_lawyer || t.reference : t.client_name} />
                    <span className="grow">
                      <span className="row-between">
                        <strong className="truncate">{isClient ? t.lead_lawyer || "Your lawyer" : t.client_name}</strong>
                        {t.last_at && <span className="muted tiny nowrap">{relative(t.last_at)}</span>}
                      </span>
                      <span className="tiny strong" style={{ color: "var(--accent-strong)" }}>{t.reference}</span>
                      <span className="muted small truncate" style={{ display: "block" }}>{t.last_preview || "No messages yet. Say hello."}</span>
                    </span>
                    {t.unread > 0 && <span className="badge badge-gold plain">{t.unread}</span>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </aside>
        <section style={{ display: "flex", flexDirection: "column", minWidth: 0 }} className={selected ? "" : "desktop-only"}>
          {current ? (
            <Conversation key={current.matter} thread={current} onSent={threads.reload} onBack={() => router.push("/messages")} />
          ) : (
            <Empty icon="message" title="Choose a conversation" />
          )}
        </section>
      </div>
      <style>{`@media (max-width: 860px) { [data-split] { grid-template-columns: 1fr !important; } }`}</style>
    </div>
  );
}

function Conversation({ thread, onSent, onBack }: { thread: Thread; onSent: () => void; onBack: () => void }) {
  const { user } = useAuth();
  const toast = useToast();
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const messages = useLoad(() => api<Message[]>("/messages/", { query: { matter: thread.matter } }), [thread.matter]);
  const isClient = user?.role === "client";

  useEffect(() => {
    api("/messages/read/", { method: "POST", body: { matter: thread.matter } }).then(onSent).catch(() => undefined);
    // Light polling keeps the conversation live without a socket.
    const id = setInterval(() => document.visibilityState === "visible" && messages.reload(), 15000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [thread.matter]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages.data?.length]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    setSending(true);
    try {
      await api("/messages/", { method: "POST", body: { matter: thread.matter, body } });
      setBody("");
      messages.reload();
      onSent();
    } catch (err) {
      toast(errorMessage(err), "err");
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <header className="row" style={{ padding: "12px 16px", borderBottom: "1px solid var(--line)" }}>
        <button className="icon-btn mobile-only" onClick={onBack} aria-label="Back to conversations"><Icon name="chevron-left" /></button>
        <span className="grow">
          <strong style={{ display: "block" }}>{isClient ? thread.lead_lawyer || "Your lawyer" : thread.client_name}</strong>
          <span className="muted small truncate" style={{ display: "block" }}>{thread.reference} · {thread.title}</span>
        </span>
        {!isClient && <Link href={`/matters/${thread.matter}`} className="btn btn-sm"><Icon name="briefcase" /> Matter</Link>}
      </header>
      <div style={{ flex: 1, overflowY: "auto", padding: "18px 16px", display: "grid", gap: 10, alignContent: "start", background: "var(--bg)" }}>
        {messages.loading && !messages.data ? <Spinner /> : !messages.data?.length ? (
          <p className="muted small" style={{ textAlign: "center", padding: 24 }}>
            <Icon name="lock" size={14} /> This conversation is private and encrypted. {isClient ? "Ask your lawyer anything." : "Write the first message."}
          </p>
        ) : (
          messages.data.map((m) => (
            <div key={m.id} style={{ justifySelf: m.mine ? "end" : "start", maxWidth: "min(78%, 560px)" }}>
              {!m.mine && <span className="tiny muted" style={{ display: "block", margin: "0 0 3px 4px" }}>{m.sender_name}</span>}
              <div style={{
                padding: "10px 14px", borderRadius: m.mine ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
                background: m.mine ? "var(--primary)" : "var(--surface)", color: m.mine ? "#fff" : "var(--ink)",
                border: m.mine ? "none" : "1px solid var(--line)", whiteSpace: "pre-wrap", overflowWrap: "anywhere",
              }}>
                {m.body}
                {m.document_title && <span className="small" style={{ display: "flex", gap: 6, marginTop: 6, opacity: 0.9 }}><Icon name="file" size={14} /> {m.document_title}</span>}
              </div>
              <span className="tiny muted" style={{ display: "block", textAlign: m.mine ? "right" : "left", margin: "3px 4px 0" }} title={fmtDateTime(m.created_at)}>{fmtTime(m.created_at)}</span>
            </div>
          ))
        )}
        <div ref={bottom} />
      </div>
      <form onSubmit={send} className="row" style={{ padding: 12, borderTop: "1px solid var(--line)", alignItems: "flex-end" }}>
        <textarea
          className="textarea grow"
          style={{ minHeight: 46, maxHeight: 160 }}
          rows={1}
          placeholder="Write a message…"
          aria-label="Message"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && window.innerWidth > 860) {
              e.preventDefault();
              (e.currentTarget.form as HTMLFormElement).requestSubmit();
            }
          }}
        />
        <button className="btn btn-primary" disabled={sending || !body.trim()} aria-label="Send"><Icon name="send" /></button>
      </form>
    </>
  );
}
